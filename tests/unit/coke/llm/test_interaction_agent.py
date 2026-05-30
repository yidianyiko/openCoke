from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agno.run.agent import RunOutput

from coke.composition import SocialSchedulingToolAdapter
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


class FakeSocialSchedulingTool:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, command, guard):
        self.calls.append((command, guard))
        return ToolExecutionResult(ok=True, facts={"friend_link_id": "link_1"})


class FakeGuard:
    def guard_state_change(self) -> None:
        return None


class FakeSharedReminderService:
    def __init__(self) -> None:
        self.calls = []

    def create_shared_reminder(self, **kwargs):
        self.calls.append(kwargs)
        return type(
            "SharedReminderResult",
            (),
            {
                "status": "created",
                "shared_reminder": type("SharedReminder", (), {"id": "shared_1"})(),
                "breakdown": {},
                "follow_up_facts": {},
            },
        )()


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


def test_agent_instructions_gate_success_claims_on_tool_ok_true():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(_request(memory_enabled=True, reminder_tool=FakeReminderTool()))

    instructions = "\n".join(factory.agent_kwargs[0]["instructions"])
    assert "ok=true" in instructions
    assert "ok=false" in instructions
    assert "needs_" in instructions
    assert "must not claim the action succeeded" in instructions


def test_instructions_require_final_protocol_reply_after_tool_work():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(_request(memory_enabled=True, social_scheduling_tool=FakeSocialSchedulingTool()))

    instructions = "\n".join(factory.agent_kwargs[0]["instructions"])
    assert "After any tool call" in instructions
    assert '{"type":"reply","segments":["..."]}' in instructions
    assert "never end with empty assistant content" in instructions


def test_protocol_retry_instruction_is_sent_as_retry_context():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(fake_agent),
    )

    agent.invoke(
        _request(
            memory_enabled=True,
            trusted_facts={
                "protocol_retry": {
                    "reason_code": "invalid_output_protocol",
                    "attempt": 2,
                    "guidance": None,
                }
            },
        )
    )

    prompt = fake_agent.calls[0]["input"]
    assert "Protocol retry instruction:" in prompt
    assert "previous assistant answer for this same turn was rejected" in prompt
    assert '{"type":"reply","segments":["..."]}' in prompt
    assert "one to three non-empty string segments" in prompt
    assert prompt.index("Protocol retry instruction:") < prompt.index("Trusted context:")


def test_protocol_retry_instruction_includes_specific_violation_guidance():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(fake_agent),
    )

    agent.invoke(
        _request(
            memory_enabled=True,
            trusted_facts={
                "protocol_retry": {
                    "reason_code": "invalid_output_protocol",
                    "attempt": 2,
                    "guidance": "reply_segments_must_contain_1_to_3_non_empty_strings",
                }
            },
        )
    )

    prompt = fake_agent.calls[0]["input"]
    assert (
        "Specific protocol violation: "
        "reply_segments_must_contain_1_to_3_non_empty_strings."
    ) in prompt


def test_agent_instructions_name_real_social_scheduling_operations():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(
        _request(
            memory_enabled=True,
            social_scheduling_tool=FakeSocialSchedulingTool(),
        )
    )

    instructions = "\n".join(factory.agent_kwargs[0]["instructions"])
    assert "operation=get_friend_link" in instructions
    assert "operation=list_friends" in instructions
    assert "operation=remove_friend" in instructions
    assert "operation=query_availability" in instructions
    assert "operation=cancel_shared_reminder" in instructions
    assert "owner_account_id from trusted_facts.account_id" in instructions
    assert "friend name" in instructions
    assert "exactly one active friend" in instructions
    assert "establish_friendship_from_token" in instructions
    assert "accept_friend_request" not in instructions
    assert "create_friend_request" not in instructions


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


def test_social_scheduling_tool_doc_describes_friend_link_and_code_operations():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(
        _request(
            memory_enabled=True,
            social_scheduling_tool=FakeSocialSchedulingTool(),
        )
    )

    tools = factory.agent_kwargs[0]["tools"]
    assert [tool.__name__ for tool in tools] == ["social_scheduling_tool"]
    doc = tools[0].__doc__ or ""
    assert "get_friend_link" in doc
    assert "reset_friend_link" in doc
    assert "disable_friend_link" in doc
    assert "establish_friendship_from_token" in doc
    assert "trusted_facts.account_id" in doc


def test_social_scheduling_tool_doc_describes_shared_reminder_creation():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(
        _request(
            memory_enabled=True,
            social_scheduling_tool=FakeSocialSchedulingTool(),
        )
    )

    doc = factory.agent_kwargs[0]["tools"][0].__doc__ or ""
    assert "create_shared_reminder" in doc
    assert "receiver_account_ids" in doc
    assert "local_trigger_at" in doc
    assert "context" in doc


def test_social_scheduling_tool_doc_describes_friend_list_availability_and_cancel():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(
        _request(
            memory_enabled=True,
            social_scheduling_tool=FakeSocialSchedulingTool(),
        )
    )

    doc = factory.agent_kwargs[0]["tools"][0].__doc__ or ""
    assert "list_friends" in doc
    assert "remove_friend" in doc
    assert "query_availability" in doc
    assert "cancel_shared_reminder" in doc
    assert "friend_account_ids" in doc
    assert "shared_reminder_id" in doc


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


