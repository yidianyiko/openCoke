from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest
from agno.run.agent import RunOutput

import coke.llm.agno_interaction_agent as agno_agent_module
from coke.composition import ReminderToolAdapter, SocialSchedulingToolAdapter
from coke.domains.reminder.repository import InMemoryReminderRepository
from coke.domains.reminder.service import ReminderService
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


class FakeSettingsTool:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, command, guard):
        self.calls.append((command, guard))
        return ToolExecutionResult(ok=True, facts={"default_timezone": "Asia/Tokyo"})


class FakeGuard:
    def guard_state_change(self) -> None:
        return None


class FakeSharedReminderService:
    def __init__(self) -> None:
        self.calls = []

    def create_shared_reminder(self, **kwargs):
        kwargs.pop("commit_guard", None)
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

    def detect_and_create_shared_reminder(self, **kwargs):
        kwargs.pop("commit_guard", None)
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


def test_inbound_text_is_sent_as_current_input_block_with_context_supporting():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(fake_agent),
    )

    agent.invoke(_request(memory_enabled=True, text="提醒我明天早上9点跑步"))

    prompt = fake_agent.calls[0]["input"]
    assert prompt.startswith('<trusted_block name="turn_source">')
    assert '<trusted_block name="current_input">' in prompt
    assert "提醒我明天早上9点跑步" in _block_text(prompt, "current_input")
    assert "This is a real message from the user" in _block_text(prompt, "turn_source")
    assert '"payload"' not in _block_text(prompt, "current_input")


def test_prompt_builder_uses_ordered_conditional_blocks_and_output_contract_last():
    request = _request(
        memory_enabled=True,
        text="提醒我明天早上9点跑步",
        trusted_facts={
            "account_id": "account_1",
            "assistant_name": "可乐",
            "user_address_name": "小鱼",
            "speaking_style": "直接一点",
            "semantic_decision": {
                "reply_necessity": "reply_needed",
                "intent_family": "reminder_op",
                "intent_action": "create_reminder",
                "ambiguity": "clear",
                "required_clarification": "none",
                "language_hint": "zh",
            },
            "domain_result": {
                "domain": "reminder",
                "intent": "create reminder",
                "action": "create_reminder",
                "effect": "created",
                "intent_fulfilled": True,
                "visible_summary": (
                    "Created reminder 跑步 at 2026-06-01T09:00:00+09:00."
                ),
                "reply_contract": "confirm_success",
                "privacy_notes": [],
            },
        },
        context={
            "focus_subject": {"subject_type": "reminder", "object_ids": ["r1"]},
            "memory_context": {
                "short_term": ["用户刚刚问过提醒。"],
                "long_term": ["用户喜欢简短回复。"],
            },
            "recent_conversation": ["user: 提醒我明天早上9点跑步"],
        },
    )

    blocks = agno_agent_module.build_prompt_blocks(request)

    assert [block.name for block in blocks] == [
        "turn_source",
        "current_input",
        "identity",
        "persona",
        "environment",
        "semantic_decision",
        "focus",
        "domain_result",
        "memory",
        "conversation",
        "voice_policy",
        "output_contract",
    ]
    rendered = agno_agent_module.render_prompt_blocks(blocks)
    assert rendered.rfind('name="output_contract"') > rendered.rfind(
        'name="voice_policy"'
    )
    assert "1-3" in _block_text(rendered, "output_contract")
    assert '{"type":"reply","segments":["text"]}' in _block_text(
        rendered, "output_contract"
    )


def test_prompt_builder_omits_empty_optional_blocks():
    blocks = agno_agent_module.build_prompt_blocks(
        _request(
            memory_enabled=True,
            trusted_facts={"persona": "", "speaking_style": "", "extra_rules": ""},
            context={},
        )
    )

    names = [block.name for block in blocks]
    assert "focus" not in names
    assert "domain_result" not in names
    assert "memory" not in names
    assert "conversation" not in names
    assert names[-1] == "output_contract"


