# A2A 어댑터 (노드용)

HQ 가 만들어 배포하는 **얇은 래퍼**. Phase 2 에서 구현한다.

하는 일은 네 가지뿐이다 (BRIEF §5.5).

1. 에이전트 카드 노출 — `http://<node>:41241/.well-known/agent-card.json`
2. `message/send` 수신 → `spec_url` 로 AGENT.md 받아오기
3. **Hermes CLI 를 작업 디렉터리를 제한한 상태로** 실행
4. 산출물 수집 → `tasks/get` 응답 + HQ 미러링

## 노드 쪽 전제 (이미 완료됨)

PM 의 `~/agora-ops/provision-all.sh` 가 각 노드에 이미 해 둔 것:

- Hermes v0.19.0 설치, 로컬 Ollama(`gpt-oss:120b`)에 연결
- `~/agora/node.env` — `AGORA_ROLE`, `AGORA_HQ_URL`, `AGORA_MODEL` 등
- `~/agora/workspace/`, `~/agora/runs/`

어댑터는 이 값을 읽어 쓰면 된다.

## 미결정 사항

**표준 A2A SDK 를 쓸지, 최소 JSON-RPC 를 직접 만들지 아직 정하지 않았다** (BRIEF §5.4).
Phase 2 의 첫 작업으로 오프라인 설치 가능 여부를 확인한 뒤 정하고,
**어느 쪽을 택했는지 `CLAUDE.md` 에 반드시 기록한다.**

동작하는 것이 표준을 지키는 것보다 우선이다.
