"""산출물 (BRIEF §3.5, §7).

모든 step 산출물은 아래 경로에만 쓴다. 재실행은 덮어쓴다.

    repo/runs/{cycle_id}/{step_id}/output/...
    repo/runs/{cycle_id}/{step_id}/report.md     ← 에이전트 완료 보고
    repo/project-001/...                          ← 확정 산출물(step DONE 시 승격)

step 을 두 번 돌려도 결과가 같아야 한다 (인수 #23). rewind/reset 의 전제다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Artifact, Step
from ..services import REPO_ROOT

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])
files_router = APIRouter(prefix="/api/files", tags=["artifacts"])


@files_router.get("", response_class=PlainTextResponse)
async def read_file(path: str = Query(..., description="repo/ 기준 상대 경로")):
    """노드가 참고 자료(SRS.md, schema.sql 등)를 읽어가는 주소.

    ⚠️ repo/ 밖으로는 절대 나갈 수 없다. 경로 탈출을 막는다.
    """
    target = (REPO_ROOT / path).resolve()
    try:
        target.relative_to(REPO_ROOT.resolve())
    except ValueError:
        raise HTTPException(400, "repo/ 밖의 경로는 읽을 수 없다")
    if not target.is_file():
        # 확정 산출물 쪽도 한 번 더 찾아본다
        alt = (REPO_ROOT / "project-001" / path).resolve()
        try:
            alt.relative_to(REPO_ROOT.resolve())
        except ValueError:
            raise HTTPException(400, "repo/ 밖의 경로는 읽을 수 없다")
        if not alt.is_file():
            raise HTTPException(404, f"그런 파일이 없다: {path}")
        target = alt
    return target.read_text(encoding="utf-8", errors="replace")


@router.get("")
async def list_artifacts(cycle: int | None = Query(None),
                         step: str | None = Query(None),
                         db: Session = Depends(get_db)):
    q = select(Artifact).order_by(Artifact.id.desc()).limit(200)
    if cycle:
        q = q.where(Artifact.cycle_id == cycle)
    arts = list(db.scalars(q).all())
    if step and cycle:
        keys = {s.id for s in db.scalars(
            select(Step).where(Step.cycle_id == cycle, Step.step_key == step)).all()}
        arts = [a for a in arts if a.step_id in keys]
    return {"ok": True, "data": [
        {"id": a.id, "cycle_id": a.cycle_id, "role": a.role, "path": a.path,
         "ts": a.ts.isoformat() if a.ts else None}
        for a in arts
    ]}


@router.get("/{artifact_id}/raw", response_class=PlainTextResponse)
async def get_artifact_raw(artifact_id: int, db: Session = Depends(get_db)):
    a = db.get(Artifact, artifact_id)
    if a is None:
        raise HTTPException(404, f"산출물 {artifact_id} 을 찾을 수 없다")
    p = REPO_ROOT / a.path
    if not p.exists():
        raise HTTPException(404, f"파일이 없다: {a.path}")
    return p.read_text(encoding="utf-8", errors="replace")