def test_prompt_builder_renders_required_clarification_instruction():
    request = _request(
        memory_enabled=True,
        trusted_facts={
            "semantic_decision": {
                "reply_necessity": "reply_needed",
                "intent_family": "reminder_op",
                "intent_action": "create_reminder",
                "ambiguity": "missing_time",
                "required_clarification": "ask_trigger_time",
                "language_hint": "zh",
            },
            "required_clarification": {
                "signal": "ask_trigger_time",
                "ambiguity": "missing_time",
                "instruction": (
                    "Ask exactly this clarification before any domain action."
                ),
            },
        },
    )

    rendered = agno_agent_module.render_prompt_blocks(
        agno_agent_module.build_prompt_blocks(request)
    )

    semantic_block = _block_text(rendered, "semantic_decision")
    assert "ask_trigger_time" in semantic_block
    assert "Ask exactly this clarification before any domain action." in semantic_block


@pytest.mark.parametrize(
    ("trigger_type", "payload", "expected"),
    [
        (
            "ReminderFireTurn",
            {"title": "提交周报", "fire_ids": ["fire_1"]},
            "Do not answer the reminder title as if the user said it.",
        ),
        (
            "ProactiveFireTurn",
            {"planned_action": "问问用户复习进度"},
            "Do not answer it as a user question.",
        ),
    ],
)
def test_prompt_builder_frames_system_sources_as_not_user_speech(
    trigger_type,
    payload,
    expected,
):
    request = _render_request(
        trigger_type=trigger_type,
        payload=payload,
    )

    rendered = agno_agent_module.render_prompt_blocks(
        agno_agent_module.build_prompt_blocks(request)
    )

    turn_source = _block_text(rendered, "turn_source")
    current_input = _block_text(rendered, "current_input")
    assert "user_spoke_this_turn: false" in turn_source
    assert expected in turn_source
    assert "This is a real message from the user" not in turn_source
    assert "提交周报" in current_input or "复习进度" in current_input


def test_voice_policy_contains_coke_texture_and_challenge_handling():
    rendered = agno_agent_module.render_prompt_blocks(
        agno_agent_module.build_prompt_blocks(_request(memory_enabled=True))
    )

    voice = _block_text(rendered, "voice_policy")
    assert "WeChat friend or supervisor" in voice
    assert "1-3 short segments" in voice
    assert "match the user's language" in voice
    assert "generic closers" in voice
    assert "还有什么可以帮您吗" in voice
    assert "Do not expose internal tools, agents, logs, or architecture" in voice
    assert "do not invent facts or times" in voice
    assert "When the user challenges" in voice
    assert "我没设过这个" in voice
    assert "Do not hard-refuse coding or deep-research chat" in voice


def test_domain_result_block_is_trusted_and_gates_success_claims():
    request = _request(
        memory_enabled=True,
        text="提醒我明天9点跑步",
        trusted_facts={
            "domain_result": {
                "domain": "reminder",
                "intent": "create reminder",
                "action": "create_reminder",
                "effect": "created",
                "intent_fulfilled": True,
                "visible_summary": "Created reminder 跑步 at 2026-06-01T09:00:00+09:00.",
                "reply_contract": "confirm_success",
                "privacy_notes": [],
            }
        },
    )

    rendered = agno_agent_module.render_prompt_blocks(
        agno_agent_module.build_prompt_blocks(request)
    )

    domain_result = _block_text(rendered, "domain_result")
    assert "trusted domain execution result" in domain_result
    assert "Created reminder 跑步" in domain_result
    assert "Do not infer success from the transcript" in domain_result
    assert "confirm_success" in domain_result


def test_requested_action_without_domain_result_must_not_be_claimed_successful():
    request = _request(
        memory_enabled=True,
        text="提醒我明天9点跑步",
        trusted_facts={
            "semantic_decision": {
                "reply_necessity": "reply_needed",
                "intent_family": "reminder_op",
                "intent_action": "create_reminder",
                "ambiguity": "clear",
                "required_clarification": "none",
                "language_hint": "zh",
            }
        },
    )

    rendered = agno_agent_module.render_prompt_blocks(
        agno_agent_module.build_prompt_blocks(request)
    )

    output_contract = _block_text(rendered, "output_contract")
    assert "A requested action without a trusted domain_result is not success" in (
        output_contract
    )
    assert "Do not claim it succeeded" in output_contract


def test_output_contract_forbids_duplicate_proactive_after_timed_reminder():
    request = _request(
        memory_enabled=True,
        trusted_facts={
            "domain_result": {
                "domain": "reminder",
                "intent": "create reminder",
                "action": "create_reminder",
                "effect": "created_timed_reminder",
                "intent_fulfilled": True,
                "visible_summary": "Created timed reminder for 2026-06-01T09:00:00+09:00.",
                "reply_contract": "confirm_success",
                "privacy_notes": [],
            }
        },
    )

    rendered = agno_agent_module.render_prompt_blocks(
        agno_agent_module.build_prompt_blocks(request)
    )

    assert "Do not create or imply a duplicate proactive follow-up" in _block_text(
        rendered, "output_contract"
    )


