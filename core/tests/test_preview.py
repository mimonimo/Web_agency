#!/usr/bin/env python3
"""완성된 사이트 미리보기 테스트 — 에이전트가 만든 웹페이지가 브라우저에서 열리는가."""
import sys, httpx
BASE = "http://127.0.0.1:8000"
ok = ng = 0
def check(l, c, d=""):
    global ok, ng
    if c: ok += 1; print(f"  ✅ {l}")
    else: ng += 1; print(f"  ❌ {l}   {d}")

c = httpx.Client(base_url=BASE, timeout=20)

print("\n[완성된 사이트 목록]")
r = c.get("/preview/sites")
check("/preview/sites 200", r.status_code == 200)
sites = r.json()["data"]
check("사이트를 최소 1개 찾는다", len(sites) >= 1, f"{len(sites)}개")

if sites:
    s = sites[0]
    print(f"     {s['url']} (파일 {s['files']}개)")
    print("\n[실제로 열리는가]")
    p = c.get(s["url"])
    check("index.html 200", p.status_code == 200)
    check("Content-Type 이 text/html", "text/html" in p.headers.get("content-type", ""),
          p.headers.get("content-type"))
    check("HTML 문서다", "<html" in p.text.lower())
    check("주문서 내용이 반영돼 있다", "밀밭제과" in p.text, p.text[:120])

    print("\n[딸린 자원도 열리는가]")
    import re
    base = s["url"].rsplit("/", 1)[0]
    for m in re.findall(r'(?:href|src)="([^":]+\.(?:css|js))"', p.text):
        rr = c.get(f"{base}/{m}")
        check(f"{m} {rr.status_code}", rr.status_code == 200)

print("\n[경로 탈출 차단]")
for bad in ("/preview/../../etc/passwd", "/preview/runs/../../../etc/hostname"):
    rr = c.get(bad)
    check(f"{bad} 차단", rr.status_code in (400, 404), str(rr.status_code))

print("\n" + "─" * 40)
print(f"통과 {ok} · 실패 {ng}")
print("==> PASS" if ng == 0 else "==> FAIL")
sys.exit(1 if ng else 0)
