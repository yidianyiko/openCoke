from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agno.run.agent import RunOutput

from coke.llm.agno_interaction_agent import AgnoInteractionAgent
from coke.turn.agent import AgentRequest, AgentToolPorts, ToolExecutionResult
from coke.turn.context import ToolProfile, TurnMode


@dataclass
class FakeAgentInstance:
    content: Any = None
    calls: list[dict[str, Any]] | None = None
    raise_timeout_once: bool = False

    def __post_init__(self) -> None:
        self.calls = [] if self.calls is None else self.calls

    def run(self, input, **kwargs):
        self.calls.append({"input": input, "kwargs": kwargs})
        if self.raise_timeout_once:
            self.raise_timeout_once = False
            raise TimeoutError("budget exceeded")
        return RunOutput(content=self.content)


class FakeAgentFactory:
    def __init__(self, instance: FakeAgentInstance) -> None:
        self.instance = instance
        self.agent_kwargs: list[dict[str, Any]] = []

    def __call__(self, **kwargs):
        self.agent_kwargs.append(kwargs)
        return self.instance


class FakeReminderTool:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, command, guard):
        self.calls.append((command, guard))
        return ToolExecutionResult(ok=True, facts={"reminder_id": "reminder_1"})


def test_invoke_maps_valid_agno_response_to_agent_result():
    fake_agent = FakeAgentInstance(
        content={"type": "reply", "segments": ["hello from model"]}
    )
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    result = agent.invoke(_request(memory_enabled=True))

    assert result.output == {"type": "reply", "segments": ["hello from model"]}
    assert result.timed_out is False
    assert fake_agent.calls[0]["kwargs"]["session_id"] == "conversation_1"
    assert fake_agent.calls[0]["kwargs"]["user_id"] == "account_1"
    assert factory.agent_kwargs[0]["add_memories_to_context"] is True
    assert factory.agent_kwargs[0]["enable_agentic_memory"] is False
    assert factory.agent_kwargs[0]["update_memory_on_run"] is False


def test_malformed_agno_response_is_not_rewritten_to_prose():
    fake_agent = FakeAgentInstance(content="not json")
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(fake_agent),
    )

    result = agent.invoke(_request(memory_enabled=True))

    assert result.output is None
    assert result.timed_out is False


def test_fenced_json_agno_response_maps_to_agent_result():
    fake_agent = FakeAgentInstance(
        content='```json\n{"type":"reply","segments":["ok"]}\n```'
    )
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(fake_agent),
    )

    result = agent.invoke(_request(memory_enabled=True))

    assert result.output == {"type": "reply", "segments": ["ok"]}
    assert result.timed_out is False


def test_inbound_text_is_sent_as_primary_agent_input_with_context_supporting():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(fake_agent),
    )

    agent.invoke(_request(memory_enabled=True, text="提醒我明天早上9点跑步"))

    prompt = fake_agent.calls[0]["input"]
    assert prompt.startswith("User message:\n提醒我明天早上9点跑步")
    assert "Trusted context:" in prompt
    assert '"payload"' not in prompt.split("Trusted context:", 1)[0]


def test_agent_instructions_direct_state_changing_intents_to_tools():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(_request(memory_enabled=True, reminder_tool=FakeReminderTool()))

    instructions = "\n".join(factory.agent_kwargs[0]["instructions"])
    assert (
        "For reminder, scheduling, friendship, settings, or calendar-import requests, call the matching tool"
        in instructions
    )
    assert (
        "Do not answer as if the action happened until the tool result says it happened"
        in instructions
    )


