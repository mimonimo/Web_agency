"""AGENT.md 생명주기 (BRIEF §4, §7).

이 수업의 교육 목표가 여기 걸려 있다. 학생이 배우는 것은 코드가 아니라
"AGENT.md 한 줄이 결과를 어떻게 바꾸는가" 다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/api/specs", tags=["specs"])

_PHASE = "Phase 3b"


@router.get("")
async def list_specs(cycle: int = Query(..., description="사이클 ID")):
    """11개 상태 목록. 대시보드의 `7 / 11 완료` 카운터 근거 (인수 #14)."""
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.get("/{role}/raw", response_class=PlainTextResponse)
async def get_spec_raw(role: str):
    """★ 노드가 읽어가는 주소 (BRIEF §4.3 의 spec_url).

    노드의 A2A 어댑터가 이걸 받아 AGENT.md 를 먼저 읽힌 뒤 작업 지시를 전달한다.
    """
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.post("/{role}/customized")
async def mark_customized(role: str):
    """수동 표시 — repo 폴링이 실패했을 때의 대비책."""
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.get("/{role}/diff", response_class=PlainTextResponse)
async def get_spec_diff(role: str, cycle: int = Query(...)):
    """학생이 무엇을 추가했는지 — 오늘의 평가 데이터다 (BRIEF §4.2).

    회고 시간에 이걸 띄운다. `specs/history/{role}/{cycle}.diff`
    """
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")
