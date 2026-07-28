#!/usr/bin/env bash
# 전체 초기화 (BRIEF §2, 인수 #35) — Phase 5 에서 구현한다.
#
#   ops/reset.sh 후 make up + provision → 처음 상태로 완전 복구
#
# ⚠️ 사이클 단위 reset(keep_specs) 과 혼동하지 마라.
#    그건 POST /api/cycles/{id}/reset 이고 학생의 AGENT.md 를 지키는 쪽이다 (BRIEF §3.4).
#    이 스크립트는 다음 수업/다음 반을 위해 **DB·볼륨까지 통째로** 지우는 쪽이다.
set -euo pipefail
echo "Phase 5 에서 구현한다." >&2
exit 1
