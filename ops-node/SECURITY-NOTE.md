# 이 폴더를 그대로 쓰기 전에

여기 있는 스크립트는 **교실 DGX 11대를 운영하는 실제 도구**다.
공개 리포에 올리면서 다음을 가렸다.

| 원래 | 이 리포에서 |
|---|---|
| 실제 노드 IP | `10.0.0.x` (문서용 예시 대역) |
| 노드 sudo 비밀번호가 계정명과 같다는 규칙 | `NODE_SUDO_PW` 환경변수로 받도록 변경 |

**쓰려면 `nodes.tsv` 를 자기 환경의 IP 로 바꿔라.** 그 파일 하나가 단일 진실 공급원이고,
나머지 스크립트는 전부 거기서 읽는다.

```bash
# 노드 정보 수정
vi ops-node/nodes.tsv        # node<TAB>ip<TAB>role<TAB>표시이름

# sudo 가 필요한 스크립트는 비밀번호를 환경변수로 넘긴다
NODE_SUDO_PW='...' bash ops-node/expose-ollama.sh
```

## 알아 둘 것 — 이 구성은 폐쇄망 전제다

- **Ollama 에는 인증이 없다.** `expose-ollama.sh` 는 11434 를 모든 인터페이스에
  여는 스크립트다. 교실 L2 안에서만 열리는 것을 전제로 만들었다.
  외부에서 닿는 대역이라면 방화벽으로 반드시 막아라.
- **HQ(8000)에도 인증이 없다.** 같은 전제다.
- **노드 비밀번호 인증을 일부러 남겨 뒀다.** SSH 키가 깨졌을 때 교실에서
  전원이 잠기는 것을 막기 위해서다. 폐쇄망이 아니라면 키 전용으로 바꿔라.

## 파일

| | |
|---|---|
| `nodes.tsv` | ★ 노드↔IP↔역할. 바꾸면 `provision-all.sh` 재실행 |
| `dgx-fan.sh` | 여러 노드에 같은 명령을 동시에 |
| `provision-all.sh` / `provision-node.sh` | Hermes↔Ollama 연결 (멱등) |
| `deploy-adapter.sh` | A2A 어댑터 배포 |
| `install-hermes.sh` / `install-heartbeat.sh` | 초기 설치 |
| `recover-artifacts.sh` | **노드에 남은 산출물을 HQ 로 회수** (실제로 51개를 되살렸다) |
| `verify-all.sh` / `status-all.sh` | 상태 점검 |
| `expose-ollama.sh` / `expose-dgx12.sh` | 포트 개방 (위 경고 참조) |
| `HANDOFF.md` / `ACCESS.md` / `DECISIONS.md` | 운영 인수인계 · 접속 · 결정 기록 |
