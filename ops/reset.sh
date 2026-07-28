#!/usr/bin/env bash
# 전체 초기화 (BRIEF §2, 인수 #35) — 다음 수업 / 다음 반을 위한 완전 리셋.
#
#   ops/reset.sh [--yes]
#
# ⚠️ 사이클 단위 reset(keep_specs) 과 혼동하지 마라.
#    그건 POST /api/cycles/{id}/reset 이고 **학생의 AGENT.md 를 지키는** 쪽이다 (BRIEF §3.4).
#    이 스크립트는 DB·산출물·노드 작업물까지 **통째로** 지우는 쪽이다.
#
# 지운 뒤 `make dev` (또는 `make up`) 만 하면 처음 상태로 돌아온다.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

if [ "${1:-}" != "--yes" ]; then
  echo "이 작업은 되돌릴 수 없다. 지우는 것:"
  echo "  - HQ DB (사이클·주문·티켓·감사로그 전부)"
  echo "  - repo/runs/ 산출물"
  echo "  - repo/project-001/ (★ 학생들이 고친 AGENT.md 포함)"
  echo "  - 노드 11대의 ~/agora/workspace/"
  echo
  read -r -p "정말 진행할까? (yes 입력) " a
  [ "$a" = "yes" ] || { echo "취소했다."; exit 1; }
fi

echo "[1] HQ 정지"
./ops/dev.sh stop >/dev/null 2>&1 || true
docker compose down 2>/dev/null || true

echo "[2] 회고용 백업"
STAMP=$(date +%Y%m%d-%H%M%S)
BK="$ROOT/repo/.archive/$STAMP"
if [ -d repo/project-001 ] || [ -f repo/agora.db ]; then
  mkdir -p "$BK"
  [ -d repo/project-001 ] && cp -r repo/project-001 "$BK/" 2>/dev/null
  [ -f repo/agora.db ]    && cp repo/agora.db "$BK/" 2>/dev/null
  echo "    → repo/.archive/$STAMP (학생 작업물은 여기 남는다)"
else
  echo "    → 백업할 것이 없다"
fi

echo "[3] HQ 데이터 삭제"
rm -f  repo/agora.db repo/agora.db-shm repo/agora.db-wal repo/hq.log "$ROOT/.hq.pid"
# showcase 는 비교·시연용으로 남긴 것이라 지우지 않는다
rm -rf repo/runs repo/project-001
mkdir -p repo

echo "[4] 노드 작업물 삭제"
OPS="$HOME/agora-ops"
if [ -x "$OPS/dgx-fan.sh" ]; then
  echo 'rm -rf ~/agora/workspace/* ~/agora/runs/* 2>/dev/null; echo "$(hostname) 정리"' \
    | "$OPS/dgx-fan.sh" 2>/dev/null | grep -c "정리" | xargs -I{} echo "    → {}대 정리"
else
  echo "    → dgx-fan.sh 가 없다. 노드는 수동으로 정리해야 한다"
fi

echo
echo "완료. 이제 'make dev' 로 처음 상태에서 다시 시작한다."
