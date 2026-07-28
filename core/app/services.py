"""DB ↔ 상태기계 사이의 번역층.

orchestrator.py 는 순수 함수라 DB 를 모른다 (BRIEF §15-1).
여기서 ORM 객체를 값(CycleView/StepView)으로 바꿔 상태기계에 넣고,
돌아온 Transition 을 DB 에 반영한다.

**모든 쓰기는 AuditLog 에 남는다. 예외 없다** (BRIEF §6, 인수 #25).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import pipelines
from .models import (
    AgentSpec,
    Artifact,
    AuditLog,
    Cycle,
    CycleMode,
    CycleStatus,
    Message,
    Node,
    Order,
    ROLES,
    ROLE_DISPLAY,
    SpecStatus,
    Step,
    StepStatus,
    Ticket,
)
from .orchestrator import Action, CycleView, StepView, Transition

REPO_ROOT = Path(os.getenv("REPO_ROOT", Path(__file__).resolve().parents[2] / "repo"))
PROJECT_ID = os.getenv("PROJECT_ID", "project-001")


def now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite 는 타임존을 보존하지 않는다. naive 로 돌아온 값을 UTC 로 본다."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── 감사 로그 ──────────────────────────────────────────────────────────
def audit(db: Session, actor: str, action: str, target: str | None = None,
          payload: dict[str, Any] | None = None) -> None:
    """모든 쓰기 요청은 여기를 지난다 (인수 #25)."""
    db.add(AuditLog(actor=actor, action=action, target=target, payload=payload))


# ── 스냅샷: ORM → 값 ───────────────────────────────────────────────────
def snapshot(db: Session, cycle: Cycle) -> tuple[CycleView, tuple[StepView, ...]]:
    pl = pipelines.load(cycle.pipeline)
    steps = db.scalars(
        select(Step).where(Step.cycle_id == cycle.id).order_by(Step.id)
    ).all()

    views = []
    for s in steps:
        d = pl.step(s.step_key)
        views.append(
            StepView(
                key=s.step_key,
                name=s.name,
                status=s.status.value if hasattr(s.status, "value") else str(s.status),
                role=s.role,
                type=d.type if d else None,
                parallel=d.parallel if d else (),
                on_reject_rewind_to=d.on_reject_rewind_to if d else None,
            )
        )

    cv = CycleView(
        id=cycle.id,
        status=cycle.status.value if hasattr(cycle.status, "value") else str(cycle.status),
        current_step=cycle.current_step,
        mode=cycle.mode.value if hasattr(cycle.mode, "value") else str(cycle.mode),
        attempt_no=cycle.attempt_no,
        pipeline=cycle.pipeline,
        pause_requested=bool(_flag(cycle, "pause_requested")),
        single_step=bool(_flag(cycle, "single_step")),
    )
    return cv, tuple(views)


# 플래그는 Cycle 행에 컬럼을 더하지 않고 AuditLog 옆 메모리 캐시로 둔다.
# 프로세스가 하나뿐인 교실 환경이라 이걸로 충분하다.
_FLAGS: dict[tuple[int, str], Any] = {}


def _flag(cycle: Cycle, name: str) -> Any:
    return _FLAGS.get((cycle.id, name))


def set_flag(cycle_id: int, name: str, value: Any) -> None:
    _FLAGS[(cycle_id, name)] = value


# ── Transition 적용 ────────────────────────────────────────────────────
def apply(db: Session, cycle: Cycle, t: Transition, actor: str = "hq") -> None:
    """상태기계의 결정을 DB 에 반영한다."""
    for k in ("pause_requested", "single_step"):
        if k in t.args:
            set_flag(cycle.id, k, t.args[k])

    if t.action is Action.FAIL_CURRENT and t.args.get("step"):
        st = _step(db, cycle.id, t.args["step"])
        if st:
            st.status = StepStatus.FAILED
            st.error = "강사가 즉시 취소했다 (abort)"
            st.ended_at = now()

    # 사람 게이트: 들어가면 WAITING_HUMAN, 통과하면 DONE 으로 닫는다
    if t.args.get("wait_step"):
        st = _step(db, cycle.id, t.args["wait_step"])
        if st and st.status == StepStatus.PENDING:
            st.status = StepStatus.WAITING_HUMAN
            st.started_at = st.started_at or now()
    if t.args.get("complete_step"):
        st = _step(db, cycle.id, t.args["complete_step"])
        if st and st.status != StepStatus.DONE:
            st.status = StepStatus.DONE
            st.ended_at = now()

    if t.action is Action.INVALIDATE_FROM:
        invalidate_from(db, cycle, t.args.get("from_step"),
                        keep_specs=t.args.get("keep_specs", True),
                        is_reset=bool(t.args.get("reset")))

    if t.args.get("create_ticket"):
        create_rework_ticket(db, cycle, t.args)

    cycle.status = CycleStatus(t.next_status)
    cycle.current_step = t.next_step
    if t.next_status == "RUNNING" and cycle.started_at is None:
        cycle.started_at = now()
    if t.next_status in ("DONE", "FAILED"):
        cycle.ended_at = now()

    audit(db, actor, f"cycle.{t.next_status.lower()}", f"cycle:{cycle.id}",
          {"step": t.next_step, "note": t.note, "action": t.action.value})
    db.commit()


def _step(db: Session, cycle_id: int, key: str) -> Step | None:
    return db.scalar(
        select(Step).where(Step.cycle_id == cycle_id, Step.step_key == key)
    )


# ── Cycle 생성 ─────────────────────────────────────────────────────────
def create_cycle(db: Session, order: Order, pipeline_name: str | None = None,
                 mode: str = "auto") -> Cycle:
    name = pipeline_name or pipelines.KIND_TO_PIPELINE.get(
        order.kind.value if hasattr(order.kind, "value") else str(order.kind),
        "web_delivery",
    )
    pl = pipelines.load(name)

    prev = db.scalars(select(Cycle).where(Cycle.order_id == order.id)).all()
    cycle = Cycle(
        order_id=order.id,
        pipeline=name,
        status=CycleStatus.READY,
        attempt_no=len(prev) + 1,
        mode=CycleMode(mode),
    )
    db.add(cycle)
    db.flush()

    for d in pl.steps:
        db.add(Step(
            cycle_id=cycle.id,
            step_key=d.id,
            name=d.name,
            role=d.role or (d.parallel[0] if d.parallel else None),
            status=StepStatus.PENDING,
        ))

    audit(db, "hq", "cycle.create", f"cycle:{cycle.id}",
          {"order_id": order.id, "pipeline": name, "attempt": cycle.attempt_no})
    db.commit()
    return cycle


# ── 산출물 무효화 (rewind / reset 의 실체) ────────────────────────────
def invalidate_from(db: Session, cycle: Cycle, from_step: str | None,
                    keep_specs: bool = True, is_reset: bool = False) -> None:
    """그 step 이후의 모든 산출물을 무효화한다 (BRIEF §3.4, 인수 #20·#21·#22)."""
    steps = db.scalars(
        select(Step).where(Step.cycle_id == cycle.id).order_by(Step.id)
    ).all()

    hit = from_step is None
    for s in steps:
        if s.step_key == from_step:
            hit = True
        if not hit:
            continue
        s.status = StepStatus.PENDING
        s.attempt = 0
        s.output_ref = None
        s.error = None
        s.started_at = None
        s.ended_at = None

        d = REPO_ROOT / "runs" / str(cycle.id) / s.step_key
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)

    db.execute(
        Artifact.__table__.delete().where(Artifact.cycle_id == cycle.id)
    )

    if is_reset and not keep_specs:
        # AGENT.md 도 기획이 만든 초안으로 되돌린다 — 완전 초기화 (인수 #22)
        for spec in db.scalars(select(AgentSpec).where(AgentSpec.cycle_id == cycle.id)):
            spec.status = SpecStatus.DRAFT
            spec.customized_at = None
        specs_dir = REPO_ROOT / PROJECT_ID / "agents"
        draft_dir = REPO_ROOT / PROJECT_ID / ".drafts"
        if draft_dir.exists():
            for role in ROLES:
                src = draft_dir / role / "AGENT.md"
                dst = specs_dir / role / "AGENT.md"
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    # ★ 해시도 초안 기준으로 되돌린다. 안 그러면 다음 스캔이
                    #   "학생이 고쳤다" 로 오인해 곧바로 customized 로 되돌아간다.
                    sp = db.scalar(select(AgentSpec).where(
                        AgentSpec.cycle_id == cycle.id, AgentSpec.role == role))
                    if sp:
                        sp.hash = hashlib.sha256(
                            src.read_text(encoding="utf-8").encode()).hexdigest()[:16]
                        sp.diff_ref = None

    audit(db, "hq", "cycle.invalidate", f"cycle:{cycle.id}",
          {"from_step": from_step, "keep_specs": keep_specs, "reset": is_reset})


