"""노드 등록·하트비트 (BRIEF §7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/nodes", tags=["nodes"])

_PHASE = "Phase 2"


class NodeRegister(BaseModel):
    role: str
    a2a_url: str
    card: dict[str, Any] | None = None
    dgx_host: str | None = None


@router.post("/register")
async def register_node(body: NodeRegister):
    """노드 11개가 여기로 등록한다 (인수 #5)."""
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.post("/{role}/heartbeat")
async def heartbeat(role: str):
    """하트비트 중단 90초 후 status=down 으로 자동 전환된다 (인수 #7)."""
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.get("")
async def list_nodes():
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")
