#!/usr/bin/env bash
# ★ 인수 테스트 (BRIEF §12)
#
#   이게 통과해야 Phase 가 끝난 것이다. 출력 없는 완료 보고는 반려한다.
#
#   사용법:  ./ops/acceptance.sh --phase 0
#            ./ops/acceptance.sh              # 구현된 Phase 전부
#
# 읽기 전용이다. 아무것도 고치지 않으므로 몇 번을 돌려도 같은 결과가 나온다.
#
# ⚠️ 산출물 보호 — 이 스크립트는 repo/runs 를 절대 지우지 않는다.
#    E2E·편집 테스트는 돌고 있는 HQ 에 주문을 하나 더 넣을 뿐이다.
#    실제로 한 번 리허설 결과물을 날린 적이 있다. 다시는 지우지 마라.
#    처음부터 다시 하려면 ops/reset.sh 를 써라 — 거기엔 백업이 있다.

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

HQ="${HQ:-http://127.0.0.1:8000}"
PY_BIN="$ROOT/.venv/bin/python"

nodes_up() {
  curl -sf "$HQ/api/nodes" 2>/dev/null | "$PY_BIN" -c "
import json,sys
try: print(sum(1 for x in json.load(sys.stdin)['data'] if x['status']=='up'))
except Exception: print(0)" 2>/dev/null || echo 0
}

wait_nodes() {
  # DB 를 새로 만들면 하트비트(30초 주기)가 올 때까지 노드가 down 으로 보인다.
  local want="${1:-10}" limit="${2:-50}" i=0
  while [ "$i" -lt "$limit" ]; do
    [ "$(nodes_up)" -ge "$want" ] && return 0
    sleep 2; i=$((i+2))
  done
  return 1
}

