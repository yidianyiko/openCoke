from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from types import SimpleNamespace
from typing import Any

import pytest

import coke.llm.agno_interaction_agent as agno_agent_module
from coke.composition import ReminderToolAdapter
from coke.domains.conversation_runtime.models import ConversationRuntimeError
from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
)
from coke.domains.conversation_runtime.service import ConversationRuntimeService
from coke.domains.reminder.models import ReminderBatchItem
from coke.domains.reminder.repository import InMemoryReminderRepository
from coke.domains.reminder.service import ReminderService
from coke.turn.agent import AgentResult, AgentToolPorts, ToolExecutionResult
from coke.turn.context import ToolProfile, TurnMode, TurnTrigger
from coke.turn.focus import FocusResolver, MessageSubject
from coke.turn.locks import ConversationLockManager
from coke.turn.output_protocol import OutputProtocolValidator
from coke.turn.pre_llm_gate import GateDecision, PreLLMGateService
from coke.turn.runner import TurnRunner
from coke.turn.semantic_interpreter import SemanticDecision
from coke.worker.__main__ import _handle_event
from coke.worker.stream_consumer import StreamEvent

NOW = datetime(2026, 5, 30, 10, 0, tzinfo=UTC)
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


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
        self.trust_facts: dict[str, Any] = {}
        self.account_timezone = "UTC"

    def evaluate(self, trigger: TurnTrigger) -> GateDecision:
        if self.allowed:
            return GateDecision.allowed(
                trust_facts={
                    "account_id": trigger.account_id,
                    **dict(self.trust_facts),
                },
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
            intent_action="chit_chat",
            ambiguity="clear",
            required_clarification="none",
            language_hint="en",
        )
        self.calls = 0
        self.requests = []

    def interpret(self, request):
        self.calls += 1
        self.requests.append(request)
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
        if request.tool_profile.reminder_tool is not None and request.payload.get(
            "execute_reminder_tool"
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
        self.outcomes = []

    def deliver(self, request):
        self.deliveries.append(request)
        if self.outcomes:
            return self.outcomes.pop(0)
        return None


class FakeDeliveryLifecycle:
    def __init__(self) -> None:
        self.calls = []

    def record_delivery(self, *, trigger, request, outcome):
        self.calls.append((trigger, request, outcome))


class StaticFocusRepository:
    def __init__(self, subject: MessageSubject | None) -> None:
        self.subject = subject

    def last_rendered_subject(self, conversation_id: str) -> MessageSubject | None:
        return self.subject


@pytest.fixture
def harness():
    clock = MutableClock(NOW)
    repository = InMemoryConversationRuntimeRepository(now=clock.now)
    runtime = ConversationRuntimeService(
        repository=repository,
        now=clock.now,
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
        now=clock.now,
        account_timezone=lambda _account_id: gate_port.account_timezone,
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
        "clock": clock,
    }


def test_intentional_no_reply_skips_interaction_agent(harness):
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="intentional_no_reply",
        intent_family="chit_chat",
        intent_action="chit_chat",
        ambiguity="clear",
        required_clarification="none",
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


def test_required_clarification_is_passed_as_trusted_agent_instruction(harness):
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="reminder_op",
        intent_action="create_reminder",
        ambiguity="missing_time",
        required_clarification="ask_trigger_time",
        language_hint="zh",
    )
    trigger = TurnTrigger(
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        payload={
            "text": "提醒我待会跑步",
            "execute_reminder_tool": True,
        },
    )

    result = harness["runner"].run_inbound_turn(trigger)

    assert result.disposition == "replied"
    assert harness["agent"].invocations == 1
    assert harness["reminder_tool"].committed == 0
    request = harness["agent"].requests[-1]
    assert request.trusted_facts["semantic_decision"]["intent_action"] == (
        "create_reminder"
    )
    assert request.trusted_facts["required_clarification"] == {
        "signal": "ask_trigger_time",
        "ambiguity": "missing_time",
        "instruction": "Ask exactly this clarification before any domain action.",
    }
    assert request.tool_profile.intent_tools_enabled is False
    assert request.tool_profile.tool_names == ()
    assert request.context.semantic_decision.intent_action == "create_reminder"


