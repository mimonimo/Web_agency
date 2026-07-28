# AGORA Web HQ 구축 지시서 — Claude Code 작업 브리프

> 이 문서를 `agora/BRIEF.md` 로 저장한 뒤, §0의 지시문으로 CC 세션을 시작한다.

---

## 0. CC에게 줄 첫 지시문 (그대로 복사)

```
너는 고등학교 AI 에이전트 PBL 수업의 중앙 서버(HQ)를 구축한다.
BRIEF.md 를 처음부터 끝까지 읽어라.

작업 규칙:
1. Phase 0 → 5 순서로 진행한다. 한 Phase가 끝나면 멈추고 보고한 뒤 승인을 기다린다.
2. 각 Phase 시작 전 plan 모드로 계획을 제시하고 승인을 받는다.
3. 추측하지 마라. BRIEF.md 에 없는 결정이 필요하면 물어라.
4. 모든 스크립트는 멱등해야 한다. 두 번 돌려도 같은 결과여야 한다.
5. Phase 완료 시 해당 인수 항목을 직접 실행하고 그 출력을 보여줘라.
   "작성했습니다"는 완료가 아니다. "돌려봤고 이렇게 나왔습니다"가 완료다.
6. Phase 종료 시 이번에 내린 결정과 남은 이슈를 CLAUDE.md 에 누적 기록한다.
7. 인터넷이 막힌 교실에서 돌아간다. CDN·외부 API·빌드 스텝에 의존하지 마라.

⚠️ 시간 제약: Phase 0~3 은 오늘 밤 안에 반드시 끝나야 한다.
   Phase 4~5 는 없어도 수업이 성립하게 설계해라.

지금은 Phase 0만 한다. 시작 전에 계획을 보여줘.
```

---

## 1. 배경 — 무엇을 위한 서버인가

소프트웨어마이스터고 학생 **11명**이 각자 AI 에이전트를 하나씩 맡아 웹에이전시
**AGORA Web** 을 운영한다. 만드는 것은 **고객사 웹사이트**이고, 납품 후 **유지보수**까지 한다.

### 1.1 이 수업의 핵심 메커니즘 — 요구사항이 흐르는 길

**모든 개발·유지보수 요구는 예외 없이 아래 경로를 탄다.**

```
요구사항 발생 (주문 사이트 / 고객 문의)
   ↓
① 영업        접수·범위 판단·SOW 작성
   ↓ (A2A)
② 기획        요구사항을 해석하고,
              ★ 각 역할별 AGENT.md 초안을 자동 생성해 배포
   ↓
[ 커스터마이징 게이트 ]  ← 파이프라인이 여기서 자동으로 멈춘다
              학생들이 자기 전문 지식을 더해 AGENT.md 를 고쳐 커밋
   ↓ (전원 커밋 완료 감지 → 자동 재개)
③~⑧ 설계·구현 (A2A 로 서로 통신)
   ↓
⑨⑩⑪ QA · 보안 · 고객검수 3중 게이트 (반려 시 되감기)
   ↓
④ 배포 → 운영 → 새 요구사항 발생 → 처음으로
```

> **★ HQ가 존재하는 이유는 이 사이클을 자동으로 돌리되,
> 사람이 원하는 지점에서 멈추고 · 고치고 · 재개하고 · 처음부터 다시 할 수 있게 하는 것이다.**
>
> 학생이 배우는 것은 코드가 아니라 **"AGENT.md 한 줄이 결과를 어떻게 바꾸는가"** 이다.
> 그러려면 **같은 사이클을 여러 번, 조건만 바꿔 돌릴 수 있어야 한다.** 이게 최우선 요구사항이다.

### 1.2 물리 구성

| 역할 | 대수 | 내용 |
|---|---|---|
| **HQ** | 1 | 이번 구축 대상. VM(Ubuntu) 위 Docker Compose |
| **학생 노드** | 11 | Hermes Agent + **A2A 어댑터**. 24시간 켜둠 |
| **DGX Spark** | 11 | Ollama 모델 서빙 전용 |

전부 **같은 L2**. **인터넷 없음**을 전제로 만든다.

### 1.3 11개 역할 (고정)

```
01 pm         02 planner    03 sales      04 sysadmin
05 designer   06 frontend   07 backend    08 dba
09 security   10 qa         11 customer
```

이 문자열이 노드 ID이자 A2A 에이전트 이름이자 `agents/<role>/AGENT.md` 경로다.
**어디서든 같은 문자열을 쓴다. 한글 표기는 UI에서만 매핑한다.**