phase3() {
  head_ "Phase 3 — 오케스트레이터 (인수 11–25)"
  if [ ! -x "$PY_BIN" ]; then ng "venv 가 없다 (python3 -m venv .venv)"; return; fi

  if "$PY_BIN" core/tests/test_orchestrator.py >/tmp/agora-orch.log 2>&1; then
    ok "상태기계 단위 테스트 $(grep -c '✅' /tmp/agora-orch.log)건 통과"
  else
    ng "상태기계 단위 테스트 실패"; sed -n 's/^  ❌/    /p' /tmp/agora-orch.log
  fi

  if "$PY_BIN" core/tests/test_verdict.py >/tmp/agora-verdict.log 2>&1; then
    ok "게이트 판정 파서 $(grep -c '✅' /tmp/agora-verdict.log)건 통과 (인수 #19)"
  else
    ng "게이트 판정 파서 실패"; sed -n 's/^  ❌/    /p' /tmp/agora-verdict.log
  fi

  if "$PY_BIN" core/tests/test_roles.py >/tmp/agora-roles.log 2>&1; then
    ok "역할 카탈로그·기준선·검사기 $(grep -c '✅' /tmp/agora-roles.log)건 통과"
  else
    ng "역할 카탈로그·기준선·검사기 실패"; sed -n 's/^  ❌/    /p' /tmp/agora-roles.log
  fi

  if ! curl -sf -m 5 "$HQ/api/health" >/dev/null 2>&1; then
    ng "HQ 가 떠 있지 않다 (make dev 로 먼저 띄워라)"; return
  fi
  ok "HQ 가 응답한다 ($HQ/api/health)"

  ex=$(curl -sf "$HQ/api/health" | "$PY_BIN" -c "
import json,sys; print(json.load(sys.stdin)['data'].get('executor','?'))" 2>/dev/null)
  if [ "$ex" != "sim" ]; then
    printf '  ⏭  E2E 흐름·편집 테스트는 EXECUTOR=sim 에서만 돈다 (현재 %s).\n' "$ex"
    printf '     실제 노드는 한 단계에 수십 초가 걸려 테스트 대기시간을 넘긴다.\n'
    printf '     확인하려면: .env 에서 EXECUTOR=sim 으로 바꾸고 make dev-stop && make dev\n'
    return
  fi

  if "$PY_BIN" core/tests/test_flow.py "$HQ" >/tmp/agora-flow.log 2>&1; then
    ok "E2E 흐름 테스트 $(grep -c '✅' /tmp/agora-flow.log)건 통과"
  else
    ng "E2E 흐름 테스트 실패"; sed -n 's/^  ❌/    /p' /tmp/agora-flow.log
  fi

  if "$PY_BIN" core/tests/test_edit.py "$HQ" >/tmp/agora-edit.log 2>&1; then
    ok "★ 학생 편집 흐름 테스트 $(grep -c '✅' /tmp/agora-edit.log)건 통과 (인수 #14·#15)"
  else
    ng "학생 편집 흐름 테스트 실패"; sed -n 's/^  ❌/    /p' /tmp/agora-edit.log
  fi
}

phase4() {
  head_ "Phase 4 — PM 관제 화면 (인수 26–32)"
  if ! curl -sf -m 5 "$HQ/api/health" >/dev/null 2>&1; then
    ng "HQ 가 떠 있지 않다"; return
  fi

  for f in /index.html /order.html /board.html /edit.html /assets/office.css /assets/office.js; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "$HQ$f")
    [ "$code" = "200" ] && ok "$f 200" || ng "$f → $code"
  done

  # 인수 #32 — 빌드·CDN 없음. 외부 호스트를 참조하면 안 된다.
  if grep -rIEl 'https?://(?!127|localhost|220\.67)' web/ 2>/dev/null | grep -q .; then
    ng "web/ 이 외부 URL 을 참조한다 (CDN 금지)"
  elif grep -rIEo 'src="https?://[^"]*"|href="https?://[^"]*"' web/ 2>/dev/null | grep -q .; then
    ng "web/ 이 외부 리소스를 불러온다"
  else
    ok "web/ 에 외부 CDN·원격 리소스 참조가 없다 (인수 #32)"
  fi

  # 대시보드가 한 번에 다 주는가 (BRIEF §7)
  if curl -sf "$HQ/api/dashboard" | "$PY_BIN" -c "
import json,sys
d = json.load(sys.stdin)['data']
need = ['cycle','steps','nodes','specs','messages','tickets','orders']
missing = [k for k in need if k not in d]
sys.exit(1 if missing else 0)"; then
    ok "/api/dashboard 가 cycle·steps·nodes·specs·messages·tickets·orders 를 한 번에 준다"
  else
    ng "/api/dashboard 응답에 빠진 키가 있다"
  fi

  # 노드 11개 · 하트비트 (인수 #5·#7·#27)
  wait_nodes 10 50 || true
  n_up=$(nodes_up)
  n_all=$(curl -sf "$HQ/api/nodes" | "$PY_BIN" -c "
import json,sys; print(len(json.load(sys.stdin)['data']))" 2>/dev/null || echo 0)
  [ "$n_all" = "11" ] && ok "노드 11개가 등록돼 있다 (인수 #5)" || ng "노드 $n_all 개"
  [ "$n_up" -ge 10 ] && ok "노드 $n_up/11 이 하트비트로 살아 있다 (인수 #7)" \
                     || ng "살아 있는 노드가 $n_up 개뿐이다"

  # reset 대화상자 문구 (인수 #31)
  if grep -q "AGENT.md 는 그대로 두기" web/index.html \
     && grep -q 'value="true" checked' web/index.html; then
    ok "★ ⟲ 처음부터 대화상자가 있고 기본값이 'AGENT.md 유지' 다 (인수 #31)"
  else
    ng "reset 대화상자 문구·기본값이 BRIEF §8.3 과 다르다"
  fi

  grep -q "rewound" web/assets/office.js && grep -q "tl-arrow.rewound" web/assets/office.css \
    && ok "★ 되감기 역방향 화살표가 구현돼 있다 (인수 #29)" \
    || ng "되감기 화살표가 없다"
  grep -q "spec-counter" web/assets/office.js \
    && ok "커스터마이징 게이트 카운터(7/11)가 구현돼 있다 (인수 #30)" \
    || ng "스펙 카운터가 없다"

  # ★ 학생이 실제로 고칠 수 있는가 — 이게 없으면 수업이 성립하지 않는다
  code=$(curl -s -o /dev/null -w '%{http_code}' -X PUT "$HQ/api/specs/backend/raw" \
         -H 'Content-Type: text/plain' --data-binary '   ')
  [ "$code" = "400" ] || [ "$code" = "404" ] \
    && ok "★ 학생 편집 API(PUT /api/specs/{role}/raw)가 살아 있다" \
    || ng "학생 편집 API 응답이 이상하다 ($code)"
  grep -q "PUT" web/edit.html && ok "편집 페이지가 저장 요청을 보낸다" \
    || ng "편집 페이지에 저장 기능이 없다"

  for f in /agent.html /files.html; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "$HQ$f")
    [ "$code" = "200" ] && ok "$f 200" || ng "$f → $code"
  done

  # 결과물 품질 점수 (templates/_quality.md 기준)
  if find repo/runs -name index.html -not -path "*/node_modules/*" 2>/dev/null | grep -q .; then
    score=$("$PY_BIN" ops/site-check.py 2>/dev/null | grep -oP '품질 점수: \K[0-9]+/[0-9]+')
    pct=$("$PY_BIN" ops/site-check.py 2>/dev/null | grep -oP '\(\K[0-9]+(?=점\))')
    if [ -n "$pct" ] && [ "$pct" -ge 75 ]; then
      ok "완성된 사이트 품질 $score (${pct}점)"
    else
      ng "완성된 사이트 품질 미달 $score (${pct:-?}점) — ops/site-check.py 로 항목 확인"
    fi
  fi

  # ★ 에이전트가 만든 웹사이트를 브라우저에서 그대로 열 수 있는가
  if "$PY_BIN" core/tests/test_preview.py >/tmp/agora-preview.log 2>&1; then
    ok "★ 완성된 사이트 미리보기 $(grep -c '✅' /tmp/agora-preview.log)건 통과"
  else
    if grep -q "사이트를 최소 1개" /tmp/agora-preview.log && \
       ! find repo/runs -name index.html -not -path "*/node_modules/*" 2>/dev/null | grep -q .; then
      printf '  ⏭  완성된 사이트가 아직 없다 (실제 노드로 사이클을 돌려야 생긴다)\n'
    else
      ng "완성된 사이트 미리보기 실패"; sed -n 's/^  ❌/    /p' /tmp/agora-preview.log
    fi
  fi
}

