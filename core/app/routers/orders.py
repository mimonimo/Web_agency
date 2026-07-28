"""주문 접수 (BRIEF §7, §9)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/orders", tags=["orders"])

_PHASE = "Phase 3a"


class OrderCreate(BaseModel):
    """web/order.html 이 제출하는 폼 (BRIEF §9 표)."""

    company: str                      # 회사/서비스 이름 (필수)
    industry: str                     # 업종 (필수)
    purpose: str                      # 목적 한 문장 (필수)
    features: list[str]               # 로그인·게시판·상품목록·장바구니·결제(모의)·문의폼·관리자·검색
    due_date: str                     # 납기 희망일 (필수)
    contact_name: str                 # 담당자 이름 (필수)
    contact: str                      # 연락처 (필수)
    reference: str | None = None      # 참고 사이트 / 톤&매너
    budget: int | None = None         # 예산(가상 크레딧)
    kind: str = "new"                 # new | change | defect | security


@router.post("")
async def create_order(body: OrderCreate):
    """제출 시: Order 생성 → Cycle 생성(READY) → mode=auto 면 즉시 start
    → S1 sales 에게 A2A 발신 (BRIEF §9)."""
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.get("")
async def list_orders():
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")
