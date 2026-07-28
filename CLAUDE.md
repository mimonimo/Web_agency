# CLAUDE.md — 누적 기록

> BRIEF 작업규칙 6: Phase 종료 시 이번에 내린 결정과 남은 이슈를 여기에 누적 기록한다.
> 새 세션은 `BRIEF.md` 와 이 파일을 먼저 읽는다.

## 진행 상황

| Phase | 범위 | 인수 | 상태 |
|---|---|---|---|
| 노드 준비 | dgx-02~11 Hermes + Ollama | — | ✅ 2026-07-28 |
| **0** | 리포 골격 · CLAUDE.md · Makefile · compose 스켈레톤 | 구조 일치 | ✅ 2026-07-28 |
| 1 | caddy · dnsmasq · postgres · 모델·마이그레이션 | 1–4 | ⬜ |
| 2 | 노드 등록 · A2A · 어댑터 · 미러링 | 5–10 | ⬜ |
| 3a | 오케스트레이터 상태기계 · pipeline 로더 | 11–13, 16–18, 23 | ⬜ |
| 3b | AgentSpec 생명주기 · 커스터마이징 게이트 · reset 2종 | 14–15, 21–22 | ⬜ |
| 3c | 게이트 반려 · rewind · 티켓 · 파이프라인 4종 · 감사로그 | 19–20, 24–25 | ⬜ |
| 4 | 픽셀 오피스 + 주문 사이트 | 26–32 | ⬜ |
| 5 | 노드 부트스트랩 · 전체 인수 | 33–36 | ⬜ |

---

## 사전 작업 — 노드 준비 (2026-07-28)

BRIEF 를 받기 전 상태와 실제가 달라서 먼저 정리했다.

| 항목 | 착수 전 실제 |
|---|---|
| Ollama + `gpt-oss:120b` | 10대 전부 설치·기동 (정상) |
| Hermes 설치됨 | dgx-05, 06, 07, 08, 09 — **5대뿐** |
| Hermes 미설치 | dgx-02, 03, 04, 10, 11 |
| Hermes → Ollama 연결 | **0대**. 전부 `openrouter.ai` + `anthropic/claude-opus-4.6` |

Hermes 가 있던 5대조차 **외부 유료 API** 를 바라보고 있었다. BRIEF §1.2 의
"인터넷 없음 전제"와 정면으로 어긋나므로 전량 로컬 Ollama 로 돌렸다.

### 내린 결정

1. **PM 은 SSH 공개키로 노드를 관리한다.** `~/.ssh/id_ed25519` (comment `dgx-12-pm`) 를
   10대 `authorized_keys` 에 배포. 비밀번호(`dgx-0X`)는 **삭제하지 않았다** —
   키가 깨져도 교실에서 잠기지 않게.
2. **모델은 노드 로컬 Ollama.** 중앙 1대에 모아 서빙하지 않는다.
   `provider: ollama` / `base_url: http://127.0.0.1:11434/v1` / `model: gpt-oss:120b`.
   네트워크를 안 타므로 인터넷·L2 장애에 영향받지 않는다.
   Ollama 는 `127.0.0.1` 만 듣게 **그대로 뒀다** (무인증이라 외부 노출은 위험).
3. **설정은 `hermes config set` 으로만 건드린다.** `config.yaml` 직접 편집 금지.
   기존 설정은 노드별 `~/.hermes/config.yaml.pre-ollama.bak` 에 백업.
4. **역할 매핑은 노드 번호 순서** (PM 승인). `~/agora-ops/nodes.tsv` 가 단일 진실 공급원.
5. **`agents/<role>/AGENT.md` 는 만들지 않았다.** BRIEF §10 · §4.1 — 초안 생성은
   S2 기획 에이전트의 몫이고 그게 수업 내용 그 자체다.

### 검증한 것

10대 전부 로컬 Ollama 를 통한 **실제 추론 왕복 성공**. 프로비저닝 2회차 재실행으로
멱등성 확인 (10/10 PASS, 변화 없음).

PM 운영 도구는 `~/agora-ops/` — 이 리포와 별개다 (노드 운영용이지 HQ 가 아니므로).

---

## Phase 0 — 리포 골격 (2026-07-28)

### 내린 결정

1. **HQ 는 dgx-12 (PM PC) 위에 올린다.** BRIEF §1.2 는 "별도 VM(Ubuntu)" 을 말하지만
   가용 장비가 DGX 11대뿐이다 (PM 승인). 디스크 3.4T 여유, 80/8000 포트 비어 있음.
2. **런타임은 Docker Compose** — BRIEF §1.2 대로. 네이티브 대안도 검토했으나
   BRIEF 구성을 지키는 쪽을 택했다 (PM 승인).
