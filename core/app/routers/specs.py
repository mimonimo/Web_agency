"""AGENT.md 생명주기 (BRIEF §4, §7).

이 수업의 교육 목표가 여기 걸려 있다. 학생이 배우는 것은 코드가 아니라
"AGENT.md 한 줄이 결과를 어떻게 바꾸는가" 다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import runner, services
from ..db import get_db
from ..models import AgentSpec, Cycle, SpecStatus
from ..orchestrator import Action, Event, next_step
from ..services import REPO_ROOT

router = APIRouter(prefix="/api/specs", tags=["specs"])


def _latest_cycle(db: Session) -> Cycle | None:
    return db.scalar(select(Cycle).order_by(Cycle.id.desc()))


@router.get("")
async def list_specs(cycle: int | None = Query(None), db: Session = Depends(get_db)):
    """11개 상태 목록. 대시보드의 `7 / 11 완료` 카운터 근거 (인수 #14)."""
    c = db.get(Cycle, cycle) if cycle else _latest_cycle(db)
    if c is None:
        return {"ok": True, "data": {"customized": 0, "total": 0, "specs": []}}
    services.scan_customized(db, c)
    specs = db.scalars(select(AgentSpec).where(AgentSpec.cycle_id == c.id)).all()
    prog = services.spec_progress(db, c)
    return {"ok": True, "data": {
        **prog,
        "cycle": c.id,
        "specs": [{"role": s.role, "status": s.status.value, "path": s.path,
                   "customized_at": s.customized_at.isoformat() if s.customized_at else None}
                  for s in specs],
    }}


@router.get("/{role}/raw", response_class=PlainTextResponse)
async def get_spec_raw(role: str, cycle: int | None = Query(None),
                       db: Session = Depends(get_db)):
    """★ 노드가 읽어가는 주소 (BRIEF §4.3 의 spec_url).

    노드의 A2A 어댑터가 이걸 받아 AGENT.md 를 먼저 읽힌 뒤 작업 지시를 전달한다.
    """
    p = services.spec_path(role)
    if not p.exists():
        raise HTTPException(404, f"{role} 의 AGENT.md 가 아직 없다 (S2 에서 생성된다)")
    return p.read_text(encoding="utf-8")


@router.post("/{role}/customized")
async def mark_customized(role: str, cycle: int | None = Query(None),
                          db: Session = Depends(get_db)):
    """수동 표시 — repo 폴링이 실패했을 때의 대비책."""
    c = db.get(Cycle, cycle) if cycle else _latest_cycle(db)
    if c is None:
        raise HTTPException(404, "사이클이 없다")
    spec = db.scalar(select(AgentSpec).where(
        AgentSpec.cycle_id == c.id, AgentSpec.role == role))
    if spec is None:
        raise HTTPException(404, f"{role} 스펙이 없다")
    spec.status = SpecStatus.CUSTOMIZED
    spec.customized_at = services.now()
    services.audit(db, role, "spec.customized.manual", f"cycle:{c.id}:{role}")
    db.commit()
    return await _maybe_resume(db, c)


async def _maybe_resume(db: Session, c: Cycle) -> dict:
    """11개가 전부 customized 되면 자동으로 RUNNING 재개 (인수 #15)."""
    prog = services.spec_progress(db, c)
    resumed = False
    if prog["total"] and prog["customized"] >= prog["total"]:
        cv, sv = services.snapshot(db, c)
        t = next_step(cv, sv, Event.SPECS_ALL_CUSTOMIZED)
        if t.action is not Action.NOOP:
            services.apply(db, c, t, actor="hq")
            if t.action is Action.RUN_STEP:
                runner.kick(c.id)
            resumed = True
    return {"ok": True, "data": {**prog, "resumed": resumed}}


@router.post("/scan")
async def scan(cycle: int | None = Query(None), db: Session = Depends(get_db)):
    """repo/ 를 훑어 바뀐 AGENT.md 를 찾는다. HQ 가 주기적으로 부른다 (BRIEF §4.2)."""
    c = db.get(Cycle, cycle) if cycle else _latest_cycle(db)
    if c is None:
        raise HTTPException(404, "사이클이 없다")
    changed = services.scan_customized(db, c)
    r = await _maybe_resume(db, c)
    r["data"]["changed"] = changed
    return r


@router.get("/{role}/diff", response_class=PlainTextResponse)
async def get_spec_diff(role: str, cycle: int | None = Query(None),
                        db: Session = Depends(get_db)):
    """학생이 무엇을 추가했는지 — 오늘의 평가 데이터다 (BRIEF §4.2).

    회고 시간에 이걸 띄운다.
    """
    c = db.get(Cycle, cycle) if cycle else _latest_cycle(db)
    if c is None:
        raise HTTPException(404, "사이클이 없다")
    spec = db.scalar(select(AgentSpec).where(
        AgentSpec.cycle_id == c.id, AgentSpec.role == role))
    if spec is None or not spec.diff_ref:
        raise HTTPException(404, f"{role} 의 diff 가 아직 없다")
    p = REPO_ROOT / spec.diff_ref
    return p.read_text(encoding="utf-8") if p.exists() else ""
