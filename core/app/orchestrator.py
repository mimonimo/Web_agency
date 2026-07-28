"""★ 상태기계. 이 파일이 심장이다 (BRIEF §2, §3).

──────────────────────────────────────────────────────────────────────────
규약 (BRIEF §15-1) — 어기면 테스트가 불가능해진다.

    상태 전이 로직을 DB 접근과 섞지 마라.
    이 모듈의 함수는 **순수 함수**다. Session 을 인자로 받지 않고,
    import 하지 않고, 파일도 건드리지 않는다.
    입력은 값(dataclass), 출력은 "무엇을 해야 하는가"(Transition) 뿐이다.

    DB 반영과 부수효과는 routers/cycles.py 가 Transition 을 보고 수행한다.
──────────────────────────────────────────────────────────────────────────

Phase 3a 에서 본체를 구현한다. 지금은 타입과 시그니처만 확정한다 —
이후 5개 세션이 이 계약 위에 얹히므로 여기가 흔들리면 전부 다시 만들어야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Event(str, Enum):
    """사이클에 가해지는 외부 자극 (BRIEF §3.4)."""

    START = "start"
    PAUSE = "pause"          # 현재 step 을 끝까지 마친 뒤 정지 (graceful)
    ABORT = "abort"          # 현재 step 을 즉시 취소. 그 step 은 FAILED
    RESUME = "resume"        # 다음 PENDING step 부터 재개
    STEP = "step"            # 한 단계만 실행하고 다시 PAUSED
    REWIND = "rewind"        # 지정 step 이후 산출물 무효화 후 거기서 재개
    RESET = "reset"          # 처음부터. keep_specs 2종
    STEP_DONE = "step_done"
    STEP_FAILED = "step_failed"
    GATE_REJECT = "gate_reject"
    SPECS_ALL_CUSTOMIZED = "specs_all_customized"  # S3 자동 재개 트리거


class Action(str, Enum):
    """Transition 이 호출자에게 시키는 일."""

    NOOP = "noop"
    RUN_STEP = "run_step"
    WAIT_HUMAN = "wait_human"
    INVALIDATE_FROM = "invalidate_from"   # 이 step 이후 산출물 무효화
    CREATE_REWORK_TICKET = "create_rework_ticket"
    FINISH = "finish"


@dataclass(frozen=True)
class StepView:
    """Step 의 값 스냅샷. ORM 객체를 여기 넘기지 않는다."""

    key: str
    name: str
    status: str
    role: str | None = None
    type: str | None = None          # None | "gate" | "human_gate"
    parallel: tuple[str, ...] = ()
    on_reject_rewind_to: str | None = None


@dataclass(frozen=True)
class CycleView:
    """Cycle 의 값 스냅샷."""

    id: int
    status: str
    current_step: str | None
    mode: str
    attempt_no: int
    pipeline: str


@dataclass(frozen=True)
class Transition:
    """상태기계의 결정. 호출자는 이대로 DB 를 고치고 부수효과를 낸다."""

    next_status: str
    next_step: str | None = None
    action: Action = Action.NOOP
    # 예: {"rewind_to": "S5", "keep_specs": True, "reason": "..."}
    args: dict[str, Any] = field(default_factory=dict)
    # 사람이 읽는 로그. 에러 메시지는 한국어로 (BRIEF §15-4)
    note: str = ""


def next_step(
    cycle: CycleView,
    steps: tuple[StepView, ...],
    event: Event,
    payload: dict[str, Any] | None = None,
) -> Transition:
    """상태기계 본체. 순수 함수.

    Phase 3a 에서 구현한다. 여기서 반드시 지켜야 할 것 (BRIEF §3.4):

    - ``pause`` 는 **현재 step 을 끝까지 마친 뒤** 정지한다. 중간에 자르지 않는다.
      (인수 #16 — 중간 절단이 아님을 로그로 증명해야 한다)
    - ``abort`` 만 현재 step 을 즉시 취소하고 그 step 을 FAILED 로 만든다.
    - ``reset`` 의 기본값은 ``keep_specs=True``. 학생이 30분 걸려 고친 AGENT.md 를
      리셋 버튼 한 번에 날리면 수업이 망한다 (BRIEF §3.4 경고).
    - 게이트 반려는 ``on_reject.rewind_to`` 가 가리키는 step 으로 되감고
      재작업 티켓을 만든다 (인수 #19).
    """
    raise NotImplementedError("Phase 3a 에서 구현한다")