def create_rework_ticket(db: Session, cycle: Cycle, args: dict[str, Any]) -> None:
    """게이트 반려 시 재작업 티켓을 자동 생성한다 (인수 #19)."""
    reject_step = args.get("reject_step")
    target = args.get("from_step")
    st = _step(db, cycle.id, reject_step) if reject_step else None
    tgt = _step(db, cycle.id, target) if target else None
    db.add(Ticket(
        cycle_id=cycle.id,
        from_role=(st.role if st else "qa") or "qa",
        to_role=(tgt.role if tgt else "backend") or "backend",
        title=f"[{reject_step} 반려] {target} 재작업",
        dod=args.get("reason") or "반려 사유를 해소하고 다시 제출한다",
        reason=args.get("reason"),
        status="todo",
    ))
    audit(db, "hq", "ticket.create_rework", f"cycle:{cycle.id}",
          {"reject_step": reject_step, "rewind_to": target})


# ── AGENT.md 생명주기 (BRIEF §4) ──────────────────────────────────────
def spec_path(role: str) -> Path:
    """이번 사이클의 **작업본**. 학생이 고치는 파일."""
    return REPO_ROOT / PROJECT_ID / "agents" / role / "AGENT.md"


# ★ 기준선 — 사람(Claude Code)이 미리 써 둔 역할 지시문. git 이 추적한다.
#   교실의 로컬 모델에게 11개 지시문을 통째로 쓰게 하면 빈 템플릿이 나온다.
#   구조와 품질 기준은 여기서 확정하고, 모델에게는 「이번 프로젝트」 한 칸만 맡긴다.
BASELINE_DIR = Path(__file__).resolve().parents[2] / "agents"

