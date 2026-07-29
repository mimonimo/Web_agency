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
    activity,
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
    """students.yaml 기준으로 노드 11개를 등록한다. 멱등.

    ★ `students.local.yaml` 이 있으면 **그쪽을 먼저 쓴다.**
      공개 리포의 `students.yaml` 은 IP 가 예시 값(10.0.0.x)이다. 그대로 두면
      부팅할 때마다 실제 노드 주소를 예시 값으로 덮어써서 HQ 가 노드를 못 부른다.
      실제로 그렇게 만들어 S5 가 ConnectTimeout 으로 죽었다.
      진짜 IP 는 `students.local.yaml` 에 두고 git 에서 제외한다.
    """
    local = ROOT / "provisioning" / "students.local.yaml"
    f = local if local.exists() else ROOT / "provisioning" / "students.yaml"
    if not f.exists():
        return
    print(f"[nodes] {f.name} 로 노드를 등록한다")
    doc = yaml.safe_load(f.read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        services.ensure_nodes(db, doc.get("students", []))
    finally:
        db.close()


def _recover_interrupted() -> None:
    """HQ 가 죽거나 재시작했을 때 **RUNNING 인 채로 남은 단계**를 되살린다.

    실행 태스크는 프로세스 메모리에 있다. HQ 를 재시작하면 태스크는 사라지는데
    DB 의 step 은 RUNNING 으로 남는다. 그러면 사이클이 영원히 그 자리에 멈춘다 —
    화면에는 "진행 중" 이라고 떠 있고 실제로는 아무도 일하지 않는다.
    수업 중에 이게 나면 손쓸 방법이 없다.

    그래서 부팅할 때 그런 단계를 PENDING 으로 되돌리고 실행기를 다시 깨운다.
    노드는 새 작업으로 받으므로 그냥 다시 한다. 되돌린 사실은 로그에 남긴다.
    """
    from .models import Step, StepStatus
    from . import runner

    from .models import CycleStatus

    db = SessionLocal()
    try:
        stuck = list(db.scalars(
            select(Step).where(Step.status == StepStatus.RUNNING)).all())

        # ★ 종료 중에 FAILED 로 찍혀 버린 것도 되살린다.
        #   실행기가 취소되면서 "frontend: ; backend: ;" 같은 **빈 사유**의
        #   실패가 남는 일이 있었다. 그러면 사이클이 통째로 죽어 아무도 못 살린다.
        #   진짜 실패는 사유가 있다. 사유가 없거나 중단 흔적이면 재시도할 값어치가 있다.
        for s in db.scalars(select(Step).where(Step.status == StepStatus.FAILED)):
            e = (s.error or "").strip()
            if not e or "CancelledError" in e or e.endswith((":", "; dba: ", ": ")) \
               or all(part.split(":", 1)[-1].strip() == ""
                      for part in e.split("오류:")[-1].split(";") if part.strip()):
                stuck.append(s)

        if not stuck:
            return
        cycles: set[int] = set()
        for s in stuck:
            was = s.status.value if hasattr(s.status, "value") else str(s.status)
            s.status = StepStatus.PENDING
            s.error = None
            s.started_at = None
            cycles.add(s.cycle_id)
            services.audit(db, "hq", "step.recover", f"cycle:{s.cycle_id}:{s.step_key}",
                           {"was": was, "note": "HQ 재시작으로 끊긴 단계를 되돌렸다"})
            services.mirror(db, s.cycle_id, "hq", s.role or "hq", "response",
                            f"{s.step_key} 다시 시작 — HQ 재시작으로 끊겼다")
        db.commit()

        for cid in cycles:
            c = db.get(Cycle, cid)
            if c is None:
                continue
            st = c.status.value if hasattr(c.status, "value") else str(c.status)
            # 사이클까지 FAILED 로 죽었으면 되살려 준다. 사람이 손댈 수 없는 상태다.
            if st == "FAILED":
                c.status = CycleStatus.RUNNING
                services.audit(db, "hq", "cycle.recover", f"cycle:{cid}",
                               {"note": "중단으로 죽은 사이클을 되살렸다"})
                db.commit()
                st = "RUNNING"
            if st == "RUNNING":
                runner.kick(cid)
        print(f"[recover] 끊긴 단계 {len(stuck)}개를 되살렸다 (사이클 {sorted(cycles)})")
    except Exception as e:                                   # noqa: BLE001
        print(f"[recover] 복구 실패(무시하고 계속): {e}")
    finally:
        db.close()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    _seed_nodes()
    _recover_interrupted()
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
          dashboard, agents, review, activity):
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
class NoStaleFiles(StaticFiles):
    """화면 파일은 **항상 서버에 물어보고** 쓰게 한다.

    ★ 실제로 겪은 일: 화면을 고친 뒤에도 어떤 역할은 옛 화면이 떴다.
      `Cache-Control` 이 없으면 브라우저가 휴리스틱 캐싱을 하고,
      **캐시 키에 쿼리스트링이 포함**되므로 먼저 열어 본
      `/agent.html?role=pm` 만 옛 페이지로 남는다.
      "관리·백엔드·QA·고객만 다른 화면이 뜬다" 가 바로 이것이었다.

    `no-cache` 는 "쓰지 마라" 가 아니라 "쓰기 전에 물어봐라" 다.
    ETag 가 같으면 304 로 끝나므로 느려지지 않는다.
    수업 중에 화면을 고쳐도 새로고침 한 번이면 반영된다.
    """

    async def get_response(self, path: str, scope):
        r = await super().get_response(path, scope)
        if path.endswith((".html", ".js", ".css")):
            r.headers["Cache-Control"] = "no-cache, must-revalidate"
        return r


if SERVE_WEB and WEB_DIR.exists():
    @app.get("/", include_in_schema=False)
    async def _root():
        return RedirectResponse("/index.html")

    app.mount("/", NoStaleFiles(directory=str(WEB_DIR), html=True), name="web")
