from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from typing import Any

import pytest

from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
)
from coke.domains.conversation_runtime.service import ConversationRuntimeService
from coke.turn.agent import AgentResult, AgentToolPorts, ToolExecutionResult
from coke.turn.context import ToolProfile, TurnMode, TurnTrigger
from coke.turn.locks import ConversationLockManager
from coke.turn.output_protocol import OutputProtocolValidator
from coke.turn.pre_llm_gate import GateDecision, PreLLMGateService
from coke.turn.runner import TurnRunner
from coke.turn.semantic_interpreter import SemanticDecision


NOW = datetime(2026, 5, 30, 10, 0, tzinfo=UTC)
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def id_factory():
    counter = count(1)
    return lambda prefix: f"{prefix}_{next(counter)}"


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, name, value, nx=False, px=None):
        if nx and name in self.values:
            return False
        self.values[name] = value
        return True

    def get(self, name):
        return self.values.get(name)

    def pexpire(self, name, ttl_ms):
        return name in self.values

    def delete(self, name):
        existed = name in self.values
        self.values.pop(name, None)
        return 1 if existed else 0

    def acquire_lock(self, name: str, token: str, ttl_ms: int) -> bool:
        return bool(self.set(name, token, nx=True, px=ttl_ms))

    def get_token(self, name: str) -> str | None:
        return self.get(name)

    def extend_if_owned(self, name: str, token: str, ttl_ms: int) -> bool:
        if self.get(name) != token:
            return False
        return bool(self.pexpire(name, ttl_ms))

    def release_if_owned(self, name: str, token: str) -> bool:
        if self.get(name) != token:
            return False
        return bool(self.delete(name))


class FakeGatePort:
    def __init__(self) -> None:
        self.allowed = True
        self.activation_guidance_required = False

    def evaluate(self, trigger: TurnTrigger) -> GateDecision:
        if self.allowed:
            return GateDecision.allowed(
                trust_facts={"account_id": trigger.account_id},
                activation_guidance_required=self.activation_guidance_required,
            )
        return GateDecision.denied(
            denial_reason="subscription_inactive",
            access_facts={"checkout_url": "https://checkout.example/account_1"},
        )


class FakeSemanticInterpreter:
    def __init__(self) -> None:
        self.next_decision = SemanticDecision(
            reply_necessity="reply_needed",
            intent_family="chit_chat",
            language_hint="en",
        )
        self.calls = 0

    def interpret(self, request):
        self.calls += 1
        return self.next_decision


class FakeMemoryPort:
    def __init__(self) -> None:
        self.short_term_reads = 0
        self.long_term_reads = 0

    def recent_context(self, conversation_id: str):
        self.short_term_reads += 1
        return ("recent message",)

    def long_term_context(self, account_id: str):
        self.long_term_reads += 1
        return ("known preference",)


class FakeReminderTool:
    def __init__(self) -> None:
        self.committed = 0

    def execute(self, command, guard):
        guard.guard_state_change()
        self.committed += 1
        return ToolExecutionResult(ok=True, facts={"reminder_id": "reminder_1"})


class FakeAgent:
    def __init__(self) -> None:
        self.next_result = AgentResult.completed(
            {"type": "reply", "segments": ["hello"]}
        )
        self.queued_results = []
        self.next_async_result = AgentResult.completed(
            {"type": "reply", "segments": ["async done"]}
        )
        self.requests = []
        self.invocations = 0
        self.before_tool = None

    def invoke(self, request):
        self.invocations += 1
        self.requests.append(request)
        if self.before_tool is not None:
            self.before_tool()
        if (
            request.tool_profile.reminder_tool is not None
            and request.payload.get("execute_reminder_tool")
        ):
            request.tool_profile.reminder_tool.execute(
                {"operation": "create"}, request.freshness_guard
            )
        if self.queued_results:
            return self.queued_results.pop(0)
        return self.next_result

    def complete_async(self, task_id: str):
        return self.next_async_result


class FakeDelivery:
    def __init__(self) -> None:
        self.deliveries = []

    def deliver(self, request):
        self.deliveries.append(request)


