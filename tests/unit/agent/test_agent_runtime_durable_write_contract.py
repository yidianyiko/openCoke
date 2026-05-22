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
from agent.agno_agent.runtime.result import CapabilityResult


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


async def _run(*, capability_results, monkeypatch, messages=None):
    captured_results = list(capability_results)

    class Out:
        content = ""

        def __init__(self):
            self.messages = messages or [{"role": "assistant", "content": ""}]

    class Agent:
        async def arun(self, **_kwargs):
            return Out()

    def fake_create(
        *, run_context, agent_input, input_message, capability_results, domain_results
    ):
        del run_context, agent_input, input_message, domain_results
        capability_results.extend(captured_results)
        return Agent()

    monkeypatch.setattr(agent_runtime, "_create_interaction_agent", fake_create)
    return await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="user.turn",
            conversation_id="conv1",
            text="hi",
            payload=UserTurnPayload(current_message_ids=["msg1"]),
            occurred_at=datetime.now(UTC),
        ),
        run_context=_ctx(),
    )


@pytest.mark.asyncio
async def test_durable_write_with_visible_summary_succeeds(monkeypatch):
    ok = CapabilityResult(
        name="reminder",
        ok=True,
        content={"visible_summary": "已设好提醒"},
        metadata={"durable_write": True},
    )

    result = await _run(capability_results=[ok], monkeypatch=monkeypatch)

    assert result.output_disposition.status == "ok"
    assert [message.content for message in result.visible_messages] == ["已设好提醒"]


@pytest.mark.asyncio
async def test_durable_write_without_visible_summary_is_failclosed(monkeypatch):
    bad = CapabilityResult(
        name="reminder",
        ok=True,
        content={},
        metadata={"durable_write": True},
    )

    result = await _run(capability_results=[bad], monkeypatch=monkeypatch)

    assert result.output_disposition.status == "empty"
    assert result.visible_messages == ()
    assert result.error_disposition is not None
    assert result.error_disposition.code == "durable_write_missing_visible_summary"
