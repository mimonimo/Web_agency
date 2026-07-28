#!/usr/bin/env bash
# 노드 하트비트 — HQ 에 30초마다 살아 있다고 알린다 (BRIEF §7, 인수 #7).
# A2A 어댑터(Phase 2)가 생기기 전까지 노드 생존만 알리는 최소 상주 프로세스다.
set -uo pipefail
. "$HOME/agora/node.env" 2>/dev/null || { echo "node.env 없음" >&2; exit 1; }

HQ="${AGORA_HQ_URL:-http://220.67.5.62:8000}"
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
