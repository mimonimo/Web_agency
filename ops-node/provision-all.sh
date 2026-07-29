#!/usr/bin/env bash
# PM(dgx-12) 에서 실행 — nodes.tsv 를 읽어 dgx-02~11 을 전부 프로비저닝한다. 멱등.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HQ_URL="${HQ_URL:-http://10.0.0.62:8000}"
OUT=$(mktemp -d)

while IFS=$'\t' read -r node ip role display; do
  case "$node" in \#*|"") continue;; esac
  (
    ssh -o BatchMode=yes -o ConnectTimeout=15 "$node" \
        "ROLE='$role' DISPLAY_NAME='$display' NODE_ID='$node' HQ_URL='$HQ_URL' bash -s" \
        < "$HERE/provision-node.sh" > "$OUT/$node.log" 2>&1
    echo $? > "$OUT/$node.rc"
  ) &
done < "$HERE/nodes.tsv"
wait

fail=0
while IFS=$'\t' read -r node ip role display; do
  case "$node" in \#*|"") continue;; esac
  rc=$(cat "$OUT/$node.rc" 2>/dev/null || echo 99)
  [ "$rc" = "0" ] || fail=1
  echo "########## $node ($ip) · $role/$display · rc=$rc ##########"
  cat "$OUT/$node.log"
done < "$HERE/nodes.tsv"
rm -rf "$OUT"

echo
[ "$fail" -eq 0 ] && echo "==> 전체 PASS" || echo "==> 실패한 노드가 있음"
exit $fail
