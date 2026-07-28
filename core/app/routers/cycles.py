"""사이클 제어 — ★ 핵심 (BRIEF §7).

이 라우터가 수업의 조작 패널이다. pause / resume / reset(keep_specs=true) 는
절대 자르면 안 되는 기능이다 (BRIEF §14).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import pipelines, runner, services
from ..db import get_db
from ..models import Cycle, Order, Step
from ..orchestrator import Action, Event, next_step

router = APIRouter(prefix="/api/cycles", tags=["cycles"])


class CycleCreate(BaseModel):
    order_id: int
    pipeline: str | None = None
    mode: str = "auto"


class RewindRequest(BaseModel):
    step_key: str


class ResetRequest(BaseModel):
    # ⚠️ 기본값은 반드시 True. 학생이 고친 AGENT.md 를 리셋 한 번에 날리면
    #    수업이 망한다 (BRIEF §3.4). False 는 UI 에서 확인 대화를 한 번 더 받는다.
    keep_specs: bool = Field(default=True)


def _get(db: Session, cycle_id: int) -> Cycle:
    c = db.get(Cycle, cycle_id)
    if c is None:
        raise HTTPException(404, f"사이클 {cycle_id} 을 찾을 수 없다")
    return c


def _fire(db: Session, cycle: Cycle, event: Event,
          payload: dict[str, Any] | None = None, actor: str = "pm") -> dict[str, Any]:
    """상태기계에 이벤트를 넣고 결과를 반영한 뒤, 필요하면 실행기를 깨운다."""
    cv, sv = services.snapshot(db, cycle)
    t = next_step(cv, sv, event, payload)
    services.apply(db, cycle, t, actor=actor)
    if t.action is Action.RUN_STEP:
        runner.kick(cycle.id)
    return {"ok": True, "data": {"status": t.next_status, "step": t.next_step,
                                 "note": t.note, "action": t.action.value}}


def _v(x: Any) -> Any:
    """Enum 이든 문자열이든 값으로 만든다 (flush 전에는 문자열일 수 있다)."""
    return x.value if hasattr(x, "value") else x


def serialize(db: Session, cycle: Cycle) -> dict[str, Any]:
    pl = pipelines.load(cycle.pipeline)
    steps = db.scalars(
        select(Step).where(Step.cycle_id == cycle.id).order_by(Step.id)
    ).all()
    return {
        "id": cycle.id,
        "order_id": cycle.order_id,
        "pipeline": cycle.pipeline,
        "status": _v(cycle.status),
        "current_step": cycle.current_step,
        "mode": _v(cycle.mode),
        "attempt_no": cycle.attempt_no,
        "steps": [
            {
                "key": s.step_key,
                "name": s.name,
                "role": s.role,
                "status": _v(s.status),
                "attempt": s.attempt,
                "type": (pl.step(s.step_key).type if pl.step(s.step_key) else None),
                "parallel": list(pl.step(s.step_key).parallel) if pl.step(s.step_key) else [],
                "error": s.error,
            }
            for s in steps
        ],
    }


@router.post("")
async def create_cycle(body: CycleCreate, db: Session = Depends(get_db)):
    order = db.get(Order, body.order_id)
    if order is None:
        raise HTTPException(404, f"주문 {body.order_id} 을 찾을 수 없다")
    if body.pipeline and body.pipeline not in pipelines.available():
        raise HTTPException(400, f"그런 파이프라인이 없다: {body.pipeline}")
    c = services.create_cycle(db, order, body.pipeline, body.mode)
    return {"ok": True, "data": serialize(db, c)}


@router.post("/{cycle_id}/start")
async def start_cycle(cycle_id: int, db: Session = Depends(get_db)):
    return _fire(db, _get(db, cycle_id), Event.START)


@router.post("/{cycle_id}/pause")
async def pause_cycle(cycle_id: int, db: Session = Depends(get_db)):
    """graceful — 현재 step 을 끝까지 마친 뒤 정지한다 (인수 #16)."""
    return _fire(db, _get(db, cycle_id), Event.PAUSE)


@router.post("/{cycle_id}/abort")
async def abort_cycle(cycle_id: int, db: Session = Depends(get_db)):
    """현재 step 을 즉시 취소. 그 step 은 FAILED."""
    return _fire(db, _get(db, cycle_id), Event.ABORT)


@router.post("/{cycle_id}/resume")
async def resume_cycle(cycle_id: int, db: Session = Depends(get_db)):
    return _fire(db, _get(db, cycle_id), Event.RESUME)


@router.post("/{cycle_id}/step")
async def step_cycle(cycle_id: int, db: Session = Depends(get_db)):
    """한 단계만 실행하고 다시 PAUSED (수업 중 시연용, 인수 #18)."""
    return _fire(db, _get(db, cycle_id), Event.STEP)


@router.post("/{cycle_id}/rewind")
async def rewind_cycle(cycle_id: int, body: RewindRequest, db: Session = Depends(get_db)):
    """그 step 이후의 모든 산출물을 무효화하고 거기서 재개 (인수 #20)."""
    return _fire(db, _get(db, cycle_id), Event.REWIND, {"step_key": body.step_key})


@router.post("/{cycle_id}/reset")
async def reset_cycle(cycle_id: int, body: ResetRequest, db: Session = Depends(get_db)):
    """사이클을 처음부터. keep_specs 2종 (인수 #21, #22)."""
    return _fire(db, _get(db, cycle_id), Event.RESET, {"keep_specs": body.keep_specs})


@router.get("")
async def list_cycles(db: Session = Depends(get_db)):
    cs = db.scalars(select(Cycle).order_by(Cycle.id.desc())).all()
    return {"ok": True, "data": [serialize(db, c) for c in cs]}


@router.get("/{cycle_id}")
async def get_cycle(cycle_id: int, db: Session = Depends(get_db)):
    """상태 + step 타임라인."""
    return {"ok": True, "data": serialize(db, _get(db, cycle_id))}


@router.get("/{cycle_id}/timeline")
async def get_timeline(cycle_id: int, db: Session = Depends(get_db)):
    return {"ok": True, "data": serialize(db, _get(db, cycle_id))["steps"]}