_PROJECT_SEC = re.compile(
    r"^##\s*이번 프로젝트\s*$.*?(?=^<!--\s*↑|\Z)", re.M | re.S)


def baseline_spec(role: str) -> str:
    p = BASELINE_DIR / role / "AGENT.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def compose_spec(role: str, project_block: str = "") -> str:
    """기준선 + 이번 프로젝트 내용 = 이번 사이클의 AGENT.md 초안.

    기준선이 없으면(역할을 새로 추가한 경우) 최소 골격이라도 만들어 준다 —
    빈 파일을 주면 학생이 무엇을 고쳐야 할지 알 수 없다.
    """
    base = baseline_spec(role)
    block = (project_block or "").strip()
    # 예전 경로 호환: 기획이 AGENT.md 전문을 보내 왔으면 「이번 프로젝트」만 뽑아 쓴다.
    if block.count("\n## ") >= 3:
        m = _PROJECT_SEC.search(block)
        block = (m.group(0).split("\n", 1)[1].strip() if m else "")
        block = "" if block.startswith("(아직") else block
    if not base:
        return _skeleton_spec(role, block)
    if not block:
        return base
    return _PROJECT_SEC.sub(
        lambda _: f"## 이번 프로젝트\n\n{block}\n\n", base, count=1)


def _skeleton_spec(role: str, block: str) -> str:
    from . import roles as roles_catalog
    r = roles_catalog.get(role)
    def _li(xs): return "\n".join(f"- {x}" for x in xs) or "- (미정)"
    return (
        f"# 나는 AGORA Web 의 {r.get('display', role)} 담당이다\n\n"
        f"## 나의 역할\n{r.get('mission', '(미정)')}\n\n"
        f"## 내 파일\n{_li(r.get('owns') or [])}\n\n"
        "## 출력 형식\n- 마크다운. 결론 먼저.\n\n"
        f"## 금지\n{_li(r.get('forbid') or [])}\n\n"
        f"## 애매할 때\n{_li([f'{k}: {v}' for k, v in (r.get('asks') or {}).items()])}\n"
        f"- 답이 없으면: {r.get('default', '범위를 늘리지 않는다')}\n\n"
        f"## 완료 보고\n{_li(r.get('report') or [])}\n\n"
        f"## 이번 프로젝트\n\n{block or '(아직 비어 있음)'}\n"
    )


