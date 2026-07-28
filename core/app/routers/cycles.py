"""사이클 제어 — ★ 핵심 (BRIEF §7).

이 라우터가 수업의 조작 패널이다. pause / resume / reset(keep_specs=true) 는
절대 자르면 안 되는 기능이다 (BRIEF §14).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/cycles", tags=["cycles"])

_PHASE = "Phase 3a"


class CycleCreate(BaseModel):
    order_id: int
    pipeline: str = "web_delivery"


class RewindRequest(BaseModel):
    step_key: str


class ResetRequest(BaseModel):
    # ⚠️ 기본값은 반드시 True. 학생이 고친 AGENT.md 를 리셋 한 번에 날리면
    #    수업이 망한다 (BRIEF §3.4). False 는 UI 에서 확인 대화를 한 번 더 받는다.
    keep_specs: bool = Field(default=True)


@router.post("")
async def create_cycle(body: CycleCreate):
    """Cycle 생성 → READY."""
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.post("/{cycle_id}/start")
async def start_cycle(cycle_id: int):
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.post("/{cycle_id}/pause")
async def pause_cycle(cycle_id: int):
    """graceful — 현재 step 을 끝까지 마친 뒤 정지한다 (인수 #16)."""
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.post("/{cycle_id}/abort")
async def abort_cycle(cycle_id: int):
    """현재 step 을 즉시 취소. 그 step 은 FAILED."""
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.post("/{cycle_id}/resume")
async def resume_cycle(cycle_id: int):
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.post("/{cycle_id}/step")
async def step_cycle(cycle_id: int):
    """한 단계만 실행하고 다시 PAUSED (수업 중 시연용, 인수 #18)."""
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.post("/{cycle_id}/rewind")
async def rewind_cycle(cycle_id: int, body: RewindRequest):
    """그 step 이후의 모든 산출물을 무효화하고 거기서 재개 (인수 #20)."""
    raise HTTPException(501, "Phase 3c 에서 구현한다")


@router.post("/{cycle_id}/reset")
async def reset_cycle(cycle_id: int, body: ResetRequest):
    """사이클을 처음부터. keep_specs 2종 (인수 #21, #22)."""
    raise HTTPException(501, "Phase 3b 에서 구현한다")


@router.get("/{cycle_id}")
async def get_cycle(cycle_id: int):
    """상태 + step 타임라인."""
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.get("/{cycle_id}/timeline")
async def get_timeline(cycle_id: int):
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")