def test_output_contract_keeps_product_notification_followups_visible():
    request = _request(memory_enabled=True, text="好的")

    rendered = agno_agent_module.render_prompt_blocks(
        agno_agent_module.build_prompt_blocks(request)
    )

    output_contract = _block_text(rendered, "output_contract")
    assert "Do not use no-reply for post-notification acknowledgements" in (
        output_contract
    )
    assert (
        "meaningless content, natural conversation endings, or explicit no-disturb"
        in (output_contract)
    )


def test_domain_failure_or_missing_info_prompt_forbids_success_claim():
    request = _request(
        memory_enabled=True,
        trusted_facts={
            "domain_result": {
                "domain": "reminder",
                "intent": "create reminder",
                "action": "create_reminder",
                "effect": "needs_time",
                "intent_fulfilled": False,
                "visible_summary": "Need a trigger time before creating the reminder.",
                "reply_contract": "ask_missing_info",
                "privacy_notes": [],
            }
        },
    )

    rendered = agno_agent_module.render_prompt_blocks(
        agno_agent_module.build_prompt_blocks(request)
    )

    domain_result = _block_text(rendered, "domain_result")
    assert "intent_fulfilled" in domain_result
    assert "false" in domain_result
    assert "Do not claim the action succeeded" in domain_result
    assert "ask_missing_info" in domain_result


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


def test_agent_instructions_route_conversational_settings_to_settings_tool():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(_request(memory_enabled=True, settings_tool=FakeSettingsTool()))

    instructions = "\n".join(factory.agent_kwargs[0]["instructions"])
    assert "For global timezone switches" in instructions
    assert "operation=set_timezone" in instructions
    assert "operation=update_settings" in instructions
    assert "operation=update_profile" in instructions
    assert "operation=reset_agent_settings" in instructions
    assert "memory_enabled=false" in instructions
    assert "proactive_enabled=false" in instructions


def test_agent_instructions_decline_unsupported_external_booking_without_reminder():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(_request(memory_enabled=True, reminder_tool=FakeReminderTool()))

    instructions = "\n".join(factory.agent_kwargs[0]["instructions"])
    assert "Unsupported external booking" in instructions
    assert (
        "call reminder_tool only when the user explicitly asks for a reminder"
        in instructions
    )
    assert "never claim the class or appointment is booked" in instructions


def test_instructions_require_final_protocol_reply_after_tool_work():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(
        _request(memory_enabled=True, social_scheduling_tool=FakeSocialSchedulingTool())
    )

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
    output_contract = _block_text(prompt, "output_contract")
    assert "Protocol retry instruction:" in output_contract
    assert "previous assistant answer for this same turn was rejected" in prompt
    assert '{"type":"reply","segments":["..."]}' in prompt
    assert "one to three non-empty string segments" in prompt
    assert prompt.rstrip().endswith("</trusted_block>")
    assert prompt.rfind('name="output_contract"') > prompt.rfind('name="voice_policy"')


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
    ) in _block_text(prompt, "output_contract")


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
    assert "operation=detect_and_create_shared_reminder" in instructions
    assert "operation=cancel_shared_reminder" in instructions
    assert "owner_account_id from trusted_facts.account_id" in instructions
    assert "raw_text set to the exact User message" in instructions
    assert "Do not compute local_trigger_at yourself" in instructions
    assert "friend name" in instructions
    assert "exactly one active friend" in instructions
    assert "establish_friendship_from_token" in instructions
    assert "accept_friend_request" not in instructions
    assert "create_friend_request" not in instructions


def test_shared_reminder_success_prompt_forbids_confirmation_flow_language():
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
    assert "immediately active" in instructions
    assert "waiting for confirmation" in instructions
    assert "accept/reject" in instructions
    assert "pending confirmation" in instructions


def test_notification_render_prompt_requires_structured_fact_grounding():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(_render_request())

    instructions = "\n".join(factory.agent_kwargs[0]["instructions"])
    assert "Render mode" in instructions
    assert "notification facts" in instructions
    assert "generic placeholder" in instructions
    assert "creator, title, time, timezone, duration, and status" in instructions


