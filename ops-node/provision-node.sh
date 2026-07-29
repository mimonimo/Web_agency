#!/usr/bin/env bash
# AGORA 노드 프로비저닝 — 노드 위에서 실행된다. 멱등하다(두 번 돌려도 같은 결과).
# 환경변수로 ROLE / DISPLAY / NODE_ID / HQ_URL 을 받는다.
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"

ROLE="${ROLE:?ROLE 미지정}"
DISPLAY_NAME="${DISPLAY_NAME:-$ROLE}"
NODE_ID="${NODE_ID:-$(whoami)}"
HQ_URL="${HQ_URL:-http://10.0.0.62:8000}"
OLLAMA_URL="http://127.0.0.1:11434"
MODEL="gpt-oss:120b"

fail=0
say() { printf '%-22s %s\n' "$1" "$2"; }

# ── 1. Ollama 확인 ────────────────────────────────────────────────
if curl -sf -m 10 "$OLLAMA_URL/v1/models" | grep -q "$MODEL"; then
  say "[1] ollama" "OK ($MODEL 서빙중)"
else
  say "[1] ollama" "실패 — $OLLAMA_URL 에서 $MODEL 을 찾을 수 없음"; fail=1
fi

# ── 2. Hermes 존재 확인 ───────────────────────────────────────────
if command -v hermes >/dev/null 2>&1; then
  say "[2] hermes" "OK ($(hermes --version 2>&1 | head -1 | awk '{print $1, $2, $3}'))"
else
  say "[2] hermes" "실패 — hermes 미설치"; fail=1
fi

# ── 3. Hermes → Ollama 연결 (멱등) ────────────────────────────────
if [ "$fail" -eq 0 ]; then
  [ -f "$HOME/.hermes/config.yaml.pre-ollama.bak" ] || \
    cp "$HOME/.hermes/config.yaml" "$HOME/.hermes/config.yaml.pre-ollama.bak" 2>/dev/null
  hermes config set model.provider ollama            >/dev/null 2>&1
  hermes config set model.base_url "$OLLAMA_URL/v1"  >/dev/null 2>&1
  hermes config set model.default "$MODEL"           >/dev/null 2>&1
  got=$(python3 - <<'PY'
import yaml, os, json
c = yaml.safe_load(open(os.path.expanduser("~/.hermes/config.yaml")))["model"]
print(f'{c.get("provider")}|{c.get("base_url")}|{c.get("default")}')
PY
)
  if [ "$got" = "ollama|$OLLAMA_URL/v1|$MODEL" ]; then
    say "[3] hermes→ollama" "OK ($got)"
  else
    say "[3] hermes→ollama" "실패 — 실제값: $got"; fail=1
  fi
fi

# ── 4. 노드 식별자 (멱등) ─────────────────────────────────────────
mkdir -p "$HOME/agora/workspace" "$HOME/agora/runs"
cat > "$HOME/agora/node.env" <<ENV
# AGORA 노드 식별자 — PM(dgx-12) 이 배포함. 손으로 고치지 말 것.
AGORA_NODE_ID=$NODE_ID
AGORA_ROLE=$ROLE
AGORA_DISPLAY_NAME=$DISPLAY_NAME
AGORA_HQ_URL=$HQ_URL
AGORA_OLLAMA_URL=$OLLAMA_URL
AGORA_MODEL=$MODEL
AGORA_WORKSPACE=$HOME/agora/workspace
ENV
say "[4] node.env" "OK (role=$ROLE, $HOME/agora/node.env)"

# ※ agents/<role>/AGENT.md 는 여기서 만들지 않는다.
#    BRIEF §10 — 초안은 S2 에서 기획 에이전트가 생성하는 것이 수업 내용이다.

[ "$fail" -eq 0 ] && say "결과" "PASS" || say "결과" "FAIL"
exit $fail
