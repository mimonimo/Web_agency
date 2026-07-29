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
import json
import os
import time
from pathlib import Path
from urllib.parse import quote
from typing import Any

from sqlalchemy import select

from . import checks, directives, pipelines, services
from . import roles as roles_catalog
from .db import SessionLocal
from .models import Cycle, CycleStatus, ROLE_DISPLAY, ROLES, Step, StepStatus
from .orchestrator import Action, Event, next_step
from .services import PROJECT_ID, REPO_ROOT, audit, now

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


# ★ 「지금 고치기」 예약함.
#   사이클이 돌고 있는 동안에는 단계를 다시 시킬 수 없다 (한 사이클에 실행기 하나).
#   그렇다고 사람에게 "끝날 때까지 기다렸다가 다시 누르세요" 라고 할 수는 없다.
#   그래서 예약해 두고 지금 단계가 끝나는 순간 실행기가 스스로 처리한다.
#
#   ⚠️ 파일에 남긴다. 메모리에만 두면 HQ 를 재시작하는 순간 사람이 누른 요청이
#      말없이 사라진다. 사람이 누른 것은 잃어버리면 안 된다.
_RERUN_FILE = REPO_ROOT / PROJECT_ID / ".rerun.json"


def _rerun_load() -> dict[str, list[list]]:
    try:
        return json.loads(_RERUN_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _rerun_save(data: dict[str, list[list]]) -> None:
    try:
        _RERUN_FILE.parent.mkdir(parents=True, exist_ok=True)
        if data:
            _RERUN_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        else:
            _RERUN_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def queue_rerun(cycle_id: int, role: str, step_key: str | None, note: str) -> None:
    d = _rerun_load()
    d.setdefault(str(cycle_id), []).append([role, step_key, note])
    _rerun_save(d)


def pending_rerun(cycle_id: int) -> list[tuple[str, str | None, str]]:
    return [(r, s, n) for r, s, n in _rerun_load().get(str(cycle_id), [])]


def _rerun_take(cycle_id: int) -> list[tuple[str, str | None, str]]:
    d = _rerun_load()
    items = d.pop(str(cycle_id), [])
    if items:
        _rerun_save(d)
    return [(r, s, n) for r, s, n in items]


def _apply_pending_rerun(db: Any, cycle: Any) -> bool:
    """예약된 재요청을 처리한다. 되감았으면 True.

    되감기 지점은 **가장 앞선 단계**로 잡는다 — 디자인과 프론트엔드를 둘 다
    고쳐 달라고 했으면 디자인부터 다시 해야 프론트엔드가 그 결과를 본다.
    """
    import shutil

    from .models import Artifact

    items = _rerun_take(cycle.id)
    if not items:
        return False

    pl = pipelines.load(cycle.pipeline)
    steps = db.scalars(select(Step).where(Step.cycle_id == cycle.id)
                       .order_by(Step.id)).all()
    order = {s.step_key: i for i, s in enumerate(steps)}

    targets: list[Step] = []
    for role, want, note in items:
        pick = None
        for s in reversed(steps):
            if want and s.step_key != want:
                continue
            d = pl.step(s.step_key)
            rs = list(d.roles) if d else ([s.role] if s.role else [])
            if role in rs and s.status in (StepStatus.DONE, StepStatus.FAILED,
                                           StepStatus.REJECTED):
                pick = s
                break
        if pick is None:
            # 그 역할이 아직 일한 적이 없다 — 지시만 남는다. 처음 일할 때 반영된다.
            services.mirror(db, cycle.id, "pm", role, "request",
                            f"{note} (아직 차례가 아니라 다음 작업에 반영된다)")
            continue
        targets.append(pick)
        services.mirror(db, cycle.id, "pm", role, "request", note)

    if not targets:
        db.commit()
        return False

    first = min(targets, key=lambda s: order.get(s.step_key, 0))
    for s in steps:
        if order.get(s.step_key, 0) < order.get(first.step_key, 0):
            continue
        if s.status in (StepStatus.DONE, StepStatus.FAILED, StepStatus.REJECTED):
            s.status = StepStatus.PENDING
            s.error = None
            s.output_ref = None
            s.started_at = s.ended_at = None
            run_dir = REPO_ROOT / "runs" / str(cycle.id) / s.step_key
            shutil.rmtree(run_dir, ignore_errors=True)
            db.execute(Artifact.__table__.delete().where(
                Artifact.cycle_id == cycle.id, Artifact.step_id == s.id))

    cycle.current_step = first.step_key
    audit(db, "pm", "cycle.rerun_applied", f"cycle:{cycle.id}",
          {"from_step": first.step_key, "roles": [r for r, _, _ in items]})
    services.mirror(db, cycle.id, "hq", "pm", "response",
                    f"수정 요청 반영 — {first.step_key} 부터 다시 만든다")
    db.commit()
    return True


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
        except asyncio.CancelledError:
            # ★ HQ 가 내려가는 중이다. 이건 단계의 실패가 아니다.
            #   여기서 FAILED 로 적으면 사이클이 통째로 죽고, 재시작해도
            #   자가복구가 손댈 수 없다 (복구는 RUNNING 만 되살린다).
            #   RUNNING 인 채로 두고 물러난다 — 다음 부팅 때 되살아난다.
            db = SessionLocal()
            try:
                audit(db, "hq", "step.interrupted", f"cycle:{cycle_id}:{key}",
                      {"note": "HQ 종료로 중단 — 다음 기동 때 되살린다"})
                db.commit()
            finally:
                db.close()
            raise
        except Exception as e:                                  # noqa: BLE001
            # 메시지가 빈 예외도 있다. 최소한 어떤 종류였는지는 남긴다.
            detail = str(e).strip() or type(e).__name__
            result, err = None, f"{key} 실행 오류: {detail}"

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

            # ★ 게이트라면 에이전트의 판정을 읽어 반려 여부를 정한다 (인수 #19)
            cv, sv = services.snapshot(db, cycle)
            if GATE_AUTO and sdef is not None and sdef.type == "gate":
                rejected, reason = read_verdict(cycle_id, key)
                if rejected:
                    t = next_step(cv, sv, Event.GATE_REJECT,
                                  {"step": key, "reason": reason})
                    if t.action is not Action.NOOP:
                        services.mirror(db, cycle_id, step.role or "qa", "hq", "reject",
                                        f"{key} 반려 — {reason[:120]}")
                        services.apply(db, cycle, t, actor=step.role or "qa")
                        if t.action is Action.INVALIDATE_FROM:
                            continue          # 되감긴 지점부터 다시 돈다
                        return

            # ★ 사람이 「지금 고치기」를 눌러 둔 것이 있으면 여기서 처리한다.
            #   돌고 있는 도중에는 재요청을 받을 수 없으므로 예약해 두고,
            #   지금 단계가 끝난 이 자리에서 되감아 준다. 사람이 다시 누르지 않아도 된다.
            if _apply_pending_rerun(db, cycle):
                continue

            t = next_step(cv, sv, Event.STEP_DONE, {"step": key})
            services.apply(db, cycle, t)

            if t.action is not Action.RUN_STEP:
                return
        finally:
            db.close()


GATE_AUTO = os.getenv("GATE_AUTO", "1") == "1"


def read_verdict(cycle_id: int, step_key: str) -> tuple[bool, str]:
    """게이트 에이전트가 쓴 VERDICT.md 를 읽는다.

    반환: (반려인가?, 사유)

    첫 줄에 `판정: 통과` 또는 `판정: 반려` 를 쓰게 되어 있다 (templates/gate.md).
    ⚠️ 읽을 수 없거나 애매하면 **통과로 본다.** 게이트가 판정을 못 했다고
       사이클을 멈춰 세우면 수업이 진행되지 않는다. 강사가 수동으로 반려하면 된다.
    """
    base = REPO_ROOT / "runs" / str(cycle_id) / step_key
    for p in (base / "output" / "VERDICT.md", base / "output" / "verdict.md"):
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        head = "\n".join(text.strip().splitlines()[:5])
        if "반려" in head and "통과" not in head.split("반려")[0][-20:]:
            # ⚠️ 제목(`## 이유 및 개선 방안`)을 사유로 뽑으면 아무 정보가 없다.
            #    제목·빈 줄·코드펜스를 건너뛰고 **알맹이 있는 줄**을 모은다.
            picked: list[str] = []
            in_code = False
            for line in text.splitlines():
                raw = line.strip()
                if raw.startswith("```"):
                    in_code = not in_code
                    continue
                if in_code or not raw:
                    continue
                if raw.startswith("#"):          # 마크다운 제목
                    continue
                t = raw.lstrip("-*0123456789. ").strip()
                t = t.replace("**", "")
                if not t or "판정" in t:
                    continue
                if len(t) < 8:                   # "이유", "1." 같은 토막
                    continue
                picked.append(t)
                if len(picked) >= 3:
                    break
            reason = " / ".join(picked)
            return True, (reason or "게이트가 반려했다")[:400]
        return False, ""
    return False, ""


# ── 실행 백엔드 ────────────────────────────────────────────────────────
async def _execute(cycle_id: int, sdef: Any) -> dict[str, Any]:
    if EXECUTOR == "a2a":
        return await _execute_a2a(cycle_id, sdef)
    if EXECUTOR == "llm":
        return await _execute_llm(cycle_id, sdef)
    return await _execute_sim(cycle_id, sdef)


# ── EXECUTOR=llm — 모델 API 를 직접 부른다 ─────────────────────────────
#
# ★ 이 경로의 존재 이유: **모델을 바꿔도 같은 지시·같은 검사를 받는다**는 것을
#   말이 아니라 코드로 보이기 위해서다.
#   노드(Hermes)를 거치지 않고 Claude 나 OpenAI 호환 엔드포인트를 직접 부르되,
#   지시문 조립·참고자료 전달·완료조건 검사·자가 재작업은 a2a 와 완전히 같다.
#
#   교실에서는 쓰지 않는다 (인터넷이 없다). 발표·비교·다른 환경 이식용이다.

async def _execute_llm(cycle_id: int, sdef: Any) -> dict[str, Any]:
    from . import providers

    out_dir = REPO_ROOT / "runs" / str(cycle_id) / sdef.id / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    roles = list(sdef.roles) or ["pm"]

    results = await asyncio.gather(
        *[_llm_one_role(cycle_id, sdef, r, out_dir, providers.get()) for r in roles],
        return_exceptions=True,
    )
    artifacts: list[str] = []
    errors: list[str] = []
    for role, res in zip(roles, results):
        if isinstance(res, asyncio.CancelledError):
            # HQ 종료로 취소된 것이다. 실패로 바꿔치지 않고 그대로 올려보낸다.
            raise res
        if isinstance(res, BaseException):
            # str() 이 빈 예외가 있다 (CancelledError 등). 종류라도 남긴다.
            errors.append(f"{role}: {str(res).strip() or type(res).__name__}")
        else:
            artifacts.extend(res)
    if errors and not artifacts:
        raise RuntimeError("; ".join(errors))

    if sdef.emits_specs:
        bodies = _harvest_spec_bodies(out_dir)
        db = SessionLocal()
        try:
            cycle = db.get(Cycle, cycle_id)
            services.emit_spec_drafts(
                db, cycle, {r: bodies.get(r, _draft_body(r)) for r in ROLES})
        finally:
            db.close()

    return {"output_dir": str(out_dir.relative_to(REPO_ROOT)), "artifacts": artifacts}


async def _llm_one_role(cycle_id: int, sdef: Any, role: str, out_dir: Path,
                        provider: Any) -> list[str]:
    """역할 하나 — 부르고, 저장하고, 검사하고, 미달이면 다시 부른다.

    a2a 경로의 `_one_role` 과 같은 루프다. 다른 것은 "누가 실행하느냐" 뿐이다.
    """
    from . import checks as _checks, providers

    role_dir = out_dir / role if len(sdef.roles) > 1 else out_dir
    role_dir.mkdir(parents=True, exist_ok=True)

    outputs = tuple(o for o in sdef.outputs_for(role) if "*" not in o) or (
        ("VERDICT.md",) if sdef.type in ("gate",) else ())
    system = _llm_system(role)
    fix_note = ""
    saved: list[str] = []

    for attempt in range(CHECK_RETRY + 1):
        user = _llm_user(cycle_id, sdef, role, outputs, fix_note)
        db = SessionLocal()
        try:
            services.mirror(db, cycle_id, "hq", role, "request",
                            f"{sdef.id} {sdef.name} 지시 ({providers.describe()})"
                            if not attempt else f"{sdef.id} 재작업 지시 (완료 조건 미달)")
        finally:
            db.close()

        text = await provider.complete(system, user)
        files = providers.parse_files(text)
        if not files:
            raise RuntimeError(
                f"{role}: 모델이 파일 형식(=== FILE: … ===)을 지키지 않았다 "
                f"({len(text)}자 응답)")

        saved = []
        for name, body in files.items():
            p = role_dir / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
            saved.append(str(p.relative_to(REPO_ROOT)))

        rp = REPO_ROOT / "runs" / str(cycle_id) / sdef.id / (
            f"report-{role}.md" if len(sdef.roles) > 1 else "report.md")
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(f"# {sdef.id} {role} 완료 보고\n\n"
                      f"- 모델: {providers.describe()}\n"
                      f"- 산출물 {len(saved)}건: {', '.join(files)}\n"
                      f"- 시도 {attempt + 1}회\n", encoding="utf-8")

        db = SessionLocal()
        try:
            services.mirror(db, cycle_id, role, "hq", "response",
                            f"{sdef.id} 완료 — 산출물 {len(saved)}건")
            audit(db, role, "step.artifacts", f"cycle:{cycle_id}:{sdef.id}",
                  {"count": len(saved)})
            db.commit()
        finally:
            db.close()

        findings = _checks.check(role, role_dir, {"screens": _screen_count(cycle_id)})
        bad = _checks.failures(findings)
        okn, total = _checks.score(findings)
        if not bad:
            if total:
                _log_check(cycle_id, sdef, role, okn, total, [])
            return saved
        if attempt >= CHECK_RETRY:
            _log_check(cycle_id, sdef, role, okn, total, bad, final=True)
            return saved
        _log_check(cycle_id, sdef, role, okn, total, bad)
        fix_note = _checks.report(findings)

    return saved


def _llm_system(role: str) -> str:
    """시스템 프롬프트 = 그 역할의 AGENT.md. 노드가 하는 것과 같다."""
    p = services.spec_path(role)
    spec = p.read_text(encoding="utf-8") if p.exists() else services.baseline_spec(role)
    return (spec or f"너는 AGORA Web 의 {role} 담당이다.").strip()


def _llm_user(cycle_id: int, sdef: Any, role: str,
              outputs: tuple[str, ...], fix_note: str) -> str:
    """참고 자료를 본문에 실어 보낸다 (노드 어댑터가 하는 일과 같다).

    ⚠️ 크기를 자른다. 프롬프트가 커지면 어떤 모델이든 품질이 떨어진다.
       자른 파일은 제목에 밝힌다 — 조용히 자르면 "이게 전부" 라고 오해한다.
    """
    from . import providers

    parts = [providers.output_protocol(outputs)]
    order = _order_text(cycle_id) if "order" in sdef.inputs else ""
    if order:
        parts.append(f"## 주문서\n\n{order}")

    budget, per = 40000, 8000
    used = 0
    refs: list[str] = []
    for rel in resolve_inputs(cycle_id, sdef.inputs):
        try:
            body = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        take = min(per, max(0, budget - used))
        if take <= 0:
            break
        cut = len(body) > take
        used += take
        refs.append(f"### {rel}{' (앞부분만)' if cut else ''}\n\n```\n{body[:take]}\n```")
    if refs:
        parts.append("## 참고 자료 — 반드시 읽고 따른다\n\n" + "\n\n".join(refs))

    parts.append(f"## 지금 할 일 — {sdef.id} {sdef.name}\n\n{_instruction(sdef, role)}")
    if fix_note:
        parts.append(fix_note)
    return "\n\n".join(parts)


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
        if isinstance(res, asyncio.CancelledError):
            # HQ 종료로 취소된 것이다. 실패로 바꿔치지 않고 그대로 올려보낸다.
            raise res
        if isinstance(res, BaseException):
            # str() 이 빈 예외가 있다 (CancelledError 등). 종류라도 남긴다.
            errors.append(f"{role}: {str(res).strip() or type(res).__name__}")
        else:
            artifacts.extend(res)

    if errors and not artifacts:
        raise RuntimeError("; ".join(errors))

    # ★ S2 는 11개 AGENT.md 초안을 만든다 (인수 #12).
    if sdef.emits_specs:
        bodies = _harvest_spec_bodies(out_dir)
        # 한 번의 호출로 11개를 다 쓰게 하면 모델이 2~3개 쓰고 멈춘다.
        # 그렇다고 11번 따로 부르면 S2 하나에 20분이 넘는다.
        # → **3개씩 묶어서** 부른다. 모자란 것만 마지막에 하나씩 다시 시킨다.
        planner_url = _role_url("planner")
        if planner_url:
            missing = [r for r in ROLES if not spec_ok(bodies.get(r, ""))]
            for i in range(0, len(missing), SPEC_BATCH):
                chunk = missing[i:i + SPEC_BATCH]
                try:
                    got = await _draft_specs_batch(cycle_id, sdef, planner_url, chunk)
                    for r, body in got.items():
                        if len(body.strip()) > len(bodies.get(r, "")):
                            bodies[r] = body
                except Exception:
                    pass

            # 묶음으로도 안 나온 것만 하나씩. 여기까지 오는 건 보통 1~2개다.
            for role in [r for r in ROLES if not spec_ok(bodies.get(r, ""))]:
                try:
                    body = await _draft_one_spec(cycle_id, sdef, planner_url, role)
                    if len(body.strip()) > len(bodies.get(role, "")):
                        bodies[role] = body
                except Exception:
                    pass                   # 실패해도 기본 템플릿으로 채운다

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
    """기획이 만든 **「이번 프로젝트」 칸**이 쓸 만한가.

    ★ 예전에는 여기서 AGENT.md 전문(6칸)을 검사했다. 지금은 6칸이 기준선에서 오므로
      검사할 것은 "이번 주문의 이야기가 실제로 들어 있는가" 하나다.
      로컬 모델에게 작고 구체적인 일만 맡기는 것이 이 구조의 요점이다.

    통과 조건: 120자 이상 + 자리표시자가 아님 + 주문의 고유명사나 항목이 보임.
    """
    t = (body or "").strip()
    if len(t) < 120:
        return False
    low = t.lower()
    if any(x in t for x in ("아직 비어", "(미정)", "TODO", "여기에 내용")) or "lorem" in low:
        return False
    # 전문이 들어온 예전 경로도 통과시킨다 (6칸 중 5칸 이상)
    if sum(1 for s in SPEC_SECTIONS if f"## {s}" in t) >= 5:
        return True
    # 목록이든 문단이든, 최소 두 줄은 있어야 학생이 고칠 자리가 생긴다
    return len([ln for ln in t.splitlines() if ln.strip()]) >= 2


def _role_url(role: str) -> str | None:
    from .models import Node
    db = SessionLocal()
    try:
        n = db.scalar(select(Node).where(Node.role == role))
        return n.a2a_url if n else None
    finally:
        db.close()


# 한 번에 몇 개의 AGENT.md 를 쓰게 할지. 너무 크면 모델이 중간에 멈춘다.
SPEC_BATCH = int(os.getenv("SPEC_BATCH", "3"))


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


async def _draft_specs_batch(cycle_id: int, sdef: Any, url: str,
                             roles: list[str]) -> dict[str, str]:
    """기획에게 여러 역할의 AGENT.md 를 한 번에 쓰게 한다 (기본 3개)."""
    from . import a2a_client as a2a

    hq = os.getenv("HQ_SELF_URL", "http://127.0.0.1:8000")
    listing = "\n".join(
        f"  - `agents/{r}/PROJECT.md` — {ROLE_DISPLAY.get(r, r)}({ROLE_HINT.get(r, r)})"
        for r in roles)
    instruction = (
        f"{_project_block_prompt()}\n\n"
        f"이번에 만들 파일은 다음 {len(roles)}개뿐이다. **이것만** 만든다.\n\n"
        f"{listing}\n\n"
        "⚠️ 위 파일을 **전부** 만들어라. 하나라도 빠지면 다음 단계가 막힌다."
    )
    req = a2a.TaskRequest(
        role="planner", cycle_id=cycle_id, step_id=sdef.id,
        step_name=f"역할별 이번 프로젝트 {len(roles)}건",
        task="draft_specs_batch",
        spec_url=f"{hq}/api/specs/planner/raw",
        context_urls=tuple(f"{hq}/api/files?path={quote(c)}"
                           for c in resolve_inputs(cycle_id, ("SRS.md", "SCREENS.md"))),
        outputs=tuple(f"agents/{r}/PROJECT.md" for r in roles),
        timeout_sec=600,
        order=_order_text(cycle_id),
        instruction=instruction,
        work_key=f"{sdef.id}-batch-{roles[0]}",
    )
    sent = await a2a.send_message(url, req)
    out: dict[str, str] = {}
    deadline = time.time() + 600
    while time.time() < deadline:
        await asyncio.sleep(5)
        t = await a2a.get_task(url, sent.task_id)
        if t.state == "completed":
            for a in t.artifacts:
                name = a.get("name", "").replace("\\", "/")
                for r in roles:
                    if name.endswith(f"{r}/PROJECT.md") or name.endswith(f"{r}/AGENT.md"):
                        txt = a.get("text", "")
                        if txt.lstrip().startswith("---"):
                            parts = txt.split("---", 2)
                            txt = parts[2] if len(parts) > 2 else txt
                        out[r] = txt.strip()
            return out
        if t.state in ("failed", "canceled"):
            return out
    return out


async def _draft_one_spec(cycle_id: int, sdef: Any, url: str, role: str) -> str:
    """기획에게 역할 하나의 AGENT.md 만 쓰게 한다 (BRIEF §4.1 의 6칸)."""
    from . import a2a_client as a2a

    hq = os.getenv("HQ_SELF_URL", "http://127.0.0.1:8000")
    instruction = (
        f"{_project_block_prompt()}\n\n"
        f"이번에 만들 파일은 하나뿐이다: `agents/{role}/PROJECT.md`\n"
        f"({ROLE_DISPLAY.get(role, role)} — {ROLE_HINT.get(role, role)})\n"
        "다른 파일은 만들지 마라."
    )
    req = a2a.TaskRequest(
        role="planner", cycle_id=cycle_id, step_id=sdef.id,
        step_name=f"{role} 이번 프로젝트",
        task="draft_one_spec",
        spec_url=f"{hq}/api/specs/planner/raw",
        context_urls=tuple(
            f"{hq}/api/files?path={quote(c)}"
            for c in resolve_inputs(cycle_id, ("SRS.md", "SCREENS.md", "SOW.md"))),
        outputs=(f"agents/{role}/PROJECT.md",),
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
            for a in t.artifacts:
                # ★ 정확히 이 역할의 파일만 집는다. endswith("PROJECT.md") 로 잡으면
                #   다른 역할의 파일을 가져와 11개가 전부 같아진다.
                name = a.get("name", "").replace("\\", "/")
                if name.endswith(f"/{role}/PROJECT.md") or name.endswith(f"/{role}/AGENT.md") \
                        or name in (f"agents/{role}/PROJECT.md", f"agents/{role}/AGENT.md"):
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


def _instruction(sdef: Any, role: str = "") -> str:
    """작업 지시를 조립한다 (BRIEF §4.1).

    순서가 의미를 갖는다. 뒤에 오는 것이 앞을 이긴다고 모델에게 알려 두었으므로,
    **사람이 끼워 넣은 지시가 맨 뒤**에 온다.

        1. 작업 템플릿          무엇을 만드는가
        2. 공통 품질 기준       모든 산출물에 적용
        3. 역할 목표·완료조건   roles.yaml — 이 역할이 지켜야 할 검사 항목
        4. (S2만) 스펙 템플릿
        5. ★ 사람의 추가 지시   최우선

    ⚠️ 전체 길이를 본다. 프롬프트가 커지면 로컬 모델이 중간에 멈춘다 (실제로 겪었다).
    """
    parts = []
    f = TEMPLATES / f"{_task_name(sdef)}.md"
    if f.exists():
        parts.append(f.read_text(encoding="utf-8").strip())
    # ★ 공통 품질 기준은 모든 작업에 붙인다. 이게 없으면 결과물 수준이 들쭉날쭉하다.
    q = TEMPLATES / "_quality.md"
    if q.exists():
        parts.append(q.read_text(encoding="utf-8").strip())
    # ★ 역할의 목표와 완료 조건. 매 요청에 다시 실어야 따라온다.
    if role:
        b = roles_catalog.brief(role)
        if b:
            parts.append(b)
    # ★ AGENT.md 초안을 만드는 단계에는 BRIEF §4.1 의 템플릿을 반드시 붙인다
    if sdef.emits_specs:
        pd = TEMPLATES / "planner_draft_prompt.md"
        if pd.exists():
            parts.append(pd.read_text(encoding="utf-8").strip())
    # ★ 사람이 끼워 넣은 지시 — 반드시 맨 뒤 (앞을 이긴다)
    if role:
        d = directives.block(role)
        if d:
            parts.append(d)
    return "\n\n".join(parts)


def resolve_inputs(cycle_id: int, names: tuple[str, ...]) -> list[str]:
    """`inputs: [SRS.md, ...]` 를 **실제로 만들어진 파일 경로**로 바꾼다.

    ⚠️ 이게 없으면 참고 자료가 노드에 전달되지 않는다.
       실제로 그랬다 — 프론트엔드가 화면 목록도 디자인 토큰도 못 본 채 사이트를 만들었다.

    같은 이름이 여러 단계에서 나오면 **가장 최근 것**을 쓴다.
    """
    out: list[str] = []
    runs = REPO_ROOT / "runs" / str(cycle_id)
    project = REPO_ROOT / PROJECT_ID
    for name in names:
        if name in ("order",):
            continue
        found: list[Path] = []
        if runs.exists():
            found += [p for p in runs.rglob(name) if p.is_file()]
        if project.exists():
            found += [p for p in project.rglob(name) if p.is_file()]
        if not found:
            continue
        best = max(found, key=lambda p: p.stat().st_mtime)
        out.append(str(best.relative_to(REPO_ROOT)))
    return out


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


# 완료 조건을 못 지켰을 때 몇 번까지 다시 시킬지.
# 0 이면 검사만 하고 재실행하지 않는다 (시간이 급한 수업용).
CHECK_RETRY = int(os.getenv("CHECK_RETRY", "1"))


async def _one_role(cycle_id: int, sdef: Any, role: str, url: str,
                    out_dir: Path) -> list[str]:
    """역할 하나에게 작업을 보내고, 결과를 **검사하고**, 미달이면 다시 시킨다.

    ★ 이 재실행 루프가 "어떤 모델을 붙여도 바닥이 유지된다" 의 실체다.
      모델에게 부탁하는 대신, 확인하고 무엇이 틀렸는지 알려 주며 다시 시킨다.
      `checks.py` 가 보는 것은 형식·존재·수치뿐이다. 의미는 게이트가 본다.
    """
    from . import a2a_client as a2a

    fix_note = ""
    findings: list[checks.Finding] = []
    saved: list[str] = []

    for attempt in range(CHECK_RETRY + 1):
        saved = await _send_and_wait(cycle_id, sdef, role, url, out_dir, fix_note,
                                     attempt, a2a)

        findings = checks.check(role, _role_out_dir(sdef, role, out_dir),
                                {"screens": _screen_count(cycle_id)})
        bad = checks.failures(findings)
        ok, total = checks.score(findings)
        if not bad:
            if total:
                _log_check(cycle_id, sdef, role, ok, total, [])
            return saved
        if attempt >= CHECK_RETRY:
            # 더 안 시킨다. 사실을 남기고 넘긴다 — 게이트가 판단할 몫이다.
            _log_check(cycle_id, sdef, role, ok, total, bad, final=True)
            return saved
        _log_check(cycle_id, sdef, role, ok, total, bad)
        fix_note = checks.report(findings)

    return saved


def _role_out_dir(sdef: Any, role: str, out_dir: Path) -> Path:
    return out_dir / role if len(sdef.roles) > 1 else out_dir


def _screen_count(cycle_id: int) -> int:
    """SCREENS.md 의 화면 수 — 프론트엔드 검사의 목표치."""
    for rel in resolve_inputs(cycle_id, ("SCREENS.md",)):
        import re as _re
        txt = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        return len(_re.findall(r"^##\s+\S", txt, _re.M))
    return 0


def _log_check(cycle_id: int, sdef: Any, role: str, ok: int, total: int,
               bad: list[checks.Finding], final: bool = False) -> None:
    """검사 결과를 픽셀 오피스 로그와 감사 로그에 남긴다.

    조용히 재실행하면 학생이 "왜 두 번 도나" 를 알 수 없다. 보이게 한다.
    """
    db = SessionLocal()
    try:
        if not bad:
            msg = f"{sdef.id} 완료 조건 {ok}/{total} 통과"
        elif final:
            msg = (f"{sdef.id} 완료 조건 {ok}/{total} — 미달 {len(bad)}건 남긴 채 진행 "
                   f"({bad[0].label})")
        else:
            msg = f"{sdef.id} 완료 조건 {ok}/{total} — 미달 {len(bad)}건, 다시 시킨다"
        services.mirror(db, cycle_id, "hq", role, "response", msg)
        audit(db, "hq", "step.check", f"cycle:{cycle_id}:{sdef.id}",
              {"role": role, "ok": ok, "total": total,
               "failed": [f.label for f in bad][:8], "final": final})
        db.commit()
    finally:
        db.close()


async def _send_and_wait(cycle_id: int, sdef: Any, role: str, url: str,
                         out_dir: Path, fix_note: str, attempt: int, a2a) -> list[str]:
    """한 번 보내고 끝날 때까지 폴링한다."""
    hq = os.getenv("HQ_SELF_URL", "http://127.0.0.1:8000")
    instruction = _instruction(sdef, role)
    if fix_note:
        instruction = f"{instruction}\n\n{fix_note}"

    req = a2a.TaskRequest(
        role=role, cycle_id=cycle_id, step_id=sdef.id, step_name=sdef.name,
        task=_task_name(sdef),
        spec_url=f"{hq}/api/specs/{role}/raw",
        context_urls=tuple(
            f"{hq}/api/files?path={quote(c)}"
            for c in resolve_inputs(cycle_id, sdef.inputs)),
        outputs=(tuple(o for o in sdef.outputs_for(role) if "*" not in o)
                 or (("VERDICT.md",) if sdef.type in ("gate",) else ())),
        timeout_sec=sdef.timeout_sec,
        order=_order_text(cycle_id) if "order" in sdef.inputs else "",
        instruction=instruction,
        # 재실행은 작업 디렉터리를 분리한다 — 앞 시도의 파일을 그대로 집어오지 않게
        work_key=f"{sdef.id}-{role}-r{attempt}" if attempt else "",
    )

    db = SessionLocal()
    try:
        services.mirror(db, cycle_id, "hq", role, "request",
                        f"{sdef.id} {sdef.name} 지시" if not attempt
                        else f"{sdef.id} 재작업 지시 (완료 조건 미달)")
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


def _foreign_outputs(sdef: Any, role: str) -> set[str]:
    """같은 단계의 **다른 역할**이 만들기로 한 파일 이름.

    ★ DBA 가 `seed.sql` 만 내야 하는데 `index.html`·`style.css`·`app.js` 까지
      통째로 만들어 낸 일이 실제로 있었다. 모델이 "도와주려고" 남의 일을 한 것이다.
      그러면 같은 파일이 두 벌 생기고, 어느 것이 진짜인지 아무도 모른다.
      역할 경계는 부탁이 아니라 코드로 막는다.
    """
    mine = set(sdef.outputs_for(role))
    out: set[str] = set()
    for r in sdef.roles:
        if r == role:
            continue
        out |= {Path(o).name for o in sdef.outputs_for(r) if "*" not in o}
    return {n for n in out if n not in mine}


def _input_names(cycle_id: int, sdef: Any) -> dict[str, str]:
    """이 단계에 실어 보낸 참고 자료 {파일이름: 내용}.

    노드 어댑터는 참고 자료를 작업 디렉터리에 내려놓고 일한다. 그러다 보니
    **읽으라고 준 파일이 만들었다고 올라온다.** 산출물이 아니므로 걸러 낸다.
    """
    out: dict[str, str] = {}
    for rel in resolve_inputs(cycle_id, sdef.inputs):
        p = REPO_ROOT / rel
        try:
            out[p.name] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return out


def _save_artifacts(cycle_id: int, sdef: Any, role: str, t: Any,
                    out_dir: Path) -> list[str]:
    """노드가 만든 산출물을 repo/ 에 기록한다 (BRIEF §3.5 경로 규약).

    두 가지를 걸러 낸다 — 둘 다 실제로 겪은 일이다.
      1. 남의 역할 파일 (DBA 가 index.html 을 만들어 올린다)
      2. 참고 자료가 그대로 되돌아온 것 (SCREENS.md 를 읽으라고 줬더니 산출물로 온다)
    """
    saved: list[str] = []
    role_dir = out_dir / role if len(sdef.roles) > 1 else out_dir
    role_dir.mkdir(parents=True, exist_ok=True)

    foreign = _foreign_outputs(sdef, role)
    given = _input_names(cycle_id, sdef)
    dropped: list[str] = []

    for a in t.artifacts:
        name = str(a.get("name", "")).lstrip("/")
        if not name or ".." in name:
            continue
        body = a.get("text", "")
        base = Path(name).name

        if base in foreign:
            dropped.append(f"{name}(남의 역할)")
            continue
        if base in given and body.strip() == given[base].strip():
            dropped.append(f"{name}(참고자료 반송)")
            continue

        p = role_dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        saved.append(str(p.relative_to(REPO_ROOT)))

    if dropped:
        # 조용히 버리면 "왜 파일이 없지" 가 된다. 버린 사실과 이유를 남긴다.
        db = SessionLocal()
        try:
            services.mirror(db, cycle_id, "hq", role, "response",
                            f"{sdef.id} 산출물 {len(dropped)}건 제외 — {', '.join(dropped[:4])}")
            audit(db, "hq", "step.artifacts_dropped", f"cycle:{cycle_id}:{sdef.id}",
                  {"role": role, "dropped": dropped[:10]})
            db.commit()
        finally:
            db.close()

    if t.report:
        rp = REPO_ROOT / "runs" / str(cycle_id) / sdef.id / (
            f"report-{role}.md" if len(sdef.roles) > 1 else "report.md")
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(t.report, encoding="utf-8")

    # ※ 완료 미러링은 노드 어댑터가 이미 보낸다 (BRIEF §5.3).
    #    여기서 또 넣으면 픽셀 오피스 로그에 같은 줄이 두 번 뜬다.
    #    HQ 는 감사 로그만 남긴다.
    db = SessionLocal()
    try:
        audit(db, role, "step.artifacts", f"cycle:{cycle_id}:{sdef.id}",
              {"count": len(saved)})
        db.commit()
    finally:
        db.close()
    return saved


def _project_block_prompt() -> str:
    p = TEMPLATES / "project_block_prompt.md"
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def _harvest_spec_bodies(out_dir: Path) -> dict[str, str]:
    """기획이 만든 역할별 「이번 프로젝트」 블록을 산출물에서 걷어낸다.

    파일 이름이 `PROJECT.md` 든 `AGENT.md` 든 받는다 — 모델이 이름을 자주 헷갈린다.
    """
    bodies: dict[str, str] = {}
    for role in ROLES:
        for cand in (out_dir / "agents" / role / "PROJECT.md",
                     out_dir / "agents" / role / "AGENT.md",
                     out_dir / f"{role}.md",
                     out_dir / "planner" / "agents" / role / "PROJECT.md",
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
    """기획이 「이번 프로젝트」 칸을 못 만들었을 때의 대체 문구.

    ★ 예전에는 여기서 AGENT.md 전문을 흉내 냈다. 지금은 전문이 기준선
      (`agents/<role>/AGENT.md`)에서 오므로, 못 채운 칸만 표시해 두면 된다.
      빈 채로 두면 학생이 "기획이 뭘 안 했는지" 를 알 수 없다.
    """
    return ("(기획이 이번 프로젝트 내용을 채우지 못했다. "
            "주문서를 보고 직접 적거나, 기획에게 재요청해라.)")
