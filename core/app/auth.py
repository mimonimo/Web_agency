"""노드 토큰 (BRIEF §10-1, 인수 #10).

노드가 HQ 에 쓰기 요청을 보낼 때 자기 토큰을 실어 보낸다.
토큰은 `NODE_TOKEN_SECRET` 에서 역할별로 파생시킨다 — 별도 저장소가 필요 없고,
`provision.py` 가 언제든 같은 값을 다시 만들어낼 수 있다 (멱등).

    token(role) = HMAC-SHA256(NODE_TOKEN_SECRET, "agora-node:" + role)[:32]

⚠️ 이건 교실용이다. 학생끼리 남의 역할을 사칭하지 못하게 하는 정도의 장치이지
   본격적인 인증이 아니다. 비밀은 `.env` 에만 있고 커밋하지 않는다 (BRIEF §15-6).

인증을 강제할지는 `REQUIRE_NODE_TOKEN` 으로 켜고 끈다.
수업 첫날 노드가 아직 토큰을 못 받았을 때 전부 401 이 나면 곤란하므로
**기본값은 꺼짐**이고, 토큰이 실려 오면 틀렸을 때만 401 을 낸다.
"""

from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import Header, HTTPException

SECRET = os.getenv("NODE_TOKEN_SECRET", "change-me-in-dotenv")
REQUIRE = os.getenv("REQUIRE_NODE_TOKEN", "0") == "1"


def token_for(role: str) -> str:
    return hmac.new(
        SECRET.encode(), f"agora-node:{role}".encode(), hashlib.sha256
    ).hexdigest()[:32]


def verify(role: str, presented: str | None) -> None:
    """틀린 토큰이면 401. 아예 안 보냈으면 REQUIRE 일 때만 401."""
    if presented is None:
        if REQUIRE:
            raise HTTPException(401, "노드 토큰이 필요하다")
        return
    if not hmac.compare_digest(presented, token_for(role)):
        raise HTTPException(401, f"{role} 노드 토큰이 올바르지 않다")


async def node_auth(
    role: str,
    x_agora_token: str | None = Header(default=None, alias="X-Agora-Token"),
) -> str:
    """경로에 {role} 이 있는 엔드포인트용 의존성."""
    verify(role, x_agora_token)
    return role
