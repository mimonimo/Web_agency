#!/usr/bin/env bash
# 새로 받은 리포를 돌아가는 상태로 만든다. 한 번만 실행하면 된다.
#
#   git clone https://github.com/mimonimo/Web_agency.git agora && cd agora
#   ./ops/bootstrap.sh
#   ./ops/dev.sh start        →  http://localhost:8000
#
# 멱등하다 — 몇 번을 돌려도 같은 결과다.
# 노드(DGX)가 없는 PC 를 전제로 `EXECUTOR=sim` 을 기본으로 잡는다.
# 실제 노드가 있으면 .env 에서 a2a 로 바꾼다.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

ok=0; ng=0
say()  { printf '  %-42s %s\n' "$1" "$2"; }
good() { ok=$((ok+1)); say "$1" "✅ $2"; }
bad()  { ng=$((ng+1)); say "$1" "❌ $2"; }

echo "════════════════════════════════════════════════════════════"
echo " AGORA Web — 새 환경 준비"
echo " $ROOT"
echo "════════════════════════════════════════════════════════════"

# ── 1. 파이썬 ─────────────────────────────────────────────────
PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "")
if [ -z "$PYV" ]; then
  bad "python3" "없다. 3.11 이상을 설치해라"
  exit 1
fi
if [ "$(printf '%s\n3.11\n' "$PYV" | sort -V | head -1)" != "3.11" ]; then
  bad "python3 $PYV" "3.11 이상이 필요하다"
else
  good "python3 $PYV" "ok"
fi

# ── 2. venv ───────────────────────────────────────────────────
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv >/dev/null 2>&1 \
    && good ".venv 생성" "새로 만들었다" \
    || { bad ".venv 생성" "python3-venv 를 설치해라 (apt install python3-venv)"; exit 1; }
else
  good ".venv" "이미 있다"
fi

# ── 3. 의존성 ─────────────────────────────────────────────────
if ./.venv/bin/python -c "import fastapi, sqlalchemy, httpx, yaml" >/dev/null 2>&1; then
  good "의존성" "이미 설치돼 있다"
else
  echo "  의존성 설치 중… (인터넷 필요)"
  if ./.venv/bin/pip install -q --upgrade pip >/dev/null 2>&1 \
     && ./.venv/bin/pip install -q -r core/requirements.txt >/dev/null 2>&1; then
    good "의존성" "설치 완료"
  elif [ -d ops/wheels ] && ls ops/wheels/*.whl >/dev/null 2>&1; then
    ./.venv/bin/pip install -q --no-index --find-links ops/wheels -r core/requirements.txt \
      && good "의존성" "오프라인 wheel 로 설치" \
      || bad "의존성" "설치 실패"
  else
    bad "의존성" "설치 실패 — 인터넷 또는 ops/wheels/ 가 필요하다"
  fi
fi

# ── 4. .env ───────────────────────────────────────────────────
if [ -f .env ]; then
  good ".env" "이미 있다 (건드리지 않는다)"
else
  cp .env.example .env
  # 노드가 없는 PC 를 전제로 sim 으로 시작한다
  if grep -q '^EXECUTOR=' .env; then
    sed -i 's/^EXECUTOR=.*/EXECUTOR=sim/' .env
  else
    echo "EXECUTOR=sim" >> .env
  fi
  # 표시용 주소는 localhost 로 (리포의 IP 는 예시 값이다)
  sed -i 's/^HQ_HOST=.*/HQ_HOST=localhost/' .env 2>/dev/null || true
  # ★ 이 PC 가 HQ 가 될 때 노드가 부를 주소. a2a 로 바꾸면 바로 필요해진다.
  MYIP=$(python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('10.255.255.255',1));print(s.getsockname()[0])" 2>/dev/null || echo "")
  if [ -n "$MYIP" ]; then
    grep -q '^HQ_SELF_URL=' .env \
      && sed -i "s#^HQ_SELF_URL=.*#HQ_SELF_URL=http://$MYIP:8000#" .env \
      || echo "HQ_SELF_URL=http://$MYIP:8000" >> .env
    good ".env" "생성 (EXECUTOR=sim · HQ_SELF_URL=http://$MYIP:8000)"
  else
    good ".env" "생성 (EXECUTOR=sim · HQ_HOST=localhost)"
  fi
fi

# ── 5. 작업 디렉터리 ──────────────────────────────────────────
mkdir -p repo/project-001/agents repo/runs
good "repo/ 작업 디렉터리" "준비됨"

# ── 6. 확인 ───────────────────────────────────────────────────
if ./.venv/bin/python -c "
import sys; sys.path.insert(0,'core')
import app.main" >/dev/null 2>&1; then
  good "앱 로드" "ok"
else
  bad "앱 로드" "임포트 실패 — .venv/bin/python -c 'import sys;sys.path.insert(0,\"core\");import app.main' 로 원인을 봐라"
fi

if ./.venv/bin/python core/tests/test_roles.py >/tmp/agora-boot.log 2>&1; then
  good "역할 카탈로그·기준선" "$(grep -c '✅' /tmp/agora-boot.log)건 통과"
else
  bad "역할 카탈로그·기준선" "실패 — /tmp/agora-boot.log 를 봐라"
fi

echo
echo "────────────────────────────────────────────────────────────"
printf ' 준비 %d · 문제 %d\n' "$ok" "$ng"
if [ "$ng" -eq 0 ]; then
  cat <<'NEXT'

 다음:
   ./ops/dev.sh start        HQ 기동 → http://localhost:8000
   ./ops/acceptance.sh       전체 인수 (HQ 가 떠 있어야 한다)
   ./ops/reference-check.sh --all   결과물 채점·비교

 알아 둘 것:
   · EXECUTOR=sim 으로 시작한다. 노드 없이 흐름·화면을 다 볼 수 있다.
     실제 DGX 노드가 있으면 .env 에서 EXECUTOR=a2a 로 바꾼다.
   · repo/runs·project-001·agora.db 는 git 에 없다. 첫 사이클을 돌리면 생긴다.
   · repo/showcase/ 는 git 에 있다 — 지난 결과물 3벌을 바로 볼 수 있다.
   · ops-node/ 의 IP 는 예시 값(10.0.0.x)이다. 쓰려면 nodes.tsv 를 고쳐라.
NEXT
  exit 0
else
  echo
  echo " 위 ❌ 를 먼저 해결해라."
  exit 1
fi