def test_single_reminder_focus_clears_reference_clarification_for_update(harness):
    harness["runner"].focus_resolver = FocusResolver(
        StaticFocusRepository(
            MessageSubject(
                subject_type="reminder",
                object_ids=("reminder_1",),
                ordered=True,
            )
        )
    )
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="reminder_op",
        intent_action="update_reminder",
        ambiguity="ambiguous_reference",
        required_clarification="ask_reference_choice",
        language_hint="zh",
    )
    trigger = TurnTrigger(
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        payload={
            "text": "把它改成60分钟",
            "execute_reminder_tool": True,
        },
    )

    result = harness["runner"].run_inbound_turn(trigger)

    assert result.disposition == "replied"
    assert harness["reminder_tool"].committed == 1
    semantic_request = harness["semantic"].requests[-1]
    assert semantic_request.focus_subject == MessageSubject(
        subject_type="reminder",
        object_ids=("reminder_1",),
        ordered=True,
    )
    agent_request = harness["agent"].requests[-1]
    assert "required_clarification" not in agent_request.trusted_facts
    assert agent_request.context.semantic_decision == SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="reminder_op",
        intent_action="update_reminder",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
    )
    assert agent_request.tool_profile.intent_tools_enabled is True
    assert agent_request.tool_profile.reminder_tool is not None


