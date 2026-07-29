"""보면서 고친다 — 프리뷰와 수정 요청.

## 왜 이게 따로 있는가

주문 접수(`/order.html`)는 **새 일을 시작하는 곳**이다. 거기에 "변경 요청"·"결함 신고"
항목이 섞여 있으면 안 된다 — 아직 아무것도 안 만들었는데 무엇을 고치라는 말인가.

고치는 요청은 **만들어진 것을 보면서** 하는 것이다. 그래서 여기가 따로 있다.

    /review.html
      왼쪽: 지금까지 만들어진 사이트 (작업 중에도 보인다)
      오른쪽: 고쳐 달라는 말 한 줄

## 두 가지 경로

| | 지금 고치기 | 다음 사이클 주문으로 |
|---|---|---|
| 언제 | 아직 작업 중이거나 방금 끝났을 때 | 이미 배포가 끝났을 때 |
| 하는 일 | 그 역할에 지시를 꽂고 **그 단계만** 다시 실행 | `change` 주문을 새로 만든다 |
| 걸리는 시간 | 2~5분 | 한 사이클 |
| 되는가 | 사이클이 살아 있어야 한다 | 언제든 |

「지금 고치기」가 이 수업에서 가장 인상적인 장면이다 —
말을 한 줄 넣으면 몇 분 뒤에 화면이 실제로 바뀐다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import directives, pipelines, runner, services
from ..db import get_db
from ..models import Cycle, Order, OrderKind, OrderSource, ROLE_DISPLAY, ROLES, Step
from ..orchestrator import Action, Event, next_step
from ..services import REPO_ROOT
from . import agents as agents_router

router = APIRouter(prefix="/api/review", tags=["review"])

# 무엇을 고쳐 달라는 말인지에 따라 누가 고쳐야 하는지가 다르다.
# 사람이 역할을 안 고르면 이 표로 짐작한다 (고르면 고른 쪽이 이긴다).
GUESS = [
    ("designer", ("색", "색상", "톤", "분위기", "폰트", "글꼴", "여백", "간격",
                  "디자인", "예쁘", "촌스", "칙칙", "팔레트")),
    ("frontend", ("화면", "버튼", "레이아웃", "배치", "모바일", "반응형", "클릭",
                  "메뉴", "링크", "폼", "입력", "표시", "안 보", "깨지")),
    ("backend", ("api", "서버", "응답", "저장", "오류", "에러", "느리", "500", "400")),
    ("dba", ("데이터", "상품", "가격", "목록이 비", "샘플", "시드")),
    ("planner", ("기능", "요구", "빠졌", "추가해", "없애", "범위")),
    ("qa", ("테스트", "검수", "확인해")),
    ("security", ("보안", "취약", "비밀번호", "개인정보")),
]


def _latest_cycle(db: Session) -> Cycle | None:
    return db.scalar(select(Cycle).order_by(Cycle.id.desc()))


def guess_role(text: str) -> str:
    low = text.lower()
    for role, words in GUESS:
        if any(w in low for w in words):
            return role
    return "frontend"          # 눈에 보이는 불만은 대개 화면 쪽이다


def _sites(cycle_id: int | None) -> list[dict]:
    """볼 수 있는 사이트 목록. **작업 중에도** 보이는 것이 요점이다.

    DB 를 보지 않고 파일시스템만 훑는다 — 단계가 DONE 이 되기 전에도,
    DB 가 초기화된 뒤에도 보이게 하려고.
    """
    out: list[dict] = []
    roots = []
    if cycle_id:
        roots.append(REPO_ROOT / "runs" / str(cycle_id))
    roots += [REPO_ROOT / services.PROJECT_ID, REPO_ROOT / "showcase"]
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for idx in root.rglob("index.html"):
            if any(p in ("node_modules", ".git", ".archive") for p in idx.parts):
                continue
            d = idx.parent
            if d in seen:
                continue
            seen.add(d)
            rel = d.relative_to(REPO_ROOT)
            parts = rel.parts
            out.append({
                "dir": str(rel),
                "url": f"/preview/{rel}/index.html",
                "step": parts[2] if len(parts) >= 3 and parts[0] == "runs" else None,
                "role": parts[4] if len(parts) >= 5 and parts[3] == "output" else None,
                "kind": "작업본" if parts[0] == "runs"
                        else ("보존본" if parts[0] == "showcase" else "확정본"),
                "files": sum(1 for _ in d.iterdir() if _.is_file()),
                "mtime": idx.stat().st_mtime,
            })
    out.sort(key=lambda s: s["mtime"], reverse=True)
    return out


def _pages(d: Path) -> list[dict]:
    """한 사이트 안의 페이지들 — 메인(index.html)과 서브(그 밖의 .html).

    프론트엔드가 한 파일에 `<section>` 으로 다 담기도 하고, 파일을 나누기도 한다.
    어느 쪽이든 사람이 눌러서 볼 수 있어야 한다.
    """
    out = []
    for p in sorted(d.glob("*.html")):
        rel = p.relative_to(REPO_ROOT)
        is_main = p.name == "index.html"
        title = p.name
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:2000]
            import re as _re
            m = _re.search(r"<title[^>]*>(.*?)</title>", head, _re.S | _re.I)
            if m and m.group(1).strip():
                title = m.group(1).strip()[:60]
        except OSError:
            pass
        out.append({"name": p.name, "title": title, "main": is_main,
                    "url": f"/preview/{rel}", "size": p.stat().st_size})
    out.sort(key=lambda x: (not x["main"], x["name"]))
    return out


@router.get("/projects")
async def projects(db: Session = Depends(get_db)):
    """작업(사이클)별로 묶은 결과물 목록.

    "1번 작업물 메인 → 1번 작업물 서브" 처럼 사이클 하나가 폴더 하나로 보인다.
    사이클이 없어진(초기화된) 결과물도 파일이 남아 있으면 목록에 나온다.
    """
    cycles = {c.id: c for c in db.scalars(select(Cycle).order_by(Cycle.id.desc())).all()}
    orders = {o.id: o for o in db.scalars(select(Order)).all()}

    groups: dict[str, dict] = {}
    for s in _sites(None) + [x for cid in cycles for x in _sites(cid)]:
        d = Path(s["dir"])
        parts = d.parts
        if parts and parts[0] == "runs" and len(parts) >= 2 and parts[1].isdigit():
            key, cid = f"cycle-{parts[1]}", int(parts[1])
        elif parts and parts[0] == "showcase":
            key, cid = "showcase", None
        else:
            key, cid = "confirmed", None

        g = groups.setdefault(key, {
            "key": key, "cycle_id": cid, "sites": [], "seen": set(),
            "title": ("보존본 (시연·비교용)" if key == "showcase"
                      else "확정 산출물" if key == "confirmed" else None),
            "order": None, "status": None,
        })
        if cid and g["title"] is None:
            c = cycles.get(cid)
            o = orders.get(c.order_id) if c else None
            g["title"] = f"#{cid} {o.title}" if o else f"#{cid} 사이클"
            g["order"] = ({"id": o.id, "kind": o.kind.value, "body": o.body}
                          if o else None)
            g["status"] = (c.status.value if c and hasattr(c.status, "value")
                           else (str(c.status) if c else None))
        if s["dir"] in g["seen"]:
            continue
        g["seen"].add(s["dir"])
        g["sites"].append({**s, "pages": _pages(REPO_ROOT / s["dir"])})

    out = []
    for g in groups.values():
        g.pop("seen", None)
        g["site_count"] = len(g["sites"])
        g["page_count"] = sum(len(s["pages"]) for s in g["sites"])
        out.append(g)
    out.sort(key=lambda g: (g["cycle_id"] is None, -(g["cycle_id"] or 0)))
    return {"ok": True, "data": out}


@router.get("/current")
async def current(db: Session = Depends(get_db)):
    """지금 볼 수 있는 것 + 지금 누가 일하고 있나."""
    c = _latest_cycle(db)
    sites = _sites(c.id if c else None)
    working: list[dict] = []
    if c:
        pl = pipelines.load(c.pipeline)
        for s in db.scalars(select(Step).where(Step.cycle_id == c.id)
                            .order_by(Step.id)).all():
            if s.status.value if hasattr(s.status, "value") else s.status:
                pass
            st = s.status.value if hasattr(s.status, "value") else str(s.status)
            if st != "RUNNING":
                continue
            d = pl.step(s.step_key)
            rs = list(d.roles) if d else ([s.role] if s.role else [])
            working.append({"step": s.step_key, "name": s.name, "roles": rs})
    return {"ok": True, "data": {
        "cycle": ({"id": c.id,
                   "status": c.status.value if hasattr(c.status, "value") else c.status,
                   "current_step": c.current_step} if c else None),
        "sites": sites,
        "latest": sites[0] if sites else None,
        "working": working,
        "roles": [{"role": r, "display_name": ROLE_DISPLAY[r]} for r in ROLES],
    }}


class ReviseIn(BaseModel):
    text: str
    role: str | None = None          # 비우면 문장으로 짐작한다
    mode: str = "now"                # now | next
    step: str | None = None          # 특정 단계를 지목할 때


@router.post("/request")
async def request_change(body: ReviseIn, db: Session = Depends(get_db)):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "무엇을 고칠지 한 줄 적어라")
    role = body.role or guess_role(text)
    if role not in ROLES:
        raise HTTPException(400, f"그런 역할이 없다: {role}")

    if body.mode == "next":
        return _as_new_order(db, text, role)
    return _fix_now(db, text, role, body.step)


def _fix_now(db: Session, text: str, role: str, step_key: str | None) -> dict:
    """지시를 꽂고 → 필요하면 일시정지하고 → 그 단계만 다시 돌린다."""
    c = _latest_cycle(db)
    if c is None:
        raise HTTPException(404, "돌고 있는 사이클이 없다. 「다음 사이클 주문으로」를 써라")

    directives.append(text, role, who="pm")
    services.audit(db, "pm", "review.fix_now", f"cycle:{c.id}:{role}",
                   {"text": text[:200]})
    db.commit()

    status = c.status.value if hasattr(c.status, "value") else str(c.status)
    paused = False
    if status == "RUNNING":
        # 재요청은 RUNNING 중에 받지 않는다. 사람이 두 번 누르지 않게 여기서 대신 멈춘다.
        cv, sv = services.snapshot(db, c)
        t = next_step(cv, sv, Event.PAUSE)
        services.apply(db, c, t, actor="pm")
        db.commit()
        paused = True

    try:
        res = agents_router.rerun_role_step(
            db, role, c.id, step_key,
            note=f"수정 요청 — {text[:80]}")
    except HTTPException as e:
        # 다시 돌릴 단계가 없으면(아직 그 역할이 일한 적 없음) 지시만 남는다.
        # 그 역할이 처음 일할 때 자동으로 반영되므로 실패가 아니다.
        return {"ok": True, "data": {
            "role": role, "applied": "pending", "paused": paused,
            "note": f"{ROLE_DISPLAY[role]} 에게 지시를 남겼다. "
                    f"그 역할이 다음에 일할 때 반영된다. ({e.detail})"}}

    return {"ok": True, "data": {
        **res["data"], "role": role, "applied": "rerun", "paused": paused,
        "note": f"{ROLE_DISPLAY[role]} 에게 지시를 넣고 {res['data']['step']} 를 다시 시켰다. "
                f"몇 분 뒤 프리뷰를 새로고침해라."}}


def _as_new_order(db: Session, text: str, role: str) -> dict:
    """완료된 결과물에 대한 개선 요구 → `change` 주문으로 접수한다."""
    prev = db.scalar(select(Order).order_by(Order.id.desc()))
    title = prev.title if prev else "개선 요청"
    order = Order(
        source=OrderSource("order_site"),
        kind=OrderKind("change"),
        title=title,
        body=f"목적: 완료된 결과물 개선\n요청 내용: {text}\n1차 담당(추정): {role}",
        requester="검수",
        status="open",
    )
    db.add(order)
    db.commit()
    services.audit(db, "pm", "review.next_cycle", f"order:{order.id}",
                   {"text": text[:200], "role": role})
    db.commit()
    cycle = services.create_cycle(db, order, "change", "manual")
    return {"ok": True, "data": {
        "order_id": order.id, "cycle_id": cycle.id, "role": role,
        "applied": "new_order",
        "note": f"변경 요청 주문 #{order.id} 을 만들었다 (사이클 #{cycle.id}, 대기 중). "
                f"픽셀 오피스에서 ▶ 시작을 누르면 진행된다."}}
