"""에이전트 상세 · 재요청.

픽셀 오피스에서 책상을 누르면 그 에이전트가 **지금 무엇을 하고 있는지**,
**무엇을 만들었는지** 보이고, 거기서 바로 다시 시킬 수 있어야 한다.

BRIEF §8.4 주의: 개인 가동률 같은 지표는 넣지 않는다. 여기서 보여주는 것은
"이 사람이 얼마나 일했나" 가 아니라 "이 역할의 작업이 어디까지 갔나" 다.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import checks, directives, pipelines, runner, services
from .. import roles as roles_catalog
from ..db import get_db
from ..models import (
    AgentSpec,
    Artifact,
    Cycle,
    Message,
    Node,
    ROLE_DISPLAY,
    ROLES,
    Step,
    StepStatus,
)
from ..orchestrator import Action, Event, next_step
from ..services import REPO_ROOT, as_utc, now

router = APIRouter(prefix="/api/agents", tags=["agents"])

HEARTBEAT_TIMEOUT = 90


def _latest_cycle(db: Session) -> Cycle | None:
    return db.scalar(select(Cycle).order_by(Cycle.id.desc()))


def _v(x: Any) -> Any:
    return x.value if hasattr(x, "value") else x


@router.get("")
async def list_agents(db: Session = Depends(get_db)):
    """11개 역할 요약 + 역할 카탈로그 + 사람이 넣은 지시 개수.

    화면이 "이 역할은 무엇을 하는 사람인가" 를 물어보지 않고도 보여줄 수 있어야 한다.
    """
    notes = directives.summary()
    return {"ok": True, "data": [
        {
            "role": r,
            "display_name": ROLE_DISPLAY[r],
            "mission": roles_catalog.mission(r),
            "node": roles_catalog.get(r).get("node"),
            "steps": roles_catalog.get(r).get("steps") or [],
            "owns": roles_catalog.owns(r),
            "notes": notes.get(r, 0),
        }
        for r in ROLES
    ], "meta": {"global_notes": notes.get("_global", 0)}}


@router.get("/{role}/catalog")
async def role_catalog(role: str):
    """역할의 목표·완료조건·금지·인계. `roles.yaml` 이 원본이다."""
    if role not in ROLES:
        raise HTTPException(404, f"그런 역할이 없다: {role}")
    r = roles_catalog.get(role)
    return {"ok": True, "data": {
        "role": role, "display_name": ROLE_DISPLAY[role], **r,
        "baseline_path": f"agents/{role}/AGENT.md",
        "spec_path": str(services.spec_path(role).relative_to(REPO_ROOT)),
        "notes_path": str(directives.role_path(role).relative_to(REPO_ROOT)),
    }}


# ── 사람이 중간에 끼워 넣는 지시 ──────────────────────────────────────
#   "디자인 파트에 지시를 하나 추가하고 싶다" 를 실제로 가능하게 하는 부분이다.
#   저장하면 그 역할이 **다음에 일할 때** 프롬프트 맨 뒤에 붙는다.

class NoteIn(BaseModel):
    text: str


@router.get("/{role}/notes")
async def get_notes(role: str):
    if role not in ROLES:
        raise HTTPException(404, f"그런 역할이 없다: {role}")
    return {"ok": True, "data": {
        "role": role,
        "text": directives.read(role),
        "items": directives.items(role),
        "global_text": directives.read(None),
        "global_items": directives.items(None),
        "path": str(directives.role_path(role).relative_to(REPO_ROOT)),
        "global_path": str(directives.global_path().relative_to(REPO_ROOT)),
        "applies_when": "이 역할이 다음에 일할 때 자동으로 반영된다. "
                        "지금 돌고 있는 단계에 넣으려면 일시정지 후 ↻재요청 해라.",
    }}


@router.post("/{role}/notes")
async def add_note(role: str, body: NoteIn, db: Session = Depends(get_db)):
    """한 줄 추가 — 웹의 빠른 입력창이 쓴다."""
    if role not in ROLES and role != "_global":
        raise HTTPException(404, f"그런 역할이 없다: {role}")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "빈 지시는 넣을 수 없다")
    target = None if role == "_global" else role
    directives.append(text, target, who="pm")
    services.audit(db, "pm", "directive.add",
                   f"role:{role}", {"text": text[:200]})
    db.commit()
    return {"ok": True, "data": {"role": role, "items": directives.items(target),
                                 "note": "다음 실행부터 반영된다"}}


@router.put("/{role}/notes", response_class=PlainTextResponse)
async def put_notes(role: str, body: str = Body(..., media_type="text/plain"),
                    db: Session = Depends(get_db)):
    """통째로 저장 — 편집기가 쓴다. 빈 내용이면 지시를 전부 취소한다."""
    if role not in ROLES and role != "_global":
        raise HTTPException(404, f"그런 역할이 없다: {role}")
    target = None if role == "_global" else role
    directives.write(body, target)
    services.audit(db, "pm", "directive.write", f"role:{role}",
                   {"bytes": len(body)})
    db.commit()
    return "저장했다. 다음 실행부터 반영된다" if body.strip() else "지시를 비웠다"


@router.delete("/{role}/notes")
async def clear_notes(role: str, db: Session = Depends(get_db)):
    target = None if role == "_global" else role
    directives.write("", target)
    services.audit(db, "pm", "directive.clear", f"role:{role}", {})
    db.commit()
    return {"ok": True, "data": {"role": role, "items": []}}


@router.get("/{role}/check")
async def check_output(role: str, cycle: int | None = Query(None),
                       step: str | None = Query(None),
                       db: Session = Depends(get_db)):
    """이 역할의 산출물이 완료 조건을 지켰는지 **지금 다시** 검사한다.

    HQ 가 단계 직후에 자동으로 하는 것과 같은 검사다. 사람이 산출물을 손으로 고친 뒤
    "이제 됐나" 를 확인할 수 있어야 해서 버튼으로도 뽑아 둔다.
    """
    if role not in ROLES:
        raise HTTPException(404, f"그런 역할이 없다: {role}")
    c = db.get(Cycle, cycle) if cycle else _latest_cycle(db)
    if c is None:
        raise HTTPException(404, "사이클이 없다")

    pl = pipelines.load(c.pipeline)
    cands: list[Path] = []
    for s in db.scalars(select(Step).where(Step.cycle_id == c.id)).all():
        if step and s.step_key != step:
            continue
        d = pl.step(s.step_key)
        rs = list(d.roles) if d else ([s.role] if s.role else [])
        if role not in rs:
            continue
        base = REPO_ROOT / "runs" / str(c.id) / s.step_key / "output"
        cands.append(base / role if len(rs) > 1 else base)

    result = []
    for out in cands:
        if not out.exists():
            continue
        fs = checks.check(role, out, {"screens": runner._screen_count(c.id)})
        if not fs:
            continue
        ok, total = checks.score(fs)
        result.append({
            "dir": str(out.relative_to(REPO_ROOT)),
            "ok": ok, "total": total,
            "findings": [{"ok": f.ok, "label": f.label,
                          "detail": f.detail, "fix": f.fix} for f in fs],
        })
    return {"ok": True, "data": {"role": role, "cycle": c.id, "results": result}}


@router.get("/{role}")
async def agent_detail(role: str, cycle: int | None = Query(None),
                       db: Session = Depends(get_db)):
    """이 에이전트가 지금 무엇을 하고 있고 무엇을 만들었는지 한 번에 준다."""
    if role not in ROLES:
        raise HTTPException(404, f"그런 역할이 없다: {role}")

    node = db.scalar(select(Node).where(Node.role == role))
    stale = (node is None or node.last_heartbeat is None
             or (now() - as_utc(node.last_heartbeat)) > timedelta(seconds=HEARTBEAT_TIMEOUT))

    data: dict[str, Any] = {
        "role": role,
        "display_name": ROLE_DISPLAY[role],
        "node": {
            "status": "down" if stale else "up",
            "dgx_host": node.dgx_host if node else None,
            "a2a_url": node.a2a_url if node else None,
            "last_heartbeat": (node.last_heartbeat.isoformat()
                               if node and node.last_heartbeat else None),
            "card": node.card if node else None,
        },
        "spec": None, "steps": [], "messages": [], "artifacts": [],
        "current": None, "cycle": None,
        # 이 역할이 무엇을 하는 사람인가 (roles.yaml)
        "catalog": {k: v for k, v in roles_catalog.get(role).items()
                    if k in ("mission", "goals", "dod", "forbid", "owns",
                             "asks", "default", "steps", "reads", "handoff")},
        # 사람이 끼워 넣은 지시
        "notes": {
            "items": directives.items(role),
            "global_items": directives.items(None),
            "path": str(directives.role_path(role).relative_to(REPO_ROOT)),
        },
        "paths": {
            "baseline": f"agents/{role}/AGENT.md",
            "spec": str(services.spec_path(role).relative_to(REPO_ROOT)),
            "notes": str(directives.role_path(role).relative_to(REPO_ROOT)),
        },
    }

    c = db.get(Cycle, cycle) if cycle else _latest_cycle(db)
    if c is None:
        return {"ok": True, "data": data}
    data["cycle"] = {"id": c.id, "status": _v(c.status),
                     "current_step": c.current_step, "pipeline": c.pipeline}

    # ── 내 AGENT.md ────────────────────────────────────────────────
    spec = db.scalar(select(AgentSpec).where(
        AgentSpec.cycle_id == c.id, AgentSpec.role == role))
    if spec:
        data["spec"] = {
            "status": _v(spec.status), "path": spec.path,
            "customized_at": spec.customized_at.isoformat() if spec.customized_at else None,
            "has_diff": bool(spec.diff_ref),
        }

    # ── 내가 맡는 단계들 ──────────────────────────────────────────
    pl = pipelines.load(c.pipeline)
    mine = []
    for s in db.scalars(select(Step).where(Step.cycle_id == c.id).order_by(Step.id)).all():
        d = pl.step(s.step_key)
        roles = list(d.roles) if d else ([s.role] if s.role else [])
        if role not in roles:
            continue
        mine.append({
            "key": s.step_key, "name": s.name, "status": _v(s.status),
            "attempt": s.attempt, "error": s.error,
            "type": d.type if d else None,
            "task": (d.task if d and d.task else ("gate" if d and d.type else None)),
            "with": [r for r in roles if r != role],
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "output_ref": s.output_ref,
        })
    data["steps"] = mine
    data["current"] = next((s for s in mine if s["status"] == "RUNNING"), None)

    # ── 내가 주고받은 메시지 ──────────────────────────────────────
    msgs = db.scalars(
        select(Message).where(
            Message.cycle_id == c.id,
            or_(Message.from_role == role, Message.to_role == role),
        ).order_by(Message.id.desc()).limit(30)
    ).all()
    data["messages"] = [
        {"id": m.id, "from": m.from_role, "to": m.to_role, "kind": _v(m.kind),
         "summary": m.summary, "ts": m.ts.isoformat() if m.ts else None}
        for m in reversed(msgs)
    ]

    # ── 내가 만든 산출물 ──────────────────────────────────────────
    step_ids = {s.id: s.step_key for s in db.scalars(
        select(Step).where(Step.cycle_id == c.id)).all()}
    arts = db.scalars(select(Artifact).where(
        Artifact.cycle_id == c.id, Artifact.role == role
    ).order_by(Artifact.id.desc()).limit(60)).all()
    data["artifacts"] = [
        {"id": a.id, "path": a.path, "step": step_ids.get(a.step_id),
         "name": Path(a.path).name,
         "ts": a.ts.isoformat() if a.ts else None}
        for a in arts
    ]

    # 완료 보고(report.md)도 같이
    reports = []
    for s in mine:
        for name in (f"report-{role}.md", "report.md"):
            p = REPO_ROOT / "runs" / str(c.id) / s["key"] / name
            if p.exists():
                reports.append({"step": s["key"], "name": name,
                                "path": str(p.relative_to(REPO_ROOT))})
                break
    data["reports"] = reports

    return {"ok": True, "data": data}


@router.get("/{role}/file", response_class=PlainTextResponse)
async def agent_file(role: str, path: str = Query(...)):
    """산출물 원문. repo/ 밖으로는 나갈 수 없다."""
    target = (REPO_ROOT / path).resolve()
    try:
        target.relative_to(REPO_ROOT.resolve())
    except ValueError:
        raise HTTPException(400, "repo/ 밖의 경로는 읽을 수 없다")
    if not target.is_file():
        raise HTTPException(404, f"그런 파일이 없다: {path}")
    return target.read_text(encoding="utf-8", errors="replace")


@router.put("/{role}/file", response_class=PlainTextResponse)
async def save_agent_file(role: str, path: str = Query(...),
                          body: str = Body(..., media_type="text/plain"),
                          db: Session = Depends(get_db)):
    """산출물을 사람이 직접 고친다.

    에이전트가 만든 결과가 어긋났을 때 다시 시키는 대신 손으로 고칠 수 있어야 한다.
    수업 중에 시간이 없을 때 쓰는 탈출구다. 고친 사실은 감사 로그에 남는다.
    """
    if role not in ROLES:
        raise HTTPException(404, f"그런 역할이 없다: {role}")
    target = (REPO_ROOT / path).resolve()
    try:
        target.relative_to(REPO_ROOT.resolve())
    except ValueError:
        raise HTTPException(400, "repo/ 밖의 경로는 쓸 수 없다")
    if not target.exists():
        raise HTTPException(404, f"그런 파일이 없다: {path}")
    if not body.strip():
        raise HTTPException(400, "빈 내용은 저장할 수 없다")
    target.write_text(body, encoding="utf-8")
    services.audit(db, "pm", "artifact.edit", path, {"role": role, "bytes": len(body)})
    db.commit()
    return "저장했다"


@router.post("/{role}/retry")
async def retry_step(role: str, step_key: str | None = Query(None),
                     cycle: int | None = Query(None),
                     db: Session = Depends(get_db)):
    """이 역할의 단계를 다시 시킨다.

    되감기(rewind)와 다르다 — 되감기는 그 이후 **모든** 단계를 무효화하지만,
    재요청은 **그 단계 하나만** 다시 돌린다. 산출물이 마음에 안 들 때 쓴다.

    사이클이 RUNNING 중이면 받지 않는다. 먼저 일시정지해야 한다.
    """
    return rerun_role_step(db, role, cycle, step_key)


def rerun_role_step(db: Session, role: str, cycle: int | None,
                    step_key: str | None, note: str = "") -> dict:
    """`↻재요청` 의 실체. 프리뷰 화면의 「지금 고치기」도 이걸 부른다."""
    if role not in ROLES:
        raise HTTPException(404, f"그런 역할이 없다: {role}")
    c = db.get(Cycle, cycle) if cycle else _latest_cycle(db)
    if c is None:
        raise HTTPException(404, "사이클이 없다")

    pl = pipelines.load(c.pipeline)
    steps = db.scalars(select(Step).where(Step.cycle_id == c.id).order_by(Step.id)).all()

    target = None
    if step_key:
        target = next((s for s in steps if s.step_key == step_key), None)
    else:
        # 이 역할이 맡은 단계 중 가장 최근에 끝난 것
        for s in reversed(steps):
            d = pl.step(s.step_key)
            roles = list(d.roles) if d else ([s.role] if s.role else [])
            if role in roles and s.status in (StepStatus.DONE, StepStatus.FAILED):
                target = s
                break
    if target is None:
        raise HTTPException(404, f"{role} 이 맡은 다시 돌릴 단계를 찾지 못했다")

    d = pl.step(target.step_key)
    roles = list(d.roles) if d else ([target.role] if target.role else [])
    if role not in roles:
        raise HTTPException(400, f"{target.step_key} 은 {role} 의 단계가 아니다")

    if _v(c.status) == "RUNNING":
        raise HTTPException(409, "사이클이 돌고 있다. 먼저 일시정지한 뒤 재요청해라")

    # 그 단계만 PENDING 으로 되돌리고 산출물을 지운다 (뒤 단계는 건드리지 않는다)
    import shutil
    target.status = StepStatus.PENDING
    target.error = None
    target.output_ref = None
    target.started_at = None
    target.ended_at = None
    run_dir = REPO_ROOT / "runs" / str(c.id) / target.step_key
    if run_dir.exists():
        shutil.rmtree(run_dir, ignore_errors=True)
    db.execute(Artifact.__table__.delete().where(
        Artifact.cycle_id == c.id, Artifact.step_id == target.id))
    services.audit(db, "pm", "step.retry", f"cycle:{c.id}:{target.step_key}",
                   {"role": role})
    db.commit()

    cv, sv = services.snapshot(db, c)
    t = next_step(cv, sv, Event.REWIND, {"step_key": target.step_key})
    if t.action is Action.NOOP:
        raise HTTPException(400, t.note)
    # rewind 는 이후 단계까지 무효화하므로, 재요청에서는 그 부분을 되돌린다.
    # 상태만 RUNNING 으로 옮기고 실행기를 깨운다.
    c.status = type(c.status)("RUNNING") if hasattr(c.status, "value") else "RUNNING"
    c.current_step = target.step_key
    services.audit(db, "pm", "cycle.running", f"cycle:{c.id}",
                   {"step": target.step_key, "note": f"{role} 재요청"})
    db.commit()
    services.mirror(db, c.id, "pm", role, "request",
                    note or f"{target.step_key} 재요청 — 다시 만들어 주세요")
    runner.kick(c.id)
    return {"ok": True, "data": {"step": target.step_key, "role": role,
                                 "status": "RUNNING",
                                 "note": f"{target.step_key} 를 {role} 에게 다시 시켰다"}}