---

## 2. 저장소 골격

```
agora/
  BRIEF.md              ← 이 문서
  CLAUDE.md             ← CC가 누적 기록
  Makefile              ← make up / down / reset / logs / provision
  docker-compose.yml
  .env.example
  core/                 ← FastAPI: agora-core (오케스트레이터 + API)
    app/
      main.py
      models.py         ← SQLAlchemy
      db.py
      orchestrator.py   ← ★ 상태기계. 이 파일이 심장이다
      a2a_client.py     ← A2A 발신
      a2a_server.py     ← HQ 자신도 A2A 에이전트로 노출(선택)
      routers/
        cycles.py  nodes.py  specs.py  tickets.py
        orders.py  messages.py  artifacts.py  dashboard.py
      pipeline.yaml     ← ★ 파이프라인 정의(데이터). 코드에 하드코딩 금지
  web/                  ← 정적. 빌드 스텝 없음
    index.html          ← 픽셀 오피스 (메인 화면)
    order.html          ← 주문 접수 사이트
    board.html          ← 티켓 보드 / 타임라인
    assets/             ← CSS·JS·스프라이트(직접 그린 SVG/CSS)
  node/                 ← 학생 노드에 배포할 것
    a2a-adapter/        ← Hermes 를 A2A 에이전트로 감싸는 어댑터
    bootstrap-node.sh
    verify-node.sh
  repo/                 ← 프로젝트 산출물 저장소(bare git + 작업 트리)
  provisioning/
    students.yaml  provision.py  seed.py
  ops/
    acceptance.sh  reset.sh  rewind.sh
```

---

## 3. ★ 핵심 — 사이클 상태기계

**이 절이 이 프로젝트의 전부다. 여기를 잘못 만들면 나머지가 무의미하다.**

### 3.1 개념 세 층

| 개념 | 뜻 | 비유 |
|---|---|---|
| **Order** | 요구사항 1건 (신규/변경/결함/보안) | 손님이 낸 주문서 |
| **Cycle** | Order 를 처리하는 실행 1회 | 주방이 한 번 요리하는 것 |
| **Step** | Cycle 안의 단계 1개 | 손질 → 볶기 → 담기 |

**같은 Order 로 Cycle 을 여러 번 돌릴 수 있다.** 이게 수업의 핵심 장치다 —
학생이 AGENT.md 를 고치고 **똑같은 주문을 다시 돌려** 결과가 어떻게 달라지는지 본다.

### 3.2 Cycle 상태

```
READY ──start──> RUNNING ──pause──> PAUSED ──resume──> RUNNING
                    │                  │
                    │                  └──rewind(step)──> RUNNING
                    ├──gate 도달──> BLOCKED (사람 대기)
                    ├──step 실패──> FAILED
                    └──끝──> DONE

어느 상태에서든:  reset(mode) ──> READY
```

### 3.3 Step 상태

```
PENDING → RUNNING → DONE
                  ↘ REJECTED   (게이트 반려 → 지정된 step 으로 되감기)
                  ↘ FAILED     (재시도 가능)
                  ↘ SKIPPED    (강사가 건너뜀)
WAITING_HUMAN                  (커스터마이징 게이트 등)
```

### 3.4 일시정지 규약 — **반드시 지킬 것**

| 명령 | 동작 |
|---|---|
| `pause` | **현재 step 을 끝까지 마친 뒤** 정지 (graceful). 중간에 자르지 않는다 |
| `abort` | 현재 step 을 즉시 취소하고 정지. 그 step 은 FAILED |
| `resume` | 다음 PENDING step 부터 재개 |
| `step` | 한 단계만 실행하고 다시 PAUSED (수업 중 시연용) |
| `rewind(step_id)` | 그 step 이후의 모든 산출물을 무효화하고 거기서 재개 |
| `reset(mode)` | 사이클을 처음부터. **mode 2종** (아래) |

**`reset` 의 두 가지 모드 — 매우 중요**

```
reset(keep_specs=true)   ← 기본값.
    산출물·티켓·로그는 지우고, agents/*/AGENT.md 는 학생이 고친 그대로 유지.
    → "지시문만 바꿔서 같은 주문을 다시 돌린다" = 수업의 핵심 실험

reset(keep_specs=false)
    AGENT.md 도 기획이 만든 초안으로 되돌린다. 완전 초기화.
    → 다음 수업/다음 반을 위한 리셋
```

> **⚠️ 기본값을 `keep_specs=true` 로 해라.** 학생이 30분 걸려 고친 AGENT.md 를
> 리셋 버튼 한 번에 날리면 수업이 망한다. `false` 는 확인 대화를 한 번 더 받는다.

