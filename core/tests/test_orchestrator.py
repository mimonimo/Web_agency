#!/usr/bin/env python3
"""상태기계 단위 테스트 — 순수 함수라 DB 없이 돈다 (BRIEF §15-1 의 보상).

    python3 core/tests/test_orchestrator.py

BRIEF §3.4 의 일시정지 규약을 하나씩 확인한다. 인수 #16~#22 의 근거다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import pipelines
from app.orchestrator import (
    Action,
    CycleView,
    Event,
    StepView,
    next_step,
)

ok = 0
ng = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global ok, ng
    if cond:
        ok += 1
        print(f"  ✅ {label}")
    else:
        ng += 1
        print(f"  ❌ {label}   {detail}")


def steps_from(name: str, statuses: dict[str, str] | None = None) -> tuple[StepView, ...]:
    """pipeline.yaml 을 읽어 StepView 튜플로. 기본은 전부 PENDING."""
    statuses = statuses or {}
    out = []
    for s in pipelines.load(name).steps:
        out.append(
            StepView(
                key=s.id,
                name=s.name,
                status=statuses.get(s.id, "PENDING"),
                role=s.role,
                type=s.type,
                parallel=s.parallel,
                on_reject_rewind_to=s.on_reject_rewind_to,
            )
        )
    return tuple(out)


def cyc(**kw) -> CycleView:
    base = dict(id=1, status="RUNNING", current_step=None,
                mode="auto", attempt_no=1, pipeline="web_delivery")
    base.update(kw)
    return CycleView(**base)


print("\n[파이프라인 로더]")
p = pipelines.load("web_delivery")
check("web_delivery 가 10단계", len(p.steps) == 10, f"실제 {len(p.steps)}")
check("S3 가 human_gate", p.step("S3").type == "human_gate")
check("S2 가 emits_specs", p.step("S2").emits_specs is True)
check("S6 반려 시 S5 로", p.step("S6").on_reject_rewind_to == "S5")
check("S8 반려 시 S2 로 (기획까지 되감음)", p.step("S8").on_reject_rewind_to == "S2")
check("S4 가 4개 역할 병렬", p.step("S4").parallel == ("designer", "dba", "backend", "sysadmin"))
check("kind=defect → web_defect", pipelines.for_kind("defect").name == "web_defect")
check("파이프라인 4종이 전부 읽힌다", len(pipelines.available()) == 4)


print("\n[start]")
t = next_step(cyc(status="READY"), steps_from("web_delivery"), Event.START)
check("READY → RUNNING, S1 실행", t.next_status == "RUNNING" and t.next_step == "S1"
      and t.action is Action.RUN_STEP, f"{t}")


print("\n[인수 #16 — pause 는 현재 step 을 자르지 않는다]")
st = steps_from("web_delivery", {"S1": "DONE", "S2": "RUNNING"})
t = next_step(cyc(current_step="S2"), st, Event.PAUSE)
check("실행 중이면 RUNNING 을 유지하고 pause 예약만 한다",
      t.next_status == "RUNNING" and t.args.get("pause_requested") is True, f"{t}")
check("메시지가 '끝까지 마친 뒤' 를 말한다", "끝까지" in t.note, t.note)

# 그 step 이 끝나면 그때 멈춘다
st = steps_from("web_delivery", {"S1": "DONE", "S2": "DONE"})
t = next_step(cyc(current_step="S2", pause_requested=True), st, Event.STEP_DONE,
              {"step": "S2"})
check("step 완료 후에야 PAUSED 가 된다", t.next_status == "PAUSED", f"{t}")
check("pause 예약이 해제된다", t.args.get("pause_requested") is False)

# 실행 중인 게 없으면 즉시 멈춘다
t = next_step(cyc(current_step="S2"), steps_from("web_delivery", {"S1": "DONE"}), Event.PAUSE)
check("실행 중이 없으면 즉시 PAUSED", t.next_status == "PAUSED", f"{t}")


print("\n[abort — 즉시 취소, 그 step 은 FAILED]")
st = steps_from("web_delivery", {"S1": "DONE", "S2": "RUNNING"})
t = next_step(cyc(current_step="S2"), st, Event.ABORT)
check("PAUSED + 현재 step 실패 처리 지시",
      t.next_status == "PAUSED" and t.action is Action.FAIL_CURRENT
      and t.args.get("step") == "S2", f"{t}")


print("\n[인수 #17 — resume 은 다음 PENDING 부터]")
st = steps_from("web_delivery", {"S1": "DONE", "S2": "DONE"})
t = next_step(cyc(status="PAUSED", current_step="S2"), st, Event.RESUME)
check("S3 으로 간다", t.next_step == "S3", f"{t}")
check("S3 은 human_gate 라 BLOCKED 가 된다",
      t.next_status == "BLOCKED" and t.action is Action.WAIT_HUMAN, f"{t}")


print("\n[인수 #13 — S3 도달 시 자동 BLOCKED]")
st = steps_from("web_delivery", {"S1": "DONE", "S2": "DONE"})
t = next_step(cyc(current_step="S2"), st, Event.STEP_DONE, {"step": "S2"})
check("S2 완료 → 자동으로 BLOCKED(S3)",
      t.next_status == "BLOCKED" and t.next_step == "S3", f"{t}")


print("\n[인수 #15 — 11개 전부 customized 되면 자동 재개]")
st = steps_from("web_delivery", {"S1": "DONE", "S2": "DONE", "S3": "WAITING_HUMAN"})
t = next_step(cyc(status="BLOCKED", current_step="S3"), st, Event.SPECS_ALL_CUSTOMIZED)
check("BLOCKED → RUNNING, S4 실행",
      t.next_status == "RUNNING" and t.next_step == "S4"
      and t.action is Action.RUN_STEP, f"{t}")


print("\n[인수 #18 — step 은 한 단계만 실행하고 PAUSED 복귀]")
st = steps_from("web_delivery", {"S1": "DONE"})
t = next_step(cyc(status="PAUSED", current_step="S1"), st, Event.STEP)
check("single_step 플래그를 세워 실행", t.args.get("single_step") is True
      and t.action is Action.RUN_STEP, f"{t}")
st = steps_from("web_delivery", {"S1": "DONE", "S2": "DONE"})
t = next_step(cyc(current_step="S2", single_step=True), st, Event.STEP_DONE, {"step": "S2"})
check("그 단계가 끝나면 PAUSED 로 돌아온다", t.next_status == "PAUSED", f"{t}")
check("single_step 플래그가 풀린다", t.args.get("single_step") is False)


print("\n[인수 #19 — 게이트 반려 → rewind_to + 재작업 티켓]")
st = steps_from("web_delivery",
                {k: "DONE" for k in ("S1", "S2", "S3", "S4", "S5")} | {"S6": "RUNNING"})
t = next_step(cyc(current_step="S6"), st, Event.GATE_REJECT,
              {"step": "S6", "reason": "로그인 실패 시 500"})
check("S5 로 되감는다", t.next_step == "S5" and t.next_status == "RUNNING", f"{t}")
check("이후 산출물 무효화 지시", t.action is Action.INVALIDATE_FROM)
check("재작업 티켓 생성 지시", t.args.get("create_ticket") is True)
check("사유가 실린다", t.args.get("reason") == "로그인 실패 시 500")

# 고객 검수 반려는 기획(S2)까지 되감는다
st = steps_from("web_delivery", {k: "DONE" for k in
                                 ("S1", "S2", "S3", "S4", "S5", "S6", "S7")} | {"S8": "RUNNING"})
t = next_step(cyc(current_step="S8"), st, Event.GATE_REJECT, {"step": "S8"})
check("고객 검수 반려는 S2(기획)로 되감는다", t.next_step == "S2", f"{t}")


print("\n[인수 #20 — rewind]")
st = steps_from("web_delivery", {k: "DONE" for k in ("S1", "S2", "S3", "S4", "S5", "S6")})
t = next_step(cyc(current_step="S6"), st, Event.REWIND, {"step_key": "S5"})
check("S5 로 되감고 거기서 재개", t.next_step == "S5" and t.next_status == "RUNNING"
      and t.action is Action.INVALIDATE_FROM, f"{t}")
t = next_step(cyc(current_step="S6"), st, Event.REWIND, {"step_key": "S99"})
check("없는 단계로 되감으면 아무 일도 안 한다", t.action is Action.NOOP, f"{t}")


print("\n[인수 #21·#22 — reset 2종. ★ 기본값이 keep_specs=True 여야 한다]")
st = steps_from("web_delivery", {"S1": "DONE", "S2": "DONE"})
t = next_step(cyc(current_step="S2"), st, Event.RESET)          # 인자 없이 호출
check("★ 기본값이 keep_specs=True", t.args.get("keep_specs") is True, f"{t}")
check("READY 로 돌아간다", t.next_status == "READY", f"{t}")
check("AGENT.md 를 지킨다고 말한다", "유지" in t.note, t.note)
t = next_step(cyc(current_step="S2"), st, Event.RESET, {"keep_specs": False})
check("keep_specs=False 면 초안으로 되돌린다", t.args.get("keep_specs") is False
      and "초안" in t.note, f"{t}")
# 어느 상태에서든 reset 을 받는다 (BRIEF §3.2)
for s in ("READY", "RUNNING", "PAUSED", "BLOCKED", "FAILED", "DONE"):
    t = next_step(cyc(status=s), st, Event.RESET)
    if t.next_status != "READY":
        check(f"{s} 에서 reset", False, f"{t}")
        break
else:
    check("어느 상태에서든 reset → READY", True)


print("\n[끝까지 완주]")
allsteps = [s.id for s in pipelines.load("web_delivery").steps]
done = {}
cur = "S1"
guard = 0
status = "RUNNING"
while guard < 50:
    guard += 1
    done[cur] = "DONE"
    st = steps_from("web_delivery", done)
    t = next_step(cyc(current_step=cur, status=status), st, Event.STEP_DONE, {"step": cur})
    status = t.next_status
    if t.next_status == "DONE":
        break
    if t.next_status == "BLOCKED":
        # 사람 게이트 — 강제 통과시킨다
        done[t.next_step] = "DONE"
        st = steps_from("web_delivery", done)
        t = next_step(cyc(current_step=t.next_step, status="BLOCKED"), st,
                      Event.SPECS_ALL_CUSTOMIZED)
        status = t.next_status
    cur = t.next_step
check("S1 → S10 을 끝까지 돌면 DONE", status == "DONE", f"status={status}")
check("모든 단계를 거쳤다", set(done) == set(allsteps),
      f"누락: {set(allsteps) - set(done)}")


print("\n[defect 파이프라인은 경로가 다르다]")
d = pipelines.load("web_defect")
check("defect 는 S1 → S6 → S5 → S6R",
      [s.id for s in d.steps] == ["S1", "S6", "S5", "S6R"],
      f"{[s.id for s in d.steps]}")
s_ = pipelines.load("web_security")
check("security 는 S7(보안)이 S5(수정)보다 먼저",
      [x.id for x in s_.steps].index("S7") < [x.id for x in s_.steps].index("S5"))


print("\n" + "─" * 40)
print(f"통과 {ok} · 실패 {ng}")
if ng:
    print("==> FAIL")
    sys.exit(1)
print("==> PASS")
