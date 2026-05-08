from datetime import UTC, datetime

from agent.agno_agent.capabilities.reminder_intent import _build_reminder_retry_input
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


def test_retry_prompt_lists_cancel_action():
    text = _build_reminder_retry_input(
        "取消提醒",
        _ctx(),
        reason="primary detector returned no executable decision",
    )

    assert "cancel" in text
