from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import agent.agno_agent.runtime.agent_runtime as agent_runtime
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload
from agent.agno_agent.runtime.result import AgentRunResult


def _agent_input() -> AgentInput:
    return AgentInput(
        input_type="user.turn",
        conversation_id="conv-1",
        text="hi",
        payload=UserTurnPayload(current_message_ids=["msg-1"]),
        occurred_at=datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
    )


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="UTC"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key=None,
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="User: hi",
        current_time=datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
        runtime_metadata={"message_source": "user"},
    )


@pytest.mark.asyncio
async def test_run_agent_runtime_returns_agent_run_result_for_no_tool_run(monkeypatch):
    class FakeAgent:
        async def arun(self, **kwargs):
            assert kwargs == {"input": "hi", "session_id": "conv-1"}
            return SimpleNamespace(
                content="fallback content",
                messages=[
                    SimpleNamespace(role="user", content="hi"),
                    SimpleNamespace(role="assistant", content="hi back"),
                ],
            )

    monkeypatch.setattr(agent_runtime, "_create_agent", lambda **kwargs: FakeAgent())

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert isinstance(result, AgentRunResult)
    assert result.visible_messages[0].content == "hi back"
    assert result.output_disposition.status == "ok"
    assert result.tool_results == ()
    assert result.post_analyze_input == {
        "input_message": "hi",
        "message_source": "user",
    }