### 3.5 멱등성 규약

모든 step 산출물은 아래 경로에만 쓴다. 재실행은 **덮어쓴다.**

```
repo/runs/{cycle_id}/{step_id}/output/...
repo/runs/{cycle_id}/{step_id}/report.md     ← 에이전트 완료 보고
repo/project-001/...                          ← 확정 산출물(step DONE 시 승격)
```

**step 을 두 번 돌려도 결과가 같아야 한다.** 이게 rewind/reset 의 전제다.

### 3.6 `pipeline.yaml` — 파이프라인은 데이터다

**코드에 단계를 하드코딩하지 마라.** 강사가 수업 중에 단계를 자를 수 있어야 한다.

```yaml
# core/app/pipeline.yaml
name: web_delivery
steps:
  - id: S1
    name: 접수·범위 합의
    role: sales
    task: intake
    inputs:  [order]
    outputs: [SOW.md, QUOTE.md]
    timeout_sec: 600

  - id: S2
    name: 요구사항 해석 + AGENT.md 초안 생성
    role: planner
    task: draft_specs
    inputs:  [order, SOW.md]
    outputs: [SRS.md, SCREENS.md, "agents/*/AGENT.md"]
    emits_specs: true          # ★ 이 단계가 11개 AGENT.md 초안을 만든다
    timeout_sec: 900

  - id: S3
    name: 커스터마이징 게이트
    type: human_gate           # ★ 여기서 자동으로 멈춘다
    wait_for: all_specs_customized
    allow_override: true       # 강사가 강제 통과 가능
    hint: "학생들이 AGENT.md 를 고쳐 커밋하면 자동 재개된다"

  - id: S4
    name: 설계
    parallel: [designer, dba, backend, sysadmin]
    task: design
    outputs: [design-tokens.json, schema.sql, api-contract.yaml, ops/run.sh]
    timeout_sec: 1200

  - id: S5
    name: 구현
    parallel: [frontend, backend, dba]
    task: implement
    timeout_sec: 1800

  - id: S6
    name: QA 게이트
    role: qa
    type: gate
    on_reject: { rewind_to: S5 }

  - id: S7
    name: 보안 게이트
    role: security
    type: gate
    on_reject: { rewind_to: S5, priority: critical }

  - id: S8
    name: 고객 검수(UAT)
    role: customer
    type: gate
    on_reject: { rewind_to: S2 }    # ★ 기획으로 돌아간다

  - id: S9
    name: 배포
    role: sysadmin
    task: deploy

  - id: S10
    name: 운영 관찰
    role: customer
    task: generate_feedback         # 문의·클레임을 만들어 새 Order 발행
    creates_orders: true
```

**요구사항 종류별로 다른 파이프라인을 쓴다.** `pipeline.change.yaml`, `pipeline.defect.yaml`,
`pipeline.security.yaml` 를 함께 만든다. 셋 다 **S1 영업에서 시작**하는 것은 동일하다.

| 종류 | 경로 |
|---|---|
| `new` 신규 | S1 → S2 → S3 → S4~S10 (전체) |
| `change` 변경 요청 | S1 영업(범위·비용) → S2 기획 → S5 구현 → S6~S8 |
| `defect` 결함 | S1(접수만) → **S6 QA 재현** → S5 수정 → S6 확인 |
| `security` 보안 | S1(접수만) → **S7 보안 최우선** → S5 수정 → S7 재점검 |

> **세 경로가 다르다는 것 자체가 수업 내용이다.** 픽셀 오피스에서 경로가 다르게 그려져야 한다.

---

## 4. ★ AGENT.md 생명주기

이 수업의 교육 목표가 여기 걸려 있다. **정확히 구현해라.**

```
[없음] ──S2 기획이 생성──> draft ──학생이 커밋──> customized ──사이클 시작──> active
                             ↑                                              │
                             └──────────── reset(keep_specs=false) ─────────┘
```

### 4.1 기획 에이전트가 만드는 것

S2 에서 planner 는 **11개 파일**을 생성한다.

```
repo/project-001/agents/pm/AGENT.md
                       /planner/AGENT.md
                       /sales/AGENT.md
                       ... (11개)
```

각 파일 맨 위에 **HQ가 관리하는 front-matter** 를 붙인다.

