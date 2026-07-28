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
    """실제 학생 노드 호출 — Phase 2 에서 a2a_client 를 연결한다."""
    raise NotImplementedError(
        "EXECUTOR=a2a 는 Phase 2(노드 A2A 어댑터) 이후에 쓸 수 있다"
    )


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