def test_tool_ports_are_exposed_as_agno_tools_and_execute_with_guard():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)
    reminder_tool = FakeReminderTool()
    guard = object()

    agent.invoke(
        _request(memory_enabled=True, reminder_tool=reminder_tool, guard=guard)
    )

    tools = factory.agent_kwargs[0]["tools"]
    assert [tool.__name__ for tool in tools] == ["reminder_tool"]
    assert "detect_and_create" in (tools[0].__doc__ or "")
    assert "owner_account_id" in (tools[0].__doc__ or "")
    assert "raw_text" in (tools[0].__doc__ or "")
    assert tools[0]({"operation": "create", "content": "pay rent"}) == {
        "ok": True,
        "facts": {"reminder_id": "reminder_1"},
        "reason_code": None,
    }
    assert reminder_tool.calls == [
        (
            {
                "operation": "create",
                "content": "pay rent",
                "owner_account_id": "account_1",
                "captured_timezone": "UTC",
                "entry_point": "conversation",
            },
            guard,
        )
    ]


def test_empty_reminder_tool_call_defaults_to_detecting_current_user_message():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)
    reminder_tool = FakeReminderTool()
    guard = object()

    agent.invoke(
        _request(
            memory_enabled=True,
            text="提醒我明天早上9点跑步",
            default_timezone="Asia/Tokyo",
            reminder_tool=reminder_tool,
            guard=guard,
        )
    )

    tools = factory.agent_kwargs[0]["tools"]
    assert tools[0]() == {
        "ok": True,
        "facts": {"reminder_id": "reminder_1"},
        "reason_code": None,
    }
    assert reminder_tool.calls == [
        (
            {
                "operation": "detect_and_create",
                "owner_account_id": "account_1",
                "raw_text": "提醒我明天早上9点跑步",
                "captured_timezone": "Asia/Tokyo",
                "entry_point": "conversation",
            },
            guard,
        )
    ]


def test_reminder_tool_unwraps_agno_kwargs_argument_shape():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)
    reminder_tool = FakeReminderTool()

    agent.invoke(
        _request(
            memory_enabled=True,
            text="提醒我明天早上9点跑步",
            reminder_tool=reminder_tool,
        )
    )

    tools = factory.agent_kwargs[0]["tools"]
    tools[0](
        kwargs={
            "operation": "detect_and_create",
            "owner_account_id": "acct_from_model",
            "raw_text": "提醒我明天早上9点跑步",
            "captured_timezone": "UTC",
            "entry_point": "conversation",
        }
    )

    assert reminder_tool.calls == [
        (
            {
                "operation": "detect_and_create",
                "owner_account_id": "acct_from_model",
                "raw_text": "提醒我明天早上9点跑步",
                "captured_timezone": "UTC",
                "entry_point": "conversation",
            },
            reminder_tool.calls[0][1],
        )
    ]


def test_memory_switch_disables_long_term_agno_memory_context():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(_request(memory_enabled=False))

    assert factory.agent_kwargs[0]["add_memories_to_context"] is False
    assert factory.agent_kwargs[0]["enable_user_memories"] is False


def test_complete_async_reruns_timed_out_request():
    fake_agent = FakeAgentInstance(
        content={"type": "reply", "segments": ["finished"]},
        raise_timeout_once=True,
    )
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(fake_agent),
        task_id_factory=lambda: "task_1",
    )

    pending = agent.invoke(_request(memory_enabled=True))
    completed = agent.complete_async(pending.task_id)

    assert pending.timed_out is True
    assert pending.task_id == "task_1"
    assert completed.output == {"type": "reply", "segments": ["finished"]}
    assert completed.timed_out is False


def _request(
    *,
    memory_enabled: bool,
    text: str = "hello",
    default_timezone: str = "UTC",
    reminder_tool=None,
    guard=None,
) -> AgentRequest:
    tool_ports = AgentToolPorts(reminder_tool=reminder_tool)
    return AgentRequest(
        turn_id="turn_1",
        conversation_id="conversation_1",
        account_id="account_1",
        mode=TurnMode.INTERACTIVE,
        trigger_type="InboundTurn",
        payload={"text": text},
        trusted_facts={
            "assistant_name": "Coke",
            "persona": "concise assistant",
            "memory_enabled": memory_enabled,
            "default_timezone": default_timezone,
        },
        tool_profile=ToolProfile.interactive(tool_ports),
        freshness_guard=guard or object(),
        context={"memory": ["recent"]},
    )
