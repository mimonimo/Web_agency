"""노드 등록·하트비트 (BRIEF §7)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth, services
from ..db import get_db
from ..models import Node, NodeStatus, ROLE_DISPLAY
from ..services import as_utc, now

router = APIRouter(prefix="/api/nodes", tags=["nodes"])

HEARTBEAT_TIMEOUT = 90   # 초. 이 시간 넘게 소식 없으면 down (인수 #7)


class NodeRegister(BaseModel):
    role: str
    a2a_url: str
    card: dict[str, Any] | None = None
    dgx_host: str | None = None


def _stale(node: Node) -> bool:
    if node.last_heartbeat is None:
        return True
    return (now() - as_utc(node.last_heartbeat)) > timedelta(seconds=HEARTBEAT_TIMEOUT)


@router.post("/register")
async def register_node(body: NodeRegister, db: Session = Depends(get_db),
                        x_agora_token: str | None = Header(None, alias="X-Agora-Token")):
    """노드 11개가 여기로 등록한다 (인수 #5). 잘못된 토큰이면 401 (인수 #10)."""
    auth.verify(body.role, x_agora_token)
    node = db.scalar(select(Node).where(Node.role == body.role))
    if node is None:
        node = Node(role=body.role, display_name=ROLE_DISPLAY.get(body.role, body.role),
                    a2a_url=body.a2a_url, dgx_host=body.dgx_host)
        db.add(node)
    else:
        node.a2a_url = body.a2a_url
        node.dgx_host = body.dgx_host or node.dgx_host
    node.card = body.card
    node.status = NodeStatus.UP
    node.last_heartbeat = now()
    services.audit(db, body.role, "node.register", f"node:{body.role}",
                   {"a2a_url": body.a2a_url})
    db.commit()
    return {"ok": True, "data": {"role": node.role, "status": node.status.value}}


@router.post("/{role}/heartbeat")
async def heartbeat(role: str, db: Session = Depends(get_db),
                    x_agora_token: str | None = Header(None, alias="X-Agora-Token")):
    """하트비트 중단 90초 후 status=down 으로 자동 전환된다 (인수 #7)."""
    auth.verify(role, x_agora_token)
    node = db.scalar(select(Node).where(Node.role == role))
    if node is None:
        raise HTTPException(404, f"등록되지 않은 노드다: {role}")
    node.last_heartbeat = now()
    node.status = NodeStatus.UP
    db.commit()
    return {"ok": True, "data": {"role": role, "status": "up"}}


@router.get("")
async def list_nodes(db: Session = Depends(get_db)):
    nodes = db.scalars(select(Node).order_by(Node.id)).all()
    changed = False
    for n in nodes:
        want = NodeStatus.DOWN if _stale(n) else NodeStatus.UP
        if n.status != want:
            n.status = want
            changed = True
    if changed:
        db.commit()
    return {"ok": True, "data": [
        {"role": n.role, "display_name": n.display_name, "a2a_url": n.a2a_url,
         "status": n.status.value, "dgx_host": n.dgx_host,
         "last_heartbeat": n.last_heartbeat.isoformat() if n.last_heartbeat else None}
        for n in nodes
    ]}


@router.get("/{role}/token")
async def get_token(role: str):
    """노드가 자기 토큰을 받아가는 주소.

    ⚠️ 교실 L2 안에서만 돈다는 전제다. 외부에 노출된 대역이면 이 엔드포인트를 막아야 한다.
    """
    from ..models import ROLES
    if role not in ROLES:
        raise HTTPException(404, f"그런 역할이 없다: {role}")
    return {"ok": True, "data": {"role": role, "token": auth.token_for(role)}}
