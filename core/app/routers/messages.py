"""A2A 미러링 수신 (BRIEF §5.3, §7).

**모든 메시지는 여기로 미러링한다. 노드 간 직접 통신도 마찬가지다.**
미러링하지 않은 메시지는 픽셀 오피스에 안 그려지고, 감사 로그에도 안 남는다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import services
from ..db import get_db
from ..models import Message

router = APIRouter(prefix="/api/messages", tags=["messages"])


class MessageMirror(BaseModel):
    from_role: str
    to_role: str
    kind: str = "mirror"               # request | response | reject | mirror
    cycle_id: int | None = None
    step_id: int | None = None
    summary: str | None = None
    payload_ref: str | None = None


@router.post("")
async def mirror_message(body: MessageMirror, db: Session = Depends(get_db)):
    """노드↔노드 직접 A2A 도 여기에 미러링돼야 한다 (인수 #9)."""
    services.mirror(db, body.cycle_id, body.from_role, body.to_role,
                    body.kind, body.summary or "", body.payload_ref)
    services.audit(db, body.from_role, "message.mirror",
                   f"{body.from_role}->{body.to_role}", {"kind": body.kind})
    db.commit()
    return {"ok": True, "data": {"mirrored": True}}


@router.get("")
async def list_messages(cycle: int | None = Query(None),
                        since: int | None = Query(None),
                        limit: int = Query(50),
                        db: Session = Depends(get_db)):
    q = select(Message).order_by(Message.id.desc()).limit(min(limit, 200))
    if cycle:
        q = q.where(Message.cycle_id == cycle)
    if since:
        q = q.where(Message.id > since)
    ms = list(db.scalars(q).all())[::-1]
    return {"ok": True, "data": [
        {"id": m.id, "from": m.from_role, "to": m.to_role, "kind": m.kind.value,
         "summary": m.summary, "cycle_id": m.cycle_id,
         "ts": m.ts.isoformat() if m.ts else None}
        for m in ms
    ]}