def emit_spec_drafts(db: Session, cycle: Cycle, bodies: dict[str, str]) -> None:
    """S2 가 11개 AGENT.md 작업본을 만든다 (인수 #12).

    `bodies` 는 **「이번 프로젝트」 칸의 내용**이다. 나머지는 기준선에서 온다.
    (예전처럼 전문이 들어와도 동작한다 — `compose_spec` 이 알아서 처리한다.)
    """
    draft_dir = REPO_ROOT / PROJECT_ID / ".drafts"
    for role in ROLES:
        body = compose_spec(role, bodies.get(role, ""))
        fm = (
            "---\n"
            f"role: {role}\n"
            f"cycle: {cycle.id}\n"
            "status: draft\n"
            "author: baseline+planner\n"
            f"generated_at: {now().isoformat()}\n"
            "customized_at: null\n"
            "---\n\n"
        )
        text = fm + body
        p = spec_path(role)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

        # reset(keep_specs=False) 로 되돌릴 원본을 따로 보관한다
        dp = draft_dir / role / "AGENT.md"
        dp.parent.mkdir(parents=True, exist_ok=True)
        dp.write_text(text, encoding="utf-8")

        existing = db.scalar(
            select(AgentSpec).where(AgentSpec.cycle_id == cycle.id, AgentSpec.role == role)
        )
        h = hashlib.sha256(text.encode()).hexdigest()[:16]
        if existing:
            existing.status = SpecStatus.DRAFT
            existing.hash = h
            existing.generated_at = now()
            existing.customized_at = None
        else:
            db.add(AgentSpec(
                cycle_id=cycle.id, role=role, status=SpecStatus.DRAFT,
                path=str(p.relative_to(REPO_ROOT)), hash=h, generated_at=now(),
            ))
    audit(db, "planner", "specs.emit", f"cycle:{cycle.id}", {"count": len(ROLES)})
    db.commit()


def spec_progress(db: Session, cycle: Cycle) -> dict[str, Any]:
    specs = db.scalars(select(AgentSpec).where(AgentSpec.cycle_id == cycle.id)).all()
    done = [s.role for s in specs if s.status == SpecStatus.CUSTOMIZED]
    pending = [s.role for s in specs if s.status != SpecStatus.CUSTOMIZED]
    return {"customized": len(done), "total": len(specs) or len(ROLES),
            "pending": pending, "done": done}


def scan_customized(db: Session, cycle: Cycle) -> int:
    """repo/ 를 훑어 AGENT.md 가 초안과 달라졌으면 customized 로 바꾼다 (BRIEF §4.2).

    HQ 가 3초 주기로 부른다. 바뀐 개수를 돌려준다.
    """
    changed = 0
    hist = REPO_ROOT / PROJECT_ID / "specs" / "history"
    for spec in db.scalars(select(AgentSpec).where(AgentSpec.cycle_id == cycle.id)):
        p = REPO_ROOT / spec.path
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        h = hashlib.sha256(text.encode()).hexdigest()[:16]
        if h != spec.hash and spec.status != SpecStatus.CUSTOMIZED:
            spec.status = SpecStatus.CUSTOMIZED
            spec.customized_at = now()
            spec.hash = h
            # diff 를 보관한다 — 학생이 무엇을 추가했는지가 평가 데이터다
            draft = REPO_ROOT / PROJECT_ID / ".drafts" / spec.role / "AGENT.md"
            if draft.exists():
                d = hist / spec.role
                d.mkdir(parents=True, exist_ok=True)
                out = d / f"{cycle.id}.diff"
                try:
                    r = subprocess.run(
                        ["diff", "-u", str(draft), str(p)],
                        capture_output=True, text=True, timeout=10,
                    )
                    out.write_text(r.stdout, encoding="utf-8")
                    spec.diff_ref = str(out.relative_to(REPO_ROOT))
                except Exception:
                    pass
            changed += 1
            audit(db, spec.role, "spec.customized", f"cycle:{cycle.id}:{spec.role}")
    if changed:
        db.commit()
    return changed


# ── 메시지 미러링 ──────────────────────────────────────────────────────
def mirror(db: Session, cycle_id: int | None, from_role: str, to_role: str,
           kind: str, summary: str = "", payload_ref: str | None = None) -> None:
    from .models import MessageKind
    db.add(Message(
        cycle_id=cycle_id, from_role=from_role, to_role=to_role,
        kind=MessageKind(kind), summary=summary[:500], payload_ref=payload_ref,
    ))
    db.commit()


# ── 노드 ───────────────────────────────────────────────────────────────
def ensure_nodes(db: Session, entries: list[dict[str, Any]]) -> int:
    """students.yaml 기준으로 노드를 등록한다. 멱등."""
    from .models import NodeStatus
    n = 0
    for e in entries:
        role = e["role"]
        node = db.scalar(select(Node).where(Node.role == role))
        url = e.get("a2a_url") or f"http://{e['ip']}:41241/"
        if node is None:
            db.add(Node(role=role, display_name=ROLE_DISPLAY.get(role, role),
                        a2a_url=url, dgx_host=e.get("dgx"),
                        status=NodeStatus.DOWN))
            n += 1
        else:
            node.a2a_url = url
            node.dgx_host = e.get("dgx")
            node.display_name = ROLE_DISPLAY.get(role, role)
    audit(db, "hq", "nodes.ensure", None, {"registered": n, "total": len(entries)})
    db.commit()
    return n
