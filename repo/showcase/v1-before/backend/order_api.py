"""
AGORA Web 백엔드 구현 - 밀밭제과 예약 주문 API

이 모듈은 FastAPI 를 이용해 간단한 인메모리 주문 시스템을 제공합니다.
요구사항:
- POST /orders   : 새 주문 생성
- GET  /orders/{order_id} : 특정 주문 조회
- DELETE /orders/{order_id}: 주문 취소
- GET  /orders   : 전체 주문 목록

응답 형식은 프로젝트 전역 규칙에 맞춰서
    성공: {"ok": true, "data": {...}}
    실패: {"ok": false, "error": "메시지"}
을 반환하며 HTTP 상태 코드는 200/400/401/403/404 를 사용합니다.
"""

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict
import uuid

app = FastAPI(title="AGORA 밀밭제과 예약 주문 API")

class OrderCreate(BaseModel):
    customer_name: str = Field(..., example="홍길동")
    pastry_type: str = Field(..., example="밀밭 쿠키")
    quantity: int = Field(..., ge=1, example=2)
    reservation_time: str = Field(..., example="2026-08-01T14:30")  # ISO8601 문자열

class Order(OrderCreate):
    order_id: str

# 인메모리 저장소 (프로세스가 살아있는 동안만 유지)
_orders: Dict[str, Order] = {}

def _response_ok(data):
    return {"ok": True, "data": data}

def _response_error(message):
    return {"ok": False, "error": message}

@app.post("/orders", status_code=status.HTTP_201_CREATED)
async def create_order(order: OrderCreate):
    order_id = str(uuid.uuid4())
    new_order = Order(**order.dict(), order_id=order_id)
    orders[order_id] = new_order
    return _response_ok(new_order.dict())

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    if order_id not in orders:
        raise HTTPException(status_code=404, detail=_response_error("주문을 찾을 수 없습니다."))
    return _response_ok(orders[order_id].dict())

@app.delete("/orders/{order_id}")
async def delete_order(order_id: str):
    if order_id not in orders:
        raise HTTPException(status_code=404, detail=_response_error("주문을 찾을 수 없습니다."))
    removed = orders.pop(order_id)
    return _response_ok({"deleted": True, "order_id": removed.order_id})

@app.get("/orders")
async def list_orders():
    all_orders = [o.dict() for o in orders.values()]
    return _response_ok(all_orders)

# Note: 실제 서비스에서는 데이터베이스와 인증/인가 로직이 필요합니다.