def test_render_notification_context_exposes_structured_facts_to_agent():
    fake_agent = FakeAgentInstance(
        content={
            "type": "reply",
            "segments": [
                "Alice shared Lunch for 2026-06-01T12:00:00 Asia/Tokyo, 45 minutes."
            ],
        }
    )
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=factory,
    )

    result = agent.invoke(
        _render_request(
            payload={
                "notification_fact": {
                    "id": "notification_fact_1",
                    "type": "shared_reminder_created",
                    "facts": {
                        "actor_display_name": "Alice",
                        "title": "Lunch",
                        "time": "2026-06-01T12:00:00",
                        "timezone": "Asia/Tokyo",
                        "duration_minutes": 45,
                        "status": "created",
                    },
                    "facts_hash": "hash_1",
                }
            }
        )
    )

    prompt = fake_agent.calls[0]["input"]
    assert "NotificationTurn" in _block_text(prompt, "turn_source")
    assert "Alice" in _block_text(prompt, "domain_result")
    assert "Lunch" in _block_text(prompt, "domain_result")
    assert "2026-06-01T12:00:00" in _block_text(prompt, "domain_result")
    assert "Asia/Tokyo" in _block_text(prompt, "domain_result")
    assert "45" in _block_text(prompt, "domain_result")
    output_contract = _block_text(prompt, "output_contract")
    assert "NotificationTurn must render a visible reply" in output_contract
    assert "Valid no-reply" not in output_contract
    system_message = factory.agent_kwargs[0]["system_message"]
    assert '{"type":"no_reply"' not in system_message
    reply_text = "".join(result.output["segments"])
    assert "Lunch" in reply_text
    assert "2026-06-01T12:00:00" in reply_text
    assert "45" in reply_text
    assert "Alice" in reply_text
    assert "go check it out" not in reply_text.lower()
    assert "快去看看" not in reply_text


def test_render_context_exposes_undelivered_notification_fact_list_to_agent():
    fake_agent = FakeAgentInstance(
        content={
            "type": "reply",
            "segments": ["Previously undelivered: Alice cancelled Lunch."],
        }
    )
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(fake_agent),
    )

    agent.invoke(
        _render_request(
            trigger_type="UndeliveredResendTurn",
            payload={
                "framing": "previously_undelivered",
                "notification_facts": [
                    {
                        "id": "notification_fact_1",
                        "type": "shared_reminder_cancelled",
                        "facts": {
                            "actor_display_name": "Alice",
                            "title": "Lunch",
                            "status": "cancelled",
                        },
                        "facts_hash": "hash_1",
                    }
                ],
            },
        )
    )

    render_context = fake_agent.calls[0]["input"].split("Trusted context:", 1)[0]
    assert "UndeliveredResendTurn" in render_context
    assert "previously_undelivered" in render_context
    assert "shared_reminder_cancelled" in render_context
    assert "Lunch" in render_context


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
    assert "list_reminders" in (tools[0].__doc__ or "")
    assert "count-only answers are incomplete" in (tools[0].__doc__ or "")
    assert "owner_account_id" in (tools[0].__doc__ or "")
    assert "raw_text" in (tools[0].__doc__ or "")
    result = tools[0]({"operation": "create", "content": "pay rent"})
    assert _base_tool_result(result) == {
        "ok": True,
        "facts": {"reminder_id": "reminder_1"},
        "reason_code": None,
    }
    assert result["domain_result"]["domain"] == "reminder"
    assert result["domain_result"]["action"] == "create"
    assert result["domain_result"]["intent_fulfilled"] is True
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


def test_reminder_list_instructions_require_full_list_not_count_only():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(_request(memory_enabled=True, reminder_tool=FakeReminderTool()))

    instructions = "\n".join(factory.agent_kwargs[0]["instructions"])
    assert "list every returned active reminder" in instructions
    assert "Do not answer with only the count" in instructions
    assert "display_time_label" in instructions
    assert "do not expose raw UTC next_fire_at" in instructions


