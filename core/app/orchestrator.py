"""★ 상태기계. 이 파일이 심장이다 (BRIEF §2, §3).

──────────────────────────────────────────────────────────────────────────
규약 (BRIEF §15-1) — 어기면 테스트가 불가능해진다.

    상태 전이 로직을 DB 접근과 섞지 마라.
    이 모듈의 함수는 **순수 함수**다. Session 을 인자로 받지 않고,
    import 하지 않고, 파일도 건드리지 않는다.
    입력은 값(dataclass), 출력은 "무엇을 해야 하는가"(Transition) 뿐이다.

    DB 반영과 부수효과는 routers/cycles.py · runner.py 가 Transition 을 보고 수행한다.
──────────────────────────────────────────────────────────────────────────
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
    FAIL_CURRENT = "fail_current"
    FINISH = "finish"


# 상태 문자열 — models.CycleStatus / StepStatus 와 값이 같다.
# 순수성을 위해 여기서 models 를 import 하지 않는다.
READY, RUNNING, PAUSED, BLOCKED, FAILED, DONE = (
    "READY", "RUNNING", "PAUSED", "BLOCKED", "FAILED", "DONE",
)
S_PENDING, S_RUNNING, S_DONE = "PENDING", "RUNNING", "DONE"
S_REJECTED, S_FAILED, S_SKIPPED, S_WAIT = (
    "REJECTED", "FAILED", "SKIPPED", "WAITING_HUMAN",
)

HUMAN_GATE = "human_gate"
GATE = "gate"


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
    mode: str = "auto"
    attempt_no: int = 1
    pipeline: str = "web_delivery"
    # 사람이 pause 를 눌렀는가. graceful pause 의 기억은 Cycle 에 저장된다.
    pause_requested: bool = False
    # `한 단계만` 모드로 돌고 있는가.
    single_step: bool = False


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


# ── 조회 헬퍼 (전부 순수) ──────────────────────────────────────────────
def _index(steps: tuple[StepView, ...], key: str | None) -> int:
    for i, s in enumerate(steps):
        if s.key == key:
            return i
    return -1


def _first_pending(steps: tuple[StepView, ...], start: int = 0) -> StepView | None:
    for s in steps[start:]:
        if s.status in (S_PENDING, S_REJECTED, S_FAILED):
            return s
    return None


def _running(steps: tuple[StepView, ...]) -> StepView | None:
    for s in steps:
        if s.status == S_RUNNING:
            return s
    return None


def _is_gate(step: StepView) -> bool:
    return step.type in (GATE, HUMAN_GATE)


def _enter(step: StepView | None, cycle: CycleView, note_prefix: str = "") -> Transition:
    """다음에 실행할 step 이 정해졌을 때의 공통 처리.

    사람 게이트면 멈추고, 아니면 실행시킨다.
    """
    if step is None:
        return Transition(DONE, None, Action.FINISH, note=f"{note_prefix}모든 단계를 마쳤다")

    if step.type == HUMAN_GATE:
        return Transition(
            BLOCKED, step.key, Action.WAIT_HUMAN,
            args={"wait_step": step.key},
            note=f"{note_prefix}{step.key} {step.name} — 사람을 기다린다",
        )

    return Transition(
        RUNNING, step.key, Action.RUN_STEP,
        note=f"{note_prefix}{step.key} {step.name} 실행",
    )


# ── 본체 ───────────────────────────────────────────────────────────────
def next_step(
    cycle: CycleView,
    steps: tuple[StepView, ...],
    event: Event,
    payload: dict[str, Any] | None = None,
) -> Transition:
    """상태기계 본체. 순수 함수.

    반드시 지켜야 할 것 (BRIEF §3.4):

    - ``pause`` 는 **현재 step 을 끝까지 마친 뒤** 정지한다. 중간에 자르지 않는다 (인수 #16).
    - ``abort`` 만 현재 step 을 즉시 취소하고 그 step 을 FAILED 로 만든다.
    - ``reset`` 의 기본값은 ``keep_specs=True``. 학생이 30분 걸려 고친 AGENT.md 를
      리셋 버튼 한 번에 날리면 수업이 망한다 (BRIEF §3.4 경고).
    - 게이트 반려는 ``on_reject.rewind_to`` 가 가리키는 step 으로 되감고
      재작업 티켓을 만든다 (인수 #19).
    """
    p = payload or {}

    # ── reset — 어느 상태에서든 받는다 (BRIEF §3.2) ────────────────────
    if event is Event.RESET:
        keep = bool(p.get("keep_specs", True))   # ⚠️ 기본값은 반드시 True
        return Transition(
            READY, None, Action.INVALIDATE_FROM,
            args={"from_step": steps[0].key if steps else None, "keep_specs": keep,
                  "reset": True},
            note=("처음부터 — AGENT.md 는 학생이 고친 그대로 유지한다"
                  if keep else
                  "처음부터 — AGENT.md 도 기획 초안으로 되돌린다"),
        )

    # ── start ────────────────────────────────────────────────────────
    if event is Event.START:
        if cycle.status not in (READY, PAUSED):
            return Transition(cycle.status, cycle.current_step, Action.NOOP,
                              note=f"이미 {cycle.status} 상태다")
        return _enter(_first_pending(steps), cycle)

    # ── pause — graceful. 현재 step 을 자르지 않는다 ──────────────────
    if event is Event.PAUSE:
        cur = _running(steps)
        if cur is not None:
            return Transition(
                RUNNING, cur.key, Action.NOOP,
                args={"pause_requested": True},
                note=f"{cur.key} 를 끝까지 마친 뒤 정지한다",
            )
        return Transition(PAUSED, cycle.current_step, Action.NOOP,
                          args={"pause_requested": False},
                          note="정지했다")

    # ── abort — 즉시 취소. 그 step 은 FAILED ─────────────────────────
    if event is Event.ABORT:
        cur = _running(steps)
        return Transition(
            PAUSED, cycle.current_step, Action.FAIL_CURRENT,
            args={"step": cur.key if cur else None, "pause_requested": False},
            note=(f"{cur.key} 를 즉시 취소했다" if cur else "실행 중인 단계가 없다"),
        )

    # ── resume ───────────────────────────────────────────────────────
    if event is Event.RESUME:
        if cycle.status not in (PAUSED, BLOCKED, READY, FAILED):
            return Transition(cycle.status, cycle.current_step, Action.NOOP,
                              note=f"{cycle.status} 에서는 재개할 수 없다")
        # 사람 게이트에서 강사가 강제 통과시킨 경우 그 게이트는 건너뛴다
        idx = _index(steps, cycle.current_step)
        if idx >= 0 and steps[idx].type == HUMAN_GATE and cycle.status == BLOCKED:
            nxt = _first_pending(steps, idx + 1)
            t = _enter(nxt, cycle, note_prefix="게이트 통과 — ")
            return Transition(t.next_status, t.next_step, t.action,
                              args={**t.args, "complete_step": steps[idx].key},
                              note=t.note)
        return _enter(_first_pending(steps), cycle,
                      note_prefix="재개 — ")

    # ── step — 한 단계만 실행하고 다시 PAUSED (인수 #18) ─────────────
    if event is Event.STEP:
        nxt = _first_pending(steps)
        t = _enter(nxt, cycle, note_prefix="한 단계만 — ")
        return Transition(t.next_status, t.next_step, t.action,
                          args={**t.args, "single_step": True}, note=t.note)

    # ── step 완료 ────────────────────────────────────────────────────
    if event is Event.STEP_DONE:
        done_key = p.get("step") or cycle.current_step
        idx = _index(steps, done_key)
        nxt = _first_pending(steps, idx + 1)

        if cycle.pause_requested:
            return Transition(
                PAUSED, nxt.key if nxt else None, Action.NOOP,
                args={"pause_requested": False},
                note=f"{done_key} 를 끝까지 마쳤다. 요청대로 정지한다",
            )
        if cycle.single_step:
            return Transition(
                PAUSED, nxt.key if nxt else None, Action.NOOP,
                args={"single_step": False},
                note=f"{done_key} 한 단계만 실행했다. 정지한다",
            )
        return _enter(nxt, cycle)

    # ── step 실패 ────────────────────────────────────────────────────
    if event is Event.STEP_FAILED:
        return Transition(
            FAILED, cycle.current_step, Action.NOOP,
            args={"error": p.get("error", "")},
            note=f"{cycle.current_step} 실패 — {p.get('error', '사유 미상')}",
        )

    # ── 게이트 반려 → 되감기 + 재작업 티켓 (인수 #19) ────────────────
    if event is Event.GATE_REJECT:
        gate_key = p.get("step") or cycle.current_step
        gi = _index(steps, gate_key)
        gate = steps[gi] if gi >= 0 else None
        target = p.get("rewind_to") or (gate.on_reject_rewind_to if gate else None)
        if target is None or _index(steps, target) < 0:
            return Transition(cycle.status, cycle.current_step, Action.NOOP,
                              note=f"되감을 단계를 찾지 못했다: {target!r}")
        return Transition(
            RUNNING, target, Action.INVALIDATE_FROM,
            args={
                "from_step": target,
                "reject_step": gate_key,
                "reason": p.get("reason", ""),
                "create_ticket": True,
                "priority": p.get("priority"),
            },
            note=f"{gate_key} 반려 → {target} 로 되감는다",
        )

    # ── 되감기 (인수 #20) ────────────────────────────────────────────
    if event is Event.REWIND:
        target = p.get("step_key")
        if target is None or _index(steps, target) < 0:
            return Transition(cycle.status, cycle.current_step, Action.NOOP,
                              note=f"그런 단계가 없다: {target!r}")
        return Transition(
            RUNNING, target, Action.INVALIDATE_FROM,
            args={"from_step": target},
            note=f"{target} 이후 산출물을 무효화하고 거기서 재개한다",
        )

    # ── 11개 AGENT.md 가 전부 customized → 자동 재개 (인수 #15) ──────
    if event is Event.SPECS_ALL_CUSTOMIZED:
        idx = _index(steps, cycle.current_step)
        if idx < 0 or steps[idx].type != HUMAN_GATE:
            return Transition(cycle.status, cycle.current_step, Action.NOOP,
                              note="커스터마이징 게이트에 있지 않다")
        nxt = _first_pending(steps, idx + 1)
        t = _enter(nxt, cycle, note_prefix="11개 전부 커스터마이징 완료 — ")
        return Transition(t.next_status, t.next_step, t.action,
                          args={**t.args, "complete_step": steps[idx].key},
                          note=t.note)

    return Transition(cycle.status, cycle.current_step, Action.NOOP,
                      note=f"처리하지 않는 이벤트: {event}")
