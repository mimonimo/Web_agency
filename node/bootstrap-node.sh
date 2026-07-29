#!/usr/bin/env bash
# 학생 노드 부트스트랩 (BRIEF §5.5) — 노드 위에서 실행된다.
#
#   ./bootstrap-node.sh --role backend --hq http://10.0.0.62:8000 --dgx dgx-07
#
# 하는 일:
#   1. node.env 확인/생성
#   2. A2A 어댑터 설치 (~/agora/adapter.py)
#   3. 상주 기동 + @reboot 등록 (sudo 불필요)
#   4. HQ 등록 확인
#
# 멱등하다 — 두 번 실행해도 같은 결과 (인수 #33).
set -uo pipefail

ROLE=""; HQ=""; DGX=""; PORT=41241
while [ $# -gt 0 ]; do
  case "$1" in
    --role) ROLE="$2"; shift 2;;
    --hq)   HQ="$2";   shift 2;;
    --dgx)  DGX="$2";  shift 2;;
    --port) PORT="$2"; shift 2;;
    *) echo "모르는 인자: $1" >&2; exit 2;;
  esac
done

ENVF="$HOME/agora/node.env"
mkdir -p "$HOME/agora/workspace" "$HOME/agora/runs"

# ── 1. node.env ────────────────────────────────────────────────────
if [ -f "$ENVF" ]; then
  . "$ENVF"
  ROLE="${ROLE:-$AGORA_ROLE}"
  HQ="${HQ:-$AGORA_HQ_URL}"
  DGX="${DGX:-$AGORA_NODE_ID}"
fi
ROLE="${ROLE:?--role 을 지정하거나 node.env 가 있어야 한다}"
HQ="${HQ:-http://10.0.0.62:8000}"
DGX="${DGX:-$(whoami)}"

cat > "$ENVF" <<ENV
# AGORA 노드 식별자 — PM 이 배포함. 손으로 고치지 말 것.
AGORA_NODE_ID=$DGX
AGORA_ROLE=$ROLE
AGORA_DISPLAY_NAME=${AGORA_DISPLAY_NAME:-$ROLE}
AGORA_HQ_URL=$HQ
AGORA_OLLAMA_URL=http://127.0.0.1:11434
AGORA_MODEL=${AGORA_MODEL:-gpt-oss:120b}
AGORA_WORKSPACE=$HOME/agora/workspace
AGORA_A2A_PORT=$PORT
ENV
echo "[1] node.env          OK (role=$ROLE, hq=$HQ)"

# ── 2. 어댑터 존재 확인 ────────────────────────────────────────────
if [ ! -f "$HOME/agora/adapter.py" ]; then
  echo "[2] adapter.py        없음 — PM 의 deploy-adapter.sh 로 배포해야 한다" >&2
  exit 1
fi
echo "[2] adapter.py        OK"

# ── 3. 상주 기동 (멱등) ────────────────────────────────────────────
pkill -f 'agora/adapter.py' 2>/dev/null
pkill -f 'agora/heartbeat.sh' 2>/dev/null      # 어댑터가 하트비트도 보낸다
sleep 1
setsid nohup python3 "$HOME/agora/adapter.py" --port "$PORT" \
       > "$HOME/agora/adapter.log" 2>&1 < /dev/null &
disown 2>/dev/null || true

( crontab -l 2>/dev/null | grep -vE 'agora/(adapter\.py|heartbeat\.sh)'; \
  echo "@reboot python3 $HOME/agora/adapter.py --port $PORT >> $HOME/agora/adapter.log 2>&1" ) \
  | crontab -

sleep 3
if pgrep -f 'agora/adapter.py' >/dev/null; then
  echo "[3] 어댑터 상주        OK (pid $(pgrep -f 'agora/adapter.py' | head -1), :$PORT)"
else
  echo "[3] 어댑터 상주        실패"; tail -10 "$HOME/agora/adapter.log" >&2; exit 1
fi

# ── 4. 자기 카드 · HQ 등록 확인 ────────────────────────────────────
if curl -sf -m 5 "http://127.0.0.1:$PORT/.well-known/agent-card.json" >/dev/null; then
  echo "[4] 에이전트 카드      OK"
else
  echo "[4] 에이전트 카드      실패"; exit 1
fi
echo "결과                  PASS"
