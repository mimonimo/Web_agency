set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
if [ -x "$HOME/.local/bin/hermes" ]; then
  echo "SKIP: 이미 설치됨 -> $(hermes --version 2>&1 | head -1)"
  exit 0
fi
echo "== Hermes 설치 시작 =="
curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o /tmp/hermes-install.sh
bash /tmp/hermes-install.sh --skip-setup 2>&1 | tail -30
echo "== 설치 후 확인 =="
"$HOME/.local/bin/hermes" --version 2>&1 | head -3