@pytest.fixture
def harness():
    repository = InMemoryConversationRuntimeRepository(now=lambda: NOW)
    runtime = ConversationRuntimeService(
        repository=repository,
        now=lambda: NOW,
        id_factory=id_factory(),
    )
    inbound = runtime.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="hello",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    gate_port = FakeGatePort()
    semantic = FakeSemanticInterpreter()
    memory = FakeMemoryPort()
    reminder_tool = FakeReminderTool()
    agent = FakeAgent()
    delivery = FakeDelivery()
    runner = TurnRunner(
        conversation_runtime=runtime,
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-1",
        ),
        pre_llm_gate=PreLLMGateService(gate_port),
        semantic_interpreter=semantic,
        memory_port=memory,
        interaction_agent=agent,
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=delivery,
        tool_ports=AgentToolPorts(reminder_tool=reminder_tool),
    )
    trigger = TurnTrigger(
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=inbound.conversation.id,
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        payload={"text": "hello"},
    )
    return {
        "repository": repository,
        "runtime": runtime,
        "gate_port": gate_port,
        "semantic": semantic,
        "memory": memory,
        "reminder_tool": reminder_tool,
        "agent": agent,
        "delivery": delivery,
        "runner": runner,
        "trigger": trigger,
    }


def test_intentional_no_reply_skips_interaction_agent(harness):
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="intentional_no_reply",
        intent_family="chit_chat",
        language_hint="en",
    )

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "no_reply"
    assert result.reason_code == "intentional_no_reply"
    assert result.visible_text is None
    assert harness["agent"].invocations == 0
    disposition = harness["runtime"].get_disposition(result.turn_id)
    assert disposition.disposition == "no_reply"


def test_inbound_reply_delivery_carries_trigger_context_token(harness):
    trigger = TurnTrigger(
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        payload={
            "text": "hello",
            "payload": {
                "provider": "wechat_personal",
                "context_token": "ctx-message-1",
            },
        },
    )

    result = harness["runner"].run_inbound_turn(trigger)

    assert result.disposition == "replied"
    assert harness["delivery"].deliveries[-1].context_token == "ctx-message-1"


def test_malformed_agent_output_fails_closed_without_rewrite(harness):
    harness["agent"].next_result = AgentResult.completed({"invalid": "shape"})

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "failed"
    assert result.reason_code == "invalid_output_protocol"
    assert result.visible_text is None
    assert harness["runner"].output_protocol.rewrite_invocations == 0
    assert harness["delivery"].deliveries == []


def test_invalid_agent_output_retries_same_turn_once_then_uses_valid_retry(harness):
    harness["agent"].queued_results = [
        AgentResult.completed(None),
        AgentResult.completed(
            {"type": "reply", "segments": ["好友已经添加好了。"]}
        ),
    ]

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert result.visible_text == "好友已经添加好了。"
    assert harness["agent"].invocations == 2
    assert harness["agent"].requests[0].turn_id == harness["agent"].requests[1].turn_id
    assert harness["agent"].requests[1].trusted_facts["protocol_retry"] == {
        "reason_code": "invalid_output_protocol",
        "attempt": 2,
        "guidance": None,
    }
    assert len(harness["delivery"].deliveries) == 1
    assert harness["delivery"].deliveries[-1].visible_text == "好友已经添加好了。"


def test_segment_count_violation_retry_carries_specific_protocol_guidance(harness):
    harness["agent"].queued_results = [
        AgentResult.completed(
            {"type": "reply", "segments": ["one", "two", "three", "four"]}
        ),
        AgentResult.completed({"type": "reply", "segments": ["one two", "three four"]}),
    ]

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert harness["agent"].invocations == 2
    assert harness["agent"].requests[1].trusted_facts["protocol_retry"] == {
        "reason_code": "invalid_output_protocol",
        "attempt": 2,
        "guidance": "reply_segments_must_contain_1_to_3_non_empty_strings",
    }


