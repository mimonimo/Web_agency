#!/usr/bin/env bash
# 학생 노드 부트스트랩 (BRIEF §5.5) — Phase 5 에서 구현한다.
#
#   ./bootstrap-node.sh --role backend --hq http://hq.agora.lan --dgx dgx-07
#
# 하는 일:
#   1. A2A 어댑터 설치 및 systemd 유닛 등록 (24시간 상주)
#   2. HQ 에 register
#   3. 에이전트 카드 노출 확인
#
# 멱등해야 한다 — 두 번 실행해도 같은 결과 (인수 #33).
#
# ※ Hermes ↔ Ollama 연결은 이 스크립트가 하지 않는다.
#    PM 쪽 ~/agora-ops/provision-all.sh 가 이미 끝내 두었다.
set -euo pipefail
echo "Phase 5 에서 구현한다. 현재 노드 준비는 PM 의 ~/agora-ops/provision-all.sh 가 담당한다." >&2
exit 1
