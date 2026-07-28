"""pipeline.yaml 로더 (BRIEF §3.6).

파이프라인은 코드가 아니라 **데이터**다. 강사가 수업 중에 단계를 자를 수 있어야 하므로
단계를 코드에 하드코딩하지 않는다. 이 모듈은 YAML 을 읽어 값으로 바꿔줄 뿐이다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).parent

# 파이프라인 이름 → 파일. 요구사항 종류별로 다른 경로를 탄다 (BRIEF §3.6 표).
PIPELINE_FILES: dict[str, str] = {
    "web_delivery": "pipeline.yaml",
    "web_change": "pipeline.change.yaml",
    "web_defect": "pipeline.defect.yaml",
    "web_security": "pipeline.security.yaml",
}

# Order.kind → 기본 파이프라인
KIND_TO_PIPELINE: dict[str, str] = {
    "new": "web_delivery",
    "change": "web_change",
    "defect": "web_defect",
    "security": "web_security",
}

DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_STEP_TIMEOUT_SEC", "900"))


@dataclass(frozen=True)
class StepDef:
    """pipeline.yaml 의 step 한 개."""

    id: str
    name: str
    role: str | None = None
    task: str | None = None
    type: str | None = None                 # None | "gate" | "human_gate"
    parallel: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    timeout_sec: int = DEFAULT_TIMEOUT
    emits_specs: bool = False
    creates_orders: bool = False
    allow_override: bool = False
    wait_for: str | None = None
    hint: str | None = None
    on_reject_rewind_to: str | None = None
    on_reject_priority: str | None = None

    @property
    def roles(self) -> tuple[str, ...]:
        """이 단계에서 일하는 역할들. 병렬 단계면 여러 개다."""
        if self.parallel:
            return self.parallel
        return (self.role,) if self.role else ()


@dataclass(frozen=True)
class Pipeline:
    name: str
    kind: str
    steps: tuple[StepDef, ...]

    def step(self, step_id: str) -> StepDef | None:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None


def _to_tuple(v: Any) -> tuple[str, ...]:
    if v is None:
        return ()
    if isinstance(v, str):
        return (v,)
    return tuple(str(x) for x in v)


def _parse(raw: dict[str, Any]) -> Pipeline:
    steps: list[StepDef] = []
    for s in raw.get("steps", []):
        on_reject = s.get("on_reject") or {}
        steps.append(
            StepDef(
                id=s["id"],
                name=s.get("name", s["id"]),
                role=s.get("role"),
                task=s.get("task"),
                type=s.get("type"),
                parallel=_to_tuple(s.get("parallel")),
                inputs=_to_tuple(s.get("inputs")),
                outputs=_to_tuple(s.get("outputs")),
                timeout_sec=int(s.get("timeout_sec", DEFAULT_TIMEOUT)),
                emits_specs=bool(s.get("emits_specs", False)),
                creates_orders=bool(s.get("creates_orders", False)),
                allow_override=bool(s.get("allow_override", False)),
                wait_for=s.get("wait_for"),
                hint=s.get("hint"),
                on_reject_rewind_to=on_reject.get("rewind_to"),
                on_reject_priority=on_reject.get("priority"),
            )
        )
    return Pipeline(name=raw["name"], kind=raw.get("kind", "new"), steps=tuple(steps))


@lru_cache(maxsize=None)
def load(name: str) -> Pipeline:
    """이름으로 파이프라인을 읽는다. 결과는 캐시된다."""
    fname = PIPELINE_FILES.get(name)
    if fname is None:
        raise KeyError(f"그런 파이프라인이 없다: {name}")
    raw = yaml.safe_load((HERE / fname).read_text(encoding="utf-8"))
    return _parse(raw)


def for_kind(kind: str) -> Pipeline:
    """Order.kind 로 파이프라인을 고른다."""
    return load(KIND_TO_PIPELINE.get(kind, "web_delivery"))


def available() -> list[str]:
    return list(PIPELINE_FILES)
