#!/usr/bin/env bash
# 노드에서 실행 — Ollama 를 127.0.0.1 이 아니라 모든 인터페이스에서 듣게 한다.
#
# ⚠️ Ollama 에는 인증이 없다. 교실 L2 안에서만 열리는 것을 전제로 한다.
#    외부망에 노출된 대역이라면 방화벽으로 막아야 한다.
#
# 멱등하다 — 두 번 돌려도 같은 결과.
set -uo pipefail
PW="${NODE_SUDO_PW:?노드 sudo 비밀번호를 NODE_SUDO_PW 로 넘겨라}"
DROPIN=/etc/systemd/system/ollama.service.d/override.conf

say() { printf '%-24s %s\n' "$1" "$2"; }

# 이미 0.0.0.0 이면 아무것도 하지 않는다
if ss -lnt | grep -qE '(0\.0\.0\.0|\*):11434'; then
  say "[1] 바인딩" "이미 0.0.0.0:11434 — 건너뜀"
else
  echo "$PW" | sudo -S mkdir -p "$(dirname "$DROPIN")" 2>/dev/null
  echo "$PW" | sudo -S tee "$DROPIN" >/dev/null <<'CONF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_ORIGINS=*"
CONF
  echo "$PW" | sudo -S systemctl daemon-reload 2>/dev/null
  echo "$PW" | sudo -S systemctl restart ollama 2>/dev/null
  say "[1] 바인딩" "0.0.0.0:11434 로 변경"
fi

# ufw 가 켜져 있으면 11434 를 연다 (노드는 보통 비활성)
if echo "$PW" | sudo -S ufw status 2>/dev/null | grep -qi "활성\|active"; then
  echo "$PW" | sudo -S ufw allow 11434/tcp >/dev/null 2>&1
  say "[2] 방화벽" "11434/tcp 허용"
else
  say "[2] 방화벽" "ufw 비활성 — 조치 불필요"
fi

# 확인
for _ in $(seq 1 20); do
  sleep 1
  ss -lnt | grep -qE '(0\.0\.0\.0|\*):11434' && break
done
if ss -lnt | grep -qE '(0\.0\.0\.0|\*):11434'; then
  say "[3] 확인" "$(ss -lnt | grep 11434 | awk '{print $4}' | tr '\n' ' ')"
else
  say "[3] 확인" "실패 — 아직 127.0.0.1 만 듣는다"; exit 1
fi

MODEL=$(curl -sf -m 5 http://127.0.0.1:11434/v1/models | grep -o 'gpt-oss:120b' | head -1)
say "[4] 모델" "${MODEL:-확인 실패}"
say "결과" "PASS"