def test_reminder_list_tool_result_overrides_count_only_final_reply():
    class CountOnlyAgentInstance:
        def __init__(self, tools):
            self.tools = tools

        def run(self, input, **kwargs):
            self.tools[0]({"operation": "list_reminders"})
            return RunOutput(
                content={"type": "reply", "segments": ["你现在一共有 2 个提醒。"]}
            )

    class ReminderListTool:
        def execute(self, command, guard):
            return ToolExecutionResult(
                ok=True,
                facts={
                    "count": 2,
                    "reminders": [
                        {
                            "content": "pay rent",
                            "next_fire_at": "2026-05-30T12:00:00+00:00",
                            "display_time_label": "2026-05-30 20:00 Asia/Shanghai",
                        },
                        {"content": "buy milk", "next_fire_at": None},
                    ],
                    "display_lines": [
                        "1. pay rent (2026-05-30 20:00 Asia/Shanghai)",
                        "2. buy milk (unscheduled)",
                    ],
                },
                domain_result=agno_agent_module.DomainExecutionResult(
                    domain="reminder",
                    intent="list reminders",
                    action="list_reminders",
                    effect="listed",
                    intent_fulfilled=True,
                    visible_summary=(
                        "Active reminder count: 2.\n"
                        "1. pay rent (2026-05-30 20:00 Asia/Shanghai)\n"
                        "2. buy milk (unscheduled)"
                    ),
                    reply_contract="render_reminder_list",
                    privacy_notes=(),
                ),
            )

    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=lambda **kwargs: CountOnlyAgentInstance(kwargs["tools"]),
    )

    result = agent.invoke(
        _request(
            memory_enabled=True,
            text="现在我一共有几个提醒？",
            reminder_tool=ReminderListTool(),
        )
    )

    reply = result.output["segments"][0]
    assert reply.startswith("你现在一共有 2 个提醒：")
    assert "1. pay rent（2026-05-30 20:00 Asia/Shanghai）" in reply
    assert "2. buy milk（未设定时间）" in reply


def test_reminder_list_tool_result_overrides_raw_utc_final_reply():
    class UtcTimeAgentInstance:
        def __init__(self, tools):
            self.tools = tools

        def run(self, input, **kwargs):
            self.tools[0]({"operation": "list_reminders"})
            return RunOutput(
                content={
                    "type": "reply",
                    "segments": [
                        "你现在一共有 1 个提醒：\n"
                        "1. pay rent（2026-05-30T12:00:00+00:00）"
                    ],
                }
            )

    class ReminderListTool:
        def execute(self, command, guard):
            return ToolExecutionResult(
                ok=True,
                facts={
                    "count": 1,
                    "reminders": [
                        {
                            "content": "pay rent",
                            "next_fire_at": "2026-05-30T12:00:00+00:00",
                            "display_time_label": "2026-05-30 20:00 Asia/Shanghai",
                        },
                    ],
                    "display_lines": [
                        "1. pay rent (2026-05-30 20:00 Asia/Shanghai)",
                    ],
                },
                domain_result=agno_agent_module.DomainExecutionResult(
                    domain="reminder",
                    intent="list reminders",
                    action="list_reminders",
                    effect="listed",
                    intent_fulfilled=True,
                    visible_summary=(
                        "Active reminder count: 1.\n"
                        "1. pay rent (2026-05-30 20:00 Asia/Shanghai)"
                    ),
                    reply_contract="render_reminder_list",
                    privacy_notes=(),
                ),
            )

    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=lambda **kwargs: UtcTimeAgentInstance(kwargs["tools"]),
    )

    result = agent.invoke(
        _request(
            memory_enabled=True,
            text="现在我一共有几个提醒？",
            reminder_tool=ReminderListTool(),
        )
    )

    reply = result.output["segments"][0]
    assert "2026-05-30 20:00 Asia/Shanghai" in reply
    assert "2026-05-30T12:00:00+00:00" not in reply


def test_tool_callable_exposes_domain_execution_result_when_adapter_provides_it():
    class DomainResultTool:
        def execute(self, command, guard):
            return ToolExecutionResult(
                ok=True,
                facts={"reminder_id": "reminder_1"},
                domain_result=agno_agent_module.DomainExecutionResult(
                    domain="reminder",
                    intent="create reminder",
                    action="create_reminder",
                    effect="created",
                    intent_fulfilled=True,
                    visible_summary="Created reminder pay rent.",
                    reply_contract="confirm_success",
                    privacy_notes=(),
                ),
            )

    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    agent.invoke(_request(memory_enabled=True, reminder_tool=DomainResultTool()))

    tool = factory.agent_kwargs[0]["tools"][0]
    result = tool({"operation": "create", "content": "pay rent"})

    assert result["ok"] is True
    assert result["domain_result"] == {
        "domain": "reminder",
        "intent": "create reminder",
        "action": "create_reminder",
        "effect": "created",
        "intent_fulfilled": True,
        "visible_summary": "Created reminder pay rent.",
        "reply_contract": "confirm_success",
        "privacy_notes": [],
    }


