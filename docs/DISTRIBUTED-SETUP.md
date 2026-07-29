# PC 11대에 분산 구성하기

**DGX 가 아니어도 된다.** 일반 PC·노트북 11대(또는 1대)로 돌릴 수 있다.
이 문서만 보고 처음부터 끝까지 따라할 수 있게 썼다.

---

## 0. 먼저 — 정말 11대가 필요한가?

| 구성 | 필요한 것 | 언제 |
|---|---|---|
| **1대 · `sim`** | 아무것도 | 구조·화면·흐름을 보여줄 때. **한 사이클 30초** |
| **1대 · `llm`** | 모델 키 하나 | 결과물 품질을 볼 때. 11개 역할을 HQ 가 병렬로 부른다 |
| **11대 · `a2a`** | PC 11대 + 각자 모델 | **학생 한 명이 PC 한 대를 맡는 수업** |

11대 구성의 값어치는 성능이 아니라 **"내 에이전트"** 다.
학생이 자기 PC 에서 자기 역할의 로그를 보고, 자기 AGENT.md 를 고쳐 결과가 바뀌는 것을
직접 확인한다. 그게 목적이 아니라면 1대로 충분하다.

---

## 1. 노드가 무엇으로 일할지 고르기

노드 어댑터(`node/a2a-adapter/adapter.py`)는 **표준 라이브러리만** 쓴다.
`AGORA_BACKEND` 하나로 실행 방식을 바꾼다.

| `AGORA_BACKEND` | 무엇이 도나 | 파일을 누가 쓰나 | 필요한 것 |
|---|---|---|---|
| `claude` | **Claude Code CLI** | CLI 가 직접 | `claude` 설치 + 로그인 |
| `anthropic` | Claude API (`/v1/messages`) | 어댑터가 저장 | API 키 |
| `openai` | OpenAI 호환 API | 어댑터가 저장 | Ollama·vLLM·LM Studio 등 |
| `hermes` (기본) | Hermes + 로컬 Ollama | Hermes 가 직접 | 교실 DGX 구성 |

`claude`·`hermes` 는 도구가 파일을 직접 만든다.
`anthropic`·`openai` 는 글만 돌아오므로 어댑터가 **출력 규약**을 붙이고 저장한다.

```
=== FILE: index.html ===
(내용)
=== END ===
```

규약을 못 지킨 응답은 **저장하지 않고 실패로 돌린다.** 억지로 통짜 저장하면
엉뚱한 내용이 `index.html` 이 되어 아무도 원인을 못 찾는다.

---

## 2. HQ 1대 (아무 PC 나)

```bash
git clone https://github.com/mimonimo/Web_agency.git agora && cd agora
./ops/bootstrap.sh

# 노드를 쓸 것이므로 a2a 로
sed -i 's/^EXECUTOR=.*/EXECUTOR=a2a/' .env

# ★ 노드 IP — 리포의 students.yaml 은 예시 값(10.0.0.x)이다.
#   HQ 는 부팅할 때마다 이 파일로 노드 주소를 덮어쓴다.
cp provisioning/students.yaml provisioning/students.local.yaml
$EDITOR provisioning/students.local.yaml     # ip 를 실제 값으로

./ops/dev.sh start        # → http://<HQ주소>:8000
```

방화벽에서 **8000** 을 열어 둔다 (노드가 HQ 로 미러링·하트비트를 보낸다).

> ⚠️ **`HQ_SELF_URL` 은 노드가 나를 부를 수 있는 주소여야 한다.**
> 노드는 이 주소로 AGENT.md 와 참고 자료를 받아 간다. `127.0.0.1` 이면 노드가
> **자기 자신**에게 물어보고 404 를 받는데, **단계는 실패하지 않는다** —
> 에이전트가 아무것도 못 받은 채 지어내기 때문이다. 가장 알아채기 어려운 종류의 고장이다.
> `bootstrap.sh` 가 이 PC 의 IP 로 자동으로 채우고, 비어 있으면 HQ 가 스스로 찾는다.
> a2a 인데 루프백이면 부팅 로그에 경고가 뜨고 `acceptance.sh` 가 실패로 잡는다.

### PM PC 를 바꿔도 노드는 안 고친다

**노드는 자기를 부른 HQ 를 따라간다.** HQ 가 매 요청에 `hq_url` 을 실어 보내고
어댑터가 그쪽으로 미러링·하트비트를 돌린다(`adopt_hq`). 새 PC 에서
`./ops/dev.sh start` 만 하면 노드 11대의 `.env` 는 손대지 않아도 된다.

```bash
# 새 PM PC 에서
git clone https://github.com/mimonimo/Web_agency.git agora && cd agora
./ops/bootstrap.sh                                   # HQ_SELF_URL 자동
sed -i 's/^EXECUTOR=.*/EXECUTOR=a2a/' .env
cp <노드IP 가 든 파일> provisioning/students.local.yaml
./ops/dev.sh start
./ops/acceptance.sh --phase 2                        # 카드 11/11 이면 끝
```

첫 단계를 보내는 순간 노드가 새 HQ 로 갈아탄다 — 노드 로그에 이렇게 남는다.

```
[hq] HQ 를 http://<옛HQ>:8000 → http://<새HQ>:8000 로 바꾼다 (요청에 실려 왔다)
```

---

## 3. 노드 11대

각 PC 에서 한 번씩. `<역할>` 은 아래 11개 중 하나다.

```
pm  planner  sales  sysadmin  designer  frontend  backend  dba  security  qa  customer
```

