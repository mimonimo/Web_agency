"""agora-core — 오케스트레이터 + API (BRIEF §2).

Phase 0 시점: API 표면만 선언돼 있다. 각 엔드포인트는 501 을 던지며
"어느 Phase 에서 구현하는지"를 한국어로 알려준다 (BRIEF §15-4).
/docs 를 열면 전체 계약이 한눈에 보인다.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from . import a2a_server
from .routers import (
    artifacts,
    cycles,
    dashboard,
    messages,
    nodes,
    orders,
    specs,
    tickets,
)

app = FastAPI(
    title="AGORA Web HQ",
    description=(
        "고등학교 AI 에이전트 PBL 수업의 중앙 오케스트레이터.\n\n"
        "요구사항 → 사이클 → step 을 돌리되, **사람이 원하는 지점에서 멈추고·고치고·"
        "재개하고·처음부터 다시** 할 수 있게 하는 것이 존재 이유다 (BRIEF §1.1)."
    ),
    version="0.1.0-phase0",
)

# BRIEF §7 의 8개 라우터
for r in (cycles, nodes, specs, tickets, orders, messages, artifacts, dashboard):
    app.include_router(r.router)

# HQ 자신도 A2A 에이전트로 노출 (선택 — BRIEF §2)
app.include_router(a2a_server.router)


@app.get("/api/health", tags=["health"])
async def health() -> dict[str, object]:
    """compose healthcheck 와 인수 #3(curl -I → 200)의 근거."""
    return {
        "ok": True,
        "data": {
            "service": "agora-core",
            "phase": "0",
            "project": os.getenv("PROJECT_ID", "project-001"),
        },
    }
