#!/usr/bin/env python3
"""학생 편집 흐름 테스트 — 웹 편집기로 AGENT.md 를 고치는 경로를 확인한다.

    python3 core/tests/test_edit.py

인수 #14(1개 수정 → 카운터 1 증가), #15(11개 완료 → 자동 재개), #30(카운터 실시간)
을 **학생이 실제로 쓰는 경로(PUT /api/specs/{role}/raw)** 로 확인한다.
"""

from __future__ import annotations

import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
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


def dash() -> dict:
    return c.get("/api/dashboard").json()["data"]


print("\n[준비 — 주문을 넣고 S3 게이트까지 간다]")
r = c.post("/api/orders", json={
    "company": "밀밭제과", "industry": "제과/베이커리",
    "purpose": "동네 단골이 온라인으로 빵을 예약 주문할 수 있게 한다",
    "features": ["로그인", "상품목록", "장바구니", "문의폼"],
    "due_date": "2026-08-30", "contact_name": "김밀밭", "contact": "010-1234-5678",
})
cid = r.json()["data"]["cycle"]["id"]
end = time.time() + 300
while time.time() < end:
    d = dash()
    if d["cycle"]["status"] == "BLOCKED":
        break
    time.sleep(1)
check("S3 커스터마이징 게이트에 멈췄다", dash()["cycle"]["status"] == "BLOCKED")
check("AGENT.md 11개가 있다", dash()["specs"]["total"] == 11)


print("\n[편집 페이지가 서빙된다]")
check("/edit.html 200", c.get("/edit.html").status_code == 200)


print("\n[학생이 읽는다 — GET /api/specs/{role}/raw]")
raw = c.get("/api/specs/backend/raw")
check("본문을 받는다", raw.status_code == 200)
check("front-matter 가 들어 있다", raw.text.startswith("---"), raw.text[:40])


print("\n[인수 #14 — 학생 1명이 저장하면 카운터가 1 오른다]")
before = dash()["specs"]["customized"]
body = ("# 나는 AGORA Web 의 백엔드 담당이다\n\n"
        "## 나의 역할\n밀밭제과 예약 주문 API 를 만든다.\n\n"
        "## 내 파일\n- api-contract.yaml\n\n"
        "## 출력 형식\n- OpenAPI 3.0\n\n"
        "## 금지\n- 예약 시간이 영업시간 밖이면 받지 않는다. 이걸 서버에서 막는다.\n\n"
        "## 애매할 때\n- 기획에게 묻는다\n\n"
        "## 완료 보고\n- report.md 에 적는다\n")
res = c.put("/api/specs/backend/raw", content=body.encode(),
            headers={"Content-Type": "text/plain"})
check("저장 200", res.status_code == 200, res.text[:200])
d = res.json()["data"]
check(f"카운터가 {before} → {d['customized']} 로 올랐다", d["customized"] == before + 1,
      str(d))
check("아직 재개되지 않았다 (11명이 안 찼으므로)", d.get("resumed") is not True)

# 저장한 내용이 실제로 반영됐는가
raw2 = c.get("/api/specs/backend/raw").text
check("학생이 쓴 내용이 저장됐다", "영업시간 밖이면 받지 않는다" in raw2)
check("★ front-matter 는 HQ 가 지켜준다", raw2.startswith("---") and "role: backend" in raw2)

diff = c.get("/api/specs/backend/diff")
check("diff 가 보관된다 (회고용 평가 데이터)",
      diff.status_code == 200 and "영업시간" in diff.text, diff.text[:80])


print("\n[방어 — 빈 내용·없는 역할]")
check("빈 내용 저장 거부 (400)",
      c.put("/api/specs/backend/raw", content=b"   ",
            headers={"Content-Type": "text/plain"}).status_code == 400)
check("없는 역할 (404)",
      c.put("/api/specs/nosuchrole/raw", content=b"x",
            headers={"Content-Type": "text/plain"}).status_code == 404)


print("\n[인수 #15·#30 — 나머지 10명이 저장하면 자동 재개된다]")
resumed_at = None
for i, role in enumerate([r for r in ROLES if r != "backend"], start=2):
    b = (f"# 나는 AGORA Web 의 {role} 담당이다\n\n"
         "## 나의 역할\n(학생이 보강)\n\n## 내 파일\n- 내 산출물\n\n"
         "## 출력 형식\n- 마크다운\n\n"
         f"## 금지\n- {role} 로서 이번 요구사항에서 조심할 것을 적었다\n\n"
         "## 애매할 때\n- 기획에게 묻는다\n\n## 완료 보고\n- report.md\n")
    rr = c.put(f"/api/specs/{role}/raw", content=b.encode(),
               headers={"Content-Type": "text/plain"})
    dd = rr.json()["data"]
    print(f"     {i:2d}/11  {role:10s} → {dd['customized']}/{dd['total']}"
          + ("   ★ 자동 재개!" if dd.get("resumed") else ""))
    if dd.get("resumed"):
        resumed_at = dd["customized"]

check("11/11 이 됐다", dash()["specs"]["customized"] == 11, str(dash()["specs"]))
check("★ 11명이 다 저장한 순간 자동 재개됐다", resumed_at == 11, str(resumed_at))
time.sleep(2)
check("사이클이 S3 을 벗어났다", dash()["cycle"]["current_step"] not in (None, "S3"),
      str(dash()["cycle"]))

print("\n" + "─" * 40)
print(f"통과 {ok} · 실패 {ng}")
print("==> PASS" if ng == 0 else "==> FAIL")
sys.exit(1 if ng else 0)
