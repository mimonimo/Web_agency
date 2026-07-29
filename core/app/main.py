"""agora-core — 오케스트레이터 + API (BRIEF §2).

두 가지 방식으로 돈다.

    네이티브:  make dev    (venv + uvicorn + SQLite)   ← docker 권한 없이 바로
    컨테이너:  make up     (compose + postgres)        ← docker 그룹 필요

어느 쪽이든 코드와 산출물 경로는 완전히 동일하다.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from . import a2a_server, services
from .db import Base, SessionLocal, engine
from .models import Cycle
from .routers import (
    agents,
    artifacts,
    cycles,
    dashboard,
    messages,
    nodes,
    orders,
    review,
    specs,
    tickets,
)

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = Path(os.getenv("WEB_DIR", ROOT / "web"))
SPEC_POLL = float(os.getenv("SPEC_POLL_INTERVAL_SEC", "3"))
SERVE_WEB = os.getenv("SERVE_WEB", "1") == "1"


async def _spec_watcher() -> None:
    """repo/ 를 주기적으로 훑어 AGENT.md 변경을 감지한다 (BRIEF §4.2).

    11개가 전부 customized 되면 사이클이 자동으로 재개된다 (인수 #15).
    """
    from .orchestrator import Action, Event, next_step
    from . import runner

    while True:
        await asyncio.sleep(SPEC_POLL)
        try:
            db = SessionLocal()
            try:
                c = db.scalar(select(Cycle).order_by(Cycle.id.desc()))
                if c is None or c.status.value != "BLOCKED":
                    continue
                services.scan_customized(db, c)
                prog = services.spec_progress(db, c)
                if prog["total"] and prog["customized"] >= prog["total"]:
                    cv, sv = services.snapshot(db, c)
                    t = next_step(cv, sv, Event.SPECS_ALL_CUSTOMIZED)
                    if t.action is not Action.NOOP:
                        services.apply(db, c, t, actor="hq")
                        if t.action is Action.RUN_STEP:
                            runner.kick(c.id)
            finally:
                db.close()
        except Exception:                                        # noqa: BLE001
            # 감시 루프는 절대 죽지 않는다. 죽으면 게이트가 영영 안 열린다.
            pass


def _seed_nodes() -> None:
    """students.yaml 기준으로 노드 11개를 등록한다. 멱등."""
    f = ROOT / "provisioning" / "students.yaml"
    if not f.exists():
        return
    doc = yaml.safe_load(f.read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        services.ensure_nodes(db, doc.get("students", []))
    finally:
        db.close()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    _seed_nodes()
    task = asyncio.create_task(_spec_watcher())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="AGORA Web HQ",
    description=(
        "고등학교 AI 에이전트 PBL 수업의 중앙 오케스트레이터.\n\n"
        "요구사항 → 사이클 → step 을 돌리되, **사람이 원하는 지점에서 멈추고·고치고·"
        "재개하고·처음부터 다시** 할 수 있게 하는 것이 존재 이유다 (BRIEF §1.1)."
    ),
    version="0.3.0",
    lifespan=lifespan,
)

# BRIEF §7 의 라우터 + 사람이 조작하는 화면용 라우터(agents·review)
for r in (cycles, nodes, specs, tickets, orders, messages, artifacts,
          dashboard, agents, review):
    app.include_router(r.router)

# HQ 자신도 A2A 에이전트로 노출 (선택 — BRIEF §2)
app.include_router(a2a_server.router)
app.include_router(artifacts.files_router)
app.include_router(artifacts.preview_router)


@app.get("/api/health", tags=["health"])
async def health() -> dict[str, object]:
    from . import runner
    return {
        "ok": True,
        "data": {
            "service": "agora-core",
            "project": os.getenv("PROJECT_ID", "project-001"),
            "executor": runner.EXECUTOR,
        },
    }


# 네이티브 실행 시 caddy 가 없으므로 정적 파일을 직접 서빙한다.
# 컨테이너로 돌릴 때는 SERVE_WEB=0 으로 끄고 caddy 에게 맡긴다.
if SERVE_WEB and WEB_DIR.exists():
    @app.get("/", include_in_schema=False)
    async def _root():
        return RedirectResponse("/index.html")

    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
