"""주문 접수 (BRIEF §7, §9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import runner, services
from ..db import get_db
from ..models import Order, OrderKind, OrderSource
from ..orchestrator import Action, Event, next_step
from .cycles import serialize

router = APIRouter(prefix="/api/orders", tags=["orders"])


class OrderCreate(BaseModel):
    """web/order.html 이 제출하는 폼 (BRIEF §9 표)."""

    company: str                      # 회사/서비스 이름 (필수)
    industry: str = ""                # 업종
    purpose: str = ""                 # 목적 한 문장
    features: list[str] = []          # 로그인·게시판·상품목록·장바구니·결제(모의)·문의폼·관리자·검색
    due_date: str = ""                # 납기 희망일
    contact_name: str = ""            # 담당자 이름
    contact: str = ""                 # 연락처
    reference: str | None = None      # 참고 사이트 / 톤&매너
    budget: int | None = None         # 예산(가상 크레딧)
    kind: str = "new"                 # new | change | defect | security
    source: str = "order_site"
    auto_start: bool = True           # mode=auto 이면 즉시 start (BRIEF §9)


def _body(o: OrderCreate) -> str:
    lines = [f"목적: {o.purpose}", f"업종: {o.industry}",
             f"필요 기능: {', '.join(o.features) or '-'}",
             f"납기 희망일: {o.due_date}",
             f"담당자: {o.contact_name} ({o.contact})"]
    if o.reference:
        lines.append(f"참고: {o.reference}")
    if o.budget:
        lines.append(f"예산(가상 크레딧): {o.budget}")
    return "\n".join(lines)


@router.post("")
async def create_order(body: OrderCreate, db: Session = Depends(get_db)):
    """제출 시: Order 생성 → Cycle 생성(READY) → mode=auto 면 즉시 start
    → S1 sales 에게 발신 (BRIEF §9)."""
    order = Order(
        source=OrderSource(body.source),
        kind=OrderKind(body.kind),
        title=body.company,
        body=_body(body),
        requester=body.contact_name or None,
        status="open",
    )
    db.add(order)
    db.commit()
    services.audit(db, "order_site", "order.create", f"order:{order.id}",
                   {"kind": body.kind, "company": body.company})
    db.commit()

    cycle = services.create_cycle(db, order, None, "auto" if body.auto_start else "manual")

    if body.auto_start:
        cv, sv = services.snapshot(db, cycle)
        t = next_step(cv, sv, Event.START)
        services.apply(db, cycle, t, actor="order_site")
        if t.action is Action.RUN_STEP:
            runner.kick(cycle.id)

    return {"ok": True, "data": {"order_id": order.id, "cycle": serialize(db, cycle)}}


@router.get("")
async def list_orders(db: Session = Depends(get_db)):
    os_ = db.scalars(select(Order).order_by(Order.id.desc())).all()
    return {"ok": True, "data": [
        {"id": o.id, "title": o.title, "kind": o.kind.value,
         "source": o.source.value, "status": o.status,
         "requester": o.requester,
         "created_at": o.created_at.isoformat() if o.created_at else None}
        for o in os_
    ]}
