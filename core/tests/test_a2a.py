#!/usr/bin/env python3
"""A2A 왕복 테스트 — 실제 학생 노드의 Hermes 를 한 번 돌려본다.

    python3 core/tests/test_a2a.py [role]      # 기본 backend

BRIEF §12 인수 #6, #8, #9 를 확인한다.
로컬 모델(gpt-oss:120b)이라 **한 번 왕복에 수 분 걸린다.** 정상이다.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app import a2a_client as a2a

HQ = "http://127.0.0.1:8000"
ROLE = sys.argv[1] if len(sys.argv) > 1 else "backend"

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


async def main() -> int:
    async with httpx.AsyncClient(timeout=20) as c:
        nodes = (await c.get(f"{HQ}/api/nodes")).json()["data"]
    node = next((n for n in nodes if n["role"] == ROLE), None)
    if node is None:
        print(f"{ROLE} 노드가 등록돼 있지 않다")
        return 1
    url = node["a2a_url"]
    print(f"\n대상: {ROLE} @ {url}")

    print("\n[인수 #6 — HQ 가 노드의 에이전트 카드를 조회한다]")
    card = await a2a.fetch_agent_card(url)
    check("카드를 받았다", bool(card))
    check(f"이름이 agora-{ROLE}", card.get("name") == f"agora-{ROLE}", card.get("name"))
    check("skills 가 있다", bool(card.get("skills")), str(card.get("skills"))[:80])
    check("A2A 카드 필수 필드가 있다",
          all(k in card for k in ("url", "version", "capabilities",
                                  "defaultInputModes", "defaultOutputModes")))

    print("\n[인수 #8 — message/send → tasks/get 폴링 → completed 수신 (1건 왕복)]")
    print("     로컬 모델이라 수 분 걸립니다. 기다리는 중...")
    msgs = await _messages()
    before_id = max((m['id'] for m in msgs), default=0)

    req = a2a.TaskRequest(
        role=ROLE, cycle_id=0, step_id="T1", step_name="왕복 확인",
        task="smoke_test",
        spec_url=f"{HQ}/api/specs/{ROLE}/raw",
        outputs=("PING.md",),
        timeout_sec=900,
    )
    t0 = time.time()
    sent = await a2a.send_message(url, req)
    check("message/send 가 taskId 를 준다", bool(sent.task_id), str(sent))
    check("즉시 working 상태로 응답한다", sent.state == "working", sent.state)

    state = sent.state
    result = None
    while time.time() - t0 < 900:
        await asyncio.sleep(5)
        result = await a2a.get_task(url, sent.task_id)
        if result.state != state:
            print(f"     [{int(time.time() - t0):>3}초] {state} → {result.state}")
            state = result.state
        if result.state in ("completed", "failed", "canceled"):
            break

    dur = int(time.time() - t0)
    check(f"completed 를 받았다 ({dur}초)", result and result.state == "completed",
          (result.error or result.state) if result else "응답 없음")
    if result and result.state == "completed":
        check("산출물이 있다", bool(result.artifacts),
              f"{len(result.artifacts)}건")
        names = [a["name"] for a in result.artifacts]
        print(f"     산출물: {', '.join(names) or '(없음)'}")
        body = next((a["text"] for a in result.artifacts if a["text"].strip()), "")
        check("산출물에 실제 내용이 들어 있다", len(body.strip()) > 20,
              repr(body[:80]))
        print(f"     미리보기: {body.strip()[:160]}...")

    print("\n[인수 #9 — 노드가 보낸 메시지가 HQ 에 미러링된다]")
    after = await _messages()
    after_id = max((m["id"] for m in after), default=0)
    # 개수가 아니라 id 로 본다 — limit 에 걸리면 개수는 안 늘어난다
    check("미러링된 메시지가 늘었다", after_id > before_id,
          f"id {before_id} → {after_id}")
    froms = {m["from"] for m in after[-6:]}
    check(f"{ROLE} 이 보낸 메시지가 있다", ROLE in froms, str(froms))

    print("\n" + "─" * 40)
    print(f"통과 {ok} · 실패 {ng}")
    print("==> PASS" if ng == 0 else "==> FAIL")
    return 1 if ng else 0


async def _messages() -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as c:
        return (await c.get(f"{HQ}/api/messages", params={"limit": 50})).json()["data"]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