def test_settings_tool_doc_and_defaults_use_trusted_account():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)
    settings_tool = FakeSettingsTool()
    guard = object()

    agent.invoke(
        _request(memory_enabled=True, settings_tool=settings_tool, guard=guard)
    )

    tools = factory.agent_kwargs[0]["tools"]
    assert [tool.__name__ for tool in tools] == ["settings_tool"]
    doc = tools[0].__doc__ or ""
    assert "set_timezone" in doc
    assert "update_settings" in doc
    assert "update_profile" in doc
    assert "reset_agent_settings" in doc
    assert "proactive_enabled" in doc
    assert "memory_enabled" in doc
    assert "trusted_facts.account_id" in doc
    result = tools[0]({"operation": "set_timezone", "default_timezone": "Asia/Tokyo"})
    assert _base_tool_result(result) == {
        "ok": True,
        "facts": {"default_timezone": "Asia/Tokyo"},
        "reason_code": None,
    }
    assert result["domain_result"]["domain"] == "settings"
    assert result["domain_result"]["action"] == "set_timezone"
    assert result["domain_result"]["intent_fulfilled"] is True
    assert settings_tool.calls == [
        (
            {
                "operation": "set_timezone",
                "default_timezone": "Asia/Tokyo",
                "account_id": "account_1",
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
    assert "detect_and_create_shared_reminder" in doc
    assert "receiver_account_ids" in doc
    assert "raw_text" in doc
    assert "Do not compute local_trigger_at yourself" in doc
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
    result = tools[0]()
    assert _base_tool_result(result) == {
        "ok": True,
        "facts": {"reminder_id": "reminder_1"},
        "reason_code": None,
    }
    assert result["domain_result"]["action"] == "detect_and_create"
    assert result["domain_result"]["intent_fulfilled"] is True
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


def test_shared_reminder_detect_tool_defaults_to_current_user_message_and_timezone():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)
    social_tool = FakeSocialSchedulingTool()
    guard = object()

    agent.invoke(
        _request(
            memory_enabled=True,
            text="帮我和 lizihao 约一个今天晚上10:30的会议",
            default_timezone="Asia/Shanghai",
            social_scheduling_tool=social_tool,
            guard=guard,
        )
    )

    tools = factory.agent_kwargs[0]["tools"]
    result = tools[0](
        operation="detect_and_create_shared_reminder",
        receiver_account_ids=["friend_1"],
    )

    assert result["ok"] is True
    assert result["domain_result"]["action"] == "detect_and_create_shared_reminder"
    assert social_tool.calls == [
        (
            {
                "operation": "detect_and_create_shared_reminder",
                "receiver_account_ids": ["friend_1"],
                "raw_text": "帮我和 lizihao 约一个今天晚上10:30的会议",
                "creator_account_id": "account_1",
                "captured_timezone": "Asia/Shanghai",
                "duration_minutes": 15,
                "context": {
                    "source": "conversation",
                    "text": "帮我和 lizihao 约一个今天晚上10:30的会议",
                },
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

    assert _base_tool_result(result) == {
        "ok": True,
        "facts": {"reminder_id": "reminder_1"},
        "reason_code": None,
    }
    assert result["domain_result"]["domain"] == "reminder"
    assert result["domain_result"]["action"] == "create"
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


def test_reminder_tool_maps_agno_update_duration_op_to_update_operation():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)
    reminder_tool = FakeReminderTool()

    agent.invoke(_request(memory_enabled=True, reminder_tool=reminder_tool))

    tool = factory.agent_kwargs[0]["tools"][0]
    tool(
        kwargs={
            "command": {
                "op": "update",
                "reminder_id": "reminder_1",
                "duration_minutes": 60,
            },
            "owner_account_id": "owner_1",
            "captured_timezone": "Asia/Shanghai",
        }
    )

    assert reminder_tool.calls == [
        (
            {
                "operation": "update_reminder",
                "reminder_id": "reminder_1",
                "duration_minutes": 60,
                "owner_account_id": "owner_1",
                "captured_timezone": "Asia/Shanghai",
                "entry_point": "conversation",
            },
            reminder_tool.calls[0][1],
        )
    ]


def test_reminder_tool_defaults_update_reminder_id_from_single_focus_subject():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)
    reminder_tool = FakeReminderTool()

    agent.invoke(
        _request(
            memory_enabled=True,
            reminder_tool=reminder_tool,
            context={
                "focus_subject": {
                    "subject_type": "reminder",
                    "object_ids": ["focused_reminder_1"],
                }
            },
        )
    )

    tool = factory.agent_kwargs[0]["tools"][0]
    tool(
        kwargs={
            "command": {
                "op": "update",
                "duration_minutes": 60,
            },
            "owner_account_id": "owner_1",
            "captured_timezone": "Asia/Shanghai",
        }
    )

    assert reminder_tool.calls == [
        (
            {
                "operation": "update_reminder",
                "reminder_id": "focused_reminder_1",
                "duration_minutes": 60,
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

    assert _base_tool_result(result) == {
        "ok": True,
        "facts": {
            "status": "created",
            "shared_reminder_id": "shared_1",
            "breakdown": {},
            "follow_up_facts": {},
        },
        "reason_code": None,
    }
    assert result["domain_result"]["domain"] == "social_scheduling"
    assert result["domain_result"]["action"] == "create_shared_reminder"
    assert result["domain_result"]["intent_fulfilled"] is True
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


def test_coach_booking_refusal_path_does_not_create_reminder_or_claim_booking():
    fake_agent = FakeAgentInstance(
        content={
            "type": "reply",
            "segments": [
                "我不能直接帮你在外部 App 里约课。真正约课需要你自己在 App 里点；如果需要，我可以帮你设提醒。"
            ],
        }
    )
    factory = FakeAgentFactory(fake_agent)
    reminder_repo = InMemoryReminderRepository()
    reminder_tool = ReminderToolAdapter(
        ReminderService(
            reminder_repo,
            now=lambda: datetime(2026, 5, 31, 12, 0),
            id_factory=lambda prefix: f"{prefix}_1",
        )
    )
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    result = agent.invoke(
        _request(
            memory_enabled=True,
            text="帮我约彭教练这周五下午4点的私教课",
            reminder_tool=reminder_tool,
        )
    )

    reply_text = "".join(result.output["segments"])
    assert reminder_repo.list_active_reminders("account_1") == []
    assert "已预约" not in reply_text
    assert "预约好了" not in reply_text
    assert "已经帮你约" not in reply_text
    assert "booked" not in reply_text.lower()


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
    settings_tool=None,
    guard=None,
    trusted_facts: dict[str, Any] | None = None,
    context: Any | None = None,
) -> AgentRequest:
    tool_kwargs = {
        "reminder_tool": reminder_tool,
        "social_scheduling_tool": social_scheduling_tool,
    }
    if settings_tool is not None:
        tool_kwargs["settings_tool"] = settings_tool
    tool_ports = AgentToolPorts(**tool_kwargs)
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
        context={"memory": ["recent"]} if context is None else context,
    )


def _render_request(
    *,
    trigger_type: str = "NotificationTurn",
    payload: dict[str, Any] | None = None,
    trusted_facts: dict[str, Any] | None = None,
) -> AgentRequest:
    facts = {
        "assistant_name": "Coke",
        "persona": "concise assistant",
        "memory_enabled": True,
        "default_timezone": "UTC",
        "account_id": "account_1",
    }
    if trusted_facts is not None:
        facts.update(trusted_facts)
    return AgentRequest(
        turn_id="turn_1",
        conversation_id="conversation_1",
        account_id="account_1",
        mode=TurnMode.RENDER,
        trigger_type=trigger_type,
        payload=payload
        or {
            "notification_fact": {
                "id": "notification_fact_1",
                "type": "friendship_created",
                "facts": {
                    "actor_display_name": "Alice",
                    "object_type": "friendship",
                    "status": "created",
                },
                "facts_hash": "hash_1",
            }
        },
        trusted_facts=facts,
        tool_profile=ToolProfile.render(),
        freshness_guard=object(),
        context={},
    )


def _block_text(prompt: str, name: str) -> str:
    start_marker = f'<trusted_block name="{name}">'
    end_marker = "</trusted_block>"
    start = prompt.index(start_marker) + len(start_marker)
    end = prompt.index(end_marker, start)
    return prompt[start:end]


def _base_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    return {key: result[key] for key in ("ok", "facts", "reason_code")}
