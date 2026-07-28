"""픽셀 오피스가 5초마다 부르는 단일 엔드포인트 (BRIEF §7).

**한 번에 다 준다.** 오피스가 여러 번 호출하지 않게 하는 것이 이 라우터의 존재 이유다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_PHASE = "Phase 4"


@router.get("")
async def dashboard():
    """반환 형태는 BRIEF §7 의 예시 JSON 을 그대로 따른다:

        {"cycle": {...}, "steps": [...], "nodes": [...],
         "specs": {"customized": 7, "total": 11, "pending": [...]},
         "messages": [...], "tickets": {...}, "orders": [...]}
    """
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")
