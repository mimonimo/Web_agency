#!/usr/bin/env bash
# PM(dgx-12) 에서 실행 — A2A 어댑터를 dgx-02~11 에 배포하고 기동한다. 멱등.
#
#   ./deploy-adapter.sh              # 전체
#   ./deploy-adapter.sh dgx-07       # 특정 노드만
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
AGORA="$HOME/agora"
HQ="${HQ_URL:-http://10.0.0.62:8000}"
OUT=$(mktemp -d)

only=("$@")
in_scope() {
  [ ${#only[@]} -eq 0 ] && return 0
  for n in "${only[@]}"; do [ "$n" = "$1" ] && return 0; done
  return 1
}

while IFS=$'\t' read -r node ip role display; do
  case "$node" in \#*|"") continue;; esac
  in_scope "$node" || continue
  (
    # 1. 어댑터 + 부트스트랩 전송
    scp -q -o BatchMode=yes \
        "$AGORA/node/a2a-adapter/adapter.py" \
        "$AGORA/node/bootstrap-node.sh" \
        "$AGORA/node/verify-node.sh" \
        "$node:~/agora/" 2>"$OUT/$node.log"
    # 2. 부트스트랩 실행
    ssh -o BatchMode=yes -o ConnectTimeout=15 "$node" \
        "chmod +x ~/agora/bootstrap-node.sh ~/agora/verify-node.sh && \
         AGORA_DISPLAY_NAME='$display' ~/agora/bootstrap-node.sh \
           --role '$role' --hq '$HQ' --dgx '$node'" \
        >>"$OUT/$node.log" 2>&1
    echo $? > "$OUT/$node.rc"
  ) &
done < "$HERE/nodes.tsv"
wait

fail=0
while IFS=$'\t' read -r node ip role display; do
  case "$node" in \#*|"") continue;; esac
  in_scope "$node" || continue
  rc=$(cat "$OUT/$node.rc" 2>/dev/null || echo 99)
  [ "$rc" = "0" ] || fail=1
  echo "########## $node · $role/$display · rc=$rc ##########"
  cat "$OUT/$node.log"
done < "$HERE/nodes.tsv"
rm -rf "$OUT"

echo
[ "$fail" -eq 0 ] && echo "==> 전체 PASS" || echo "==> 실패한 노드가 있음"
exit $fail