```markdown
---
role: backend
cycle: 3
status: draft          # draft | customized
author: planner-agent
generated_at: 2026-07-29T10:14:00+09:00
customized_at: null
---

# 나는 AGORA Web 의 백엔드 조수다
(이하 기획이 생성한 초안 — 공통 헤더 + 역할 본문)
```

**기획에게 주는 지시 템플릿** (HQ가 `templates/planner_draft_prompt.md` 로 보관)

```
아래 요구사항(SRS.md)을 읽고, 11개 역할 각각에 대해 AGENT.md 초안을 작성한다.
각 파일은 다음 6칸을 반드시 포함한다:
  나의 역할 / 내 파일 / 출력 형식 / 금지 / 애매할 때 / 완료 보고
이번 요구사항에서 그 역할이 특별히 조심해야 할 것을 '금지' 칸에 최소 1줄 넣는다.
초안은 완벽할 필요 없다. 학생이 자기 전문 지식으로 보강할 것이다.
파일은 agents/<role>/AGENT.md 로 저장한다.
```

### 4.2 커스터마이징 게이트 (S3)

- HQ가 `repo/` 를 **3초 주기로 폴링**(또는 git post-receive 훅)하여 파일 변경을 감지
- 파일이 바뀌고 내용이 초안과 다르면 → `status: customized`, `customized_at` 기록
- **11개가 전부 customized 되면 자동으로 RUNNING 재개**
- 대시보드에 `7 / 11 완료` 실시간 표시
- 강사용 **강제 통과 버튼** 제공 (`allow_override: true`)

> **diff 를 보관해라.** `specs/history/{role}/{cycle}.diff` —
> 학생이 무엇을 추가했는지가 **오늘의 평가 데이터**다. 회고 시간에 이걸 띄운다.

### 4.3 AGENT.md 를 노드에 전달하는 방법

에이전트는 **세션 시작 시 자기 AGENT.md 를 읽는다.** HQ는 A2A 요청에 다음을 실어 보낸다.

```json
{
  "role": "backend",
  "cycle_id": 3,
  "step_id": "S5",
  "spec_url": "http://hq.agora.lan/api/specs/backend/raw",
  "context_files": ["SRS.md", "api-contract.yaml", "schema.sql"],
  "task": "implement",
  "output_dir": "runs/3/S5/output/"
}
```

노드의 A2A 어댑터가 `spec_url` 을 받아 **AGENT.md 를 먼저 읽힌 뒤** 작업 지시를 전달한다.

---

## 5. A2A 규약

### 5.1 구조

```
HQ(오케스트레이터) ──A2A──> 학생 노드 11개
        ↑                        │
        └── 모든 메시지 미러링 ──┘   (픽셀 오피스가 이걸 그린다)

학생 노드 ──A2A──> 학생 노드   (직접 통신 허용, 단 HQ에 반드시 미러링)
```

### 5.2 에이전트 카드

각 노드는 A2A 에이전트 카드를 노출한다.

```
http://node-backend.agora.lan:41241/.well-known/agent-card.json
```

```json
{
  "name": "agora-backend",
  "description": "AGORA Web 백엔드 담당",
  "url": "http://node-backend.agora.lan:41241/",
  "version": "1.0",
  "capabilities": { "streaming": false, "pushNotifications": false },
  "defaultInputModes": ["text"],
  "defaultOutputModes": ["text"],
  "skills": [
    { "id": "design",    "name": "API 계약 설계", "tags": ["design"] },
    { "id": "implement", "name": "서버 구현",     "tags": ["build"] },
    { "id": "fix",       "name": "결함 수정",     "tags": ["maintain"] }
  ]
}
```

### 5.3 흐름

```
1. HQ → 노드   message/send      { task, spec_url, context_files, output_dir }
2. 노드 → HQ   { taskId, state: "working" }
3. HQ          tasks/get 폴링 (5초)
4. 노드 → HQ   { state: "completed", artifacts: [...] }
5. HQ          artifacts 를 repo/ 에 기록, step DONE 처리
```

**모든 메시지는 HQ `POST /api/messages` 에 미러링한다.** 노드 간 직접 통신도 마찬가지다.
미러링하지 않은 메시지는 픽셀 오피스에 안 그려지고, **감사 로그에도 안 남는다.**

### 5.4 ⚠️ CC에게 주는 현실적 지시

