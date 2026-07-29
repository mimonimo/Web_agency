"""모델 백엔드 — 어떤 모델을 붙여도 같은 지시·같은 검사를 받는다.

## 왜 이게 따로 있는가

수업은 교실 안 DGX 의 로컬 모델(`gpt-oss:120b`)로 돈다. 하지만 이 시스템의 목표는
"그 모델에 맞춘 것" 이 아니라 **"어떤 모델을 붙여도 결과의 바닥이 유지되는 것"** 이다.

    기준선 지시문 · 참고 자료 전달 · 완료 조건 주입 · 기계 검사 · 자가 재작업
    → 이 다섯은 모델과 무관하다.

그래서 모델을 갈아끼우는 지점을 여기 하나로 모았다.
Claude 를 붙이면 더 잘 나온다. 붙이지 않아도 바닥은 유지된다. 그게 설계 의도다.

## 붙이는 방법

```bash
# Claude (Anthropic API)
EXECUTOR=llm
LLM_PROVIDER=anthropic
LLM_MODEL=claude-opus-5
ANTHROPIC_API_KEY=sk-ant-...          # 또는 `ant auth login` 프로필

# OpenAI 호환 엔드포인트 — Ollama · vLLM · LM Studio · OpenRouter 등
EXECUTOR=llm
LLM_PROVIDER=openai
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=gpt-oss:120b
LLM_API_KEY=아무거나                   # 로컬 서버는 대개 안 본다
```

## 출력 규약

모델은 파일을 이 형식으로 낸다. 형식을 어기면 `parse_files()` 가 못 읽고,
읽을 게 없으면 검사에서 걸려 자동으로 다시 시킨다 — 조용히 넘어가지 않는다.

    === FILE: index.html ===
    <!doctype html>
    ...
    === END ===
"""

from __future__ import annotations

import os
import re

import httpx

TIMEOUT = float(os.getenv("LLM_TIMEOUT_SEC", "600"))
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "16000"))

FILE_BLOCK = re.compile(
    r"===\s*FILE:\s*(?P<name>[^\n=]+?)\s*===\r?\n(?P<body>.*?)(?:\r?\n)?===\s*END\s*===",
    re.S)

# 모델이 형식을 조금씩 다르게 쓴다. 흔한 변형도 받아 준다.
FENCE_BLOCK = re.compile(
    r"(?:^|\n)#{1,4}\s*`?(?P<name>[\w./-]+\.[A-Za-z0-9]{1,5})`?\s*\n+"
    r"```[\w-]*\r?\n(?P<body>.*?)```", re.S)


def parse_files(text: str) -> dict[str, str]:
    """모델 답변에서 파일들을 뽑아낸다.

    ⚠️ 하나도 못 뽑으면 빈 dict 를 준다. 억지로 통짜 저장하지 않는다 —
       엉뚱한 내용이 `index.html` 로 저장되면 아무도 원인을 못 찾는다.
    """
    out: dict[str, str] = {}
    for m in FILE_BLOCK.finditer(text):
        name = m.group("name").strip().strip("`").lstrip("/")
        if name and ".." not in name:
            out[name] = m.group("body")
    if out:
        return out
    for m in FENCE_BLOCK.finditer(text):        # 두 번째 기회
        name = m.group("name").strip().lstrip("/")
        if name and ".." not in name:
            out.setdefault(name, m.group("body"))
    return out


def output_protocol(outputs: tuple[str, ...] | list[str]) -> str:
    """만들어야 할 파일과 형식을 못 박는 블록. 프롬프트 맨 앞에 붙인다."""
    want = "\n".join(f"  - {o}" for o in outputs) or "  - (지시문에 적힌 파일)"
    return (
        "## 출력 형식 — 반드시 지켜라\n\n"
        "만들 파일:\n" + want + "\n\n"
        "각 파일을 아래 형식으로 **하나씩** 내라. 설명은 파일 밖에 짧게만 쓴다.\n\n"
        "```\n"
        "=== FILE: 파일이름 ===\n"
        "(파일 내용 전체)\n"
        "=== END ===\n"
        "```\n\n"
        "⚠️ 파일 내용 안에는 ``` 코드펜스를 쓰지 마라. 내용만 그대로 쓴다.\n"
        "⚠️ 위에 적힌 파일을 **전부** 내라. 하나라도 빠지면 다음 단계가 막힌다."
    )


class ProviderError(RuntimeError):
    pass


class AnthropicProvider:
    """Claude — 공식 SDK 를 쓴다.

    SDK 가 없으면 설치 방법을 알려 주고 멈춘다. 조용히 다른 경로로 새지 않는다.
    """

    def __init__(self) -> None:
        self.model = os.getenv("LLM_MODEL", "claude-opus-5")
        try:
            import anthropic                                   # noqa: F401
        except ImportError as e:
            raise ProviderError(
                "anthropic SDK 가 없다. `\\.venv/bin/pip install anthropic` 로 설치해라. "
                "(교실은 오프라인이므로 기본 requirements 에는 넣지 않았다)") from e

    async def complete(self, system: str, user: str) -> str:
        import anthropic

        client = anthropic.AsyncAnthropic()      # 키는 환경/프로필에서 찾는다
        # 긴 산출물이 많다. 스트리밍으로 받아야 요청 타임아웃에 걸리지 않는다.
        async with client.messages.stream(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            msg = await stream.get_final_message()
        if msg.stop_reason == "refusal":
            raise ProviderError("모델이 응답을 거절했다 (stop_reason=refusal)")
        return "".join(b.text for b in msg.content if b.type == "text")


class OpenAICompatProvider:
    """OpenAI 호환 엔드포인트 — Ollama · vLLM · LM Studio · OpenRouter.

    Anthropic 이 아니므로 SDK 를 끌어오지 않고 HTTP 로 직접 부른다.
    이미 있는 httpx 만 쓰므로 교실 노드에 추가 설치가 필요 없다.
    """

    def __init__(self) -> None:
        self.base = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
        self.model = os.getenv("LLM_MODEL", "gpt-oss:120b")
        self.key = os.getenv("LLM_API_KEY", "not-needed")

    async def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.post(f"{self.base}/chat/completions", json=payload,
                             headers={"Authorization": f"Bearer {self.key}"})
            if r.status_code >= 400:
                raise ProviderError(f"{self.base} 가 {r.status_code} 를 냈다: "
                                    f"{r.text[:200]}")
            data = r.json()
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"응답 형식을 읽을 수 없다: {str(data)[:200]}") from e


def get() -> AnthropicProvider | OpenAICompatProvider:
    name = os.getenv("LLM_PROVIDER", "openai").lower()
    if name in ("anthropic", "claude"):
        return AnthropicProvider()
    if name in ("openai", "openai-compatible", "ollama", "vllm"):
        return OpenAICompatProvider()
    raise ProviderError(
        f"모르는 LLM_PROVIDER: {name!r} (anthropic | openai 중에서 골라라)")


def describe() -> str:
    name = os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv("LLM_MODEL", "?")
    where = "" if name in ("anthropic", "claude") else f" @ {os.getenv('LLM_BASE_URL', '?')}"
    return f"{name}:{model}{where}"
