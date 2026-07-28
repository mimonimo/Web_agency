#!/usr/bin/env python3
"""완성된 사이트 품질 채점 (templates/_quality.md 기준).

    .venv/bin/python ops/site-check.py [사이트디렉터리]

인자를 안 주면 repo/ 안에서 가장 최근 index.html 을 찾는다.
게이트 에이전트가 보는 것과 같은 항목을 기계적으로 확인해,
지시문을 고쳤을 때 결과가 실제로 나아졌는지 숫자로 비교하기 위한 도구다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "repo"


def find_site(arg: str | None) -> Path | None:
    if arg:
        p = Path(arg)
        if p.is_dir():
            p = p / "index.html"
        return p if p.is_file() else None
    cands = [p for p in REPO.rglob("index.html")
             if "node_modules" not in p.parts and ".archive" not in p.parts]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def main() -> int:
    site = find_site(sys.argv[1] if len(sys.argv) > 1 else None)
    if site is None:
        print("index.html 을 찾지 못했다.")
        return 2

    d = site.parent
    html = site.read_text(encoding="utf-8", errors="replace")
    css = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                    for p in d.glob("*.css"))
    js = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                   for p in d.glob("*.js") if p.name != "server.js")
    allsrc = html + css + js

    print(f"\n대상: {site.relative_to(REPO) if site.is_relative_to(REPO) else site}")
    print(f"파일: {', '.join(sorted(p.name for p in d.iterdir() if p.is_file()))}\n")

    checks: list[tuple[str, bool, str]] = []

    def c(label: str, cond: bool, detail: str = "") -> None:
        checks.append((label, bool(cond), detail))

    # ── 교실 환경 (인터넷 없음) ────────────────────────────────────
    ext = re.findall(r'(?:src|href)=["\'](https?://[^"\']+)', html)
    c("외부 CDN·원격 리소스 없음", not ext, f"{len(ext)}건: {ext[:2]}")
    c("구글폰트 없음", "fonts.googleapis" not in allsrc)
    c("node_modules 없음", not (d / "node_modules").exists())

    # ── 반응형 ────────────────────────────────────────────────────
    c("viewport 메타 태그", 'name="viewport"' in html)
    c("미디어쿼리 또는 반응형 그리드",
      "@media" in css or "auto-fill" in css or "auto-fit" in css or "minmax(" in css)

    # ── 구조 ──────────────────────────────────────────────────────
    sem = [t for t in ("<header", "<nav", "<main", "<section", "<footer")
           if t in html.lower()]
    c(f"시맨틱 태그 {len(sem)}/5", len(sem) >= 3, ", ".join(sem))
    br = html.lower().count("<br")
    c("<br> 로 폼을 배치하지 않음", br <= 2, f"{br}개")
    c("flexbox/grid 레이아웃", "display:flex" in css.replace(" ", "")
      or "display:grid" in css.replace(" ", ""))

    # ── 디자인 시스템 ─────────────────────────────────────────────
    varsdef = len(re.findall(r"--[a-z0-9-]+\s*:", css))
    varsuse = len(re.findall(r"var\(--", css))
    c(f"CSS 변수 정의 {varsdef}개", varsdef >= 6, f"{varsdef}개")
    c(f"CSS 변수 사용 {varsuse}회", varsuse >= 6, f"{varsuse}회")
    c("한글 폰트 스택", "Noto Sans KR" in css or "Malgun" in css or "system-ui" in css)
    # 기본 파랑/초록만 쓰는지 (톤&매너 무시 신호)
    c("기본 색(#4CAF50 등)에 의존하지 않음",
      not re.search(r"#4CAF50|#45a049|#0066CC", css, re.I))

    # ── 접근성 ────────────────────────────────────────────────────
    inputs = len(re.findall(r"<input\b", html, re.I)) + len(re.findall(r"<select\b", html, re.I))
    labels = len(re.findall(r"<label\b[^>]*\bfor=", html, re.I))
    c(f"label 이 입력 수를 덮음 ({labels}/{inputs})", inputs == 0 or labels >= inputs,
      f"input {inputs} · label {labels}")
    imgs = re.findall(r"<img\b[^>]*>", html, re.I)
    c("모든 img 에 alt", all("alt=" in i for i in imgs), f"{len(imgs)}개")
    c("클릭되는 div 없음", not re.search(r'<div[^>]*onclick', html, re.I))

    # ── 화면 수 ───────────────────────────────────────────────────
    sections = len(re.findall(r'<section\b', html, re.I))
    screens_md = next((p for p in (REPO).rglob("SCREENS.md")), None)
    want = 0
    if screens_md:
        want = len(re.findall(r"^##\s+\S", screens_md.read_text(encoding="utf-8"), re.M))
    c(f"화면 구현 {sections}개 (SCREENS.md 목표 {want}개)",
      want == 0 or sections >= max(2, want // 2), f"section {sections} vs 목표 {want}")

    # ── 내용 ──────────────────────────────────────────────────────
    c("자리표시자(TODO/lorem) 없음",
      not re.search(r"\bTODO\b|lorem ipsum|여기에 내용", allsrc, re.I))
    c("본문이 비어 있지 않음", len(re.sub(r"<[^>]+>", "", html).strip()) > 200,
      f"{len(re.sub(r'<[^>]+>', '', html).strip())}자")
    c("동작 스크립트가 있음", len(js.strip()) > 200, f"{len(js.strip())}자")

    ok = sum(1 for _, v, _ in checks if v)
    for label, v, detail in checks:
        print(f"  {'✅' if v else '❌'} {label}" + (f"   {detail}" if not v and detail else ""))

    pct = round(ok / len(checks) * 100)
    print(f"\n{'─' * 44}")
    print(f"품질 점수: {ok}/{len(checks)}  ({pct}점)")
    if pct >= 85:
        print("==> 좋음")
    elif pct >= 60:
        print("==> 보통 — 게이트에서 지적될 항목이 있다")
    else:
        print("==> 낮음 — 지시문이나 참고 자료 전달을 점검해라")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
