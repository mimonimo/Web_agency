#!/usr/bin/env bash
# PM(dgx-12) 에서 실행 — 각 노드에서 로컬 Ollama 를 통한 Hermes 추론 왕복을 실제로 시켜본다.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT=$(mktemp -d)

while IFS=$'\t' read -r node ip role display; do
  case "$node" in \#*|"") continue;; esac
  (
    ssh -o BatchMode=yes -o ConnectTimeout=15 "$node" bash -s <<EOS > "$OUT/$node.log" 2>&1
export PATH="\$HOME/.local/bin:\$PATH"
. \$HOME/agora/node.env
echo "role=\$AGORA_ROLE model=\$AGORA_MODEL"
timeout 900 hermes -z "You are the '$role' agent of AGORA Web. Reply with exactly one line: AGORA-$role-OK" --yolo 2>&1 | tail -3
EOS
    echo $? > "$OUT/$node.rc"
  ) &
done < "$HERE/nodes.tsv"
wait

fail=0
while IFS=$'\t' read -r node ip role display; do
  case "$node" in \#*|"") continue;; esac
  log=$(cat "$OUT/$node.log" 2>/dev/null)
  if grep -q "AGORA-$role-OK" <<<"$log"; then
    printf '%-8s %-10s %-8s ✅ 추론 OK\n' "$node" "$role" "$display"
  else
    printf '%-8s %-10s %-8s ❌ 실패\n%s\n' "$node" "$role" "$display" "$log"
    fail=1
  fi
done < "$HERE/nodes.tsv"
rm -rf "$OUT"

echo
[ "$fail" -eq 0 ] && echo "==> 전체 PASS" || echo "==> 실패한 노드가 있음"
exit $fail
