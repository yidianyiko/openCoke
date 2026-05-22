from datetime import UTC, datetime

import pytest

from agent.agno_agent.runtime import event_adapter
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload
from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition


def _legacy_context():
    return {
        "user": {"id": "u1", "nickname": "Alice"},
        "character": {"id": "c1", "name": "Coke"},
        "conversation": {"id": "conv1", "platform": "business"},
        "relation": {"uid": "u1", "cid": "c1"},
        "platform": "business",
    }


@pytest.mark.asyncio
async def test_event_adapter_calls_agent_runtime_with_typed_context(monkeypatch):
    captured = {}
    fake_result = AgentRunResult(
        visible_messages=(),
        post_analyze_input=None,
        domain_results=[],
        capability_results=(),
        metrics={},
        trace={},
        output_disposition=OutputDisposition(status="empty"),
    )

    async def fake_run_agent_runtime(*, agent_input, run_context):
        captured["agent_input"] = agent_input
        captured["run_context"] = run_context
        return fake_result

    monkeypatch.setattr(event_adapter, "run_agent_runtime", fake_run_agent_runtime)

    agent_input = AgentInput(
        input_type="user.turn",
        conversation_id="conv1",
        text="hi",
        payload=UserTurnPayload(current_message_ids=["msg1"]),
        occurred_at=datetime.now(UTC),
    )
    result = await event_adapter.run_agent_runtime_event(
        agent_input=agent_input,
        context=_legacy_context(),
        message_source="user",
    )

    assert result is fake_result
    assert captured["agent_input"] is agent_input
    assert captured["run_context"].user.id == "u1"
    assert captured["run_context"].conversation.id == "conv1"
    assert captured["run_context"].runtime_metadata["message_source"] == "user"
