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
# 화면에 띄울 주소. 실제 운영 IP 는 커밋하지 않는다 — .env 의 HQ_HOST 에서 읽는다.
HQ_ADDR="$(grep -sE '^HQ_HOST=' .env 2>/dev/null | tail -1 | cut -d= -f2)"
HQ_ADDR="${HQ_ADDR:-localhost}"
# PORT / HQ_PORT 둘 다 받는다. 문서에는 PORT 로 안내돼 있는데
# HQ_PORT 만 보고 있어 새 PC 에서 포트를 못 바꾸는 일이 있었다.
PORT="${PORT:-${HQ_PORT:-8000}}"

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
        echo "HQ 기동 완료 → http://$HQ_ADDR:$PORT/  (pid $(cat "$PIDF"))"
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
    # runs/ 뿐 아니라 showcase/ 도 본다.
    # ★ 사이트는 프론트엔드가 만든다. dba/backend 폴더의 index.html 은 역할 이탈이므로
    #   목록에 띄우지 않는다 (HQ 의 /preview/sites 와 같은 규칙).
    find repo -name index.html -not -path "*/node_modules/*" -not -path "*/.archive/*" \
      2>/dev/null | sort \
      | grep -vE "/(pm|planner|sales|sysadmin|designer|backend|dba|security|qa|customer)/" \
      | sed "s|^repo/|  http://${HQ_ADDR}:${PORT}/preview/|"
    ;;
  status)
    if running; then
      echo "돌고 있다 (pid $(cat "$PIDF"))"
      curl -s "http://127.0.0.1:$PORT/api/health"; echo
      n=$(find repo/runs -type f 2>/dev/null | wc -l)
      s=$(find repo -name index.html -not -path "*/node_modules/*" \
            -not -path "*/.archive/*" 2>/dev/null | wc -l)
      echo "산출물 ${n}개 · 완성된 사이트 ${s}개"
    else echo "안 돌고 있다"; fi
    ;;
  log) tail -f "$LOG" ;;
  *) echo "사용법: ops/dev.sh start|stop|restart|status|log|sites" >&2; exit 2 ;;
esac
