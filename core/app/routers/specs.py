"""AGENT.md 생명주기 (BRIEF §4, §7).

이 수업의 교육 목표가 여기 걸려 있다. 학생이 배우는 것은 코드가 아니라
"AGENT.md 한 줄이 결과를 어떻게 바꾸는가" 다.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
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


@router.put("/{role}/raw")
async def put_spec_raw(role: str, body: str = Body(..., media_type="text/plain"),
                       db: Session = Depends(get_db)):
    """★ 학생이 자기 AGENT.md 를 고쳐 저장하는 주소.

    web/edit.html 이 이걸 부른다. 저장하면 HQ 가 곧바로 스캔해
    `status: customized` 로 바꾸고, 11개가 다 차면 사이클이 자동 재개된다 (인수 #14·#15).

    front-matter 는 HQ 가 관리한다 — 학생이 지웠거나 고쳤어도 원래 것으로 되돌린다.
    """
    from ..models import ROLES
    if role not in ROLES:
        raise HTTPException(404, f"그런 역할이 없다: {role}")

    p = services.spec_path(role)
    if not p.exists():
        raise HTTPException(404, f"{role} 의 AGENT.md 가 아직 없다 (S2 에서 생성된다)")
    if not body or not body.strip():
        raise HTTPException(400, "빈 내용은 저장할 수 없다")

    old = p.read_text(encoding="utf-8")
    fm = ""
    if old.startswith("---"):
        parts = old.split("---", 2)
        if len(parts) > 2:
            fm = "---" + parts[1] + "---\n\n"

    new_body = body
    if new_body.lstrip().startswith("---"):      # 학생이 머리말째 붙여넣었으면 떼어낸다
        parts = new_body.split("---", 2)
        new_body = parts[2] if len(parts) > 2 else new_body

    p.write_text(fm + new_body.strip() + "\n", encoding="utf-8")
    services.audit(db, role, "spec.edit", f"specs:{role}", {"bytes": len(new_body)})
    db.commit()

    c = _latest_cycle(db)
    if c is None:
        return {"ok": True, "data": {"saved": True}}
    services.scan_customized(db, c)
    r = await _maybe_resume(db, c)
    r["data"]["saved"] = True
    return r


@router.get("/{role}/baseline", response_class=PlainTextResponse)
async def get_baseline(role: str):
    """기준선 — 사람(Claude Code)이 미리 써 둔 역할 지시문 원본.

    학생 화면에서 "원래 뭐라고 적혀 있었나" 를 볼 수 있어야 한다.
    읽기 전용이다. 이 파일은 git 이 추적하고, 수업 중에는 바뀌지 않는다.
    """
    from ..models import ROLES
    if role not in ROLES:
        raise HTTPException(404, f"그런 역할이 없다: {role}")
    txt = services.baseline_spec(role)
    if not txt:
        raise HTTPException(404, f"{role} 의 기준선이 없다 (agents/{role}/AGENT.md)")
    return txt


@router.get("/{role}/draft", response_class=PlainTextResponse)
async def get_draft(role: str, cycle: int | None = Query(None),
                    db: Session = Depends(get_db)):
    """이번 사이클의 **초안** — 학생이 고치기 전 상태. 비교용."""
    from ..models import ROLES
    if role not in ROLES:
        raise HTTPException(404, f"그런 역할이 없다: {role}")
    p = REPO_ROOT / services.PROJECT_ID / ".drafts" / role / "AGENT.md"
    if not p.exists():
        raise HTTPException(404, f"{role} 의 초안이 아직 없다")
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
