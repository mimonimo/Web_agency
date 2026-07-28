"""티켓 · 게이트 반려 (BRIEF §7)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["tickets"])

_PHASE = "Phase 3c"


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
    rewind_to: str


@router.post("/tickets")
async def create_ticket(body: TicketCreate):
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.post("/tickets/{ticket_id}/transition")
async def transition_ticket(ticket_id: int, body: TicketTransition):
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.post("/gates/{step}/reject")
async def reject_gate(step: str, body: GateReject):
    """★ 반려 → rewind. 세 반려(QA·보안·검수)를 가르치는 장치다 (BRIEF §14).

    rewind_to 로 지정된 step 으로 되감고 재작업 티켓을 자동 생성한다 (인수 #19).
    """
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")
