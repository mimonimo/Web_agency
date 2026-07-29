#!/usr/bin/env bash
# 노드에 남아 있는 산출물을 HQ 로 회수한다.
#
#   ./recover-artifacts.sh <cycle_id>
#
# HQ 의 repo/runs/ 가 지워졌거나 전송이 실패했을 때 쓴다.
# 노드의 ~/agora/workspace/cycle-<id>/<step>/output/ 이 원본이다.
# `ops/reset.sh` 로 노드를 정리하기 전까지는 언제든 되살릴 수 있다.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
AGORA="$HOME/agora"
CID="${1:?사용법: ./recover-artifacts.sh <cycle_id>}"
DEST="$AGORA/repo/runs/$CID"

# 노드에서 돌릴 스크립트 — 따옴표 지옥을 피하려고 파일로 넘긴다.
PULL=$(mktemp)
cat > "$PULL" <<'REMOTE'
set -u
CID="$1"; ST="$2"
D="$HOME/agora/workspace/cycle-$CID/$ST"
[ -d "$D/output" ] || exit 0
cd "$D" || exit 0
tar cf - --exclude=node_modules --exclude=.git --exclude='*.log' \
         --exclude=prompt.txt --exclude=package-lock.json output 2>/dev/null
REMOTE

echo "사이클 #$CID 산출물을 노드에서 회수한다 → $DEST"
mkdir -p "$DEST"
total=0

while IFS=$'\t' read -r node ip role display <&3; do
  case "$node" in \#*|"") continue;; esac

  # ⚠️ -n 이 없으면 ssh 가 이 while 루프의 stdin(nodes.tsv)을 통째로 먹어
  #    첫 노드만 처리하고 끝난다. 실제로 겪었다.
  steps=$(ssh -n -o BatchMode=yes -o ConnectTimeout=10 "$node" \
          "ls ~/agora/workspace/cycle-$CID 2>/dev/null" 2>/dev/null)
  [ -z "$steps" ] && continue

  n=0
  for st in $steps; do
    base="${st%%-*}"                 # S2-backend → S2
    tmp=$(mktemp -d)
    ssh -o BatchMode=yes "$node" "bash -s $CID $st" < "$PULL" 2>/dev/null \
      | tar xf - -C "$tmp" 2>/dev/null
    if [ ! -d "$tmp/output" ]; then rm -rf "$tmp"; continue; fi

    # 한 단계를 여러 역할이 나눠 맡았으면 역할별 하위 폴더로 나눈다
    if [ -d "$DEST/$base/output" ] && [ "$st" = "$base" ]; then
      out="$DEST/$base/output/$role"
    else
      out="$DEST/$base/output"
    fi
    mkdir -p "$out"
    cp -rn "$tmp/output/." "$out/" 2>/dev/null
    n=$((n + $(find "$tmp/output" -type f | wc -l)))
    rm -rf "$tmp"
  done

  # 완료 보고
  ssh -n -o BatchMode=yes "$node" \
    "cat ~/agora/workspace/cycle-$CID/*/report.md 2>/dev/null" 2>/dev/null \
    > "$DEST/report-$role.md" 2>/dev/null
  [ -s "$DEST/report-$role.md" ] || rm -f "$DEST/report-$role.md"

  [ "$n" -gt 0 ] && { printf '  %-9s %-10s %3d개\n' "$node" "$role" "$n"; total=$((total+n)); }
done 3< "$HERE/nodes.tsv"
rm -f "$PULL"

echo
echo "회수 완료: $total 개"
found=$(find "$DEST" -name "index.html" -not -path "*/node_modules/*" 2>/dev/null)
if [ -n "$found" ]; then
  echo
  echo "완성된 웹사이트:"
  echo "$found" | while read -r f; do
    rel="${f#"$AGORA/repo/"}"
    echo "  http://10.0.0.62:8000/preview/$rel"
  done
else
  echo "  (index.html 을 찾지 못했다 — 프론트엔드가 만든 사이트가 없는 사이클일 수 있다)"
fi