```bash
git clone https://github.com/mimonimo/Web_agency.git agora-node && cd agora-node

mkdir -p ~/agora-node && cp node/a2a-adapter/adapter.py ~/agora-node/
cd ~/agora-node

cat > .env <<'ENV'
AGORA_ROLE=frontend
AGORA_NODE_ID=pc-06
AGORA_DISPLAY_NAME=프론트엔드
AGORA_HQ_URL=http://<HQ주소>:8000
AGORA_BACKEND=claude
AGORA_MODEL=claude-opus-5
ENV

python3 adapter.py --port 41241
```

방화벽에서 **41241** 을 연다 (HQ 가 노드를 부른다).

### 백엔드별로 더 필요한 것

```bash
# claude  — Claude Code CLI 가 파일을 직접 쓴다
npm i -g @anthropic-ai/claude-code
claude auth login                # 또는  export ANTHROPIC_API_KEY=sk-ant-...
# 경로가 다르면  AGORA_CLAUDE_BIN=/usr/local/bin/claude

# anthropic — CLI 없이 API 직접
echo 'AGORA_BACKEND=anthropic'   >> .env
echo 'AGORA_MODEL=claude-opus-5' >> .env
echo 'AGORA_API_KEY=sk-ant-...'  >> .env

# openai 호환 — 로컬 Ollama 등
echo 'AGORA_BACKEND=openai'                        >> .env
echo 'AGORA_API_BASE=http://127.0.0.1:11434/v1'    >> .env
echo 'AGORA_MODEL=gpt-oss:120b'                    >> .env
```

### 재부팅해도 뜨게

```bash
(crontab -l 2>/dev/null; \
 echo "@reboot sleep 20 && cd ~/agora-node && python3 adapter.py --port 41241 >> adapter.log 2>&1") \
 | crontab -
```

---

## 4. 제대로 붙었는지 확인 — 이것만 보면 된다

```bash
# HQ 에서
./ops/acceptance.sh --phase 2
```

```
✅ 에이전트 카드 11/11 조회 성공 (인수 #6)
✅ 노드 11/11 하트비트 정상 (인수 #7)
```

> ⚠️ **하트비트만 보고 안심하지 마라.**
> 하트비트는 **노드가 HQ 로 밀어 넣는 것**이다. HQ 가 노드를 못 불러도 화면에는
> 11대 전부 `up` 으로 뜬다. 실제로 이 함정에 걸려 모든 단계가 `ConnectTimeout` 으로
> 죽는데 노드는 멀쩡해 보였다. **카드 조회(인수 #6)가 진짜 판정이다.**

노드 하나만 볼 때:

```bash
curl -s http://<노드IP>:41241/.well-known/agent-card.json
curl -s http://<노드IP>:41241/health     # {"ok":true,"backend":"claude","model":...}
```

---

## 5. 수업 흐름

1. 프로젝터에 HQ 의 `/` (픽셀 오피스) 또는 `/console.html` 을 띄운다
2. `/order.html` 에서 주문을 넣는다
3. S1 영업 → S2 기획이 **AGENT.md 11개**를 만든다 (가장 오래 걸린다)
4. **S3 에서 자동으로 멈춘다.** 학생이 각자 `/edit.html?role=<자기역할>` 에서
   자기 지시문을 고치고 저장한다
5. **11/11 이 되면 자동 재개.** 설계 → 구현 → QA·보안·검수 게이트 → 배포 → 운영
6. 결과물은 `/projects.html`, 고칠 것은 `/review.html` 에서 보면서 바로 요청

자세한 것은 [`FLOW.md`](../FLOW.md).

---

## 6. 막히면

| 증상 | 확인 |
|---|---|
| 카드 조회 0/11 | `students.local.yaml` 의 IP. 하트비트가 `up` 이어도 소용없다 |
| 단계가 계속 실패 | 노드의 `~/agora-node/workspace/cycle-N/<step>/run.log` |
| `claude 를 찾을 수 없다` | `which claude` → `AGORA_CLAUDE_BIN` 에 절대경로 |
| `파일 형식을 지키지 않았다` | `anthropic`/`openai` 백엔드에서 모델이 규약을 어긴 것. `run.log` 에 응답 앞부분이 남는다 |
| 노드가 무응답 | `curl <노드>:41241/health`. 죽었으면 `python3 adapter.py --port 41241` 재실행 |
| 산출물이 사라졌다 | 노드의 `workspace/` 에 원본이 있다. `ops-node/recover-artifacts.sh <사이클>` |

결과물에서 반복되는 결함과 대처는 [`KNOWN-ISSUES.md`](KNOWN-ISSUES.md).

---

## 7. 한 대에서 11개 역할을 다 돌리기 (PC 가 부족할 때)

포트만 다르게 해서 같은 PC 에 여러 어댑터를 띄우면 된다.

```bash
for r in pm planner sales sysadmin designer frontend backend dba security qa customer; do
  d=~/agora-node-$r && mkdir -p "$d" && cp adapter.py "$d/"
  cat > "$d/.env" <<ENV
AGORA_ROLE=$r
AGORA_NODE_ID=local-$r
AGORA_HQ_URL=http://127.0.0.1:8000
AGORA_BACKEND=claude
ENV
done
# 포트를 41241 부터 하나씩 올려 띄우고, students.local.yaml 의 a2a_url 을 맞춘다
```

이 경우 `students.local.yaml` 에 `a2a_url` 을 직접 적는다
(`ip` 대신 `a2a_url: http://127.0.0.1:41246/` 처럼).
