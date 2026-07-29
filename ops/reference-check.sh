#!/usr/bin/env bash
# 레퍼런스 케이스 채점 — 테스트 케이스처럼 언제든 다시 돌린다.
#
#   ./ops/reference-check.sh              # Claude 레퍼런스
#   ./ops/reference-check.sh --all        # 로컬 v1 · v2 · Claude 비교
#
# 채점 대상은 `repo/showcase/` 의 보존본이다. `ops/reset.sh` 도 건드리지 않으므로
# 수업을 몇 번 돌려도 남는다.
set -uo pipefail
cd "$(dirname "$0")/.."
PY=./.venv/bin/python
[ -x "$PY" ] || PY=python3

REF=repo/showcase/claude-reference

if [ ! -d "$REF" ]; then
  echo "레퍼런스가 없다: $REF" >&2
  exit 2
fi

echo "════════════════════════════════════════════════════════════"
echo " 레퍼런스 채점 — Claude Code 가 11개 역할을 직접 수행한 결과"
echo "════════════════════════════════════════════════════════════"

"$PY" ops/site-check.py "$REF" | tail -25

echo
echo "── 역할별 완료조건 (checks.py) ───────────────────────────────"
"$PY" - "$REF" <<'PYEOF'
import shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, "core")
from app import checks

base = Path(sys.argv[1]); docs = base / "docs"

GROUPS = [
    ("sales",    ["docs/SOW.md", "docs/QUOTE.md"]),
    ("planner",  ["docs/SRS.md", "docs/SCREENS.md"]),
    ("designer", ["docs/design-tokens.json", "docs/UI-GUIDE.md"]),
    ("dba",      ["docs/schema.sql", "docs/seed.sql"]),
    ("backend",  ["server.js", "README.md", "docs/api-contract.yaml"]),
    ("frontend", ["index.html", "style.css", "app.js"]),
    ("sysadmin", ["docs/ops/run.sh", "docs/DEPLOY.md", "docs/DEPLOY-LOG.md"]),
    ("qa",       [("docs/VERDICT-qa.md", "VERDICT.md")]),
    ("security", [("docs/VERDICT-security.md", "VERDICT.md")]),
    ("customer", [("docs/VERDICT-customer.md", "VERDICT.md"), "docs/FEEDBACK.md"]),
]

tot_ok = tot = 0
for role, files in GROUPS:
    t = Path(tempfile.mkdtemp())
    for f in files:
        src, dst = (f, Path(f).name) if isinstance(f, str) else f
        p = base / src
        if p.exists():
            shutil.copy(p, t / dst)
    found = checks.check(role, t, {"screens": 5})
    ok, n = checks.score(found)
    tot_ok += ok; tot += n
    bad = [x.label for x in checks.failures(found)]
    mark = "✅" if not bad else "❌"
    print(f"  {mark} {role:9} {ok:>2}/{n:<2}  {', '.join(bad) if bad else ''}")
    shutil.rmtree(t, ignore_errors=True)

pct = round(tot_ok / tot * 100) if tot else 0
print(f"\n  합계 {tot_ok}/{tot}  ({pct}점)")
sys.exit(0 if tot_ok == tot else 1)
PYEOF
rc=$?

if [ "${1:-}" = "--all" ]; then
  echo
  echo "── 세 판 비교 ────────────────────────────────────────────────"
  "$PY" - <<'PYEOF'
import re, sys
from pathlib import Path
sys.path.insert(0, "core")
from app import checks

CASES = [("로컬 v1 (개선 전)", "repo/showcase/v1-before"),
         ("로컬 v2 (개선 후)", "repo/showcase/v2-after"),
         ("Claude Code",       "repo/showcase/claude-reference")]

print(f"  {'':18} {'검사':>7} {'섹션':>4} {'변수정의':>8} {'변수사용':>8} {'aria':>5} {'미디어':>6} {'js':>7}")
for name, d in CASES:
    p = Path(d)
    if not (p / "index.html").exists():
        print(f"  {name:18} (없음)")
        continue
    found = checks.check("frontend", p, {"screens": 5})
    ok, n = checks.score(found)
    html = (p / "index.html").read_text(encoding="utf-8")
    css = "\n".join(x.read_text(encoding="utf-8") for x in p.glob("*.css"))
    js = "\n".join(x.read_text(encoding="utf-8") for x in p.glob("*.js") if x.name != "server.js")
    print(f"  {name:18} {ok:>3}/{n:<3} {len(re.findall(r'<section', html, re.I)):>4}"
          f" {len(re.findall(r'--[a-z0-9-]+\s*:', css)):>8}"
          f" {len(re.findall(r'var\(--', css)):>8}"
          f" {len(re.findall(r'aria-|role=', html)):>5}"
          f" {len(re.findall(r'@media', css)):>6}"
          f" {len(js):>7}")
PYEOF
fi

echo
echo "AGORA Web:  /preview/showcase/claude-reference/index.html"
echo "문서:       repo/showcase/claude-reference/docs/RESULT.md"
exit $rc
