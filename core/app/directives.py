"""사람이 에이전트에게 **중간에 끼어들어 지시하는** 경로.

## 왜 필요한가

AGENT.md 는 사이클이 시작될 때 한 번 정해진다. 그런데 실제 수업에서는
일이 돌아가는 도중에 하고 싶은 말이 생긴다.

    "디자인은 좋은데 버튼이 너무 큰 것 같다. 좀 줄여 줘."
    "프론트엔드, 장바구니 화면은 이번엔 빼도 된다."
    "QA, 모바일 화면 폭도 꼭 확인해라."

이걸 반영할 방법이 없으면 사람이 할 수 있는 건 구경뿐이다.
이 모듈이 그 경로다.

## 어디에 쓰나 (사람이 만지는 파일)

    repo/<project>/NOTES.md                  ← 전원에게 (PM 용)
    repo/<project>/agents/<role>/NOTES.md    ← 그 역할에게만

웹에서는 `/agent.html?role=designer` 의 **「추가 지시」** 패널,
또는 `/edit.html?role=designer` 의 「추가 지시」 탭에서 고친다.

## 언제 반영되나

**그 역할이 다음에 일할 때** 자동으로 프롬프트에 붙는다 (`runner._instruction`).
이미 돌고 있는 단계에는 안 붙는다 — 그 경우 일시정지 후 `↻재요청` 을 하면 된다.
지시는 사이클이 끝날 때까지 남는다. 지우려면 파일을 비우면 된다.

## 왜 파일인가

DB 테이블이 아니라 파일로 둔 이유:
- 학생이 웹에서든 SSH 로든 같은 것을 본다
- `git diff` 로 "사람이 무엇을 끼워 넣었나" 가 그대로 남는다 (평가 자료)
- HQ 를 재시작해도 살아남는다
"""

from __future__ import annotations

import re
from pathlib import Path

from .services import PROJECT_ID, REPO_ROOT, now

MAX_BYTES = 4000          # 프롬프트가 커지면 로컬 모델이 멈춘다. 넉넉하되 상한은 둔다.
HEADER = "# 사람이 추가한 지시\n"


def global_path() -> Path:
    return REPO_ROOT / PROJECT_ID / "NOTES.md"


def role_path(role: str) -> Path:
    return REPO_ROOT / PROJECT_ID / "agents" / role / "NOTES.md"


def _read(p: Path) -> str:
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def read(role: str | None = None) -> str:
    """역할별(또는 전역) 추가 지시 원문."""
    return _read(role_path(role) if role else global_path())


def write(text: str, role: str | None = None) -> Path:
    """통째로 저장한다. 빈 문자열이면 파일을 지운다(= 지시 취소)."""
    p = role_path(role) if role else global_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    body = text.strip()
    if not body:
        p.unlink(missing_ok=True)
        return p
    p.write_text(body[:MAX_BYTES] + ("\n" if not body.endswith("\n") else ""),
                 encoding="utf-8")
    return p


def append(line: str, role: str | None = None, who: str = "pm") -> Path:
    """한 줄 덧붙이기 — 웹의 빠른 입력창이 쓴다.

    누가 언제 넣었는지 같이 남긴다. 나중에 "이 지시가 결과를 어떻게 바꿨나" 를
    되짚을 수 있어야 한다.
    """
    line = line.strip()
    if not line:
        raise ValueError("빈 지시는 넣을 수 없다")
    cur = read(role)
    if not cur:
        cur = HEADER
    stamp = now().strftime("%H:%M")
    cur = cur.rstrip() + f"\n- ({stamp} {who}) {line}\n"
    return write(cur, role)


def items(role: str | None = None) -> list[str]:
    """지시를 줄 단위로 — 화면에 목록으로 뿌리기 위한 것."""
    out = []
    for ln in read(role).splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        out.append(re.sub(r"^[-*]\s*", "", s))
    return out


def block(role: str) -> str:
    """작업 지시 프롬프트에 붙일 블록. 없으면 빈 문자열.

    ★ 이 블록은 **맨 뒤**에 붙인다. 앞에 붙이면 뒤의 일반 지시가 덮어쓴다.
      그리고 "최우선" 이라고 명시한다 — 안 그러면 모델이 참고 사항으로만 본다.
    """
    parts: list[str] = []
    g = read(None).strip()
    if g:
        parts.append(_strip_header(g))
    r = read(role).strip()
    if r:
        parts.append(_strip_header(r))
    if not parts:
        return ""
    body = "\n".join(parts)
    return (
        "## ★ 사람이 직접 추가한 지시 — 최우선으로 반영한다\n\n"
        f"{body}\n\n"
        "위 지시는 앞의 어떤 지침보다 우선한다. 앞의 지침과 충돌하면 **위 지시를 따른다.**\n"
        "반영할 수 없는 지시가 있으면 완료 보고(`report.md`)에 그 이유를 적어라. "
        "말없이 무시하지 마라."
    )


def _strip_header(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines()
                     if ln.strip() and not ln.strip().startswith("# 사람이 추가한 지시"))


def summary() -> dict[str, int]:
    """역할별 지시 개수 — 픽셀 오피스 배지에 쓴다."""
    from .models import ROLES
    out = {"_global": len(items(None))}
    for r in ROLES:
        n = len(items(r))
        if n:
            out[r] = n
    return out
