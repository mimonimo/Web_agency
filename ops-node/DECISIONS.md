# 노드 셋업 기록 — 2026-07-28

> BRIEF 작업규칙 6번에 따른 누적 기록. HQ 리포(`agora/`)를 만들면 이 내용을
> `agora/CLAUDE.md` 로 합칠 것.

## 착수 전 실제 상태 (지시 내용과 달랐던 부분)

"각 DGX 에 Hermes 와 Ollama 가 설치되어 있다"는 전제로 시작했으나, 실측 결과는 달랐다.

| 항목 | 실제 |
|---|---|
| Ollama + `gpt-oss:120b` | 10대 전부 설치·기동 (정상) |
| Hermes 설치됨 | dgx-05, 06, 07, 08, 09 — **5대뿐** |
| Hermes 미설치 | dgx-02, 03, 04, 10, 11 — **5대** |
| Hermes 부트스트랩 미완료 | dgx-07 (설치는 됨, 설정 마법사 미실행) |
| Hermes → Ollama 연결 | **0대**. 전부 `openrouter.ai` + `anthropic/claude-opus-4.6` |

즉 Hermes 가 있던 5대조차 로컬 모델이 아니라 **외부 유료 API 를 바라보고 있었다.**
BRIEF §1.2 의 "인터넷 없음 전제"와 정면으로 어긋나므로 전량 로컬 Ollama 로 돌렸다.

## 내린 결정

1. **PM 은 SSH 공개키로 노드를 관리한다.**
   `~/.ssh/id_ed25519` (comment `dgx-12-pm`) 를 10대 `authorized_keys` 에 배포하고
   `~/.ssh/config` 에 `dgx-02`~`dgx-11` 별칭을 등록했다.
   비밀번호(설치 시 정한 값)는 **삭제하지 않았다** — 키가 깨져도 교실에서 잠기지 않게.

2. **모델은 노드 로컬 Ollama 를 쓴다.** 중앙 1대에 모아 서빙하지 않는다.
   `provider: ollama` / `base_url: http://127.0.0.1:11434/v1` / `model: gpt-oss:120b`.
   - 이유: DGX 11대가 Ollama 서빙 전용이라는 BRIEF §1.2 구성과 일치하고,
     네트워크를 안 타므로 인터넷·L2 장애에 영향받지 않는다.
   - Ollama 는 `127.0.0.1` 만 듣고 있고 **그대로 뒀다.** 외부 노출 불필요 + 무인증이라 위험.

3. **설정은 `hermes config set` 으로만 건드린다.** `config.yaml` 직접 편집 금지.
   버전이 올라가도 깨지지 않고 멱등하다.
   기존 설정은 노드마다 `~/.hermes/config.yaml.pre-ollama.bak` 로 백업했다.

4. **역할 매핑은 노드 번호 순서.** (PM 승인) `nodes.tsv` 가 단일 진실 공급원이다.
   dgx-02 planner / 03 sales / 04 sysadmin / 05 designer / 06 frontend /
   07 backend / 08 dba / 09 security / 10 qa / 11 customer. dgx-12 = pm.

5. **`agents/<role>/AGENT.md` 는 미리 만들지 않았다.**
   BRIEF §10 · §4.1 — 초안 생성은 S2 에서 기획 에이전트가 하는 것이 수업 내용 그 자체다.
   노드에는 역할 메타데이터(`~/agora/node.env`)만 배포했다.

6. **Hermes 설치는 `--skip-setup` 비대화형.** 설치 마법사는 `/dev/tty` 를 요구하므로
   SSH 비대화형 세션에서 자동으로 건너뛴다. 이후 `hermes config set` 으로 설정을 채웠다.

## 남은 이슈

- **HQ 미구축.** BRIEF Phase 0~3 (오케스트레이터·상태기계·A2A) 이 아직 없다.
  `node.env` 의 `AGORA_HQ_URL=http://10.0.0.62:8000` 은 **자리만 잡아 둔 값**이며
  아직 아무것도 듣고 있지 않다.
- **A2A 어댑터 없음.** BRIEF §5.5 의 `node/a2a-adapter/` 는 HQ 가 만들어 배포하는 것이라
  HQ 구축 후에 진행해야 한다. 노드 41241 포트는 아직 안 열려 있다.
- **`hermes` 상주(데몬) 미설정.** 현재는 호출할 때만 뜨는 CLI 상태다.
  BRIEF §1.2 의 "24시간 켜둠"은 A2A 어댑터가 생긴 뒤 systemd 유닛으로 잡는 게 맞다.
- **`.hermes/.env` 에 OpenRouter 등 외부 키가 남아 있다.** 로컬 모델만 쓰므로 당장은
  무해하지만, 학생에게 노드를 넘기기 전에 정리할지 PM 판단 필요.
- **DNS 없음.** BRIEF 는 `hq.agora.lan` / `node-backend.agora.lan` 을 쓰는데
  현재는 전부 생 IP 다. dnsmasq 는 Phase 1 작업이다.
- **dgx-12 sudo 비밀번호를 모른다.** PM PC 에 패키지 설치가 필요하면 사람이 직접 해야 한다
  (그래서 `sshpass` 대신 pty 기반 파이썬 헬퍼로 초기 키 배포를 처리했다).
