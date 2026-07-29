"""활동 피드 — 에이전트가 지금 무엇을 하고 있나.

## 왜 필요한가

주문을 넣고 나면 사람이 할 수 있는 일이 없다. 몇 분 동안 아무 반응이 없으면
"돌고 있는 건가, 죽은 건가" 를 알 수 없고, 그러면 이 시스템을 믿지 않게 된다.

터미널에서 명령을 하나 치면 진행 상황이 줄줄 흐르는 것과 같은 화면이 필요하다.
사람이 보고 싶은 것은 완료 보고가 아니라 **지금 이 순간**이다.

    23:41:02  hq   → designer   S4 설계 지시 · 참고자료 3건 · 최대 20분
    23:41:05  designer          S4 착수 — gpt-oss:120b
    23:43:18  designer → hq     S4 완료 — 산출물 2건 (design-tokens.json, UI-GUIDE.md)
    23:43:18  hq                S4 완료 조건 6/6 통과
    23:43:19  hq   → frontend   S5 구현 지시 · 참고자료 6건

## 무엇을 합치나

세 곳에 흩어져 있던 것을 시간순 하나로 합친다.

| 출처 | 무엇 |
|---|---|
| `messages` | 에이전트끼리 오간 말 (노드가 미러링) |
| `audit_logs` | HQ 가 한 판단 — 검사 결과, 게이트 판정, 사람의 개입 |
| `steps` | 단계가 언제 시작·종료했나, 지금 몇 초째인가 |

`after` 로 마지막에 본 지점을 넘기면 그 뒤만 준다 (폴링용).
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import pipelines, services
from ..db import get_db
from ..models import AuditLog, Cycle, Message, ROLE_DISPLAY, Step
from ..services import as_utc, now

router = APIRouter(prefix="/api/activity", tags=["activity"])

# 사람이 보고 싶어 하지 않는 잡음. 감사 로그에는 남지만 피드에는 안 띄운다.
NOISE = {"message.mirror", "node.heartbeat", "spec.scan", "nodes.ensure",
         "node.register", "spec.list"}

# 감사 로그를 사람 말로 바꾼다. 코드 이름을 그대로 보여 주면 아무도 못 읽는다.
SAY = {
    "step.check":        "완료 조건 검사",
    "step.artifacts":    "산출물 수신",
    "step.done":         "단계 완료",
    "step.retry":        "단계 재요청",
    "cycle.running":     "사이클 진행",
    "cycle.paused":      "일시정지",
    "cycle.done":        "사이클 완료",
    "gate.approve":      "게이트 통과",
    "ticket.create_rework": "재작업 티켓 생성",
    "ticket.create":     "티켓 생성",
    "specs.emit":        "AGENT.md 초안 생성",
    "spec.edit":         "학생이 AGENT.md 수정",
    "directive.add":     "사람이 지시 추가",
    "directive.write":   "사람이 지시 수정",
    "review.fix_now":    "사람이 수정 요청 (지금 고치기)",
    "review.next_cycle": "사람이 개선 요구 (다음 사이클)",
    "artifact.edit":     "사람이 산출물 수정",
    "file.edit":         "사람이 파일 수정",
    "file.create":       "사람이 파일 생성",
    "order.create":      "주문 접수",
}


def _detail(a: AuditLog) -> str:
    p = a.payload or {}
    if a.action == "step.check":
        s = f"{p.get('ok')}/{p.get('total')} 통과"
        bad = p.get("failed") or []
        if bad:
            s += f" — 미달: {', '.join(bad[:3])}"
            if p.get("final"):
                s += " (그대로 진행)"
            else:
                s += " (다시 시킨다)"
        return s
    if a.action == "step.artifacts":
        return f"{p.get('count', 0)}건"
    if a.action in ("directive.add", "review.fix_now", "review.next_cycle"):
        return str(p.get("text", ""))[:160]
    if a.action == "gate.approve":
        return str(p.get("reason", ""))[:160]
    if a.action == "order.create":
        return f"{p.get('company', '')} ({p.get('kind', '')})"
    if a.action == "step.done":
        return f"산출물 {p.get('artifacts', 0)}건"
    return ", ".join(f"{k}={v}" for k, v in list(p.items())[:3]) if p else ""


@router.get("")
async def feed(cycle: int | None = Query(None),
               after_msg: int = Query(0),
               after_log: int = Query(0),
               limit: int = Query(120),
               db: Session = Depends(get_db)):
    """시간순 활동 피드 + 지금 도는 단계의 경과 시간."""
    c = (db.get(Cycle, cycle) if cycle
         else db.scalar(select(Cycle).order_by(Cycle.id.desc())))

    ev: list[dict] = []

    q = select(Message).order_by(Message.id.desc()).limit(min(limit, 300))
    if c:
        q = q.where(Message.cycle_id == c.id)
    if after_msg:
        q = q.where(Message.id > after_msg)
    for m in db.scalars(q).all():
        kind = m.kind.value if hasattr(m.kind, "value") else str(m.kind)
        ev.append({
            "src": "msg", "id": m.id, "ts": m.ts.isoformat() if m.ts else None,
            "from": m.from_role, "to": m.to_role, "kind": kind,
            "text": m.summary or "", "detail": "",
        })

    q2 = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 300))
    if after_log:
        q2 = q2.where(AuditLog.id > after_log)
    for a in db.scalars(q2).all():
        if a.action in NOISE:
            continue
        if c and a.target and ":" in a.target and a.target.startswith("cycle:"):
            try:
                if int(a.target.split(":")[1]) != c.id:
                    continue
            except (ValueError, IndexError):
                pass
        ev.append({
            "src": "log", "id": a.id, "ts": a.ts.isoformat() if a.ts else None,
            "from": a.actor, "to": (a.payload or {}).get("role", ""),
            "kind": "audit", "text": SAY.get(a.action, a.action),
            "detail": _detail(a), "action": a.action,
        })

    ev.sort(key=lambda e: (e["ts"] or "", e["id"]))
    ev = ev[-limit:]

    # 지금 도는 단계 — 몇 초째인가. 이게 있어야 "죽은 건가" 를 안 묻는다.
    running: list[dict] = []
    steps_all: list[dict] = []
    if c:
        pl = pipelines.load(c.pipeline)
        t0 = now()
        for s in db.scalars(select(Step).where(Step.cycle_id == c.id)
                            .order_by(Step.id)).all():
            st = s.status.value if hasattr(s.status, "value") else str(s.status)
            d = pl.step(s.step_key)
            rs = list(d.roles) if d else ([s.role] if s.role else [])
            row = {
                "key": s.step_key, "name": s.name, "status": st,
                "roles": rs, "attempt": s.attempt,
                "timeout": (d.timeout_sec if d else None),
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "elapsed": (int((t0 - as_utc(s.started_at)).total_seconds())
                            if s.started_at and st == "RUNNING" else None),
            }
            steps_all.append(row)
            if st == "RUNNING":
                running.append(row)

    return {"ok": True, "data": {
        "cycle": ({"id": c.id,
                   "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                   "current_step": c.current_step} if c else None),
        "events": ev,
        "running": running,
        "steps": steps_all,
        "cursor": {
            "msg": max([e["id"] for e in ev if e["src"] == "msg"] + [after_msg]),
            "log": max([e["id"] for e in ev if e["src"] == "log"] + [after_log]),
        },
        "roles": ROLE_DISPLAY,
    }}


@router.get("/prompt")
async def prompt(role: str = Query(...), step: str | None = Query(None),
                 cycle: int | None = Query(None), db: Session = Depends(get_db)):
    """이 에이전트가 **실제로 받은 지시문**을 보여 준다.

    "무슨 일을 시켰길래 저런 결과가 나왔나" 를 눈으로 확인할 수 있어야
    지시문을 고칠 마음이 생긴다. 그게 이 수업의 목적이다.
    """
    from .. import runner
    c = (db.get(Cycle, cycle) if cycle
         else db.scalar(select(Cycle).order_by(Cycle.id.desc())))
    if c is None:
        return {"ok": True, "data": {"role": role, "instruction": "", "note": "사이클이 없다"}}

    pl = pipelines.load(c.pipeline)
    key = step or c.current_step
    sdef = pl.step(key) if key else None
    if sdef is None:
        for s in pl.steps:
            if role in (s.roles or ()):
                sdef = s
                break
    if sdef is None:
        return {"ok": True, "data": {"role": role, "instruction": "",
                                     "note": "이 역할이 맡은 단계를 찾지 못했다"}}

    inputs = runner.resolve_inputs(c.id, sdef.inputs)
    return {"ok": True, "data": {
        "role": role, "step": sdef.id, "step_name": sdef.name,
        "task": sdef.task or sdef.type or "work",
        "instruction": runner._instruction(sdef, role),
        "inputs": inputs,
        "outputs": list(sdef.outputs_for(role)),
        "order": runner._order_text(c.id) if "order" in sdef.inputs else "",
        "timeout": sdef.timeout_sec,
    }}
