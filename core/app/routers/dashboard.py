"""픽셀 오피스가 5초마다 부르는 단일 엔드포인트 (BRIEF §7).

**한 번에 다 준다.** 오피스가 여러 번 호출하지 않게 하는 것이 이 라우터의 존재 이유다.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import pipelines, services
from ..db import get_db
from ..models import (
    AgentSpec,
    Artifact,
    Cycle,
    Message,
    Node,
    Order,
    ROLE_DISPLAY,
    ROLES,
    SpecStatus,
    Step,
    Ticket,
)
from ..services import as_utc, now

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

HEARTBEAT_TIMEOUT = 90


@router.get("")
async def dashboard(cycle: int | None = Query(None), db: Session = Depends(get_db)):
    """반환 형태는 BRIEF §7 의 예시 JSON 을 따른다."""
    c = db.get(Cycle, cycle) if cycle else db.scalar(
        select(Cycle).order_by(Cycle.id.desc()))

    data: dict[str, Any] = {
        "cycle": None, "steps": [], "nodes": [], "specs": {},
        "messages": [], "tickets": {}, "orders": [], "roles": [],
    }

    # ── 노드 (책상 11개) ──────────────────────────────────────────────
    nodes = {n.role: n for n in db.scalars(select(Node)).all()}
    busy_role: dict[str, str] = {}
    if c:
        pl = pipelines.load(c.pipeline)
        cur = pl.step(c.current_step) if c.current_step else None
        if cur and c.status.value == "RUNNING":
            for r in cur.roles:
                busy_role[r] = cur.id

    for role in ROLES:
        n = nodes.get(role)
        stale = (n is None or n.last_heartbeat is None
                 or (now() - as_utc(n.last_heartbeat)) > timedelta(seconds=HEARTBEAT_TIMEOUT))
        data["nodes"].append({
            "role": role,
            "display_name": ROLE_DISPLAY.get(role, role),
            "status": ("down" if stale else "up"),
            "dgx_host": n.dgx_host if n else None,
            "a2a_url": n.a2a_url if n else None,
            "busy": role in busy_role,
            "current_step": busy_role.get(role),
        })
    data["roles"] = [{"role": r, "display": ROLE_DISPLAY[r]} for r in ROLES]

    # ── 주문 ─────────────────────────────────────────────────────────
    data["orders"] = [
        {"id": o.id, "title": o.title, "kind": o.kind.value, "status": o.status,
         "created_at": o.created_at.isoformat() if o.created_at else None}
        for o in db.scalars(select(Order).order_by(Order.id.desc()).limit(10)).all()
    ]

    if c is None:
        return {"ok": True, "data": data}

    # ── 사이클 · 단계 ────────────────────────────────────────────────
    pl = pipelines.load(c.pipeline)
    steps = db.scalars(
        select(Step).where(Step.cycle_id == c.id).order_by(Step.id)).all()
    data["cycle"] = {
        "id": c.id, "order_id": c.order_id, "pipeline": c.pipeline,
        "status": c.status.value, "current_step": c.current_step,
        "mode": c.mode.value, "attempt_no": c.attempt_no,
    }
    data["steps"] = [
        {"key": s.step_key, "name": s.name, "role": s.role,
         "status": s.status.value, "attempt": s.attempt, "error": s.error,
         "type": (pl.step(s.step_key).type if pl.step(s.step_key) else None),
         "parallel": list(pl.step(s.step_key).parallel) if pl.step(s.step_key) else [],
         "rewind_to": (pl.step(s.step_key).on_reject_rewind_to
                       if pl.step(s.step_key) else None)}
        for s in steps
    ]

    # ── AGENT.md 커스터마이징 진행도 (7 / 11) ────────────────────────
    services.scan_customized(db, c)
    specs = db.scalars(select(AgentSpec).where(AgentSpec.cycle_id == c.id)).all()
    data["specs"] = {
        "customized": sum(1 for s in specs if s.status == SpecStatus.CUSTOMIZED),
        "total": len(specs),
        "pending": [s.role for s in specs if s.status != SpecStatus.CUSTOMIZED],
        "by_role": {s.role: s.status.value for s in specs},
    }

    # ── 메시지 (봉투 애니메이션의 원천) ──────────────────────────────
    ms = list(db.scalars(
        select(Message).where(Message.cycle_id == c.id)
        .order_by(Message.id.desc()).limit(30)).all())[::-1]
    data["messages"] = [
        {"id": m.id, "from": m.from_role, "to": m.to_role, "kind": m.kind.value,
         "summary": m.summary, "ts": m.ts.isoformat() if m.ts else None}
        for m in ms
    ]

    # ── 티켓 집계 ────────────────────────────────────────────────────
    counts = dict(db.execute(
        select(Ticket.status, func.count()).where(Ticket.cycle_id == c.id)
        .group_by(Ticket.status)).all())
    data["tickets"] = {
        "todo": counts.get("todo", 0), "doing": counts.get("doing", 0),
        "done": counts.get("done", 0), "rejected": counts.get("rejected", 0),
        "list": [
            {"id": t.id, "title": t.title, "from": t.from_role, "to": t.to_role,
             "status": t.status, "reason": t.reason}
            for t in db.scalars(
                select(Ticket).where(Ticket.cycle_id == c.id)
                .order_by(Ticket.id.desc()).limit(10)).all()
        ],
    }

    data["artifacts"] = db.scalar(
        select(func.count()).select_from(Artifact).where(Artifact.cycle_id == c.id)) or 0

    return {"ok": True, "data": data}
