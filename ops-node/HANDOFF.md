# AGORA Web — 인수인계

2026-07-28 작업 종료 시점 기준. 새 세션은 이 문서와 `~/agora/CLAUDE.md` 를 먼저 읽어라.

---

## 1. 지금 무엇이 돌고 있나

| | |
|---|---|
| **HQ** | dgx-12 `~/agora`, 네이티브(venv+SQLite), 포트 8000 |
| **실행 모드** | `EXECUTOR=a2a` — 실제 학생 노드의 Hermes 가 일한다 |
| **노드** | dgx-02~11 + dgx-12(pm 겸임) = **11개**, A2A 어댑터 상주 |
| **모델** | 각 노드 로컬 Ollama `gpt-oss:120b` (127.0.0.1:11434) |
| **재부팅** | HQ·pm어댑터·노드어댑터 전부 `@reboot` 등록됨 |

```bash
cd ~/agora
./ops/dev.sh status     # 상태 + 산출물·사이트 개수
./ops/dev.sh sites      # 완성된 사이트 주소
./ops/dev.sh restart    # 재기동
make test               # 상태기계 + E2E (sim 모드에서)
./ops/acceptance.sh     # 전체 인수
```

## 1-1. ★ 완성된 웹사이트 — 바로 보기

에이전트들이 만든 「밀밭제과」 사이트 두 벌이 보존돼 있다.

```
/preview/showcase/v2-after/index.html    ← 최종본 (품질 19/19, 100점)
/preview/showcase/v1-before/index.html   ← 개선 전 (10/19, 53점) — 비교용
```

픽셀 오피스 상단 바의 `🌐 완성된 사이트 열기` 버튼으로도 열린다.
주소만 뽑으려면 `./ops/dev.sh sites`.

| | v1 (전) | v2 (후) |
|---|---|---|
| viewport | 없음 | 있음 |
| 시맨틱 태그 | 0/5 | 5/5 |
| 레이아웃 | `<br>` | flex/grid |
| CSS 변수 | 0개 | 24회 |
| 색 | 기본 초록 | 밀밭제과 톤 (금빛·크림) |
| 화면 | 1개 | 5개 |

## 2. 접속

방화벽(ufw)이 8022 만 열려 있다. **아직 8000 을 열지 않았다.**

```bash
# 호스트 PC 에서 — 터널 (지금 바로 됨)
ssh -p 8022 -L 8000:127.0.0.1:8000 dgx-12@10.0.0.62
#  → http://localhost:8000

# 또는 dgx-12 에서 한 번만 (root 필요) — 그 뒤로는 터널 불필요
sudo bash ~/agora-ops/expose-dgx12.sh
#  → http://10.0.0.62:8000
```

| 주소 | 내용 |
|---|---|
| `/` | 픽셀 오피스 (PM 관제). 책상을 누르면 에이전트 상세 |
| `/agent.html` | 역할별 현황·산출물 열람/수정·↻재요청 |
| `/files.html` | `repo/` 탐색기 — 조회·수정·사이트 열기 |
| `/board.html` | 티켓 보드 + 타임라인 |
| `/edit.html` | **학생용 AGENT.md 편집** |
| `/order.html` | 주문 접수 |
| `/preview/...` | **에이전트가 만든 웹사이트** |
| `/docs` | API 문서 |

## 3. 수업 진행 순서

1. 프로젝터에 `/` (픽셀 오피스)를 띄운다.
2. `/order.html` 에서 주문을 넣는다 (또는 `./ops/rehearsal.sh` 로 시연).
3. S1 영업 → S2 기획이 **AGENT.md 11개**를 만든다 (여기가 가장 오래 걸린다).
4. **S3 에서 자동으로 멈춘다.** 학생들이 각자
   `/edit.html?role=<자기역할>` 에서 자기 AGENT.md 를 고치고 **저장**.
5. 11/11 이 되면 **자동 재개**. S4 설계 → S5 구현 → S6~S8 게이트 → S9 배포 → S10 운영.
6. 완성된 사이트는 픽셀 오피스 상단 `🌐 완성된 사이트 열기` 로 본다.
7. 회고: `⟲ 처음부터` → **"AGENT.md 는 그대로 두기"** 로 같은 주문을 다시 돌린다.
   지시문만 바꿔서 결과가 어떻게 달라지는지 보는 것이 이 수업의 핵심이다.

**소요 시간**: 한 사이클 25~40분. S2 가 절반을 차지한다.

