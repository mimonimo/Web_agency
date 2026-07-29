# AGORA Web — 구조

11명의 AI 에이전트가 **웹 에이전시처럼** 일하는 것을 학생이 조종하며 배우는 시스템.

이 문서는 "무엇이 어디에 있고, 왜 그렇게 만들었나" 를 설명한다.
운영 방법은 [`agora-ops/HANDOFF.md`](https://github.com/mimonimo/Web_agency), 수업 흐름은 [`FLOW.md`](FLOW.md).

---

## 1. 한 장으로

```
                    ┌──────────────── 사람 ────────────────┐
                    │  주문 접수 · 지시 추가 · 보고 고치기   │
                    │  AGENT.md 편집 · 게이트 판정 · 되감기  │
                    └───────────────┬──────────────────────┘
                                    │  브라우저 (CDN 없음)
                    ┌───────────────▼──────────────────────┐
                    │   HQ  (dgx-12)  FastAPI + SQLite      │
                    │                                       │
   pipeline.yaml ──▶│  orchestrator  상태기계 (순수 함수)    │
   roles.yaml    ──▶│  runner        단계 실행 + 자가 재작업 │
   agents/*.md   ──▶│  checks        산출물 기계 검사        │
   templates/    ──▶│  directives    사람이 끼워 넣는 지시   │
                    └───────────────┬──────────────────────┘
                                    │  A2A (JSON-RPC 2.0)
        ┌───────────┬───────────┬───┴───────┬───────────┬───────────┐
     dgx-02      dgx-03      dgx-04       …          dgx-11      dgx-12
     기획         영업        인프라                    고객       관리(PM)
   ┌─────────────────────────────────────────────────────────────────┐
   │  각 노드: A2A 어댑터 → Hermes → 로컬 Ollama (gpt-oss:120b)        │
   │  모델은 노드 안에 있다. 네트워크를 안 타므로 인터넷이 없어도 돈다.  │
   └─────────────────────────────────────────────────────────────────┘
```

---

## 2. 설계에서 가장 중요한 결정 세 가지

### 2-1. 지시문의 뼈대는 사람이 쓴다

교실의 로컬 모델(`gpt-oss:120b`)에게 "11개 역할 지시문을 알아서 잘 써라" 를 시키면
빈 템플릿이나 서로 똑같은 문장이 나온다. 실제로 그랬다.

그래서 **구조와 품질 기준은 사람이 확정**하고, 모델에게는 짧고 구체적인 일만 맡긴다.

| | 누가 | 무엇 | 어디에 |
|---|---|---|---|
| 기준선 | 사람 (Claude Code) | 역할·금지·완료조건·보고 | `agents/<role>/AGENT.md` (git) |
| 이번 프로젝트 | 기획 에이전트 | 이번 주문에서 맡는 일 4줄 | 기준선의 「이번 프로젝트」 칸 |
| 보강 | 학생 | 자기 전문 지식 | `repo/<project>/agents/<role>/AGENT.md` |
| 개입 | 사람 (수시로) | 작업 도중의 요구 | `.../NOTES.md` |

이 구조는 **모델을 바꿔도 유지된다.** Claude 를 붙이든 더 큰 오픈 모델을 붙이든,
품질의 바닥은 기준선이 잡는다. 좋은 모델은 그 위에서 더 잘할 뿐이다.

### 2-2. 부탁하지 않고 검사한다

모델에게 "viewport 를 넣어라" 라고 **부탁**하는 것과,
넣었는지 **확인하고** 안 넣었으면 그 사실을 알려 주며 다시 시키는 것은 다른 일이다.

```
지시 → 실행 → ★검사(checks.py) → 미달이면 실패 목록을 붙여 재실행 → 게이트
                                   └ 기본 1회. CHECK_RETRY 로 조절.
```

`checks.py` 가 보는 것은 **형식·존재·수치**뿐이다 (viewport 유무, CSS 변수 개수,
외래키 유무, 판정 첫 줄 형식…). 의미는 QA·보안·검수 게이트 에이전트가 본다.
기계가 볼 수 있는 것을 기계가 보면, 게이트는 진짜 문제에 집중할 수 있다.

검사기가 제대로 구별하는지는 실제 결과물 두 벌로 확인한다 —
`repo/showcase/v1-before`(8/15) vs `v2-after`(15/15).

### 2-3. 파이프라인은 코드가 아니라 데이터

단계를 코드에 하드코딩하면 강사가 수업 중에 손댈 수 없다.
`pipeline.yaml` 에 단계·담당·입력·출력·타임아웃이 다 있다. 4종이 있다.

| 파일 | 언제 |
|---|---|
| `pipeline.yaml` | 신규 개발 (S1~S10) |
| `pipeline.change.yaml` | 변경 요청 |
| `pipeline.defect.yaml` | 결함 신고 |
| `pipeline.security.yaml` | 보안 이슈 |

`inputs` 가 특히 중요하다. 여기 안 적으면 그 에이전트는 앞 단계 산출물을 **못 본다.**
실제로 이걸 빠뜨려서 프론트엔드가 화면 목록도 디자인 토큰도 없이 사이트를 만든 적이 있다
(품질 53점). 채우고 나니 100점이 됐다.

---

## 3. 디렉터리

```
agora/
  agents/<role>/AGENT.md      ★ 기준선 11개 — 사람이 쓴 역할 지시문 (git 추적)
  core/app/
    main.py                   FastAPI 앱 · 부팅 복구 · 스펙 감시 루프
    orchestrator.py           ★ 상태기계 (순수 함수. DB 를 모른다)
    runner.py                 단계 실행 · 자가 재작업 · A2A 호출
    checks.py                 ★ 산출물 기계 검사 (역할별 DoD)
    roles.py / roles.yaml     ★ 역할 카탈로그 — 목표·완료조건·금지·인계
    directives.py             ★ 사람이 끼워 넣는 지시 (NOTES.md)
    services.py               DB 반영 · 기준선 합성 · 미러링 · 감사 로그
    pipelines.py              pipeline.yaml 로더
    a2a_client.py / a2a_server.py
    templates/                작업 지시 템플릿 (task 별 + 공통 품질 기준)
    routers/                  cycles nodes specs tickets orders messages
                              artifacts dashboard agents review activity
  web/                        화면 9개 (빌드 없음 · 프레임워크 없음 · CDN 없음)
  node/a2a-adapter/           노드에 배포되는 어댑터 (표준 라이브러리만)
  repo/                       ← 작업 공간 (대부분 git 제외)
    <project>/agents/<role>/  AGENT.md(작업본) · NOTES.md(추가 지시)
    runs/<cycle>/<step>/      단계별 산출물 + 완료 보고
    showcase/                 시연·비교용 보존본
  ops/                        dev.sh · acceptance.sh · reset.sh · rehearsal.sh
  core/tests/                 상태기계 · 흐름 · 판정 · 역할카탈로그 · 미리보기
```

---

## 4. 사이클 상태기계

```
READY ──start──▶ RUNNING ──(모든 단계 완료)──▶ DONE
                   │  ▲
        pause      │  │  resume
                   ▼  │
                 PAUSED
                   │
   human_gate 도달 ▼
                BLOCKED ──(11명이 AGENT.md 저장)──▶ 자동 재개
                   │
      게이트 반려   ▼
              되감기(rewind) + 재작업 티켓 자동 생성
```

- `orchestrator.next_step(cycle, steps, event)` 은 **순수 함수**다.
  DB 를 import 하지 않는다. 그래서 상태기계만 따로 테스트할 수 있다 (38건).
- DB 반영은 `services.apply()` 가 한다.
- **`reset` 의 기본값은 `keep_specs=True`.** 학생이 고친 AGENT.md 를
  리셋 한 번에 날리면 수업이 망한다.

### 사람이 개입하는 다섯 지점

| 지점 | 화면 | 무슨 일이 일어나나 |
|---|---|---|
| 주문 | `/order.html` | 새 사이클 생성 |
| S3 게이트 | `/edit.html` | 11명이 다 저장하면 **자동 재개** |
| 작업 도중 | `/agent.html`, `/review.html` | 지시가 다음 실행 프롬프트 맨 뒤에 붙는다 |
| 게이트 판정 | `/board.html` | 통과(사유 기록) 또는 반려 → 되감기 |
| 아무 때나 | `/index.html` | 일시정지 · 한 단계 · 되감기 · 처음부터 |

---

## 5. 작업 지시가 조립되는 순서

`runner._instruction(sdef, role)` — **뒤에 오는 것이 앞을 이긴다**고 모델에게 알려 두었다.

```
1. templates/<task>.md        무엇을 만드는가
2. templates/_quality.md      공통 품질 기준 (오프라인·시맨틱·토큰·접근성·응답형식)
3. roles.brief(role)          이 역할의 목표 + 완료 조건 + 금지    ← roles.yaml
4. (S2만) 스펙 템플릿
5. ★ directives.block(role)   사람이 끼워 넣은 지시 — 최우선
```

여기에 A2A 요청이 함께 싣는 것:

- `spec_url` — 그 역할의 AGENT.md (노드가 먼저 읽는다)
- `context_urls` — `inputs` 를 **실제 파일 경로로 해석**해서 전달 (`resolve_inputs`)
- `order` — 주문서 원문 (지어내지 못하게)
- `outputs` — 만들어야 할 파일 이름

> ⚠️ **프롬프트 크기를 항상 본다.** 게이트에 심사 파일을 8종 붙였더니 26KB 가 됐고
> 로컬 모델이 멈췄다. 어댑터가 파일당 4000자 / 전체 14000자로 자르고,
> 자른 파일은 제목에 `(앞부분만)` 이라고 밝힌다. 조용히 자르면
> 에이전트가 "이게 전부" 라고 오해한다.
>
> **참고 자료를 안 주면 지어내고, 너무 주면 멈춘다.**

---

## 6. A2A — HQ ↔ 노드

와이어 포맷은 A2A 표준과 글자 그대로 같게 맞추고 구현만 직접 했다.

```
POST /                     JSON-RPC 2.0
  message/send  → { taskId }
  tasks/get     → { state: submitted|working|completed|failed, artifacts[], report }
GET /.well-known/agent-card.json
```

**표준 SDK 를 쓰지 않은 이유**: 어댑터가 하는 일은 네 가지뿐인데
SDK 를 쓰면 학생 노드 11대에 31개 패키지와 venv 를 얹어야 한다.
`python3 adapter.py` 한 줄로 뜨는 쪽이 교실에서 안전하다.
필드명·엔드포인트가 같으므로 나중에 갈아끼울 수 있다.

노드는 작업을 받으면 HQ 에 **미러링**한다 (착수·완료·경고).
미러링하지 않은 메시지는 화면에도 감사 로그에도 안 남는다.

---

## 7. 화면 9개

| 화면 | 하는 일 |
|---|---|
| `/index.html` | 픽셀 오피스 — 관제. 책상을 누르면 에이전트 상세 |
| `/console.html` | ★ 실시간 콘솔 — 활동 피드 · 경과 시간 · **받은 지시문 전문** |
| `/review.html` | ★ 보면서 고치기 — 프리뷰 + 「지금 고치기 / 다음 사이클로」 |
| `/projects.html` | 작업물 — 사이클별 결과물, 메인·서브 페이지 |
| `/agent.html` | 역할 상세 — 목표·완료조건, **지시 추가**, 검사, ↻재요청 |
| `/edit.html` | AGENT.md 편집 (학생) — 기준선·작업본·추가지시·초안비교 4탭 |
| `/board.html` | 티켓 — 생성·이동·담당변경·삭제, **게이트 통과/반려** |
| `/files.html` | `repo/` 탐색기 — 검색·조회·수정·새 파일·다운로드·미리보기 |
| `/order.html` | 신규 접수 전용 |

빌드 도구가 없다. 프레임워크가 없다. CDN 이 없다.
교실에서 인터넷이 끊겨도 그대로 돈다.

---

## 8. 실행 백엔드를 갈아끼우는 지점

```
EXECUTOR=sim   HQ 안에서 산출물을 흉내낸다 (한 단계 1~4초) — 흐름·화면 확인용
EXECUTOR=a2a   실제 학생 노드의 Hermes 를 호출한다          — 수업 당일
```

어느 쪽이든 **상태기계와 산출물 경로는 완전히 같다.**
다른 모델(Claude API, 더 큰 오픈 모델)을 붙이려면
`runner._execute_*` 를 하나 더 만들고 `EXECUTOR` 에 이름을 더하면 된다.
지시문·검사·개입은 그대로 쓴다 — 그러라고 분리해 둔 것이다.

---

## 9. 고장에 대한 대비

| 무엇이 고장나나 | 어떻게 되나 |
|---|---|
| HQ 재시작 | 부팅 때 RUNNING 인 채 끊긴 단계를 되살린다 (`_recover_interrupted`) |
| 노드 무응답 | 타임아웃까지 기다렸다가 그 단계만 FAILED. 사이클은 안 죽는다 |
| 산출물 소실 | 노드에 원본이 남아 있다 (`agora-ops/recover-artifacts.sh`) |
| 게이트가 판정을 못 함 | **통과로 본다.** 판정을 못 했다고 수업을 멈추지 않는다 |
| 검사 코드가 터짐 | 그 검사만 건너뛴다. 사이클은 계속 간다 |
| 스펙 감시 루프 예외 | 삼켜서 계속 돈다. 죽으면 게이트가 영영 안 열린다 |
| 실수로 초기화 | `ops/reset.sh` 가 `repo/.archive/` 에 백업을 남긴다 |

---

## 10. 검증

```bash
make test              # 상태기계 38건 + 역할카탈로그 89건 + E2E 흐름
./ops/acceptance.sh    # 전체 인수 111건
./ops/rehearsal.sh     # 실제 노드로 한 사이클 완주 (25~40분)
.venv/bin/python ops/site-check.py   # 완성된 사이트 19항목 채점
```

"작성했습니다" 는 완료가 아니다. 출력이 있어야 완료다.