3. **`pm` 에이전트는 dgx-12 가 겸임** → 등록 노드 총 **11개**.
   BRIEF 인수 #5("노드 11개 register")를 구조 변경 없이 만족한다 (PM 승인).
4. **`models.py` 는 Phase 0 에서 컬럼까지 확정했다.** 골격만 두는 것이 원칙이지만,
   BRIEF §6 의 컬럼명이 이후 전 세션의 계약이라 여기서 못 박는 편이 안전하다.
   마이그레이션 실행은 Phase 1.
5. **라우터는 501 을 던지되 시그니처는 진짜로 선언했다.** `/docs` 를 열면 전체 API
   표면이 바로 드러나고, 이후 세션은 빈칸만 채운다. 어느 Phase 에서 구현하는지를
   에러 메시지에 한국어로 적었다 (BRIEF §15-4).
6. **`orchestrator.py` 는 순수 함수 계약만 뒀다** (BRIEF §15-1).
   `next_step(cycle, steps, event) -> Transition`. Session 을 인자로 받지 않고
   import 하지도 않는다. DB 반영은 `routers/cycles.py` 의 몫.
7. **`pipeline.yaml` 4종은 스텁이 아니라 실물로 작성했다.** 파이프라인은 코드가 아니라
   데이터이고 (BRIEF §3.6) BRIEF 에 전문이 주어져 있으므로 미룰 이유가 없다.
8. **`make preload` 를 만들었다.** 교실에는 인터넷이 없다 (BRIEF 작업규칙 7).
   인터넷이 되는 지금 이미지 pull 과 core 빌드를 끝내 두기 위한 타깃이다.
9. **`dnsmasq` 는 compose 에 넣지 않고 Phase 1 로 미뤘다.** 호스트의
   `systemd-resolved` 가 이미 53 번을 잡고 있어 포트 처리 방식을 먼저 정해야 한다.
10. **`.env` 와 `provisioning/out/` 은 gitignore.** 토큰·비밀 커밋 금지 (BRIEF §15-6).
    `repo/runs/` 도 제외했다 — 재생성 가능하고 reset 으로 날아가는 것들이다.

### 남은 이슈

- **★ Docker 그룹 권한이 없다.** dgx-12 계정이 `docker` 그룹에 없어 컨테이너를 띄울 수 없다.
  **Phase 1 `make up` 의 선행 조건**이다:
  ```
  sudo usermod -aG docker $USER     # 후 재로그인
  ```
  Phase 0 는 골격만 만들므로 영향 없이 끝났다.

- **★ BRIEF 내부 모순 — defect 파이프라인의 시작 지점.**
  §3.6 본문은 "셋 다 **S1 영업에서 시작**하는 것은 동일하다" 라고 하는데,
  인수 #24 는 "pipeline.defect.yaml 로 Cycle 생성 → **S6(QA)부터 시작**하는지 확인"
  이라고 한다. 둘이 어긋난다.
  현재 `pipeline.defect.yaml` 은 본문을 따라 S1 을 접수 전용(`intake_only`)으로 두었다.
  **Phase 3c 착수 전 PM 확인 필요.**

- **A2A 표준 SDK vs 자체 JSON-RPC 미결정** (BRIEF §5.4).
  Phase 2 의 첫 작업으로 오프라인 설치 가능 여부를 확인한 뒤 정하고,
  **어느 쪽을 택했는지 여기에 반드시 기록한다.**

- **학생 명단이 없다.** `provisioning/students.yaml` 의 `name` 은 전부 비어 있다.
  역할·노드·IP 는 채워져 있으므로 이름만 넣고 `make provision` 을 다시 돌리면 된다.

- **`repo/` 의 git 초기화를 아직 안 했다.** bare git + 작업 트리 구성은 Phase 1.

- **계약 씨앗 4종이 아직 없다** (BRIEF §11 — `SRS.md`, `design-tokens.json`,
  `schema.sql`, `api-contract.yaml`). `provision.py` 가 만드는 것이라 Phase 2.
  **빈 파일 금지** — 학생이 백지에서 시작하면 하루가 무너진다.

- **노드에 A2A 어댑터가 없다.** 41241 포트는 아직 아무것도 안 듣는다. Phase 2.

- **Hermes 상주(데몬) 미설정.** 현재는 호출할 때만 뜨는 CLI 상태다.
  BRIEF §1.2 의 "24시간 켜둠" 은 A2A 어댑터가 생긴 뒤 systemd 유닛으로 잡는 게 맞다.

- **노드 `~/.hermes/.env` 에 OpenRouter 등 외부 키가 남아 있다.** 로컬 모델만 쓰므로
  당장 무해하지만, 학생에게 노드를 넘기기 전 정리할지 PM 판단 필요.
