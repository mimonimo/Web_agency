#!/usr/bin/env bash
# PM(dgx-12) 에서 실행 — 노드 10대의 상태를 한 줄씩 요약한다. 추론은 하지 않아 빠르다.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT=$(mktemp -d)

while IFS=$'\t' read -r node ip role display; do
  case "$node" in \#*|"") continue;; esac
  (
    ssh -o BatchMode=yes -o ConnectTimeout=10 "$node" bash -s > "$OUT/$node.log" 2>&1 <<'EOS'
export PATH="$HOME/.local/bin:$PATH"
ol=$(curl -sf -m 5 http://127.0.0.1:11434/v1/models | grep -c 'gpt-oss:120b' || echo 0)
hv=$(command -v hermes >/dev/null && hermes --version 2>/dev/null | head -1 | awk '{print $3}' || echo "-")
cfg=$(python3 -c "
import yaml,os
try:
    c=yaml.safe_load(open(os.path.expanduser('~/.hermes/config.yaml')))['model']
    print(f\"{c.get('provider')}:{c.get('default')}\")
except Exception: print('-')
" 2>/dev/null)
r=$(. $HOME/agora/node.env 2>/dev/null && echo $AGORA_ROLE || echo "-")
up=$(uptime -p 2>/dev/null | sed 's/up //')
echo "$hv|$([ "$ol" -gt 0 ] && echo ollama-OK || echo ollama-NG)|$cfg|$r|$up"
EOS
    echo $? > "$OUT/$node.rc"
  ) &
done < "$HERE/nodes.tsv"
wait

printf '%-8s %-14s %-8s %-11s %-28s %-10s %s\n' 노드 IP 역할 hermes "모델설정" ollama 가동시간
printf '%s\n' "----------------------------------------------------------------------------------------------------"
while IFS=$'\t' read -r node ip role display; do
  case "$node" in \#*|"") continue;; esac
  rc=$(cat "$OUT/$node.rc" 2>/dev/null || echo 99)
  if [ "$rc" != "0" ]; then
    printf '%-8s %-14s %-8s ❌ 접속 실패\n' "$node" "$ip" "$role"; continue
  fi
  IFS='|' read -r hv ol cfg r up < "$OUT/$node.log"
  printf '%-8s %-14s %-8s %-11s %-28s %-10s %s\n' "$node" "$ip" "$r" "$hv" "$cfg" "$ol" "$up"
done < "$HERE/nodes.tsv"
rm -rf "$OUT"
