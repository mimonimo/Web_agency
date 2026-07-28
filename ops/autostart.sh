#!/usr/bin/env bash
# HQ 재부팅 자동 기동 등록 (인수 #36). sudo 불필요 — crontab @reboot 를 쓴다.
#
#   ops/autostart.sh install | remove | status
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
LINE="@reboot sleep 20 && $ROOT/ops/dev.sh start >> $ROOT/repo/boot.log 2>&1"

case "${1:-status}" in
  install)
    ( crontab -l 2>/dev/null | grep -v 'ops/dev.sh start'; echo "$LINE" ) | crontab -
    echo "등록했다:"; crontab -l | grep 'ops/dev.sh start'
    ;;
  remove)
    crontab -l 2>/dev/null | grep -v 'ops/dev.sh start' | crontab -
    echo "해제했다."
    ;;
  status)
    if crontab -l 2>/dev/null | grep -q 'ops/dev.sh start'; then
      echo "등록됨: $(crontab -l | grep 'ops/dev.sh start')"
    else
      echo "미등록 (ops/autostart.sh install 로 등록)"
    fi
    ;;
  *) echo "사용법: ops/autostart.sh install|remove|status" >&2; exit 2;;
esac
