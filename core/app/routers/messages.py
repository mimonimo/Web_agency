"""A2A 미러링 수신 (BRIEF §5.3, §7).

**모든 메시지는 여기로 미러링한다. 노드 간 직접 통신도 마찬가지다.**
미러링하지 않은 메시지는 픽셀 오피스에 안 그려지고, 감사 로그에도 안 남는다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/messages", tags=["messages"])

_PHASE = "Phase 2"


class MessageMirror(BaseModel):
    from_role: str
    to_role: str
    kind: str                          # request | response | reject | mirror
    cycle_id: int | None = None
    step_id: int | None = None
    summary: str | None = None
    payload_ref: str | None = None


@router.post("")
async def mirror_message(body: MessageMirror):
    """노드↔노드 직접 A2A 도 여기에 미러링돼야 한다 (인수 #9)."""
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.get("")
async def list_messages(cycle: int | None = Query(None), since: str | None = Query(None)):
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")