def test_invalid_agent_output_retries_same_turn_once_then_uses_valid_retry(harness):
    harness["agent"].queued_results = [
        AgentResult.completed(None),
        AgentResult.completed({"type": "reply", "segments": ["好友已经添加好了。"]}),
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


def test_replayed_inbound_turn_with_existing_reply_reconciles_without_agent_or_delivery(
    harness,
):
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

    first = harness["runner"].run_inbound_turn(trigger)
    agent_invocations = harness["agent"].invocations
    tool_commits = harness["reminder_tool"].committed
    delivery_count = len(harness["delivery"].deliveries)

    replay = harness["runner"].run_inbound_turn(trigger)

    assert first.disposition == "replied"
    assert replay.turn_id == first.turn_id
    assert replay.disposition == "replied"
    assert replay.visible_text == "hello"
    assert harness["agent"].invocations == agent_invocations
    assert harness["reminder_tool"].committed == tool_commits
    assert len(harness["delivery"].deliveries) == delivery_count


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


def test_superseded_after_tool_entry_commits_no_domain_facts(harness):
    reminder_repository = InMemoryReminderRepository()
    reminder_service = ReminderService(
        repository=reminder_repository,
        now=lambda: NOW,
        id_factory=id_factory(),
    )
    adapter = ReminderToolAdapter(reminder_service)
    start = harness["runtime"].start_turn(
        conversation_id=harness["trigger"].conversation_id,
        trigger_id="inbound:provider:message-2",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE.value,
    )

    class SupersedeAfterEntryGuard:
        calls = 0

        def guard_state_change(self):
            self.calls += 1
            if self.calls == 1:
                harness["runtime"].guard_state_change(
                    start.turn.id,
                    start.turn.input_to_seq,
                )
                return
            harness["runtime"].record_inbound(
                account_id="account_1",
                channel_identity_id="channel_identity_1",
                causal_inbound_event_id="provider:message-3",
                text="newer instruction",
                payload={"provider": "whatsapp_evolution"},
                traceparent=TRACEPARENT,
            )
            harness["runtime"].guard_state_change(
                start.turn.id,
                start.turn.input_to_seq,
            )

    guard = SupersedeAfterEntryGuard()

    with pytest.raises(ConversationRuntimeError, match="turn_superseded"):
        adapter.execute(
            {
                "operation": "create",
                "account_id": "account_1",
                "content": "pay rent",
                "trigger_time": NOW.isoformat(),
                "captured_timezone": "UTC",
            },
            guard,
        )

    assert guard.calls == 2
    assert reminder_repository.list_active_reminders("account_1") == []
    assert harness["runtime"].get_disposition(start.turn.id).disposition == "superseded"


def test_duration_update_turn_replies_and_lifecycle_event_is_worker_ackable(harness):
    reminder_repository = InMemoryReminderRepository()
    reminder_service = ReminderService(
        repository=reminder_repository,
        now=lambda: NOW,
        id_factory=id_factory(),
    )
    created = reminder_service.execute_batch(
        owner_account_id="account_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="work block",
                trigger_time=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
                captured_timezone="Asia/Shanghai",
                duration_minutes=15,
            )
        ],
    )
    reminder_id = created.items[0].reminder_id
    adapter = ReminderToolAdapter(reminder_service)

    class DurationUpdateAgent:
        def __init__(self) -> None:
            self.tool_result = None

        def invoke(self, request):
            self.tool_result = request.tool_profile.reminder_tool.execute(
                {
                    "operation": "update_reminder",
                    "owner_account_id": request.account_id,
                    "reminder_id": reminder_id,
                    "duration_minutes": 60,
                },
                request.freshness_guard,
            )
            return AgentResult.completed(
                {"type": "reply", "segments": ["已改成60分钟。"]}
            )

        def complete_async(self, task_id: str):
            raise AssertionError("duration update should complete synchronously")

    agent = DurationUpdateAgent()
    runner = TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-duration-update",
        ),
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=harness["semantic"],
        memory_port=harness["memory"],
        interaction_agent=agent,
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=harness["delivery"],
        tool_ports=AgentToolPorts(reminder_tool=adapter),
        now=harness["clock"].now,
        account_timezone=lambda _account_id: "Asia/Shanghai",
    )
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="reminder_op",
        intent_action="update_reminder",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
    )
    trigger = TurnTrigger(
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        payload={"text": "把提醒改成60分钟"},
    )

    result = runner.run_inbound_turn(trigger)

    assert result.disposition == "replied"
    assert agent.tool_result is not None
    assert agent.tool_result.ok is True
    reminder = reminder_repository.get_reminder(reminder_id)
    assert reminder is not None
    assert reminder.duration_minutes == 60
    assert harness["delivery"].deliveries[-1].visible_text == "已改成60分钟。"

    lifecycle_event = reminder_repository.outbox_records[-1]
    assert lifecycle_event.topic == "reminder.lifecycle"
    assert lifecycle_event.payload["operation"] == "update"
    assert lifecycle_event.payload["duration_minutes"] == 60
    worker_runtime = SimpleNamespace(
        session=SimpleNamespace(commit=lambda: None),
        turn_runner=SimpleNamespace(
            run_inbound_turn=lambda _trigger: pytest.fail(
                "reminder.lifecycle must not spawn an inbound turn"
            ),
            run_render_turn=lambda _trigger: pytest.fail(
                "reminder.lifecycle must not spawn a render turn"
            ),
        ),
        reply_pubsub=None,
    )

    _handle_event(
        worker_runtime,
        StreamEvent(
            event_id=lifecycle_event.id,
            topic=lifecycle_event.topic,
            idempotency_key=lifecycle_event.idempotency_key,
            traceparent=lifecycle_event.traceparent,
            payload=lifecycle_event.payload,
            stream_message_id="1-0",
        ),
    )


def test_render_delivery_failure_updates_output_class_lifecycle(harness):
    lifecycle = FakeDeliveryLifecycle()
    delivery = FakeDelivery()
    delivery.outcomes = [SimpleNamespace(status="failed", error_code="provider_failed")]
    runner = TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-2",
        ),
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=harness["semantic"],
        memory_port=harness["memory"],
        interaction_agent=harness["agent"],
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=delivery,
        tool_ports=AgentToolPorts(reminder_tool=harness["reminder_tool"]),
        delivery_lifecycle=lifecycle,
    )

    result = runner.run_render_turn(
        TurnTrigger(
            trigger_id="reminder_fire:account_1:2026-05-30T10:00:00+00:00",
            trigger_type="ReminderFireTurn",
            mode=TurnMode.RENDER,
            conversation_id=harness["trigger"].conversation_id,
            account_id="account_1",
            payload={"fire_ids": ["fire_1"]},
        )
    )

    assert result.disposition == "replied"
    assert [(call[0].trigger_type, call[2].status) for call in lifecycle.calls] == [
        ("ReminderFireTurn", "failed")
    ]


