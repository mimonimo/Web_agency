"""산출물 (BRIEF §3.5, §7).

모든 step 산출물은 아래 경로에만 쓴다. 재실행은 덮어쓴다.

    repo/runs/{cycle_id}/{step_id}/output/...
    repo/runs/{cycle_id}/{step_id}/report.md     ← 에이전트 완료 보고
    repo/project-001/...                          ← 확정 산출물(step DONE 시 승격)

step 을 두 번 돌려도 결과가 같아야 한다 (인수 #23). rewind/reset 의 전제다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])

_PHASE = "Phase 3a"


@router.get("")
async def list_artifacts(cycle: int | None = Query(None), step: str | None = Query(None)):
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")


@router.get("/{artifact_id}/raw")
async def get_artifact_raw(artifact_id: int):
    raise HTTPException(501, f"{_PHASE} 에서 구현한다")