def test_tool_callable_accepts_command_as_json_string_envelope():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)
    reminder_tool = FakeReminderTool()

    agent.invoke(_request(memory_enabled=True, reminder_tool=reminder_tool))

    tool = factory.agent_kwargs[0]["tools"][0]
    result = tool(
        '{"operation":"create","owner_account_id":"owner_2","content":"pay rent"}'
    )

    assert result == {
        "ok": True,
        "facts": {"reminder_id": "reminder_1"},
        "reason_code": None,
    }
    assert reminder_tool.calls == [
        (
            {
                "operation": "create",
                "owner_account_id": "owner_2",
                "content": "pay rent",
                "captured_timezone": "UTC",
                "entry_point": "conversation",
            },
            reminder_tool.calls[0][1],
        )
    ]


def test_reminder_tool_maps_agno_command_op_complete_without_defaulting_to_create():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)
    reminder_tool = FakeReminderTool()

    agent.invoke(_request(memory_enabled=True, reminder_tool=reminder_tool))

    tool = factory.agent_kwargs[0]["tools"][0]
    result = tool(
        kwargs={
            "command": {
                "op": "complete",
                "reminder_id": "reminder_1",
            },
            "owner_account_id": "owner_1",
            "captured_timezone": "Asia/Shanghai",
        }
    )

    assert result["ok"] is True
    assert reminder_tool.calls == [
        (
            {
                "operation": "complete_reminder",
                "reminder_id": "reminder_1",
                "owner_account_id": "owner_1",
                "captured_timezone": "Asia/Shanghai",
                "entry_point": "conversation",
            },
            reminder_tool.calls[0][1],
        )
    ]


def test_reminder_tool_maps_agno_modify_time_op_to_reschedule_operation():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)
    reminder_tool = FakeReminderTool()

    agent.invoke(_request(memory_enabled=True, reminder_tool=reminder_tool))

    tool = factory.agent_kwargs[0]["tools"][0]
    tool(
        kwargs={
            "command": {
                "op": "modify_time",
                "reminder_id": "reminder_1",
                "new_trigger_time": "2029-01-21T11:00:00+08:00",
            },
            "owner_account_id": "owner_1",
            "captured_timezone": "Asia/Shanghai",
        }
    )

    assert reminder_tool.calls == [
        (
            {
                "operation": "reschedule_reminder",
                "reminder_id": "reminder_1",
                "trigger_time": "2029-01-21T11:00:00+08:00",
                "owner_account_id": "owner_1",
                "captured_timezone": "Asia/Shanghai",
                "entry_point": "conversation",
            },
            reminder_tool.calls[0][1],
        )
    ]


def test_tool_callable_coerces_json_string_list_fields_once_for_all_tools():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    service = FakeSharedReminderService()
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(
        _request(
            memory_enabled=True,
            social_scheduling_tool=SocialSchedulingToolAdapter(service),
            guard=FakeGuard(),
        )
    )

    tool = factory.agent_kwargs[0]["tools"][0]
    result = tool(
        command={
            "operation": "create_shared_reminder",
            "creator_account_id": "creator_1",
            "receiver_account_ids": '["friend_1", "friend_2"]',
            "title": "Team sync",
            "local_trigger_at": "2026-05-31T08:49:17",
            "captured_timezone": "UTC",
            "duration_minutes": 15,
            "context": {"source": "unit"},
        }
    )

    assert result["ok"] is True
    assert service.calls[0]["receiver_account_ids"] == ["friend_1", "friend_2"]


def test_social_scheduling_tool_normalizes_live_agno_kwargs_string_shape():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    service = FakeSharedReminderService()
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)
    guard = FakeGuard()

    agent.invoke(
        _request(
            memory_enabled=True,
            social_scheduling_tool=SocialSchedulingToolAdapter(service),
            guard=guard,
        )
    )

    tool = factory.agent_kwargs[0]["tools"][0]
    result = tool(
        kwargs={
            "operation": "create_shared_reminder",
            "creator_account_id": "94a66a76ad4247ff87400bda8ec5012c",
            "receiver_account_ids": ["4b9f7196-ac61-4bca-96e5-c7a84c00e671"],
            "title": "RR8 agent shared phase456_20260530T0845Z",
            "local_trigger_at": "2026-05-31T08:49:17",
            "captured_timezone": "UTC",
            "duration_minutes": 15,
            "context": "gcp clean live phase 5 verification",
        }
    )

    assert result == {
        "ok": True,
        "facts": {
            "status": "created",
            "shared_reminder_id": "shared_1",
            "breakdown": {},
            "follow_up_facts": {},
        },
        "reason_code": None,
    }
    assert service.calls == [
        {
            "creator_account_id": "94a66a76ad4247ff87400bda8ec5012c",
            "receiver_account_ids": ["4b9f7196-ac61-4bca-96e5-c7a84c00e671"],
            "title": "RR8 agent shared phase456_20260530T0845Z",
            "local_trigger_at": datetime.fromisoformat("2026-05-31T08:49:17"),
            "captured_timezone": "UTC",
            "duration_minutes": 15,
            "context": {"text": "gcp clean live phase 5 verification"},
        }
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
    social_scheduling_tool=None,
    guard=None,
    trusted_facts: dict[str, Any] | None = None,
) -> AgentRequest:
    tool_ports = AgentToolPorts(
        reminder_tool=reminder_tool,
        social_scheduling_tool=social_scheduling_tool,
    )
    facts = {
        "assistant_name": "Coke",
        "persona": "concise assistant",
        "memory_enabled": memory_enabled,
        "default_timezone": default_timezone,
    }
    if trusted_facts is not None:
        facts.update(trusted_facts)
    return AgentRequest(
        turn_id="turn_1",
        conversation_id="conversation_1",
        account_id="account_1",
        mode=TurnMode.INTERACTIVE,
        trigger_type="InboundTurn",
        payload={"text": text},
        trusted_facts=facts,
        tool_profile=ToolProfile.interactive(tool_ports),
        freshness_guard=guard or object(),
        context={"memory": ["recent"]},
    )
