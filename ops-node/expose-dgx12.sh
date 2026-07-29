#!/usr/bin/env bash
# dgx-12(PM PC 겸 HQ) 포트 개방 — root 권한이 필요하다.
#
#   sudo bash ~/agora-ops/expose-dgx12.sh
#
# 여는 것:
#   8022/tcp   SSH        (이미 열려 있음 — 건드리지 않는다)
#   8000/tcp   HQ 웹서비스 (픽셀 오피스 · 주문 사이트 · API)
#   11434/tcp  Ollama     (다른 DGX 와 동일하게 맞춤)
#
# ⚠️ Ollama 와 HQ 에는 인증이 없다. 교실 L2 안에서만 열리는 것을 전제로 한다.
#    외부망에 노출된 대역이라면 8000·11434 는 SSH 터널로만 쓰는 편이 안전하다.
#    되돌리려면:  sudo ufw delete allow 8000/tcp ; sudo ufw delete allow 11434/tcp
#
# 멱등하다 — 두 번 돌려도 같은 결과.
set -uo pipefail
[ "$(id -u)" -eq 0 ] || { echo "root 로 실행해야 한다: sudo bash $0" >&2; exit 1; }

say() { printf '%-26s %s\n' "$1" "$2"; }

# ── 1. Ollama 를 모든 인터페이스에서 듣게 ──────────────────────────
DROPIN=/etc/systemd/system/ollama.service.d/override.conf
if ss -lnt | grep -qE '(0\.0\.0\.0|\*):11434'; then
  say "[1] Ollama 바인딩" "이미 0.0.0.0:11434 — 건너뜀"
else
  mkdir -p "$(dirname "$DROPIN")"
  cat > "$DROPIN" <<'CONF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_ORIGINS=*"
CONF
  systemctl daemon-reload
  systemctl restart ollama
  say "[1] Ollama 바인딩" "0.0.0.0:11434 로 변경"
fi

# ── 2. 방화벽 ──────────────────────────────────────────────────────
if ufw status | grep -qiE "활성|active"; then
  ufw allow 8022/tcp  >/dev/null 2>&1     # 이미 있어도 무해
  ufw allow 8000/tcp  >/dev/null 2>&1
  ufw allow 11434/tcp >/dev/null 2>&1
  say "[2] 방화벽" "8022 · 8000 · 11434 허용"
else
  say "[2] 방화벽" "ufw 비활성 — 조치 불필요"
fi

# ── 3. 확인 ────────────────────────────────────────────────────────
for _ in $(seq 1 20); do
  sleep 1
  ss -lnt | grep -qE '(0\.0\.0\.0|\*):11434' && break
done
say "[3] 듣는 포트" "$(ss -lnt | grep -E ':(8022|8000|11434)\b' | awk '{print $4}' | tr '\n' ' ')"

IP=$(hostname -I | awk '{print $1}')
for p in 8000 11434; do
  code=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://$IP:$p/" 2>/dev/null)
  say "[4] http://$IP:$p" "${code:-무응답}"
done

echo
echo "이제 호스트 PC 에서 바로 접속된다:"
echo "  http://$IP:8000/          픽셀 오피스 (PM 관제)"
echo "  http://$IP:11434/v1/models  Ollama"
