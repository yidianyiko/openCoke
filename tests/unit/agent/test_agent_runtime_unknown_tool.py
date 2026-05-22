from datetime import UTC, datetime

import pytest

from agent.agno_agent.runtime import agent_runtime
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload


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
async def test_unknown_tool_call_results_in_failclosed_disposition(monkeypatch):
    class FakeAgent:
        async def arun(self, **_kwargs):
            raise agent_runtime.UnknownToolError("bogus_tool")

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", lambda **_kwargs: FakeAgent()
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="user.turn",
            conversation_id="conv1",
            text="hi",
            payload=UserTurnPayload(current_message_ids=["msg1"]),
            occurred_at=datetime.now(UTC),
        ),
        run_context=_ctx(),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "agent_runtime_unknown_tool"
    assert result.error_disposition.retryable is False