> **A2A 스펙과 SDK 버전은 계속 바뀐다. 그리고 이 교실은 인터넷이 없다.**
>
> 1. 먼저 오프라인에서 A2A Python SDK 가 설치 가능한지 확인해라.
> 2. **가능하면** 표준 SDK 를 쓴다.
> 3. **불가능하거나 버전이 안 맞으면** — 위 §5.2·5.3 모양을 그대로 따르는
>    **최소 JSON-RPC 구현을 직접 만든다.** 필드명과 엔드포인트 이름을 A2A 와 동일하게 맞춰
>    나중에 갈아끼울 수 있게 한다.
> 4. 어느 쪽을 택했는지 `CLAUDE.md` 에 반드시 기록해라.
>
> **동작하는 것이 표준을 지키는 것보다 우선이다.** 내일 아침에 돌아야 한다.

### 5.5 노드 어댑터 (`node/a2a-adapter/`)

HQ가 만들어 배포하는 얇은 래퍼. 하는 일은 네 가지뿐이다.

1. 에이전트 카드 노출
2. `message/send` 수신 → `spec_url` 로 AGENT.md 받아오기
3. Hermes CLI 를 **작업 디렉터리를 제한한 상태로** 실행
4. 산출물 수집 → `tasks/get` 응답 + HQ 미러링

```bash
# 노드에서
./bootstrap-node.sh --role backend --hq http://hq.agora.lan --dgx dgx-07
./verify-node.sh      # DGX 연결 / Hermes 상주 / HQ 등록 / A2A 카드 응답 각각 판정
```

---

## 6. 데이터 모델 (Postgres)

```
Node        id, role, display_name, a2a_url, status(up/down), last_heartbeat, dgx_host
Order       id, source(order_site/inquiry/manual), kind(new/change/defect/security),
            title, body, requester, status, created_at
Cycle       id, order_id, pipeline, status, current_step, mode(auto/manual),
            attempt_no, started_at, ended_at
Step        id, cycle_id, step_key, name, role, status, attempt,
            input_ref, output_ref, error, started_at, ended_at
AgentSpec   id, cycle_id, role, status(draft/customized), path, hash,
            generated_at, customized_at, diff_ref
Message     id, cycle_id, step_id, from_role, to_role, kind(request/response/reject/mirror),
            summary, payload_ref, ts
Ticket      id, cycle_id, from_role, to_role, title, dod, status, parent_id, reason, due
Artifact    id, cycle_id, step_id, role, path, size, ts
AuditLog    id, actor, action, target, payload, ts
```

**모든 쓰기 요청은 AuditLog 에 남는다.** 예외 없다.

---

## 7. HQ API

```
# 사이클 제어  ★ 핵심
POST   /api/cycles                    {order_id, pipeline}  → 생성(READY)
POST   /api/cycles/{id}/start
POST   /api/cycles/{id}/pause         graceful
POST   /api/cycles/{id}/abort
POST   /api/cycles/{id}/resume
POST   /api/cycles/{id}/step          한 단계만
POST   /api/cycles/{id}/rewind        {step_key}
POST   /api/cycles/{id}/reset         {keep_specs: true|false}
GET    /api/cycles/{id}               상태 + step 타임라인
GET    /api/cycles/{id}/timeline

# 스펙(AGENT.md)
GET    /api/specs?cycle=3             11개 상태 목록
GET    /api/specs/{role}/raw          ← 노드가 읽어가는 주소
POST   /api/specs/{role}/customized   수동 표시(폴링 실패 대비)
GET    /api/specs/{role}/diff?cycle=3

# 노드 · 통신
POST   /api/nodes/register            {role, a2a_url, card}
POST   /api/nodes/{role}/heartbeat
GET    /api/nodes
POST   /api/messages                  A2A 미러링 수신
GET    /api/messages?cycle=3&since=

# 업무
POST   /api/orders                    주문 사이트 제출
GET    /api/orders
POST   /api/tickets  /  POST /api/tickets/{id}/transition
POST   /api/gates/{step}/reject       {reason, rewind_to}

# 대시보드
GET    /api/dashboard                 픽셀 오피스가 5초마다 부르는 단일 엔드포인트
```

`GET /api/dashboard` 는 **한 번에 다 준다** (오피스가 여러 번 호출하지 않게).

```json
{
  "cycle": {"id":3,"status":"BLOCKED","current_step":"S3","pipeline":"web_delivery"},
  "steps": [...],
  "nodes": [{"role":"backend","status":"up","busy":true,"current_step":"S5"}],
  "specs": {"customized": 7, "total": 11, "pending": ["qa","security","dba","customer"]},
  "messages": [{"from":"planner","to":"backend","kind":"request","ts":"..."}],
  "tickets": {"todo":4,"doing":2,"done":9,"rejected":1},
  "orders": [...]
}
```

---

## 8. 픽셀 오피스 (`web/index.html`)

