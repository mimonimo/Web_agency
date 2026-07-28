"""step 실행기 (BRIEF §15-2).

    step 실행은 전부 async 태스크. 하나가 막혀도 pause 요청은 즉시 받아야 한다.

실행 백엔드는 갈아끼울 수 있다:

    EXECUTOR=sim   — HQ 안에서 산출물을 흉내낸다. 노드 없이 흐름·화면을 확인하는 용도.
    EXECUTOR=a2a   — 실제 학생 노드의 Hermes 를 A2A 로 호출한다 (Phase 2).

수업 당일은 a2a 로 돌리고, 흐름 시연·리허설은 sim 으로 돌린다.
어느 쪽이든 **상태기계와 산출물 경로는 완전히 동일하다.**
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

from sqlalchemy import select

from . import pipelines, services
from .db import SessionLocal
from .models import Cycle, CycleStatus, ROLES, Step, StepStatus
from .orchestrator import Action, Event, next_step
from .services import REPO_ROOT, audit, now

EXECUTOR = os.getenv("EXECUTOR", "sim")
SIM_STEP_SEC = float(os.getenv("SIM_STEP_SEC", "2.0"))

# 사이클마다 태스크 하나
_TASKS: dict[int, asyncio.Task] = {}


def is_running(cycle_id: int) -> bool:
    t = _TASKS.get(cycle_id)
    return t is not None and not t.done()


def kick(cycle_id: int) -> None:
    """사이클을 굴린다. 이미 돌고 있으면 아무것도 하지 않는다."""
    if is_running(cycle_id):
        return
    _TASKS[cycle_id] = asyncio.create_task(_drive(cycle_id))


async def _drive(cycle_id: int) -> None:
    """RUNNING 인 동안 step 을 하나씩 실행한다."""
    guard = 0
    while guard < 200:
        guard += 1
        db = SessionLocal()
        try:
            cycle = db.get(Cycle, cycle_id)
            if cycle is None or cycle.status != CycleStatus.RUNNING:
                return
            key = cycle.current_step
            if not key:
                return
            step = db.scalar(
                select(Step).where(Step.cycle_id == cycle_id, Step.step_key == key)
            )
            if step is None:
                return
            pl = pipelines.load(cycle.pipeline)
            sdef = pl.step(key)
            step.status = StepStatus.RUNNING
            step.attempt += 1
            step.started_at = now()
            db.commit()
            timeout = sdef.timeout_sec if sdef else 900
        finally:
            db.close()

        # ── 실제 작업. 여기서 오래 걸려도 pause 요청은 API 가 즉시 받는다 ──
        try:
            result = await asyncio.wait_for(
                _execute(cycle_id, sdef), timeout=timeout
            )
            err = None
        except asyncio.TimeoutError:
            result, err = None, f"{key} 시간 초과 ({timeout}초)"
        except Exception as e:                                  # noqa: BLE001
            result, err = None, f"{key} 실행 오류: {e}"

        db = SessionLocal()
        try:
            cycle = db.get(Cycle, cycle_id)
            step = db.scalar(
                select(Step).where(Step.cycle_id == cycle_id, Step.step_key == key)
            )
            if cycle is None or step is None:
                return

            if err:
                step.status = StepStatus.FAILED
                step.error = err
                step.ended_at = now()
                db.commit()
                cv, sv = services.snapshot(db, cycle)
                services.apply(db, cycle, next_step(cv, sv, Event.STEP_FAILED,
                                                    {"error": err}))
                return

            step.status = StepStatus.DONE
            step.output_ref = result.get("output_dir") if result else None
            step.ended_at = now()
            db.commit()

            if result and result.get("artifacts"):
                from .models import Artifact
                for a in result["artifacts"]:
                    db.add(Artifact(cycle_id=cycle_id, step_id=step.id,
                                    role=step.role, path=a))
                db.commit()

            cv, sv = services.snapshot(db, cycle)
            t = next_step(cv, sv, Event.STEP_DONE, {"step": key})
            services.apply(db, cycle, t)

            if t.action is not Action.RUN_STEP:
                return
        finally:
            db.close()


# ── 실행 백엔드 ────────────────────────────────────────────────────────
async def _execute(cycle_id: int, sdef: Any) -> dict[str, Any]:
    if EXECUTOR == "a2a":
        return await _execute_a2a(cycle_id, sdef)
    return await _execute_sim(cycle_id, sdef)


async def _execute_sim(cycle_id: int, sdef: Any) -> dict[str, Any]:
    """노드 없이 산출물을 흉내낸다. 흐름과 화면을 확인하는 용도."""
    out_dir = REPO_ROOT / "runs" / str(cycle_id) / sdef.id / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        cycle = db.get(Cycle, cycle_id)
        for role in (sdef.roles or ("hq",)):
            services.mirror(db, cycle_id, "hq", role, "request",
                            f"{sdef.id} {sdef.name} 지시")

        await asyncio.sleep(SIM_STEP_SEC)

        artifacts: list[str] = []
        for name in (sdef.outputs or (f"{sdef.id}.md",)):
            if "*" in name:
                continue
            p = out_dir / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                f"# {name}\n\n"
                f"- 사이클: {cycle_id}\n- 단계: {sdef.id} {sdef.name}\n"
                f"- 담당: {', '.join(sdef.roles) or '-'}\n"
                f"- 생성: {now().isoformat()}\n\n"
                f"(시뮬레이션 산출물 — EXECUTOR=a2a 로 바꾸면 실제 노드가 만든다)\n",
                encoding="utf-8",
            )
            artifacts.append(str(p.relative_to(REPO_ROOT)))

        # ★ S2 는 11개 AGENT.md 초안을 만든다 (인수 #12)
        if sdef.emits_specs:
            services.emit_spec_drafts(db, cycle, {
                role: _draft_body(role) for role in ROLES
            })

        report = REPO_ROOT / "runs" / str(cycle_id) / sdef.id / "report.md"
        report.write_text(
            f"# {sdef.id} 완료 보고\n\n"
            f"- 단계: {sdef.name}\n- 담당: {', '.join(sdef.roles) or '-'}\n"
            f"- 산출물 {len(artifacts)}건\n",
            encoding="utf-8",
        )

        for role in (sdef.roles or ("hq",)):
            services.mirror(db, cycle_id, role, "hq", "response",
                            f"{sdef.id} 완료 — 산출물 {len(artifacts)}건")
        audit(db, "hq", "step.done", f"cycle:{cycle_id}:{sdef.id}",
              {"artifacts": len(artifacts)})
        db.commit()
    finally:
        db.close()

    return {"output_dir": str(out_dir.relative_to(REPO_ROOT)), "artifacts": artifacts}


async def _execute_a2a(cycle_id: int, sdef: Any) -> dict[str, Any]:
    """실제 학생 노드의 Hermes 를 A2A 로 호출한다 (BRIEF §5.3).

    병렬 단계면 해당 역할들에게 **동시에** 보내고 전부 끝날 때까지 기다린다.
    """
    from . import a2a_client as a2a
    from .models import Node

    out_dir = REPO_ROOT / "runs" / str(cycle_id) / sdef.id / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    roles = list(sdef.roles) or ["pm"]

    db = SessionLocal()
    try:
        urls = {n.role: n.a2a_url
                for n in db.scalars(select(Node).where(Node.role.in_(roles))).all()}
    finally:
        db.close()

    missing = [r for r in roles if not urls.get(r)]
    if missing:
        raise RuntimeError(f"노드가 등록되지 않았다: {', '.join(missing)}")

    results = await asyncio.gather(
        *[_one_role(cycle_id, sdef, r, urls[r], out_dir) for r in roles],
        return_exceptions=True,
    )

    artifacts: list[str] = []
    errors: list[str] = []
    for role, res in zip(roles, results):
        if isinstance(res, Exception):
            errors.append(f"{role}: {res}")
        else:
            artifacts.extend(res)

    if errors and not artifacts:
        raise RuntimeError("; ".join(errors))

    # ★ S2 는 11개 AGENT.md 초안을 만든다 (인수 #12).
    if sdef.emits_specs:
        bodies = _harvest_spec_bodies(out_dir)
        # 한 번의 호출로 11개를 다 쓰게 하면 모델이 중간에 멈춘다.
        # 빠진 역할은 **하나씩 따로** 기획에게 다시 시킨다. 느리지만 확실하다.
        planner_url = _role_url("planner")
        for role in ROLES:
            if spec_ok(bodies.get(role, "")):
                continue
            if not planner_url:
                break
            try:
                body = await _draft_one_spec(cycle_id, sdef, planner_url, role)
                if spec_ok(body):
                    bodies[role] = body
                elif body and len(body.strip()) > len(bodies.get(role, "")):
                    bodies[role] = body      # 완벽하진 않아도 있는 게 낫다
            except Exception:
                pass                       # 실패해도 기본 템플릿으로 채운다

        db = SessionLocal()
        try:
            cycle = db.get(Cycle, cycle_id)
            services.emit_spec_drafts(
                db, cycle, {r: bodies.get(r, _draft_body(r)) for r in ROLES})
        finally:
            db.close()

    return {"output_dir": str(out_dir.relative_to(REPO_ROOT)), "artifacts": artifacts}


SPEC_SECTIONS = ("나의 역할", "내 파일", "출력 형식", "금지", "애매할 때", "완료 보고")


def spec_ok(body: str) -> bool:
    """AGENT.md 초안이 쓸 만한가 (BRIEF §4.1 의 6칸).

    학생이 **고칠 수 있어야** 의미가 있다. 한 줄짜리 압축본은 고칠 자리가 없다.
    - 6칸이 `## 제목` 으로 나뉘어 있을 것
    - 각 칸에 최소한의 알맹이가 있을 것
    """
    if not body or len(body.strip()) < 300:
        return False
    text = body
    headed = sum(1 for sec in SPEC_SECTIONS if f"## {sec}" in text)
    return headed >= 5


def _role_url(role: str) -> str | None:
    from .models import Node
    db = SessionLocal()
    try:
        n = db.scalar(select(Node).where(Node.role == role))
        return n.a2a_url if n else None
    finally:
        db.close()


ROLE_HINT = {
    "pm": "일정·병목 관리와 우선순위 판단",
    "planner": "요구사항 해석과 화면 정의",
    "sales": "고객 접수·범위 합의·견적",
    "sysadmin": "실행 환경과 배포",
    "designer": "화면 디자인과 디자인 토큰",
    "frontend": "화면 구현",
    "backend": "서버·API 구현",
    "dba": "데이터 모델과 쿼리",
    "security": "취약점 점검과 데이터 보호",
    "qa": "테스트와 결함 발견",
    "customer": "고객 입장의 검수와 문의",
}


async def _draft_one_spec(cycle_id: int, sdef: Any, url: str, role: str) -> str:
    """기획에게 역할 하나의 AGENT.md 만 쓰게 한다 (BRIEF §4.1 의 6칸)."""
    from . import a2a_client as a2a

    hq = os.getenv("HQ_SELF_URL", "http://127.0.0.1:8000")
    instruction = (
        f"`{role}` 역할({ROLE_HINT.get(role, role)}) 한 개의 AGENT.md 초안만 쓴다.\n"
        f"파일 경로는 정확히 `agents/{role}/AGENT.md` 다. 다른 파일은 만들지 마라.\n\n"
        "다음 6칸을 반드시 이 순서로 포함한다:\n"
        "  ## 나의 역할 / ## 내 파일 / ## 출력 형식 / ## 금지 / ## 애매할 때 / ## 완료 보고\n\n"
        "이번 요구사항에서 **이 역할이 특별히 조심해야 할 것**을 '금지' 칸에 최소 1줄 넣는다.\n"
        "초안은 완벽할 필요 없다. 학생이 자기 전문 지식으로 보강할 것이다.\n"
        "front-matter(--- 머리말)는 쓰지 마라. HQ 가 붙인다."
    )
    req = a2a.TaskRequest(
        role="planner", cycle_id=cycle_id, step_id=sdef.id,
        step_name=f"{role} AGENT.md 초안",
        task="draft_one_spec",
        spec_url=f"{hq}/api/specs/planner/raw",
        context_urls=(f"{hq}/api/files?path=runs/{cycle_id}/{sdef.id}/output/SRS.md",),
        outputs=(f"agents/{role}/AGENT.md",),
        timeout_sec=300,
        order=_order_text(cycle_id),
        instruction=instruction,
        work_key=f"{sdef.id}-{role}",     # 역할마다 작업 디렉터리를 분리한다
    )
    sent = await a2a.send_message(url, req)
    deadline = time.time() + 300
    while time.time() < deadline:
        await asyncio.sleep(4)
        t = await a2a.get_task(url, sent.task_id)
        if t.state == "completed":
            want = f"agents/{role}/AGENT.md"
            for a in t.artifacts:
                # ★ 정확히 이 역할의 파일만 집는다. endswith("AGENT.md") 로 잡으면
                #   다른 역할의 파일을 가져와 11개가 전부 같아진다.
                name = a.get("name", "").replace("\\", "/")
                if name == want or name.endswith(f"/{role}/AGENT.md"):
                    txt = a.get("text", "")
                    if txt.lstrip().startswith("---"):
                        parts = txt.split("---", 2)
                        txt = parts[2] if len(parts) > 2 else txt
                    return txt.strip()
            return ""
        if t.state in ("failed", "canceled"):
            return ""
    return ""


TEMPLATES = Path(__file__).parent / "templates"


def _task_name(sdef: Any) -> str:
    """이 단계의 태스크 이름. 게이트는 task 가 비어 있으므로 'gate' 로 본다."""
    if sdef.task:
        return sdef.task
    if sdef.type in ("gate", "human_gate"):
        return "gate"
    return "work"


def _instruction(sdef: Any) -> str:
    """작업 지시 템플릿 (BRIEF §4.1). 없으면 빈 문자열."""
    parts = []
    f = TEMPLATES / f"{_task_name(sdef)}.md"
    if f.exists():
        parts.append(f.read_text(encoding="utf-8").strip())
    # ★ AGENT.md 초안을 만드는 단계에는 BRIEF §4.1 의 템플릿을 반드시 붙인다
    if sdef.emits_specs:
        pd = TEMPLATES / "planner_draft_prompt.md"
        if pd.exists():
            parts.append(pd.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts)


def _order_text(cycle_id: int) -> str:
    """이 사이클이 처리 중인 주문서 원문. 에이전트가 지어내지 않게 하는 근거."""
    db = SessionLocal()
    try:
        from .models import Order
        c = db.get(Cycle, cycle_id)
        if c is None:
            return ""
        o = db.get(Order, c.order_id)
        if o is None:
            return ""
        kind = o.kind.value if hasattr(o.kind, "value") else str(o.kind)
        return (f"고객사/서비스: {o.title}\n"
                f"요구 종류: {kind}\n"
                f"담당자: {o.requester or '-'}\n\n{o.body}")
    finally:
        db.close()


async def _one_role(cycle_id: int, sdef: Any, role: str, url: str,
                    out_dir: Path) -> list[str]:
    """역할 하나에게 작업을 보내고 끝날 때까지 폴링한다."""
    from . import a2a_client as a2a

    hq = os.getenv("HQ_SELF_URL", "http://127.0.0.1:8000")
    req = a2a.TaskRequest(
        role=role, cycle_id=cycle_id, step_id=sdef.id, step_name=sdef.name,
        task=_task_name(sdef),
        spec_url=f"{hq}/api/specs/{role}/raw",
        context_urls=tuple(f"{hq}/api/files?path={c}" for c in sdef.inputs
                           if c not in ("order",)),
        outputs=(tuple(o for o in sdef.outputs if "*" not in o)
                 or (("VERDICT.md",) if sdef.type in ("gate",) else ())),
        timeout_sec=sdef.timeout_sec,
        order=_order_text(cycle_id) if "order" in sdef.inputs else "",
        instruction=_instruction(sdef),
    )

    db = SessionLocal()
    try:
        services.mirror(db, cycle_id, "hq", role, "request",
                        f"{sdef.id} {sdef.name} 지시")
    finally:
        db.close()

    sent = await a2a.send_message(url, req)
    if not sent.task_id:
        raise RuntimeError(f"{role}: taskId 를 받지 못했다")

    deadline = time.time() + sdef.timeout_sec
    while time.time() < deadline:
        await asyncio.sleep(a2a.POLL_SEC)
        try:
            t = await a2a.get_task(url, sent.task_id)
        except Exception:
            continue                       # 노드가 잠깐 바쁠 수 있다. 계속 기다린다.
        if t.state == "completed":
            return _save_artifacts(cycle_id, sdef, role, t, out_dir)
        if t.state in ("failed", "canceled"):
            raise RuntimeError(f"{role}: {t.error or t.state}")

    await a2a.cancel_task(url, sent.task_id)
    raise RuntimeError(f"{role}: 시간 초과 ({sdef.timeout_sec}초)")


def _save_artifacts(cycle_id: int, sdef: Any, role: str, t: Any,
                    out_dir: Path) -> list[str]:
    """노드가 만든 산출물을 repo/ 에 기록한다 (BRIEF §3.5 경로 규약)."""
    saved: list[str] = []
    role_dir = out_dir / role if len(sdef.roles) > 1 else out_dir
    role_dir.mkdir(parents=True, exist_ok=True)

    for a in t.artifacts:
        name = str(a.get("name", "")).lstrip("/")
        if not name or ".." in name:
            continue
        p = role_dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(a.get("text", ""), encoding="utf-8")
        saved.append(str(p.relative_to(REPO_ROOT)))

    if t.report:
        rp = REPO_ROOT / "runs" / str(cycle_id) / sdef.id / (
            f"report-{role}.md" if len(sdef.roles) > 1 else "report.md")
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(t.report, encoding="utf-8")

    db = SessionLocal()
    try:
        services.mirror(db, cycle_id, role, "hq", "response",
                        f"{sdef.id} 완료 — 산출물 {len(saved)}건")
        audit(db, role, "step.artifacts", f"cycle:{cycle_id}:{sdef.id}",
              {"count": len(saved)})
        db.commit()
    finally:
        db.close()
    return saved


def _harvest_spec_bodies(out_dir: Path) -> dict[str, str]:
    """기획이 만든 agents/<role>/AGENT.md 를 산출물에서 걷어낸다."""
    bodies: dict[str, str] = {}
    for role in ROLES:
        for cand in (out_dir / "agents" / role / "AGENT.md",
                     out_dir / f"{role}.md",
                     out_dir / "planner" / "agents" / role / "AGENT.md"):
            if cand.exists():
                txt = cand.read_text(encoding="utf-8", errors="replace")
                # 어댑터가 붙였을 수 있는 front-matter 는 떼고 본문만 쓴다
                if txt.lstrip().startswith("---"):
                    parts = txt.split("---", 2)
                    txt = parts[2] if len(parts) > 2 else txt
                bodies[role] = txt.strip()
                break
    return bodies


def _draft_body(role: str) -> str:
    """기획이 만드는 AGENT.md 초안 (BRIEF §4.1 의 6칸).

    초안은 완벽할 필요 없다. 학생이 자기 전문 지식으로 보강할 것이다.
    """
    return (
        f"# 나는 AGORA Web 의 {role} 담당이다\n\n"
        "## 나의 역할\n(기획이 생성한 초안)\n\n"
        "## 내 파일\n- `repo/project-001/` 아래 내 역할 산출물\n\n"
        "## 출력 형식\n- 마크다운. 결론 먼저.\n\n"
        "## 금지\n- 요구사항에 없는 기능을 임의로 추가하지 않는다\n\n"
        "## 애매할 때\n- 기획(planner)에게 A2A 로 묻는다\n\n"
        "## 완료 보고\n- `report.md` 에 산출물 목록과 남은 이슈를 적는다\n\n"
        "<!-- ↑ 여기까지가 기획이 만든 초안이다.\n"
        "     학생은 자기 전문 지식을 더해 이 파일을 고치고 커밋한다. -->\n"
    )
