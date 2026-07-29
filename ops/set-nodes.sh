#!/usr/bin/env bash
# 노드 IP 를 이 PC 에 맞춘다 — 새 PM PC 에서 클론한 직후 한 번.
#
#   ./ops/set-nodes.sh 220.67.5          # 대역만 주면 된다 (dgx-02→.52 … dgx-12→.62)
#   ./ops/set-nodes.sh --check           # 만들어 둔 것이 맞는지만 확인
#
# 공개 리포의 `provisioning/students.yaml` 은 IP 가 예시 값(10.0.0.x)이다.
# 실제 값은 `students.local.yaml` 에 두고 git 에서 제외한다 —
# **HQ 는 부팅할 때마다 이 파일로 노드 주소를 덮어쓴다** (main._seed_nodes).
#
# ★ 파일을 USB 로 옮길 필요가 없다. 예시 파일에 노드↔번호 규칙이 이미 들어 있어서
#   앞 세 자리만 바꾸면 11대가 전부 맞는다.
set -uo pipefail
cd "$(dirname "$0")/.."

SRC=provisioning/students.yaml
DST=provisioning/students.local.yaml

check() {
  [ -f "$DST" ] || { echo "  ❌ $DST 가 없다. ./ops/set-nodes.sh <대역> 을 먼저 돌려라"; return 1; }
  echo "  파일: $DST"
  local ng=0 n=0
  # yaml 파서를 쓰지 않는다 — 클론 직후 venv 가 없을 수도 있다
  while read -r role ip; do
    n=$((n+1))
    printf '  %-10s %-16s ' "$role" "$ip"
    if curl -sf -m 4 "http://$ip:41241/.well-known/agent-card.json" >/dev/null 2>&1; then
      echo "✅ 에이전트 카드 응답"
    else
      echo "❌ 응답 없음 (노드가 꺼졌거나 IP 가 틀렸다)"; ng=$((ng+1))
    fi
  done < <(awk '
    /^[[:space:]]*-?[[:space:]]*role:/ { sub(/.*role:[[:space:]]*/,""); gsub(/"/,""); r=$0 }
    /^[[:space:]]*ip:/                 { sub(/.*ip:[[:space:]]*/,"");   gsub(/"/,""); if (r!="") { print r, $0; r="" } }
  ' "$DST")
  echo "────────────────────────────────"
  if [ "$ng" -eq 0 ] && [ "$n" -gt 0 ]; then
    echo "  ✅ 노드 $n 대 전부 응답한다."
    echo "     .env 에 EXECUTOR=a2a 를 넣고 ./ops/dev.sh restart 하면 된다."
    return 0
  fi
  echo "  ❌ $n 대 중 $ng 대가 응답하지 않는다."
  echo
  echo "  ⚠️ 하트비트가 'up' 으로 떠도 소용없다 — 하트비트는 노드가 HQ 로 밀어 넣는 것이라"
  echo "     HQ 가 노드를 못 불러도 살아 있어 보인다. 위의 카드 응답이 진짜 판정이다."
  return 1
}

if [ "${1:-}" = "--check" ]; then
  echo "════════════════════════════════════════════════════════════"
  echo " 노드 확인"
  echo "════════════════════════════════════════════════════════════"
  check; exit $?
fi

PREFIX="${1:-}"
if [ -z "$PREFIX" ]; then
  cat <<'USAGE'
쓰는 법:
  ./ops/set-nodes.sh 220.67.5      노드 대역 앞 세 자리
  ./ops/set-nodes.sh --check       만들어 둔 것이 맞는지 확인

대역을 모르겠으면 노드 아무 데서나 `hostname -I` 를 찍어 보면 된다.
노드 번호 규칙(dgx-02→.52 … dgx-12→.62)은 예시 파일에 이미 들어 있다.
USAGE
  exit 2
fi

PREFIX="${PREFIX%.}"                       # 끝의 점은 있어도 없어도 되게
case "$PREFIX" in
  *.*.*) ;;
  *) echo "❌ 대역은 세 자리다 — 예: 220.67.5"; exit 2 ;;
esac

[ -f "$SRC" ] || { echo "❌ $SRC 가 없다"; exit 1; }

if [ -f "$DST" ]; then
  cp "$DST" "$DST.bak"
  echo "  기존 파일을 $DST.bak 로 백업했다"
fi

sed "s/10\.0\.0\./$PREFIX./g" "$SRC" > "$DST"
echo "  ✅ $DST 생성 ($PREFIX.x)"
echo

echo "════════════════════════════════════════════════════════════"
echo " 노드 확인"
echo "════════════════════════════════════════════════════════════"
check
