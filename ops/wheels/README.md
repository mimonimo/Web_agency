# a2a-sdk 오프라인 wheel 보관소

BRIEF §5.4 의 "표준 SDK 를 쓸 수 있는지 먼저 확인해라" 에 대한 답.

**확인 결과: 설치 가능하다.** `a2a-sdk 1.1.2` + 의존성 30개, aarch64 wheel 전부 존재.
인터넷이 있는 2026-07-28 에 미리 받아 두었다 (`.whl` 은 gitignore — 용량 때문).

```bash
# 다시 받으려면 (인터넷 필요)
.venv/bin/pip download a2a-sdk -d ops/wheels

# 오프라인 설치
.venv/bin/pip install --no-index --find-links ops/wheels a2a-sdk
```

## 그런데 왜 안 썼나

와이어 포맷(`message/send`, `tasks/get`, `/.well-known/agent-card.json`, JSON-RPC 2.0)은
**A2A 와 글자 그대로 동일하게** 맞췄지만, 구현은 stdlib 로 직접 했다.

이유: 노드 어댑터가 하는 일은 네 가지뿐인데(BRIEF §5.5), SDK 를 쓰면 학생 노드 11대에
google-api-core · protobuf · cryptography 를 포함한 31개 패키지와 venv 를 얹어야 한다.
어댑터를 `python3 adapter.py` 한 줄로 띄울 수 있는 쪽이 교실에서 훨씬 안전하다.

필드명과 엔드포인트가 같으므로 **나중에 SDK 로 갈아끼울 수 있다.**
그때는 위 오프라인 설치 명령을 쓰면 된다.
