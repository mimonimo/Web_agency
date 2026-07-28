#!/usr/bin/env bash
# ★ 인수 테스트 (BRIEF §12)
#
#   이게 통과해야 Phase 가 끝난 것이다. 출력 없는 완료 보고는 반려한다.
#
#   사용법:  ./ops/acceptance.sh --phase 0
#            ./ops/acceptance.sh              # 구현된 Phase 전부
#
# 읽기 전용이다. 아무것도 고치지 않으므로 몇 번을 돌려도 같은 결과가 나온다.

set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

PHASE="${2:-}"
[ "${1:-}" = "--phase" ] || PHASE="all"

pass=0; fail=0

ok()   { printf '  ✅ %s\n' "$1"; pass=$((pass+1)); }
ng()   { printf '  ❌ %s\n' "$1"; fail=$((fail+1)); }
head_() { printf '\n[%s]\n' "$1"; }

# 경로가 존재하는지 (BRIEF §2 구조 일치)
want_file() { [ -f "$ROOT/$1" ] && ok "$1" || ng "$1 (파일 없음)"; }
want_dir()  { [ -d "$ROOT/$1" ] && ok "$1/" || ng "$1/ (디렉터리 없음)"; }
want_exec() { [ -x "$ROOT/$1" ] && ok "$1 (실행권한)" || ng "$1 (실행권한 없음)"; }

phase0() {
  head_ "Phase 0 — 리포 골격 (BRIEF §2 구조 일치)"

  for f in BRIEF.md CLAUDE.md Makefile docker-compose.yml .env.example .gitignore; do
    want_file "$f"
  done

  want_file core/Dockerfile
  want_file core/requirements.txt
  for f in main.py models.py db.py orchestrator.py a2a_client.py a2a_server.py; do
    want_file "core/app/$f"
  done
  for r in cycles nodes specs tickets orders messages artifacts dashboard; do
    want_file "core/app/routers/$r.py"
  done
  for p in pipeline.yaml pipeline.change.yaml pipeline.defect.yaml pipeline.security.yaml; do
    want_file "core/app/$p"
  done

  for f in index.html order.html board.html; do want_file "web/$f"; done
  want_dir web/assets

  want_dir  node/a2a-adapter
  want_exec node/bootstrap-node.sh
  want_exec node/verify-node.sh

  want_dir repo

  want_file provisioning/students.yaml
  want_file provisioning/provision.py
  want_file provisioning/seed.py

  want_exec ops/acceptance.sh
  want_exec ops/reset.sh
  want_exec ops/rewind.sh

  head_ "Phase 0 — 파일이 실제로 유효한가"

  # 파이썬이 파싱되는가
  if python3 - <<'PY' 2>/dev/null
import ast, pathlib, sys
bad = []
for p in pathlib.Path("core").rglob("*.py"):
    try:
        ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError as e:
        bad.append(f"{p}: {e}")
for p in pathlib.Path("provisioning").rglob("*.py"):
    try:
        ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError as e:
        bad.append(f"{p}: {e}")
sys.exit(1 if bad else 0)
PY
  then ok "모든 .py 가 파싱된다"
  else ng "파싱 실패한 .py 가 있다"
  fi

  # pipeline 4종이 유효 YAML 이고 steps 를 갖는가
  if python3 - <<'PY' 2>/dev/null
import yaml, sys, pathlib
for name in ("pipeline.yaml", "pipeline.change.yaml",
             "pipeline.defect.yaml", "pipeline.security.yaml"):
    d = yaml.safe_load(pathlib.Path("core/app", name).read_text(encoding="utf-8"))
    assert d.get("name"), name
    assert d.get("steps"), name
    ids = [s["id"] for s in d["steps"]]
    assert len(ids) == len(set(ids)), f"{name}: step id 중복"
    # 셋 다 S1 영업에서 시작한다 (BRIEF §3.6)
    assert ids[0] == "S1", f"{name}: S1 로 시작하지 않는다"
sys.exit(0)
PY
  then ok "pipeline 4종이 유효 YAML 이고 전부 S1 로 시작한다"
  else ng "pipeline YAML 검증 실패"
  fi

  # students.yaml 이 역할 11개를 정확히 담는가
  if python3 - <<'PY' 2>/dev/null
import yaml, sys, pathlib
ROLES = ["pm","planner","sales","sysadmin","designer","frontend",
         "backend","dba","security","qa","customer"]
d = yaml.safe_load(pathlib.Path("provisioning/students.yaml").read_text(encoding="utf-8"))
got = [s["role"] for s in d["students"]]
sys.exit(0 if got == ROLES else 1)
PY
  then ok "students.yaml 이 역할 11개를 BRIEF §1.3 순서대로 담는다"
  else ng "students.yaml 역할 목록 불일치"
  fi

  # compose 문법 (데몬 접속 불필요)
  if command -v docker >/dev/null 2>&1; then
    if [ -f .env ] || cp .env.example .env 2>/dev/null; then :; fi
    if docker compose config >/dev/null 2>&1; then
      ok "docker compose config — compose 문법 유효"
    else
      ng "docker compose config 실패"
    fi
  else
    ng "docker 명령을 찾을 수 없다"
  fi

  # 비밀이 커밋되지 않는가 (BRIEF §15-6)
  if grep -qx '.env' .gitignore && grep -qx 'provisioning/out/' .gitignore; then
    ok ".gitignore 가 .env 와 provisioning/out/ 을 막는다"
  else
    ng ".gitignore 가 비밀 경로를 막지 않는다"
  fi

  if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    ok "git 리포로 초기화돼 있다"
  else
    ng "git 리포가 아니다"
  fi
}

not_yet() { head_ "$1"; printf '  ⏭  아직 구현하지 않았다\n'; }

case "$PHASE" in
  0)   phase0 ;;
  all) phase0
       not_yet "Phase 1 — 기반 (인수 1–4)"
       not_yet "Phase 2 — 노드 · A2A (인수 5–10)"
       not_yet "Phase 3 — 오케스트레이터 (인수 11–25)"
       not_yet "Phase 4 — 픽셀 오피스 (인수 26–32)"
       not_yet "Phase 5 — 전체 (인수 33–36)" ;;
  *)   echo "아직 없는 Phase: $PHASE" >&2; exit 2 ;;
esac

printf '\n────────────────────────────────\n'
printf '통과 %d · 실패 %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ] && { echo "==> PASS"; exit 0; } || { echo "==> FAIL"; exit 1; }
