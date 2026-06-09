from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from agno.run.agent import RunCompletedEvent, RunContentEvent

from coke.llm.agno_interaction_agent import AgnoInteractionAgent
from coke.turn.agent import AgentRequest, AgentToolPorts, ToolExecutionResult
from coke.turn.context import ToolProfile, TurnMode


@dataclass
class StreamingFakeAgentInstance:
    chunks: tuple[str, ...]
    final_content: str
    calls: list[dict[str, Any]]

    async def arun(self, input, **kwargs):
        self.calls.append({"method": "arun", "input": input, "kwargs": kwargs})

        async def stream():
            for chunk in self.chunks:
                yield RunContentEvent(content=chunk)
            yield RunCompletedEvent(content=self.final_content)

        return stream()


class ToolCallingStreamingFakeAgentInstance(StreamingFakeAgentInstance):
    def __init__(self, *, chunks: tuple[str, ...], final_content: str) -> None:
        super().__init__(chunks=chunks, final_content=final_content, calls=[])
        self.factory_kwargs: dict[str, Any] = {}

    async def arun(self, input, **kwargs):
        self.factory_kwargs["tools"][0](command={"operation": "list_reminders"})
        return await super().arun(input, **kwargs)


class FakeAgentFactory:
    def __init__(self, instance: StreamingFakeAgentInstance) -> None:
        self.instance = instance
        self.agent_kwargs: list[dict[str, Any]] = []

    def __call__(self, **kwargs):
        self.agent_kwargs.append(kwargs)
        if hasattr(self.instance, "factory_kwargs"):
            self.instance.factory_kwargs = kwargs
        return self.instance


class FakeReminderTool:
    def execute(self, command, guard):
        return ToolExecutionResult(ok=True, facts={"reminders": []})


@pytest.mark.asyncio
async def test_ainvoke_streaming_yields_complete_segments_before_final_result():
    final_content = '{"type":"reply","segments":["Hello there.","How can I help?"]}'
    fake_agent = StreamingFakeAgentInstance(
        chunks=(
            '{"type":"reply","segments":["Hello',
            ' there.",',
            '"How can I help?"]}',
        ),
        final_content=final_content,
        calls=[],
    )
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(fake_agent),
    )

    events = [
        event async for event in agent.ainvoke_streaming(_request(memory_enabled=True))
    ]

    assert events[0] == "Hello there."
    assert events[1] == "How can I help?"
    assert events[2].output == {
        "type": "reply",
        "segments": ["Hello there.", "How can I help?"],
    }
    assert events[2].tool_events == ()
    assert fake_agent.calls[0]["kwargs"]["stream"] is True
    assert fake_agent.calls[0]["kwargs"]["stream_events"] is True
    assert fake_agent.calls[0]["kwargs"]["run_id"] == "turn_1"


@pytest.mark.asyncio
async def test_ainvoke_streaming_preserves_tool_events_on_final_result():
    fake_agent = ToolCallingStreamingFakeAgentInstance(
        chunks=('{"type":"reply","segments":["Listed"]}',),
        final_content='{"type":"reply","segments":["Listed"]}',
    )
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(fake_agent),
    )

    events = [
        event
        async for event in agent.ainvoke_streaming(
            _request(memory_enabled=True, reminder_tool=FakeReminderTool())
        )
    ]

    assert events[-1].tool_events


def _request(
    *,
    memory_enabled: bool,
    reminder_tool=None,
) -> AgentRequest:
    tool_ports = AgentToolPorts(reminder_tool=reminder_tool)
    return AgentRequest(
        turn_id="turn_1",
        conversation_id="conversation_1",
        account_id="account_1",
        mode=TurnMode.INTERACTIVE,
        trigger_type="InboundTurn",
        payload={"text": "hello"},
        trusted_facts={
            "assistant_name": "Coke",
            "persona": "concise assistant",
            "memory_enabled": memory_enabled,
            "default_timezone": "UTC",
        },
        tool_profile=ToolProfile.interactive(tool_ports),
        freshness_guard=object(),
        context={},
    )
