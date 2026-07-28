#!/usr/bin/env bash
# 네이티브로 HQ 를 띄운다 (docker 권한 없이). venv + uvicorn + SQLite.
#
#   ops/dev.sh start | stop | restart | status | log
#
# docker 그룹 권한이 생기면 `make up` 으로 컨테이너 구성으로 옮겨가면 된다.
# 코드와 산출물 경로는 양쪽이 완전히 동일하다.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
PIDF="$ROOT/.hq.pid"
LOG="$ROOT/repo/hq.log"
PORT="${HQ_PORT:-8000}"

[ -f .env ] || cp .env.example .env

running() { [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; }

case "${1:-start}" in
  start)
    if running; then echo "이미 돌고 있다 (pid $(cat "$PIDF"))"; exit 0; fi
    mkdir -p repo
    set -a; . ./.env; set +a
    cd core
    setsid nohup "$ROOT/.venv/bin/uvicorn" app.main:app \
        --host 0.0.0.0 --port "$PORT" >"$LOG" 2>&1 < /dev/null &
    echo $! > "$PIDF"
    disown 2>/dev/null || true
    for _ in $(seq 1 40); do
      sleep 0.5
      if curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
        echo "HQ 기동 완료 → http://220.67.5.62:$PORT/  (pid $(cat "$PIDF"))"
        exit 0
      fi
    done
    echo "기동 실패. 로그:"; tail -20 "$LOG"; exit 1
    ;;
  stop)
    if running; then kill "$(cat "$PIDF")" && echo "정지했다"; else echo "안 돌고 있다"; fi
    rm -f "$PIDF"
    ;;
  restart) "$0" stop; sleep 1; "$0" start ;;
  # artifacts-guard: 산출물이 얼마나 쌓여 있는지 알려준다
  sites)
    find repo/runs -name index.html -not -path "*/node_modules/*" 2>/dev/null \
      | sed "s|repo/|  http://220.67.5.62:${PORT}/preview/|"
    ;;
  status)
    if running; then
      echo "돌고 있다 (pid $(cat "$PIDF"))"
      curl -s "http://127.0.0.1:$PORT/api/health"; echo
      n=$(find repo/runs -type f 2>/dev/null | wc -l)
      s=$(find repo/runs -name index.html -not -path "*/node_modules/*" 2>/dev/null | wc -l)
      echo "산출물 ${n}개 · 완성된 사이트 ${s}개"
    else echo "안 돌고 있다"; fi
    ;;
  log) tail -f "$LOG" ;;
  *) echo "사용법: ops/dev.sh start|stop|restart|status|log|sites" >&2; exit 2 ;;
esac