**빌드 없음. 프레임워크 없음. CDN 없음. 도트는 CSS/SVG 로 직접 그린다.**
5초마다 `/api/dashboard` 폴링.

### 8.1 화면 구성

```
┌─────────────────────────────────────────────────────────┐
│ [⏸ 일시정지] [▶ 재개] [⏭ 한 단계] [⏮ 되감기] [⟲ 처음부터] │ ← 컨트롤 바
│ 사이클 #3 · web_delivery · BLOCKED · S3 커스터마이징 게이트 │
├─────────────────────────────────────────────────────────┤
│  [접수 카운터]                          [서버실]          │
│                                                          │
│   🧑pm    🧑planner  🧑sales   🧑sysadmin                  │
│   🧑design 🧑front   🧑back    🧑dba                       │
│                                                          │
│   [QA실]   [보안실]   [검수실]        🧑customer (로비)   │
├─────────────────────────────────────────────────────────┤
│ S1 ✅ ─ S2 ✅ ─ S3 ⏸ ─ S4 ○ ─ S5 ○ ─ S6 ○ ─ S7 ○ ─ S8 ○ │ ← 타임라인
└─────────────────────────────────────────────────────────┘
```

### 8.2 반드시 보여야 하는 것

| 요소 | 규칙 |
|---|---|
| **책상 11개** | 노드 up/down, 현재 step 담당자는 **테두리 강조** |
| **A2A 메시지** | 책상 사이를 **봉투가 이동하는 애니메이션**. 반려는 빨간 봉투 |
| **회의실 3개** | QA·보안·검수 게이트 진행 중이면 불이 켜진다 |
| **로비의 customer** | 문의 발생 시 벨을 누른다(아이콘 깜빡) |
| **서버실** | 배포 상태·사이트 up/down. 장애 시 경광등 |
| **타임라인** | step 상태를 색으로. **되감기가 일어나면 화살표가 역방향으로 그려진다** ★ |
| **커스터마이징 게이트** | 각 책상에 `AGENT.md 대기` 배지 → 커밋되면 ✅ 로 변경, `7/11` 카운터 |

> **★ 되감기 화살표가 이 화면의 하이라이트다.**
> QA가 반려하면 S6 → S5 로 화살표가 **거꾸로** 그려지고 그 구간이 빨갛게 물든다.
> 학생들이 "야 또 돌아왔어" 하고 소리치게 만드는 게 목적이다.

### 8.3 컨트롤 바 동작

| 버튼 | API | 확인 대화 |
|---|---|---|
| ⏸ 일시정지 | `pause` | 없음 |
| ▶ 재개 | `resume` | 없음 |
| ⏭ 한 단계 | `step` | 없음 |
| ⏮ 되감기 | `rewind` (step 선택) | **있음** |
| ⟲ 처음부터 | `reset` | **있음 + keep_specs 선택 라디오** |

`reset` 대화 상자 문구를 정확히 이렇게 한다.

```
사이클을 처음부터 다시 시작합니다.

( • ) AGENT.md 는 그대로 두기        ← 기본 선택
      학생들이 고친 지시문을 유지한 채 같은 주문을 다시 돌립니다.

(   ) AGENT.md 도 초안으로 되돌리기
      학생들의 수정 내용이 모두 사라집니다.
```

### 8.4 학생별 개인 화면은 만들지 않는다

**공용 관제 화면 하나만** 만든다. 교실 프로젝터에 상시 띄운다.
개인 가동률 같은 지표는 **띄우지 않는다** — "3번 책상이 논다"가 아니라
"B사가 설계 단계에서 멈춰 있다"로 보여야 화살이 사람이 아니라 병목을 가리킨다.

---

## 9. 주문 접수 사이트 (`web/order.html`)

정적 HTML + `POST /api/orders`.

| 항목 | 필수 |
|---|---|
| 회사/서비스 이름, 업종 | ✓ |
| 목적 (한 문장) | ✓ |
| 필요 기능 (체크박스: 로그인·게시판·상품목록·장바구니·결제(모의)·문의폼·관리자·검색) | ✓ |
| 납기 희망일 | ✓ |
| 참고 사이트 / 톤&매너 | |
| 예산(가상 크레딧) | |
| 담당자 이름·연락처 | ✓ |

제출 시 HQ 동작:

```
Order 생성(kind=new)
  → Cycle 생성(pipeline=web_delivery, status=READY)
  → mode=auto 이면 즉시 start
  → S1 sales 에게 A2A 발신
  → 픽셀 오피스 접수 카운터에 봉투 도착 애니메이션
```

