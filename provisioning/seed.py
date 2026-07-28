#!/usr/bin/env python3
"""씨앗 데이터 (BRIEF §10) — Phase 2 에서 구현한다. 멱등.

넣는 것:
    - 씨앗 주문 1건 (밀밭제과, kind=new, status=READY 로 **자동 시작하지 않음**)
    - 샘플 티켓 2건

넣지 않는 것:
    - **AGENT.md 초안 11개는 미리 넣지 않는다.**
      S2 에서 기획 에이전트가 만드는 게 수업이다 (BRIEF §10, §4.1).
"""

from __future__ import annotations

import sys


def main() -> int:
    print("Phase 2 에서 구현한다.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