## 4. 역할 ↔ 노드

`~/agora-ops/nodes.tsv` 가 단일 진실 공급원. 바꾸면 `./provision-all.sh` 재실행.

| 노드 | IP | 역할 |
|---|---|---|
| dgx-02 | .52 | planner 기획 |
| dgx-03 | .53 | sales 영업 |
| dgx-04 | .54 | sysadmin 인프라 |
| dgx-05 | .55 | designer 디자인 |
| dgx-06 | .56 | frontend 프론트 |
| dgx-07 | .57 | backend 백엔드 |
| dgx-08 | .58 | dba DB |
| dgx-09 | .59 | security 보안 |
| dgx-10 | .60 | qa QA |
| dgx-11 | .61 | customer 고객 |
| dgx-12 | .62 | pm 관리 + **HQ** |

dgx-01(.51)도 살아 있으나 역할 배정에는 없다.

## 5. 문제가 생기면

| 증상 | 확인 |
|---|---|
| 책상이 다 꺼져 있다 | 하트비트 30초 주기. DB 를 새로 만들었으면 1분 기다린다 |
| 노드가 응답 없다 | `echo '~/agora/verify-node.sh' \| ~/agora-ops/dgx-fan.sh dgx-07` |
| 산출물이 사라졌다 | `~/agora-ops/recover-artifacts.sh <사이클>` — 노드에 원본이 있다 |
| 결과물 품질이 낮다 | `.venv/bin/python ops/site-check.py` 로 19항목 채점 |
| 단계가 멈춰 있다 | `/agent.html?role=<역할>` 에서 현재 작업 확인 → ↻재요청 |
| 처음부터 다시 | `./ops/reset.sh` — `repo/.archive/` 에 백업을 남긴다 |

**주의**: `repo/runs/` 를 손으로 지우지 마라. 완성된 사이트가 거기 있다.
초기화는 반드시 `ops/reset.sh` 로.

**남겨야 할 결과물은 `repo/showcase/` 로 복사해 둔다.**
DB 를 초기화하면 사이클 번호가 1 부터 다시 시작하므로 `runs/1` 이 덮어써진다.
`showcase/` 는 `reset.sh` 도 건드리지 않는다.

```bash
cp -r repo/runs/3/S5/output repo/showcase/v2-after
```

미리보기: `/preview/showcase/<폴더>/index.html`

## 6. 남은 일 (우선순위 순)

1. **`sudo bash ~/agora-ops/expose-dgx12.sh`** — 8000·11434 개방 (root 필요)
2. **학생 명단** — `~/agora/provisioning/students.yaml` 의 `name` 이 전부 비어 있다
3. **수업 전 리허설 1회** — `./ops/rehearsal.sh` (25~40분). 당일 아침에 한 번 돌려
   노드 상태와 소요 시간을 확인해라
4. **`board.html` 티켓 조작** — 지금은 조회만 된다. 상태 변경 UI 는 없다
   (API `POST /api/tickets/{id}/transition` 은 있다)
5. **Docker 전환** — `sudo usermod -aG docker $USER` 후 `make up`.
   지금은 네이티브로 돌아가므로 급하지 않다
6. **defect 파이프라인 S1/S6 모순** — BRIEF 본문과 인수 #24 가 어긋난다.
   현재는 본문을 따랐다. `~/agora/CLAUDE.md` Phase 0 기록 참조

## 7. 알아둘 것

- **교실엔 인터넷이 없다.** 리허설에서 프론트엔드가 `npm install` 을 돌렸다
  (노드에 인터넷이 있어서 됐다). `templates/_quality.md` 와 각 AGENT.md '금지' 칸에
  금지 문구를 넣어 뒀지만, 수업 당일 노드 인터넷을 끊어 두는 편이 확실하다.
- **`EXECUTOR=sim`** 으로 바꾸면 노드 없이 흐름만 빠르게 돌려볼 수 있다 (한 단계 1~4초).
  `.env` 를 고치고 `make dev-stop && make dev`. E2E 테스트도 sim 에서만 돈다.
- **모든 쓰기는 감사 로그에 남는다** (`audit_logs` 테이블). 회고 자료로 쓸 수 있다.
- **학생이 고친 diff 가 보관된다** — `/api/specs/{role}/diff`.
  "AGENT.md 한 줄이 결과를 어떻게 바꿨나" 를 보여주는 평가 데이터다.