---

## 10. 프로비저닝

`provisioning/students.yaml`

```yaml
project: project-001
students:
  - no: 1   name: "홍길동"   role: pm         node: node-pm       dgx: dgx-01
  - no: 2   name: "김철수"   role: planner    node: node-planner  dgx: dgx-02
  # ... 11명
```

`provision.py` (전부 멱등)

1. Node 11개 등록 + 토큰 발급
2. `repo/project-001/` 초기화 — **계약 씨앗 4종을 70% 채운 상태로 커밋** (§11)
3. `provisioning/out/node-{role}.env` 생성 — 학생 배포용
4. `provisioning/out/명단.md` — 강사용 요약표

`seed.py`

- 씨앗 주문 1건 등록 (밀밭제과, kind=new, status=READY 로 **자동 시작하지 않음**)
- 샘플 티켓 2건
- **AGENT.md 초안 11개는 미리 넣지 않는다.** S2 에서 기획 에이전트가 만드는 게 수업이다

---

## 11. 계약 씨앗 4종 — **빈 파일 금지**

`repo/project-001/` 에 아래를 **미리 채워** 커밋한다. 학생이 백지에서 시작하면 하루가 무너진다.

| 파일 | 채워 둘 정도 |
|---|---|
| `SRS.md` | 로그인 항목은 **수용 기준까지 완성**, 게시판·문의폼은 제목만 |
| `design-tokens.json` | **8색 확정** + 폰트 6단계 + 4px 간격 스케일 |
| `schema.sql` | `users` 테이블 완성 (PK·UNIQUE·created_at 포함) |
| `api-contract.yaml` | `POST /api/login` 하나만 요청·응답 예시까지 |

응답 규격은 전 API 공통으로 못 박는다.

```
성공  { "ok": true,  "data": {...} }
실패  { "ok": false, "error": "메시지" }
상태코드  200 / 400 / 401 / 403 / 404
```

---

## 12. ★ 인수 테스트 (`ops/acceptance.sh`)

**이게 통과해야 Phase 가 끝난 것이다.** 출력 없는 완료 보고는 반려한다.

```
[Phase 1] 기반
 1. make up 후 모든 컨테이너 healthy
 2. dig hq.agora.lan @hq → 정상 해석
 3. curl -I http://hq.agora.lan → 200
 4. Postgres 마이그레이션 2회 실행 → 두 번째에 에러 없음

[Phase 2] 노드 · A2A
 5. 노드 11개 register → GET /api/nodes 에 11개
 6. 각 노드의 에이전트 카드를 HQ가 조회 성공
 7. heartbeat 중단 90초 후 status=down 자동 전환
 8. HQ → 노드 message/send → tasks/get 폴링 → completed 수신 (1건 왕복)
 9. 노드↔노드 직접 A2A 메시지가 /api/messages 에 미러링됨
10. 잘못된 토큰 → 401

[Phase 3] 오케스트레이터  ★ 가장 중요
11. Order 생성 → Cycle 자동 시작 → S1 이 RUNNING 이 된다
12. S2 완료 시 agents/*/AGENT.md 11개가 생성되고 전부 status=draft
13. S3 도달 시 Cycle 이 자동으로 BLOCKED 가 된다
14. AGENT.md 1개 수정·커밋 → specs.customized 가 1 증가
15. 11개 전부 customized → Cycle 이 자동으로 RUNNING 재개
16. pause 호출 → 현재 step 을 끝까지 마친 뒤 PAUSED (중간 절단 아님을 로그로 증명)
17. resume → 다음 step 부터 재개
18. step → 한 단계만 실행하고 PAUSED 복귀
19. 게이트 reject → rewind_to 로 지정된 step 으로 되감기 + 재작업 티켓 자동 생성
20. rewind(S5) → S5 이후 산출물이 무효화되고 S5 부터 재개
21. reset(keep_specs=true)  → 산출물은 초기화, AGENT.md 는 customized 유지 ★
22. reset(keep_specs=false) → AGENT.md 도 draft 로 복귀
23. 같은 step 을 2회 실행 → 산출물이 동일 (멱등)
24. pipeline.defect.yaml 로 Cycle 생성 → S6(QA)부터 시작하는지 확인
25. 모든 쓰기 요청이 AuditLog 에 남음

[Phase 4] 픽셀 오피스
26. 대시보드가 사이클 상태를 5초 내 반영
27. 노드 1대 kill → 해당 책상이 down 으로 전환
28. A2A 메시지 발생 → 봉투 애니메이션이 그려짐
29. 게이트 반려 발생 → 타임라인에 역방향 화살표
30. 커스터마이징 게이트에서 7/11 카운터가 실시간 갱신
31. ⟲ 처음부터 → keep_specs 선택 대화가 뜨고, 기본값이 '유지'
32. 네트워크 차단 상태에서도 브라우저에서 그대로 동작 (빌드·CDN 없음)

[Phase 5] 전체
33. bootstrap-node.sh 2회 실행 → 멱등
34. verify-node.sh 가 DGX·Hermes·HQ등록·A2A카드를 각각 판정
35. ops/reset.sh 후 make up + provision → 처음 상태로 완전 복구
36. HQ 재부팅 후 전 서비스 자동 기동
```

