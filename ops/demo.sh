#!/usr/bin/env bash
# 수업 시연 시나리오 — PM 화면(픽셀 오피스)을 띄워 놓고 이 스크립트를 돌린다.
#
#   ops/demo.sh
#
# 하는 일: 주문 접수 → S3 게이트에서 멈춤 → 학생들이 AGENT.md 고침 → 자동 재개
#          → QA 반려 → ★ 되감기 화살표 → 재작업 → 완주
set -uo pipefail
cd "$(dirname "$0")/.."
HQ="${HQ:-http://127.0.0.1:8000}"
PY="$(pwd)/.venv/bin/python"
REPO="$(pwd)/repo"
ROLES=(pm planner sales sysadmin designer frontend backend dba security qa customer)

say()  { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
info() { printf '   %s\n' "$*"; }

state() { curl -s "$HQ/api/dashboard" | "$PY" -c "
import json,sys; d=json.load(sys.stdin)['data']; c=d.get('cycle') or {}
print(f\"{c.get('status','-')} @ {c.get('current_step','-')}  \"
      f\"AGENT.md {d['specs'].get('customized',0)}/{d['specs'].get('total',0)}  \"
      f\"티켓 {d['tickets'].get('todo',0)}\")"; }

wait_for() {  # wait_for <상태> <타임아웃초>
  local want="$1" limit="${2:-90}" i=0
  while [ $i -lt "$limit" ]; do
    curl -s "$HQ/api/dashboard" | grep -q "\"status\": *\"$want\"" && return 0
    sleep 1; i=$((i+1))
  done
  return 1
}

say "1. 고객이 주문을 넣는다"
CID=$(curl -s -X POST "$HQ/api/orders" -H 'Content-Type: application/json' -d '{
  "company":"밀밭제과","industry":"제과/베이커리",
  "purpose":"동네 단골이 온라인으로 주문할 수 있게 한다",
  "features":["로그인","상품목록","장바구니","문의폼"],
  "due_date":"2026-08-30","contact_name":"김밀밭","contact":"010-0000-0000","kind":"new"}' \
  | "$PY" -c "import json,sys; print(json.load(sys.stdin)['data']['cycle']['id'])")
info "사이클 #$CID 시작 — 영업(S1) 이 접수를 받는다"

say "2. 기획(S2)이 AGENT.md 11개를 만들고, S3 커스터마이징 게이트에서 자동으로 멈춘다"
wait_for BLOCKED 120 || { echo "게이트 도달 실패"; exit 1; }
info "$(state)"
info "→ 지금 학생들이 자기 AGENT.md 를 고칠 차례다"

say "3. 학생들이 AGENT.md 를 하나씩 고쳐 커밋한다 (7/11 카운터가 오른다)"
for r in "${ROLES[@]}"; do
  f="$REPO/project-001/agents/$r/AGENT.md"
  [ -f "$f" ] || continue
  printf '\n## %s 학생이 보강한 규칙\n- 이 역할에서 특히 조심할 것\n' "$r" >> "$f"
  curl -s -X POST "$HQ/api/specs/scan" >/dev/null
  printf '   %-10s → %s\n' "$r" "$(state)"
  sleep 1
done

say "4. 11개가 다 차면 자동으로 재개된다"
sleep 3; info "$(state)"

say "5. QA 게이트까지 진행되기를 기다린다"
for _ in $(seq 1 90); do
  cur=$(curl -s "$HQ/api/dashboard" | "$PY" -c "
import json,sys; print((json.load(sys.stdin)['data'].get('cycle') or {}).get('current_step',''))")
  [ "$cur" = "S6" ] && break
  sleep 1
done
info "$(state)"

say "6. ★ QA 가 반려한다 — 타임라인에 되감기 화살표가 그려진다"
curl -s -X POST "$HQ/api/gates/S6/reject" -H 'Content-Type: application/json' \
     -d "{\"reason\":\"로그인 실패 시 500 이 난다\",\"cycle_id\":$CID}" \
     | "$PY" -c "import json,sys; print('  ', json.load(sys.stdin)['data']['note'])"
info "$(state)"
info "→ PM 화면 타임라인의 S6 ⟵ S5 구간이 빨갛게 물든다"

say "7. 재작업 후 끝까지 간다"
for _ in $(seq 1 120); do
  s=$(curl -s "$HQ/api/dashboard" | "$PY" -c "
import json,sys; print((json.load(sys.stdin)['data'].get('cycle') or {}).get('status',''))")
  [ "$s" = "DONE" ] && break
  sleep 1
done
info "$(state)"

say "시연 끝. 같은 주문을 조건만 바꿔 다시 돌리려면:"
info "PM 화면에서 [⟲ 처음부터] → 'AGENT.md 는 그대로 두기' 를 고른다."
info "학생이 고친 지시문은 유지된 채 사이클만 처음부터 다시 돈다."
