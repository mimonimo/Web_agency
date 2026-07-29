"""티켓 · 게이트 반려 (BRIEF §7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import runner, services
from ..db import get_db
from ..models import Cycle, Ticket
from ..orchestrator import Action, Event, next_step

router = APIRouter(prefix="/api", tags=["tickets"])


class TicketCreate(BaseModel):
    cycle_id: int
    from_role: str
    to_role: str
    title: str
    dod: str | None = None
    parent_id: int | None = None


class TicketTransition(BaseModel):
    status: str
    reason: str | None = None


class GateReject(BaseModel):
    reason: str
    rewind_to: str | None = None
    cycle_id: int | None = None


@router.post("/tickets")
async def create_ticket(body: TicketCreate, db: Session = Depends(get_db)):
    t = Ticket(cycle_id=body.cycle_id, from_role=body.from_role, to_role=body.to_role,
               title=body.title, dod=body.dod, parent_id=body.parent_id, status="todo")
    db.add(t)
    services.audit(db, body.from_role, "ticket.create", f"cycle:{body.cycle_id}",
                   {"title": body.title})
    db.commit()
    return {"ok": True, "data": {"id": t.id}}


@router.get("/tickets")
async def list_tickets(cycle: int | None = None, db: Session = Depends(get_db)):
    q = select(Ticket).order_by(Ticket.id.desc())
    if cycle:
        q = q.where(Ticket.cycle_id == cycle)
    ts = db.scalars(q).all()
    return {"ok": True, "data": [
        {"id": t.id, "title": t.title, "from": t.from_role, "to": t.to_role,
         "status": t.status, "reason": t.reason, "dod": t.dod,
         "cycle_id": t.cycle_id, "parent_id": t.parent_id}
        for t in ts
    ]}


class TicketPatch(BaseModel):
    """티켓을 사람이 손보는 경로 — 담당·제목·완료조건·사유를 고친다."""
    to_role: str | None = None
    title: str | None = None
    dod: str | None = None
    reason: str | None = None


@router.patch("/tickets/{ticket_id}")
async def patch_ticket(ticket_id: int, body: TicketPatch,
                       db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    if t is None:
        raise HTTPException(404, f"티켓 {ticket_id} 을 찾을 수 없다")
    changed = {}
    for f in ("to_role", "title", "dod", "reason"):
        v = getattr(body, f)
        if v is not None and str(v).strip() != "":
            setattr(t, f, v)
            changed[f] = v
    if not changed:
        raise HTTPException(400, "바꿀 내용이 없다")
    services.audit(db, "pm", "ticket.patch", f"ticket:{ticket_id}", changed)
    db.commit()
    return {"ok": True, "data": {"id": t.id, **changed}}


@router.delete("/tickets/{ticket_id}")
async def delete_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """잘못 만든 티켓을 지운다. 지운 사실은 감사 로그에 남는다."""
    t = db.get(Ticket, ticket_id)
    if t is None:
        raise HTTPException(404, f"티켓 {ticket_id} 을 찾을 수 없다")
    services.audit(db, "pm", "ticket.delete", f"ticket:{ticket_id}",
                   {"title": t.title, "status": t.status})
    db.delete(t)
    db.commit()
    return {"ok": True, "data": {"id": ticket_id, "deleted": True}}


@router.post("/tickets/{ticket_id}/transition")
async def transition_ticket(ticket_id: int, body: TicketTransition,
                            db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    if t is None:
        raise HTTPException(404, f"티켓 {ticket_id} 을 찾을 수 없다")
    t.status = body.status
    if body.reason:
        t.reason = body.reason
    services.audit(db, "pm", "ticket.transition", f"ticket:{ticket_id}",
                   {"status": body.status})
    db.commit()
    return {"ok": True, "data": {"id": t.id, "status": t.status}}


class GateApprove(BaseModel):
    reason: str = ""
    cycle_id: int | None = None


@router.post("/gates/{step}/approve")
async def approve_gate(step: str, body: GateApprove, db: Session = Depends(get_db)):
    """게이트를 사람이 통과시킨다 (강사 강제 통과 포함).

    ⚠️ 사유를 남긴다. 왜 통과시켰는지 없이 통과한 게이트는 나중에 아무도 설명 못 한다.
    """
    cycle = (db.get(Cycle, body.cycle_id) if body.cycle_id
             else db.scalar(select(Cycle).order_by(Cycle.id.desc())))
    if cycle is None:
        raise HTTPException(404, "사이클이 없다")
    # 사람 게이트에서 BLOCKED 인 경우 RESUME 이 그 게이트를 건너뛴다 (orchestrator).
    cv, sv = services.snapshot(db, cycle)
    t = next_step(cv, sv, Event.RESUME, {"step": step})
    if t.action is Action.NOOP:
        raise HTTPException(400, t.note)
    services.apply(db, cycle, t, actor="pm")
    services.audit(db, "pm", "gate.approve", f"cycle:{cycle.id}:{step}",
                   {"reason": body.reason or "(사유 없음)"})
    db.commit()
    if t.action is Action.RUN_STEP:
        runner.kick(cycle.id)
    return {"ok": True, "data": {"status": t.next_status, "step": t.next_step,
                                 "note": t.note}}


@router.post("/gates/{step}/reject")
async def reject_gate(step: str, body: GateReject, db: Session = Depends(get_db)):
    """★ 반려 → rewind. 세 반려(QA·보안·검수)를 가르치는 장치다 (BRIEF §14).

    rewind_to 로 지정된 step 으로 되감고 재작업 티켓을 자동 생성한다 (인수 #19).
    """
    cycle = (db.get(Cycle, body.cycle_id) if body.cycle_id
             else db.scalar(select(Cycle).order_by(Cycle.id.desc())))
    if cycle is None:
        raise HTTPException(404, "사이클이 없다")
    cv, sv = services.snapshot(db, cycle)
    t = next_step(cv, sv, Event.GATE_REJECT,
                  {"step": step, "reason": body.reason, "rewind_to": body.rewind_to})
    if t.action is Action.NOOP:
        raise HTTPException(400, t.note)
    services.apply(db, cycle, t, actor=(sv[0].role if sv else "qa"))
    if t.action is Action.INVALIDATE_FROM:
        runner.kick(cycle.id)
    return {"ok": True, "data": {"status": t.next_status, "step": t.next_step,
                                 "note": t.note}}