---

## 13. Phase 계획

| 세션 | Phase | 범위 | 인수 | 필수 |
|---|---|---|---|---|
| 1 | **0** | 리포 골격 · CLAUDE.md · Makefile · compose 스켈레톤 | 구조 일치 | ★ |
| 2 | **1** | caddy · dnsmasq · postgres · 모델·마이그레이션 | 1–4 | ★ |
| 3 | **2** | 노드 등록 · A2A 클라이언트/서버 · 어댑터 · 미러링 | 5–10 | ★ |
| 4 | **3a** | 오케스트레이터 상태기계 · pipeline.yaml 로더 · step 실행 | 11–13, 16–18, 23 | ★★ |
| 5 | **3b** | AgentSpec 생명주기 · 커스터마이징 게이트 · reset 2종 | 14–15, 21–22 | ★★ |
| 6 | **3c** | 게이트 반려 · rewind · 티켓 · 파이프라인 4종 · 감사로그 | 19–20, 24–25 | ★ |
| 7 | **4** | 픽셀 오피스 + 주문 사이트 | 26–32 | ☆ |
| 8 | **5** | 노드 부트스트랩 · 전체 인수 | 33–36 | ☆ |

**세션 시작 시 붙일 문장**

```
BRIEF.md 와 CLAUDE.md 를 읽어라.
Phase 3a 까지 완료된 상태다. 이번 세션은 Phase 3b 만 한다.
plan 모드로 계획을 보여주고, 승인 후 구현해라.
완료 시 인수 14–15, 21–22 를 실제로 실행해 출력을 보여줘라.
끝나면 결정 사항과 남은 이슈를 CLAUDE.md 에 추가해라.
```

> **세션 4(Phase 3a)에서 상태기계를 완전히 확정한다.** 이후 세션은 그 위에 얹는 구조라
> 흔들림이 없다. 반대로 여기가 흔들리면 전부 다시 만들어야 한다.

---

## 14. 시간이 부족할 때 자르는 순서

**위에서부터 버린다.**

1. Phase 5 노드 부트스트랩 자동화 → 손으로 11대 세팅
2. 픽셀 오피스의 봉투 애니메이션 → 텍스트 로그 스트림으로 대체
3. 주문 사이트 → 강사가 `POST /api/orders` 로 직접 넣음
4. 파이프라인 4종 → `web_delivery` 하나만. 유지보수는 강사가 수동 rewind
5. A2A 표준 준수 → 자체 JSON-RPC 로 대체

**절대 자르면 안 되는 것**

- **pause / resume / reset(keep_specs=true)** — 이게 없으면 수업이 성립하지 않는다
- **S2 의 AGENT.md 초안 생성 + S3 커스터마이징 게이트** — 이게 수업의 내용 그 자체다
- **게이트 반려 → rewind** — 세 반려를 가르치는 장치

---

## 15. CC가 지킬 코드 규칙

1. **오케스트레이터는 순수 함수로.** `next_step(cycle, steps, event) → transition`
   상태 전이 로직을 DB 접근과 섞지 마라. 테스트가 안 된다.
2. **step 실행은 전부 async 태스크.** 하나가 막혀도 pause 요청은 즉시 받아야 한다.
3. **모든 외부 호출에 타임아웃.** 로컬 모델은 느리다. 기본 900초, `pipeline.yaml` 에서 재정의.
4. **에러 메시지는 한국어로.** 학생과 강사가 읽는다.
5. **`repo/` 조작은 반드시 git 커밋과 함께.** 커밋 메시지 형식:
   `[cycle-3][S5][backend] 구현 산출물` — 회고 시간에 이 로그를 띄운다.
6. **비밀·토큰을 repo 에 커밋하지 마라.** `.env` 와 `provisioning/out/` 는 gitignore.
