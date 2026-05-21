from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)


def _ctx() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="u1", nickname="Alice", timezone="UTC"),
        character=TrustedCharacterContext(id="c1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="u1", cid="c1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_invalid_primary_structured_output_fails_without_retry_agent():
    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content="intentaction cancel")

    result = await ReminderIntentPort(detector_agent=PrimaryAgent()).run(
        "取消提醒",
        _ctx(),
    )

    assert result.ok is False
    assert result.error == "ReminderDetectInvalidDecision"
    assert result.metadata["durable_write"] is False
