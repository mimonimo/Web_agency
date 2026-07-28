#!/usr/bin/env bash
# 노드 판정 (BRIEF §5.5, 인수 #34).
# DGX 연결 / Hermes 상주 / HQ 등록 / A2A 카드 응답을 **각각** 판정한다.
# 하나로 뭉뚱그리지 마라 — 어디가 깨졌는지 학생이 스스로 알아야 한다.
set -uo pipefail
. "$HOME/agora/node.env" 2>/dev/null || { echo "node.env 가 없다. bootstrap-node.sh 를 먼저 돌려라." >&2; exit 1; }
PORT="${AGORA_A2A_PORT:-41241}"
fail=0
say() { printf '%-22s %s\n' "$1" "$2"; }

# 1. DGX(Ollama) 연결
if curl -sf -m 5 "$AGORA_OLLAMA_URL/v1/models" | grep -q "$AGORA_MODEL"; then
  say "[1] Ollama 모델" "OK ($AGORA_MODEL)"
else
  say "[1] Ollama 모델" "실패 — $AGORA_OLLAMA_URL 에 $AGORA_MODEL 이 없다"; fail=1
fi

# 2. Hermes 설치 + Ollama 연결 설정
if [ -x "$HOME/.local/bin/hermes" ]; then
  cfg=$(python3 -c "
import yaml,os
try:
    c=yaml.safe_load(open(os.path.expanduser('~/.hermes/config.yaml')))['model']
    print(f\"{c.get('provider')}|{c.get('default')}\")
except Exception: print('-')" 2>/dev/null)
  if [ "$cfg" = "ollama|$AGORA_MODEL" ]; then
    say "[2] Hermes" "OK (provider=ollama, model=$AGORA_MODEL)"
  else
    say "[2] Hermes" "설치는 됐으나 모델 설정이 다르다: $cfg"; fail=1
  fi
else
  say "[2] Hermes" "실패 — 설치되지 않았다"; fail=1
fi

# 3. A2A 어댑터 상주 + 카드
if pgrep -f 'agora/adapter.py' >/dev/null; then
  if curl -sf -m 5 "http://127.0.0.1:$PORT/.well-known/agent-card.json" | grep -q "agora-$AGORA_ROLE"; then
    say "[3] A2A 어댑터" "OK (:$PORT, agora-$AGORA_ROLE)"
  else
    say "[3] A2A 어댑터" "상주 중이나 카드 응답이 이상하다"; fail=1
  fi
else
  say "[3] A2A 어댑터" "실패 — 상주하지 않는다"; fail=1
fi

# 4. HQ 등록 상태
st=$(curl -sf -m 5 "$AGORA_HQ_URL/api/nodes" 2>/dev/null \
     | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)['data']
    print(next((n['status'] for n in d if n['role']=='$AGORA_ROLE'), 'unregistered'))
except Exception: print('unreachable')" 2>/dev/null)
case "$st" in
  up)   say "[4] HQ 등록" "OK (up)";;
  down) say "[4] HQ 등록" "등록은 됐으나 down — 하트비트 확인 필요"; fail=1;;
  *)    say "[4] HQ 등록" "실패 ($st)"; fail=1;;
esac

[ "$fail" -eq 0 ] && say "결과" "PASS" || say "결과" "FAIL"
exit $fail
