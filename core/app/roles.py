"""역할 카탈로그 로더 (`roles.yaml`).

역할의 **목표와 완료조건**을 코드 밖에 두기 위한 얇은 층이다.
세 곳이 이걸 읽는다.

  1. `runner._instruction()`  — 노드에 보내는 작업 지시에 목표·DoD 를 주입
  2. `checks.py`              — 산출물이 DoD 를 지켰는지 기계적으로 검사
  3. `routers/agents.py`      — 학생 화면에 목표·완료조건 표시

★ 왜 코드가 아니라 데이터인가
  교실의 로컬 모델은 "알아서 잘" 못 한다. 목표가 프롬프트 어딘가에 한 번 적혀 있으면
  무시하고 지어낸다. **매 요청에 다시 실어 보내고, 결과를 기계로 검사**해야 따라온다.
  그리고 강사가 수업 중에 목표를 고칠 수 있어야 한다 — 코드 말고 여기서.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import yaml

CATALOG = Path(__file__).parent / "roles.yaml"

_lock = threading.Lock()
_cache: dict[str, Any] | None = None
_mtime: float = 0.0


def _load() -> dict[str, Any]:
    """파일이 바뀌면 다시 읽는다 — 강사가 수업 중에 고쳐도 재기동이 필요 없게."""
    global _cache, _mtime
    with _lock:
        try:
            m = CATALOG.stat().st_mtime
        except FileNotFoundError:
            return {"roles": {}}
        if _cache is None or m != _mtime:
            _cache = yaml.safe_load(CATALOG.read_text(encoding="utf-8")) or {}
            _mtime = m
        return _cache


def all_roles() -> dict[str, Any]:
    return dict(_load().get("roles") or {})


def get(role: str) -> dict[str, Any]:
    """역할 하나의 카탈로그. 없으면 빈 dict (역할이 추가돼도 터지지 않게)."""
    return dict(all_roles().get(role) or {})


def mission(role: str) -> str:
    return str(get(role).get("mission") or "")


def goals(role: str) -> list[str]:
    return [str(x) for x in (get(role).get("goals") or [])]


def dod(role: str) -> list[str]:
    return [str(x) for x in (get(role).get("dod") or [])]


def forbid(role: str) -> list[str]:
    return [str(x) for x in (get(role).get("forbid") or [])]


def owns(role: str) -> list[str]:
    return [str(x) for x in (get(role).get("owns") or [])]


def brief(role: str) -> str:
    """작업 지시에 붙일 요약 블록.

    ⚠️ 짧게 유지한다. 프롬프트가 커지면 로컬 모델이 멈춘다 (실제로 겪었다).
       목표 4줄 + DoD 8줄 + 금지 5줄 = 대략 1200자 이내.
    """
    r = get(role)
    if not r:
        return ""
    out: list[str] = [f"## 이 역할의 목표\n\n{r.get('mission', '')}"]

    g = goals(role)[:4]
    if g:
        out.append("이번 단계에서 달성할 것:\n" + "\n".join(f"- {x}" for x in g))

    d = dod(role)[:8]
    if d:
        out.append(
            "## 완료 조건 — 하나라도 못 지키면 게이트에서 반려된다\n\n"
            + "\n".join(f"- [ ] {x}" for x in d)
            + "\n\n제출하기 전에 위 목록을 **직접 확인**해라. 확인하지 않고 내면 되돌아온다."
        )

    f = forbid(role)[:5]
    if f:
        out.append("## 이 역할이 특히 조심할 것\n\n" + "\n".join(f"- {x}" for x in f))

    o = owns(role)
    if o:
        out.append(f"## 내가 만드는 파일\n\n{', '.join(o)}")

    return "\n\n".join(out)
