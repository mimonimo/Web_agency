"""HQ 자신도 A2A 에이전트로 노출 (선택 — BRIEF §2).

노드가 HQ 를 하나의 에이전트로 보고 말을 걸 수 있게 하는 쪽. 필수가 아니므로
Phase 2 에서 시간이 남을 때만 채운다. 자르는 순서(BRIEF §14)에서 이른 쪽에 있다.

에이전트 카드 모양은 BRIEF §5.2 를 따른다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["a2a"])


def hq_agent_card(hq_url: str) -> dict[str, Any]:
    """HQ 자신의 A2A 에이전트 카드 (BRIEF §5.2 형식)."""
    return {
        "name": "agora-hq",
        "description": "AGORA Web 중앙 오케스트레이터",
        "url": hq_url,
        "version": "1.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [
            {"id": "dispatch", "name": "작업 배분", "tags": ["orchestrate"]},
            {"id": "mirror", "name": "메시지 미러링", "tags": ["audit"]},
        ],
    }


@router.get("/.well-known/agent-card.json")
async def agent_card() -> dict[str, Any]:
    """Phase 2 에서 실제 HQ URL 을 넣어 반환한다."""
    return hq_agent_card("http://hq.agora.lan/")