def test_invalid_agent_output_retry_still_invalid_fails_closed(harness):
    harness["agent"].queued_results = [
        AgentResult.completed(None),
        AgentResult.completed({"invalid": "shape"}),
    ]

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "failed"
    assert result.reason_code == "invalid_output_protocol"
    assert harness["agent"].invocations == 2
    assert harness["delivery"].deliveries == []


def test_invalid_agent_output_retry_does_not_loop(harness):
    harness["agent"].queued_results = [
        AgentResult.completed(None),
        AgentResult.completed(None),
        AgentResult.completed({"type": "reply", "segments": ["would be bad"]}),
    ]

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "failed"
    assert result.reason_code == "invalid_output_protocol"
    assert harness["agent"].invocations == 2
    assert harness["delivery"].deliveries == []


def test_superseded_inbound_yields_distinct_disposition_and_blocks_state_commit(
    harness,
):
    def supersede_before_tool():
        harness["runtime"].record_inbound(
            account_id="account_1",
            channel_identity_id="channel_identity_1",
            causal_inbound_event_id="provider:message-2",
            text="actually cancel that",
            payload={"provider": "whatsapp_evolution"},
            traceparent=TRACEPARENT,
        )

    harness["agent"].before_tool = supersede_before_tool

    trigger = harness["trigger"]
    trigger = TurnTrigger(
        trigger_id=trigger.trigger_id,
        trigger_type=trigger.trigger_type,
        mode=trigger.mode,
        conversation_id=trigger.conversation_id,
        account_id=trigger.account_id,
        channel_identity_id=trigger.channel_identity_id,
        payload={"text": "create a reminder", "execute_reminder_tool": True},
    )
    result = harness["runner"].run_inbound_turn(trigger)

    assert result.disposition == "superseded"
    assert result.reason_code == "newer_inbound_seq"
    assert harness["reminder_tool"].committed == 0
    assert harness["delivery"].deliveries == []


def test_denied_access_gate_yields_access_denied_turn_rendered_in_constrained_mode(
    harness,
):
    harness["gate_port"].allowed = False
    harness["agent"].next_result = AgentResult.completed(
        {"type": "reply", "segments": ["Your access needs attention."]}
    )

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert result.trigger_type == "AccessDeniedTurn"
    assert harness["semantic"].calls == 0
    assert harness["agent"].invocations == 1
    request = harness["agent"].requests[-1]
    assert request.mode == TurnMode.RENDER
    assert request.tool_profile == ToolProfile.render(constrained=True)
    assert request.trusted_facts["denial_reason"] == "subscription_inactive"


def test_render_mode_exposes_no_intent_or_business_mutation_tools(harness):
    result = harness["runner"].run_render_turn(
        TurnTrigger(
            trigger_id="notification:fact-1",
            trigger_type="NotificationTurn",
            mode=TurnMode.RENDER,
            conversation_id=harness["trigger"].conversation_id,
            account_id="account_1",
            payload={"facts": {"type": "friendship_created"}},
        )
    )

    assert result.disposition == "replied"
    request = harness["agent"].requests[-1]
    assert request.mode == TurnMode.RENDER
    assert request.tool_profile.intent_tools_enabled is False
    assert request.tool_profile.tool_names == ()
    assert request.tool_profile.reminder_tool is None


def test_timeout_yields_waiting_text_pending_async_then_transitions_to_replied(
    harness,
):
    harness["agent"].next_result = AgentResult.timeout(task_id="async-1")
    harness["agent"].next_async_result = AgentResult.completed(
        {"type": "reply", "segments": ["final answer"]}
    )

    pending = harness["runner"].run_inbound_turn(harness["trigger"])
    final = harness["runner"].complete_async_reply(pending.async_task_id)

    assert pending.disposition == "pending_async_reply"
    assert pending.async_task_id == "async-1"
    assert harness["delivery"].deliveries[0].message_type == "waiting"
    assert harness["delivery"].deliveries[0].visible_text == "Still working on it."
    assert final.disposition == "replied"
    assert final.visible_text == "final answer"
    assert harness["runtime"].get_disposition(final.turn_id).disposition == "replied"