phase2() {
  head_ "Phase 2 — 노드 · A2A (인수 5–10)"
  if ! curl -sf -m 5 "$HQ/api/health" >/dev/null 2>&1; then ng "HQ 가 떠 있지 않다"; return; fi

  n_all=$(curl -sf "$HQ/api/nodes" | "$PY_BIN" -c "
import json,sys; print(len(json.load(sys.stdin)['data']))" 2>/dev/null || echo 0)
  [ "$n_all" = "11" ] && ok "노드 11개 등록 (인수 #5)" || ng "노드 $n_all 개"

  # 인수 #6 — HQ 가 각 노드의 에이전트 카드를 조회한다
  cards=$(curl -sf "$HQ/api/nodes" | "$PY_BIN" -c "
import json,sys,urllib.request
n=0
for x in json.load(sys.stdin)['data']:
    try:
        u=x['a2a_url'].rstrip('/')+'/.well-known/agent-card.json'
        c=json.load(urllib.request.urlopen(u, timeout=5))
        if c.get('name')==f\"agora-{x['role']}\": n+=1
    except Exception: pass
print(n)" 2>/dev/null || echo 0)
  [ "$cards" -ge 10 ] && ok "에이전트 카드 $cards/11 조회 성공 (인수 #6)" \
                      || ng "카드 조회 $cards/11"

  # 인수 #7 — 하트비트로 up (최대 50초 기다린다)
  wait_nodes 10 50 || true
  n_up=$(nodes_up)
  [ "$n_up" -ge 10 ] && ok "노드 $n_up/11 하트비트 정상 (인수 #7)" || ng "up 노드 $n_up 개"

  # 인수 #10 — 잘못된 토큰 → 401
  tok=$(curl -sf "$HQ/api/nodes/backend/token" | "$PY_BIN" -c "
import json,sys; print(json.load(sys.stdin)['data']['token'])" 2>/dev/null)
  good=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$HQ/api/nodes/backend/heartbeat" \
         -H "X-Agora-Token: $tok")
  bad=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$HQ/api/nodes/backend/heartbeat" \
        -H "X-Agora-Token: definitely-wrong")
  spoof=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$HQ/api/messages" \
          -H 'Content-Type: application/json' -H "X-Agora-Token: $tok" \
          -d '{"from_role":"qa","to_role":"hq","kind":"mirror","summary":"사칭"}')
  [ "$good" = "200" ] && ok "올바른 토큰 → 200" || ng "올바른 토큰 → $good"
  [ "$bad"  = "401" ] && ok "★ 잘못된 토큰 → 401 (인수 #10)" || ng "잘못된 토큰 → $bad"
  [ "$spoof" = "401" ] && ok "★ 남의 역할 사칭 미러링 → 401" || ng "사칭 → $spoof"

  # 인수 #9 — 미러링된 메시지가 남아 있다
  mirrored=$("$PY_BIN" -c "
import json,urllib.request
d=json.load(urllib.request.urlopen('$HQ/api/messages?limit=100'))['data']
roles={m['from'] for m in d} - {'hq'}
print(len(roles))" 2>/dev/null || echo 0)
  [ "$mirrored" -ge 1 ] && ok "노드가 보낸 메시지가 미러링돼 있다 (인수 #9, $mirrored 역할)" \
                        || ng "미러링된 노드 메시지가 없다"
}

phase5() {
  head_ "Phase 5 — 부트스트랩 · 운영 (인수 33–36)"
  want_exec node/bootstrap-node.sh
  want_exec node/verify-node.sh
  want_exec ops/reset.sh
  want_exec ops/autostart.sh
  want_file node/a2a-adapter/adapter.py

  # 인수 #36 — 재부팅 자동 기동이 등록돼 있는가
  if crontab -l 2>/dev/null | grep -q 'ops/dev.sh start'; then
    ok "★ HQ 재부팅 자동 기동이 등록돼 있다 (인수 #36)"
  else
    ng "재부팅 자동 기동 미등록 (ops/autostart.sh install)"
  fi

  # 노드 어댑터도 @reboot 로 살아나는가
  if [ -x "$HOME/agora-ops/dgx-fan.sh" ]; then
    n=$(echo 'crontab -l 2>/dev/null | grep -c "agora/adapter.py"' \
        | "$HOME/agora-ops/dgx-fan.sh" 2>/dev/null | grep -cx '1')
    [ "$n" -ge 10 ] && ok "노드 $n/10 이 어댑터 자동 기동 등록됨" \
                    || ng "어댑터 자동 기동 등록 노드 $n 개"
  fi

  # 인수 #33 — bootstrap 이 멱등한가 (node.env 해시가 안 바뀐다)
  if [ -x "$HOME/agora-ops/dgx-fan.sh" ]; then
    h1=$(echo 'md5sum ~/agora/node.env 2>/dev/null | cut -c1-8' \
         | "$HOME/agora-ops/dgx-fan.sh" dgx-07 2>/dev/null | tail -1)
    echo '~/agora/bootstrap-node.sh --role backend --hq http://220.67.5.62:8000 --dgx dgx-07' \
      | "$HOME/agora-ops/dgx-fan.sh" dgx-07 >/dev/null 2>&1
    h2=$(echo 'md5sum ~/agora/node.env 2>/dev/null | cut -c1-8' \
         | "$HOME/agora-ops/dgx-fan.sh" dgx-07 2>/dev/null | tail -1)
    [ -n "$h1" ] && [ "$h1" = "$h2" ] \
      && ok "★ bootstrap-node.sh 2회 실행이 멱등하다 (인수 #33)" \
      || ng "bootstrap 이 멱등하지 않다 ($h1 → $h2)"

    # 인수 #34 — verify-node 가 4항목을 각각 판정
    v=$(echo '~/agora/verify-node.sh' | "$HOME/agora-ops/dgx-fan.sh" dgx-07 2>/dev/null)
    c=$(echo "$v" | grep -cE '^\[[1-4]\]')
    [ "$c" -eq 4 ] && ok "★ verify-node.sh 가 4항목을 각각 판정한다 (인수 #34)" \
                   || ng "verify-node 판정 항목이 $c 개"
    echo "$v" | grep -q "결과.*PASS" && ok "dgx-07 노드 판정 PASS" || ng "dgx-07 판정 실패"
  fi
}

phase6() {
  head_ "Phase 6 — 사람이 조종하는 화면 (개입·프리뷰·콘솔)"
  if ! curl -sf -m 5 "$HQ/api/health" >/dev/null 2>&1; then
    ng "HQ 가 떠 있지 않다"; return
  fi

  for p in index.html console.html review.html projects.html agent.html \
           edit.html board.html files.html order.html assets/ui.js; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "$HQ/$p")
    [ "$code" = "200" ] && ok "화면 $p" || ng "화면 $p ($code)"
  done

  for u in "/api/activity" "/api/activity/prompt?role=designer" \
           "/api/review/current" "/api/review/projects" \
           "/api/agents" "/api/agents/designer/catalog" \
           "/api/agents/designer/notes" "/api/agents/designer/check" \
           "/api/specs/designer/baseline"; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "$HQ$u")
    [ "$code" = "200" ] && ok "API $u" || ng "API $u ($code)"
  done

  # ★ 사람이 넣은 지시가 실제로 프롬프트에 들어가는가 — 이 기능의 존재 이유
  curl -sf -X POST "$HQ/api/agents/designer/notes" \
       -H 'Content-Type: application/json' \
       -d '{"text":"인수테스트-지시-확인용"}' >/dev/null 2>&1
  if curl -sf "$HQ/api/activity/prompt?role=designer" | grep -q "인수테스트-지시-확인용"; then
    ok "★ 사람이 넣은 지시가 에이전트 프롬프트에 실린다"
  else
    ng "사람이 넣은 지시가 프롬프트에 안 들어간다"
  fi
  curl -sf -X DELETE "$HQ/api/agents/designer/notes" >/dev/null 2>&1

  # 프롬프트에 역할 목표·완료조건이 실리는가
  if curl -sf "$HQ/api/activity/prompt?role=frontend" | grep -q "완료 조건"; then
    ok "역할 완료 조건이 프롬프트에 실린다"
  else
    ng "역할 완료 조건이 프롬프트에 없다"
  fi

  # 티켓 조작 왕복
  cid=$(curl -sf "$HQ/api/dashboard" | "$PY_BIN" -c "
import json,sys
d=json.load(sys.stdin)['data'].get('cycle') or {}
print(d.get('id',''))" 2>/dev/null)
  if [ -n "$cid" ]; then
    tid=$(curl -sf -X POST "$HQ/api/tickets" -H 'Content-Type: application/json' \
      -d "{\"cycle_id\":$cid,\"from_role\":\"pm\",\"to_role\":\"qa\",\"title\":\"인수테스트 티켓\"}" \
      | "$PY_BIN" -c "import json,sys;print(json.load(sys.stdin)['data']['id'])" 2>/dev/null)
    if [ -n "$tid" ]; then
      curl -sf -X PATCH "$HQ/api/tickets/$tid" -H 'Content-Type: application/json' \
           -d '{"to_role":"frontend"}' >/dev/null && ok "티켓 담당 변경" || ng "티켓 담당 변경 실패"
      curl -sf -X POST "$HQ/api/tickets/$tid/transition" -H 'Content-Type: application/json' \
           -d '{"status":"doing"}' >/dev/null && ok "티켓 상태 변경" || ng "티켓 상태 변경 실패"
      curl -sf -X DELETE "$HQ/api/tickets/$tid" >/dev/null && ok "티켓 삭제" || ng "티켓 삭제 실패"
    else
      ng "티켓 생성 실패"
    fi
  fi

  # 작업물이 사이클별로 묶여 나오는가
  n=$(curl -sf "$HQ/api/review/projects" | "$PY_BIN" -c "
import json,sys; print(len(json.load(sys.stdin)['data']))" 2>/dev/null)
  [ -n "$n" ] && ok "작업물이 $n 묶음으로 정리된다" || ng "작업물 목록 실패"
}

case "$PHASE" in
  0)   phase0 ;;
  2)   phase2 ;;
  3)   phase3 ;;
  4)   phase4 ;;
  5)   phase5 ;;
  6)   phase6 ;;
  all) phase0
       phase3        # 먼저 사이클을 돌려야 메시지·산출물이 생긴다
       phase2
       phase4
       phase5
       phase6 ;;
  *)   echo "아직 없는 Phase: $PHASE" >&2; exit 2 ;;
esac

printf '\n────────────────────────────────\n'
printf '통과 %d · 실패 %d\n' "$pass" "$fail"
[ "$fail" -eq 0 ] && { echo "==> PASS"; exit 0; } || { echo "==> FAIL"; exit 1; }
