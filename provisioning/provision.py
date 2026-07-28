#!/usr/bin/env python3
"""프로비저닝 (BRIEF §10) — Phase 2 에서 구현한다. 전부 멱등해야 한다.

하는 일:
    1. Node 11개 등록 + 토큰 발급
    2. repo/project-001/ 초기화 — 계약 씨앗 4종을 70% 채운 상태로 커밋 (BRIEF §11)
    3. provisioning/out/node-{role}.env 생성 — 학생 배포용
    4. provisioning/out/명단.md — 강사용 요약표

⚠️ provisioning/out/ 은 .gitignore 에 있다. 토큰이 들어가므로 커밋 금지 (BRIEF §15-6).
"""

from __future__ import annotations

import sys


def main() -> int:
    print("Phase 2 에서 구현한다.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
