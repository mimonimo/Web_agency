set -uo pipefail
mkdir -p ~/agora
cat > ~/agora/heartbeat.sh <<'INNER'
#!/usr/bin/env bash
# 노드 하트비트 — HQ 에 30초마다 살아 있다고 알린다 (BRIEF §7, 인수 #7).
# A2A 어댑터(Phase 2)가 생기기 전까지 노드 생존만 알리는 최소 상주 프로세스다.
set -uo pipefail
. "$HOME/agora/node.env" 2>/dev/null || { echo "node.env 없음" >&2; exit 1; }

HQ="${AGORA_HQ_URL:-http://10.0.0.62:8000}"
ROLE="${AGORA_ROLE:?}"
A2A="http://$(hostname -I | awk '{print $1}'):41241/"

# 최초 1회 등록
curl -sf -m 5 -X POST "$HQ/api/nodes/register" \
     -H 'Content-Type: application/json' \
     -d "{\"role\":\"$ROLE\",\"a2a_url\":\"$A2A\",\"dgx_host\":\"$AGORA_NODE_ID\"}" >/dev/null

while true; do
  curl -sf -m 5 -X POST "$HQ/api/nodes/$ROLE/heartbeat" >/dev/null 2>&1
  sleep 30
done
INNER
chmod +x ~/agora/heartbeat.sh

# 이미 돌고 있으면 죽이고 다시 (멱등)
pkill -f 'agora/heartbeat.sh' 2>/dev/null
setsid nohup ~/agora/heartbeat.sh > ~/agora/heartbeat.log 2>&1 < /dev/null &
disown 2>/dev/null || true

# 재부팅 후에도 뜨게 (sudo 불필요)
( crontab -l 2>/dev/null | grep -v 'agora/heartbeat.sh'; \
  echo "@reboot $HOME/agora/heartbeat.sh >> $HOME/agora/heartbeat.log 2>&1" ) | crontab -

sleep 2
pgrep -f 'agora/heartbeat.sh' >/dev/null && echo "하트비트 상주 OK (pid $(pgrep -f 'agora/heartbeat.sh' | head -1))" || echo "하트비트 기동 실패"
