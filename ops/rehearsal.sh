#!/usr/bin/env bash
# 수업 전 리허설 — 실제 학생 노드(EXECUTOR=a2a)로 사이클을 끝까지 돌린다.
#
#   ops/rehearsal.sh
#
# 로컬 모델이라 오래 걸린다(20~40분). 진행 상황을 계속 찍는다.
# 학생 역할은 스크립트가 대신한다 (S3 게이트에서 11개 AGENT.md 를 저장).
set -uo pipefail
cd "$(dirname "$0")/.."
HQ="${HQ:-http://127.0.0.1:8000}"
PY="$(pwd)/.venv/bin/python"
ROLES=(pm planner sales sysadmin designer frontend backend dba security qa customer)
T0=$(date +%s)

el() { printf '[%3d분]' $((($(date +%s) - T0) / 60)); }
say() { printf '\n\033[1;36m▶ %s %s\033[0m\n' "$(el)" "$*"; }

state() { curl -s "$HQ/api/dashboard" | "$PY" -c "
import json,sys
d=json.load(sys.stdin)['data']; c=d.get('cycle') or {}
done=sum(1 for s in d['steps'] if s['status']=='DONE')
print(f\"{c.get('status','-'):8s} @ {str(c.get('current_step')):5s} \"
      f\"단계 {done}/{len(d['steps'])}  AGENT.md {d['specs'].get('customized',0)}/{d['specs'].get('total',0)}  \"
      f\"메시지 {len(d['messages'])}  티켓 {d['tickets'].get('todo',0)}\")" 2>/dev/null; }

cstatus() { curl -s "$HQ/api/dashboard" | "$PY" -c "
import json,sys; print((json.load(sys.stdin)['data'].get('cycle') or {}).get('status',''))" 2>/dev/null; }

ex=$(curl -sf "$HQ/api/health" | "$PY" -c "
import json,sys; print(json.load(sys.stdin)['data'].get('executor'))" 2>/dev/null)
[ "$ex" = "a2a" ] || { echo "EXECUTOR 가 a2a 가 아니다 (현재 $ex). .env 를 고치고 make dev-stop && make dev" >&2; exit 1; }

nodes_up() { curl -sf "$HQ/api/nodes" | "$PY" -c "
import json,sys
try: print(sum(1 for x in json.load(sys.stdin)['data'] if x['status']=='up'))
except Exception: print(0)" 2>/dev/null || echo 0; }

# DB 를 새로 만들면 하트비트(30초 주기)가 올 때까지 노드가 down 으로 보인다.
say "노드가 올라오기를 기다린다 (하트비트 30초 주기)"
i=0
while [ "$(nodes_up)" -lt 11 ] && [ "$i" -lt 90 ]; do sleep 5; i=$((i+5)); done
up=$(nodes_up)
say "노드 $up/11 up · 실행기 $ex"
[ "${up:-0}" -ge 10 ] || { echo "살아 있는 노드가 부족하다" >&2; exit 1; }

say "1. 주문 접수"
CID=$(curl -s -X POST "$HQ/api/orders" -H 'Content-Type: application/json' -d '{
  "company":"밀밭제과","industry":"제과/베이커리",
  "purpose":"동네 단골이 온라인으로 빵을 예약 주문할 수 있게 한다",
  "features":["로그인","상품목록","장바구니","문의폼"],
  "due_date":"2026-08-30","contact_name":"김밀밭","contact":"010-1234-5678",
  "reference":"따뜻하고 아날로그한 느낌","kind":"new"}' \
  | "$PY" -c "import json,sys; print(json.load(sys.stdin)['data']['cycle']['id'])")
echo "   사이클 #$CID"

say "2. S3 커스터마이징 게이트까지 (영업 → 기획)"
last=""
while [ "$(cstatus)" != "BLOCKED" ]; do
  s=$(state); [ "$s" != "$last" ] && { printf '   %s %s\n' "$(el)" "$s"; last="$s"; }
  sleep 20
done
printf '   %s %s\n' "$(el)" "$(state)"

say "3. 학생 11명이 AGENT.md 를 고쳐 저장한다"
for r in "${ROLES[@]}"; do
  cur=$(curl -sf "$HQ/api/specs/$r/raw" | sed '1,/^---$/d' | sed '1,/^---$/d')
  printf '%s\n\n## 학생이 보강한 규칙\n- %s 로서 이번 요구사항(밀밭제과 예약 주문)에서 특히 조심할 것을 적었다.\n' \
    "$cur" "$r" > /tmp/agora-spec.md
  n=$(curl -s -X PUT "$HQ/api/specs/$r/raw" -H 'Content-Type: text/plain' \
      --data-binary @/tmp/agora-spec.md \
      | "$PY" -c "import json,sys; d=json.load(sys.stdin)['data']; print(f\"{d['customized']}/{d['total']}\" + (' ★자동재개' if d.get('resumed') else ''))" 2>/dev/null)
  printf '   %-10s → %s\n' "$r" "$n"
done
rm -f /tmp/agora-spec.md

say "4. 설계 → 구현 → 게이트 3종 → 배포 → 운영 (끝까지)"
last=""
while : ; do
  st=$(cstatus)
  case "$st" in
    DONE)   printf '   %s %s\n' "$(el)" "$(state)"; break;;
    FAILED) printf '   %s ❌ %s\n' "$(el)" "$(state)"; break;;
  esac
  s=$(state); [ "$s" != "$last" ] && { printf '   %s %s\n' "$(el)" "$s"; last="$s"; }
  sleep 30
done

say "5. 결과"
curl -s "$HQ/api/dashboard" | "$PY" -c "
import json,sys
d=json.load(sys.stdin)['data']
print('   단계별:')
for s in d['steps']:
    mark = {'DONE':'✅','FAILED':'❌','PENDING':'○','RUNNING':'▶'}.get(s['status'],'·')
    print(f\"     {mark} {s['key']:4s} {s['name']:28s} {s['status']}\" + (f\"  ← {s['error'][:60]}\" if s['error'] else ''))
print(f\"   산출물 {d.get('artifacts',0)}건 · 메시지 {len(d['messages'])}건\")"
echo
echo "   산출물 트리:"
find repo/runs -name '*.md' -o -name '*.json' -o -name '*.yaml' -o -name '*.sql' -o -name '*.sh' 2>/dev/null \
  | sort | sed 's/^/     /' | head -40
printf '\n총 소요 %s\n' "$(el)"
