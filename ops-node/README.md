# AGORA 노드 운영 (PM: dgx-12)

이 디렉터리는 **관리 PC(dgx-12 = pm 역할)** 에서 학생 노드 dgx-02~11 을 다루는 도구 모음이다.
모든 스크립트는 멱등하다 — 두 번 돌려도 결과가 같다.

## 스크립트

| 스크립트 | 하는 일 |
|---|---|
| `status-all.sh` | 10대 상태 한 줄 요약 (추론 안 함, 빠름) |
| `provision-all.sh` | 10대 프로비저닝 — Hermes↔Ollama 연결, `node.env` 배포 |
| `provision-node.sh` | 노드 1대에서 실행되는 본체 (`provision-all.sh` 가 밀어 넣음) |
| `verify-all.sh` | 10대에서 **실제 추론 왕복**을 시켜 검증 (느림, 모델 로딩 포함) |
| `dgx-fan.sh` | 임의 셸 스크립트를 10대에 동시 실행 |
| `install-hermes.sh` | Hermes 미설치 노드에 설치 (설치돼 있으면 건너뜀) |
| `nodes.tsv` | 노드 ↔ IP ↔ 역할 매핑 (**단일 진실 공급원**) |

```bash
./status-all.sh                              # 현황
./provision-all.sh                           # 재적용
./verify-all.sh                              # 실제 추론 검증
echo 'ollama list' | ./dgx-fan.sh            # 전체에 임의 명령
echo 'ollama list' | ./dgx-fan.sh dgx-07     # 특정 노드만
```

## 접속

`~/.ssh/config` 에 `dgx-02` ~ `dgx-11` 별칭이 등록돼 있고, PM 키(`~/.ssh/id_ed25519`,
comment `dgx-12-pm`)로 무암호 접속한다. 비밀번호(설치 시 정한 값)는 그대로 살아 있으므로
키가 깨져도 잠기지 않는다.

```bash
ssh dgx-07                                   # 바로 접속
```

## 역할 매핑

BRIEF §1.3 의 11개 역할 중 `pm` 은 이 PC(dgx-12)이고, 나머지 10개를 노드 번호 순서로 배정했다.

| 노드 | IP | 역할 | 표기 |
|---|---|---|---|
| dgx-02 | 10.0.0.52 | `planner` | 기획 |
| dgx-03 | 10.0.0.53 | `sales` | 영업 |
| dgx-04 | 10.0.0.54 | `sysadmin` | 인프라 |
| dgx-05 | 10.0.0.55 | `designer` | 디자인 |
| dgx-06 | 10.0.0.56 | `frontend` | 프론트엔드 |
| dgx-07 | 10.0.0.57 | `backend` | 백엔드 |
| dgx-08 | 10.0.0.58 | `dba` | DB |
| dgx-09 | 10.0.0.59 | `security` | 보안 |
| dgx-10 | 10.0.0.60 | `qa` | QA |
| dgx-11 | 10.0.0.61 | `customer` | 고객 |
| dgx-12 | 10.0.0.62 | `pm` | 관리 (이 PC) |

역할을 바꾸려면 `nodes.tsv` 만 고치고 `./provision-all.sh` 를 다시 돌린다.

## 노드에 배포된 것

각 노드 `~/agora/node.env`:

```
AGORA_NODE_ID=dgx-07
AGORA_ROLE=backend
AGORA_DISPLAY_NAME=백엔드
AGORA_HQ_URL=http://10.0.0.62:8000     ← HQ 미구축. 자리만 잡아 둠
AGORA_OLLAMA_URL=http://127.0.0.1:11434
AGORA_MODEL=gpt-oss:120b
AGORA_WORKSPACE=~/agora/workspace
```

`~/agora/workspace/`, `~/agora/runs/` 도 함께 생성된다.

## 모델 경로

```
Hermes (~/.local/bin/hermes)
   └─ provider: ollama · base_url: http://127.0.0.1:11434/v1 · model: gpt-oss:120b
        └─ 각 노드 로컬 Ollama (systemd, 127.0.0.1:11434)
```

**노드마다 자기 DGX 의 Ollama 를 쓴다.** 네트워크를 타지 않으므로 인터넷이 끊겨도 돈다.
원래 설정(OpenRouter + `anthropic/claude-opus-4.6`)은 각 노드
`~/.hermes/config.yaml.pre-ollama.bak` 에 보관돼 있다.
