#!/usr/bin/env bash
# 별빛공방 — 실행 (S4 인프라)
# 인터넷 없이 동작한다. 외부 패키지를 설치하지 않는다.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8080}"

if command -v node >/dev/null 2>&1 && [ -f server.js ]; then
  echo "API + 화면 → http://localhost:$PORT/"
  PORT="$PORT" exec node server.js
fi

# node 가 없으면 화면만 띄운다 (예약은 브라우저 안에서 동작한다)
echo "화면만 → http://localhost:$PORT/  (node 가 없어 API 는 뜨지 않는다)"
exec python3 -m http.server "$PORT"
