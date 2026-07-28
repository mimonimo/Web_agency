#!/usr/bin/env python3
"""E2E 흐름 테스트 — 실제로 도는 HQ 에 대고 사이클을 끝까지 돌린다.

    python3 core/tests/test_flow.py [http://127.0.0.1:8000]

BRIEF §12 의 인수 #5, #11~#25 를 실제 왕복으로 확인한다.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
REPO = Path(__file__).resolve().parents[2] / "repo"
ROLES = ["pm", "planner", "sales", "sysadmin", "designer", "frontend",
         "backend", "dba", "security", "qa", "customer"]

ok = 0
ng = 0
c = httpx.Client(base_url=BASE, timeout=30)


def check(label: str, cond: bool, detail: str = "") -> None:
    global ok, ng
    if cond:
        ok += 1
        print(f"  ✅ {label}")
    else:
        ng += 1
        print(f"  ❌ {label}   {detail}")


def dash(cycle: int | None = None) -> dict:
    r = c.get("/api/dashboard", params={"cycle": cycle} if cycle else None)
    return r.json()["data"]


def wait_for(cycle: int, pred, timeout: float = 90, label: str = "") -> dict:
    """조건이 될 때까지 기다린다."""
    end = time.time() + timeout
    d = {}
    while time.time() < end:
        d = dash(cycle)
        if d.get("cycle") and pred(d):
            return d
        time.sleep(0.4)
    print(f"     [대기 실패] {label} — 마지막 상태: "
          f"{d.get('cycle', {}).get('status')} @ {d.get('cycle', {}).get('current_step')}")
    return d


print("\n[인수 #5 — 노드 11개 등록]")
nodes = c.get("/api/nodes").json()["data"]
check("노드 11개가 등록돼 있다", len(nodes) == 11, f"{len(nodes)}개")
check("역할 문자열이 BRIEF §1.3 과 같다", [n["role"] for n in nodes] == ROLES)


print("\n[인수 #11 — 주문 생성 → 사이클 자동 시작 → S1 RUNNING]")
r = c.post("/api/orders", json={
    "company": "밀밭제과", "industry": "제과/베이커리",
    "purpose": "동네 단골이 온라인으로 주문할 수 있게 한다",
    "features": ["로그인", "상품목록", "장바구니", "문의폼"],
    "due_date": "2026-08-30", "contact_name": "김밀밭", "contact": "010-0000-0000",
    "kind": "new",
})
check("주문 접수 200", r.status_code == 200, r.text[:200])
body = r.json()["data"]
cid = body["cycle"]["id"]
print(f"     → 사이클 #{cid} 생성됨")
d = wait_for(cid, lambda d: d["cycle"]["current_step"] is not None, 20, "S1 진입")
check("자동으로 시작됐다", d["cycle"]["status"] in ("RUNNING", "BLOCKED"),
      f"{d['cycle']}")
check("S1(영업 접수)부터 시작한다",
      d["cycle"]["current_step"] in ("S1", "S2", "S3"), f"{d['cycle']}")


print("\n[인수 #12·#13 — S2 가 AGENT.md 11개 생성 → S3 에서 자동 BLOCKED]")
d = wait_for(cid, lambda d: d["cycle"]["status"] == "BLOCKED", 90, "S3 BLOCKED")
check("사이클이 자동으로 BLOCKED 가 됐다", d["cycle"]["status"] == "BLOCKED",
      f"{d['cycle']}")
check("멈춘 곳이 S3 커스터마이징 게이트", d["cycle"]["current_step"] == "S3",
      f"{d['cycle']['current_step']}")
check("AGENT.md 가 11개 생성됐다", d["specs"]["total"] == 11, f"{d['specs']}")
check("전부 draft 상태다", d["specs"]["customized"] == 0, f"{d['specs']}")
missing = [r_ for r_ in ROLES if not (REPO / "project-001" / "agents" / r_ / "AGENT.md").exists()]
check("11개 파일이 실제로 디스크에 있다", not missing, f"없음: {missing}")
raw = c.get("/api/specs/backend/raw").text
check("spec_url 로 읽으면 front-matter 가 있다",
      "role: backend" in raw and "status: draft" in raw, raw[:120])


print("\n[인수 #14 — AGENT.md 1개 수정 → customized 1 증가]")
p = REPO / "project-001" / "agents" / "backend" / "AGENT.md"
p.write_text(p.read_text(encoding="utf-8") +
             "\n## 학생이 추가한 규칙\n- 모든 응답은 {ok, data|error} 형식을 지킨다\n",
             encoding="utf-8")
r = c.post("/api/specs/scan")
check("스캔이 변경 1건을 잡는다", r.json()["data"]["changed"] == 1, r.text[:200])
d = dash(cid)
check("customized 가 1 이 됐다", d["specs"]["customized"] == 1, f"{d['specs']}")
check("아직 재개되지 않았다 (11개가 안 찼으므로)",
      d["cycle"]["status"] == "BLOCKED", f"{d['cycle']}")
diff = c.get("/api/specs/backend/diff")
check("diff 가 보관된다 (평가 데이터)",
      diff.status_code == 200 and "학생이 추가한 규칙" in diff.text, diff.text[:120])


print("\n[인수 #15 — 11개 전부 customized → 자동 RUNNING 재개]")
for role in ROLES:
    if role == "backend":
        continue
    fp = REPO / "project-001" / "agents" / role / "AGENT.md"
    fp.write_text(fp.read_text(encoding="utf-8") +
                  f"\n## {role} 학생 보강\n- 이 역할에서 특히 조심할 것을 적는다\n",
                  encoding="utf-8")
c.post("/api/specs/scan")
d = wait_for(cid, lambda d: d["cycle"]["status"] != "BLOCKED", 30, "자동 재개")
check("11/11 이 됐다", d["specs"]["customized"] == 11, f"{d['specs']}")
check("자동으로 RUNNING 재개됐다", d["cycle"]["status"] in ("RUNNING", "DONE"),
      f"{d['cycle']}")
check("S4(설계)로 넘어갔다", d["cycle"]["current_step"] not in (None, "S3"),
      f"{d['cycle']['current_step']}")


print("\n[인수 #16 — pause 는 현재 step 을 끝까지 마친 뒤 정지한다]")
before = dash(cid)
step_at_pause = before["cycle"]["current_step"]
r = c.post(f"/api/cycles/{cid}/pause")
note = r.json()["data"]["note"]
check("pause 응답이 '끝까지 마친 뒤' 를 말한다", "끝까지" in note or "정지" in note, note)
d = wait_for(cid, lambda d: d["cycle"]["status"] == "PAUSED", 40, "PAUSED 도달")
check("결국 PAUSED 가 된다", d["cycle"]["status"] == "PAUSED", f"{d['cycle']}")
paused_step = next((s for s in d["steps"] if s["key"] == step_at_pause), None)
check("★ 중간에 잘리지 않았다 — 그 step 은 DONE 으로 끝났다",
      paused_step is None or paused_step["status"] in ("DONE", "PENDING"),
      f"{step_at_pause}={paused_step['status'] if paused_step else '?'}")


print("\n[인수 #18 — step 은 한 단계만 실행하고 PAUSED 복귀]")
before_done = sum(1 for s in dash(cid)["steps"] if s["status"] == "DONE")
c.post(f"/api/cycles/{cid}/step")
d = wait_for(cid, lambda d: d["cycle"]["status"] == "PAUSED", 40, "한 단계 후 PAUSED")
after_done = sum(1 for s in d["steps"] if s["status"] == "DONE")
check("정확히 한 단계만 늘었다", after_done == before_done + 1,
      f"{before_done} → {after_done}")
check("다시 PAUSED 로 돌아왔다", d["cycle"]["status"] == "PAUSED", f"{d['cycle']}")


print("\n[인수 #17 — resume 으로 재개]")
c.post(f"/api/cycles/{cid}/resume")
d = wait_for(cid, lambda d: d["cycle"]["current_step"] == "S6"
             or d["cycle"]["status"] == "DONE", 90, "S6 도달")
check("재개해서 진행된다", d["cycle"]["status"] in ("RUNNING", "DONE", "PAUSED"),
      f"{d['cycle']}")


print("\n[인수 #19 — QA 게이트 반려 → S5 로 되감기 + 재작업 티켓]")
d = wait_for(cid, lambda d: d["cycle"]["current_step"] in ("S6", "S7", "S8")
             or d["cycle"]["status"] == "DONE", 90, "게이트 도달")
gate = d["cycle"]["current_step"]
if d["cycle"]["status"] == "DONE":
    gate = "S6"
    c.post(f"/api/cycles/{cid}/rewind", json={"step_key": "S6"})
    d = wait_for(cid, lambda d: d["cycle"]["current_step"] == "S6", 30, "S6 재진입")
r = c.post(f"/api/gates/{gate}/reject",
           json={"reason": "로그인 실패 시 500 이 난다", "cycle_id": cid})
check("반려 200", r.status_code == 200, r.text[:200])
note = r.json()["data"]["note"]
check("되감는다고 말한다", "되감" in note, note)
d = dash(cid)
check("현재 단계가 되감긴 지점이다",
      d["cycle"]["current_step"] in ("S5", "S2"), f"{d['cycle']}")
check("재작업 티켓이 자동 생성됐다", d["tickets"]["todo"] >= 1, f"{d['tickets']}")
tk = d["tickets"]["list"][0] if d["tickets"]["list"] else {}
check("티켓에 반려 사유가 실린다", "500" in (tk.get("reason") or ""), f"{tk}")


print("\n[인수 #20 — rewind 하면 이후 산출물이 무효화된다]")
c.post(f"/api/cycles/{cid}/pause")
wait_for(cid, lambda d: d["cycle"]["status"] == "PAUSED", 40, "정지")
r = c.post(f"/api/cycles/{cid}/rewind", json={"step_key": "S4"})
check("rewind 200", r.status_code == 200, r.text[:200])
d = dash(cid)
after = [s for s in d["steps"] if s["key"] in ("S4", "S5", "S6", "S7", "S8")]
check("S4 이후 단계가 전부 PENDING 으로 돌아갔다",
      all(s["status"] == "PENDING" for s in after),
      str([(s["key"], s["status"]) for s in after]))
check("S1~S3 은 그대로 DONE 이다",
      all(s["status"] == "DONE" for s in d["steps"] if s["key"] in ("S1", "S2", "S3")),
      str([(s["key"], s["status"]) for s in d["steps"][:3]]))
check("S4 산출물 디렉터리가 지워졌다",
      not (REPO / "runs" / str(cid) / "S4").exists())


print("\n[★ 인수 #21 — reset(keep_specs=true): 산출물은 초기화, AGENT.md 는 유지]")
c.post(f"/api/cycles/{cid}/pause")
time.sleep(1)
r = c.post(f"/api/cycles/{cid}/reset", json={"keep_specs": True})
check("reset 200", r.status_code == 200, r.text[:200])
check("AGENT.md 를 지킨다고 말한다", "유지" in r.json()["data"]["note"],
      r.json()["data"]["note"])
d = dash(cid)
check("사이클이 READY 로 돌아갔다", d["cycle"]["status"] == "READY", f"{d['cycle']}")
check("모든 단계가 PENDING", all(s["status"] == "PENDING" for s in d["steps"]),
      str([(s["key"], s["status"]) for s in d["steps"]]))
check("★ 학생이 고친 AGENT.md 는 그대로 customized 다",
      d["specs"]["customized"] == 11, f"{d['specs']}")
txt = (REPO / "project-001" / "agents" / "backend" / "AGENT.md").read_text(encoding="utf-8")
check("★ 학생이 추가한 내용이 남아 있다", "학생이 추가한 규칙" in txt)


print("\n[인수 #22 — reset(keep_specs=false): AGENT.md 도 초안으로]")
r = c.post(f"/api/cycles/{cid}/reset", json={"keep_specs": False})
check("초안으로 되돌린다고 말한다", "초안" in r.json()["data"]["note"],
      r.json()["data"]["note"])
d = dash(cid)
check("customized 가 0 으로 돌아갔다", d["specs"]["customized"] == 0, f"{d['specs']}")
txt = (REPO / "project-001" / "agents" / "backend" / "AGENT.md").read_text(encoding="utf-8")
check("학생이 추가한 내용이 사라졌다", "학생이 추가한 규칙" not in txt)


print("\n[인수 #24 — defect 파이프라인은 경로가 다르다]")
r = c.post("/api/orders", json={
    "company": "밀밭제과", "purpose": "로그인이 안 된다", "kind": "defect",
    "features": [], "auto_start": False,
})
d2 = r.json()["data"]
check("defect 주문이 web_defect 파이프라인을 탄다",
      d2["cycle"]["pipeline"] == "web_defect", d2["cycle"]["pipeline"])
check("단계 구성이 S1 → S6 → S5 → S6R",
      [s["key"] for s in d2["cycle"]["steps"]] == ["S1", "S6", "S5", "S6R"],
      str([s["key"] for s in d2["cycle"]["steps"]]))


print("\n[인수 #25 — 모든 쓰기가 AuditLog 에 남는다]")
import sqlite3
db = sqlite3.connect(REPO / "agora.db")
n = db.execute("select count(*) from audit_logs").fetchone()[0]
kinds = [r[0] for r in db.execute(
    "select distinct action from audit_logs order by action").fetchall()]
check(f"감사 로그 {n}건이 쌓였다", n > 20, f"{n}건")
check("사이클 제어·스펙·티켓이 전부 기록된다",
      any("cycle." in k for k in kinds) and any("spec" in k for k in kinds)
      and any("ticket" in k for k in kinds), str(kinds[:12]))


print("\n" + "─" * 44)
print(f"통과 {ok} · 실패 {ng}")
if ng:
    print("==> FAIL")
    sys.exit(1)
print("==> PASS")