def test_render_delivery_request_links_committed_outbound_message_id(harness):
    result = harness["runner"].run_render_turn(
        TurnTrigger(
            trigger_id="notification:fact-1",
            trigger_type="NotificationTurn",
            mode=TurnMode.RENDER,
            conversation_id=harness["trigger"].conversation_id,
            account_id="account_1",
            payload={
                "notification_fact_id": "fact_1",
                "recipient_account_ids": ["account_1"],
            },
        )
    )

    outbound = harness["runtime"].outbound_messages_for_turn(result.turn_id)

    assert result.disposition == "replied"
    assert len(outbound) == 1
    assert harness["delivery"].deliveries[-1].message_id == outbound[0].id


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


def test_render_turn_context_contains_source_framing_for_system_trigger(harness):
    result = harness["runner"].run_render_turn(
        TurnTrigger(
            trigger_id="reminder_fire:account_1:2026-05-30T10:00:00+00:00",
            trigger_type="ReminderFireTurn",
            mode=TurnMode.RENDER,
            conversation_id=harness["trigger"].conversation_id,
            account_id="account_1",
            payload={"title": "提交周报", "fire_ids": ["fire_1"]},
        )
    )

    assert result.disposition == "replied"
    request = harness["agent"].requests[-1]
    assert request.trusted_facts["turn_source"] == {
        "trigger_type": "ReminderFireTurn",
        "user_spoke_this_turn": False,
        "instruction": (
            "Render the reminder fact to the user. Do not answer the reminder "
            "title as if the user said it."
        ),
    }


def test_inbound_agent_trusted_facts_include_account_local_current_time_and_prompt_environment(
    harness,
):
    harness["clock"].value = datetime(2026, 5, 31, 6, 2, tzinfo=UTC)
    harness["gate_port"].trust_facts["default_timezone"] = "Asia/Shanghai"

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    request = harness["agent"].requests[-1]
    assert request.trusted_facts["default_timezone"] == "Asia/Shanghai"
    assert request.trusted_facts["current_time"] == "2026-05-31T14:02:00+08:00"
    rendered = agno_agent_module.render_prompt_blocks(
        agno_agent_module.build_prompt_blocks(request)
    )
    assert '<trusted_block name="environment">' in rendered
    assert '"default_timezone": "Asia/Shanghai"' in rendered
    assert '"current_time": "2026-05-31T14:02:00+08:00"' in rendered


def test_each_inbound_turn_uses_fresh_current_time(harness):
    harness["gate_port"].trust_facts["default_timezone"] = "Asia/Shanghai"
    harness["clock"].value = datetime(2026, 5, 31, 6, 2, tzinfo=UTC)

    harness["runner"].run_inbound_turn(harness["trigger"])

    harness["runtime"].record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="second",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    harness["clock"].value = datetime(2026, 5, 31, 6, 7, tzinfo=UTC)
    second_trigger = TurnTrigger(
        trigger_id="inbound:provider:message-2",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        payload={"text": "second"},
    )

    harness["runner"].run_inbound_turn(second_trigger)

    assert harness["agent"].requests[-2].trusted_facts["current_time"] == (
        "2026-05-31T14:02:00+08:00"
    )
    assert harness["agent"].requests[-1].trusted_facts["current_time"] == (
        "2026-05-31T14:07:00+08:00"
    )


def test_render_turn_trusted_facts_include_account_local_current_time(harness):
    harness["clock"].value = datetime(2026, 5, 31, 6, 2, tzinfo=UTC)
    harness["gate_port"].account_timezone = "Asia/Shanghai"

    result = harness["runner"].run_render_turn(
        TurnTrigger(
            trigger_id="reminder_fire:account_1:2026-05-31T06:02:00+00:00",
            trigger_type="ReminderFireTurn",
            mode=TurnMode.RENDER,
            conversation_id=harness["trigger"].conversation_id,
            account_id="account_1",
            payload={"fire_ids": ["fire_1"]},
        )
    )

    assert result.disposition == "replied"
    request = harness["agent"].requests[-1]
    assert request.trusted_facts["default_timezone"] == "Asia/Shanghai"
    assert request.trusted_facts["current_time"] == "2026-05-31T14:02:00+08:00"


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
