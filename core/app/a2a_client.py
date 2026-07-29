"""HQ → 노드 A2A 발신 (BRIEF §5.3).

흐름:
    1. HQ → 노드   message/send   {task, spec_url, context_urls, outputs}
    2. 노드 → HQ   {taskId, state: "working"}
    3. HQ          tasks/get 폴링 (5초)
    4. 노드 → HQ   {state: "completed", artifacts: [...]}
    5. HQ          artifacts 를 repo/ 에 기록, step DONE 처리

★ 표준 SDK vs 자체 구현 — BRIEF §5.4 에 대한 답은 CLAUDE.md 와
  ops/wheels/README.md 에 기록했다. 요약: **와이어 포맷은 A2A 와 동일**하고
  구현만 직접 했다. 필드명·엔드포인트가 같으므로 나중에 SDK 로 갈아끼울 수 있다.

모든 외부 호출에 타임아웃을 건다. 로컬 모델은 느리다 (BRIEF §15-3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

POLL_SEC = float(os.getenv("A2A_POLL_INTERVAL_SEC", "5"))


@dataclass(frozen=True)
class TaskRequest:
    """BRIEF §4.3 의 페이로드. 필드명을 A2A 와 동일하게 맞춰 둔다."""

    role: str
    cycle_id: int
    step_id: str
    task: str
    spec_url: str                       # 노드가 AGENT.md 를 읽어가는 주소
    step_name: str = ""
    context_urls: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    timeout_sec: int = 900
    order: str = ""            # 주문서 원문 — 지어내지 않게 하는 근거
    instruction: str = ""      # 이 태스크의 지시 템플릿 (BRIEF §4.1)
    work_key: str = ""         # 노드 작업 디렉터리 구분자 (비면 step_id)
    hq_url: str = ""           # ★ 나(HQ)의 주소. 노드가 여기로 보고한다

    def to_params(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "hq_url": self.hq_url,
            "cycle_id": self.cycle_id,
            "step_id": self.step_id,
            "step_name": self.step_name,
            "task": self.task,
            "spec_url": self.spec_url,
            "context_urls": list(self.context_urls),
            "outputs": list(self.outputs),
            "timeout_sec": self.timeout_sec,
            "order": self.order,
            "instruction": self.instruction,
            "work_key": self.work_key or self.step_id,
        }


@dataclass
class TaskResult:
    task_id: str
    state: str                          # working | completed | failed | canceled
    artifacts: list[dict] = field(default_factory=list)
    report: str = ""
    error: str | None = None


async def _rpc(client: httpx.AsyncClient, url: str, method: str,
               params: dict[str, Any]) -> dict[str, Any]:
    r = await client.post(url, json={
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    })
    r.raise_for_status()
    body = r.json()
    if "error" in body and body["error"]:
        raise RuntimeError(f"{method} 오류: {body['error'].get('message')}")
    return body.get("result") or {}


async def send_message(a2a_url: str, req: TaskRequest,
                       timeout_sec: int = 30) -> TaskResult:
    """노드에 `message/send` 를 보낸다. 즉시 taskId 를 받는다."""
    async with httpx.AsyncClient(timeout=timeout_sec) as c:
        res = await _rpc(c, a2a_url, "message/send", req.to_params())
    return TaskResult(task_id=res.get("taskId", ""), state=res.get("state", "working"))


async def get_task(a2a_url: str, task_id: str, timeout_sec: int = 30) -> TaskResult:
    """`tasks/get` 폴링."""
    async with httpx.AsyncClient(timeout=timeout_sec) as c:
        res = await _rpc(c, a2a_url, "tasks/get", {"taskId": task_id})
    return TaskResult(
        task_id=res.get("taskId", task_id),
        state=res.get("state", "working"),
        artifacts=res.get("artifacts") or [],
        report=res.get("report") or "",
        error=res.get("error"),
    )


async def cancel_task(a2a_url: str, task_id: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await _rpc(c, a2a_url, "tasks/cancel", {"taskId": task_id})
    except Exception:
        pass


async def fetch_agent_card(a2a_url: str, timeout_sec: int = 10) -> dict[str, Any]:
    """`/.well-known/agent-card.json` 조회 (인수 #6)."""
    base = a2a_url.rstrip("/")
    async with httpx.AsyncClient(timeout=timeout_sec) as c:
        r = await c.get(f"{base}/.well-known/agent-card.json")
        r.raise_for_status()
        return r.json()
