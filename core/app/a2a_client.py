"""HQ → 노드 A2A 발신 (BRIEF §5.3).

흐름:
    1. HQ → 노드   message/send   {task, spec_url, context_files, output_dir}
    2. 노드 → HQ   {taskId, state: "working"}
    3. HQ          tasks/get 폴링 (5초)
    4. 노드 → HQ   {state: "completed", artifacts: [...]}
    5. HQ          artifacts 를 repo/ 에 기록, step DONE 처리

⚠️ 표준 SDK vs 자체 구현 — BRIEF §5.4
    A2A 스펙과 SDK 버전은 계속 바뀌고 교실에는 인터넷이 없다.
    Phase 2 에서 오프라인 설치 가능 여부를 먼저 확인하고, 안 되면
    위 모양을 그대로 따르는 최소 JSON-RPC 를 직접 만든다.
    **어느 쪽을 택했는지 CLAUDE.md 에 반드시 기록한다.**
    아직 정해지지 않았다 — Phase 2 의 첫 작업이다.

모든 외부 호출에는 타임아웃을 건다. 로컬 모델은 느리다 (BRIEF §15-3).
기본 900초, pipeline.yaml 에서 step 별로 재정의한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskRequest:
    """BRIEF §4.3 의 페이로드. 필드명을 A2A 와 동일하게 맞춰 둔다."""

    role: str
    cycle_id: int
    step_id: str
    spec_url: str                    # 노드가 AGENT.md 를 읽어가는 주소
    context_files: tuple[str, ...]
    task: str
    output_dir: str


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    state: str                       # working | completed | failed
    artifacts: tuple[str, ...] = ()
    error: str | None = None


async def send_message(a2a_url: str, req: TaskRequest, timeout_sec: int = 900) -> TaskResult:
    """노드에 `message/send` 를 보낸다. Phase 2 에서 구현."""
    raise NotImplementedError("Phase 2 에서 구현한다")


async def get_task(a2a_url: str, task_id: str, timeout_sec: int = 30) -> TaskResult:
    """`tasks/get` 폴링. Phase 2 에서 구현."""
    raise NotImplementedError("Phase 2 에서 구현한다")


async def fetch_agent_card(a2a_url: str, timeout_sec: int = 10) -> dict[str, Any]:
    """`/.well-known/agent-card.json` 조회 (인수 #6). Phase 2 에서 구현."""
    raise NotImplementedError("Phase 2 에서 구현한다")
