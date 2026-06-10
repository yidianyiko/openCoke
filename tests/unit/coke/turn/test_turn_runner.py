from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import count
from types import SimpleNamespace
from typing import Any

import pytest

import coke.llm.agno_interaction_agent as agno_agent_module
from coke.composition import ReminderToolAdapter, SocialSchedulingToolAdapter
from coke.domains.conversation_runtime.models import ConversationRuntimeError
from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
)
from coke.domains.conversation_runtime.service import ConversationRuntimeService
from coke.domains.reminder.models import Reminder, ReminderBatchItem, ReminderFire
from coke.domains.reminder.repository import InMemoryReminderRepository
from coke.domains.reminder.service import ReminderService
from coke.domains.social_scheduling.availability import (
    ParticipantReachabilityPort,
    ReminderAvailabilityPort,
)
from coke.domains.social_scheduling.models import (
    Friendship,
    RecoverableSchedulingIntent,
)
from coke.domains.social_scheduling.repository import (
    InMemorySocialSchedulingRepository,
)
from coke.domains.social_scheduling.service import SocialSchedulingService
from coke.turn.agent import AgentResult, AgentToolPorts, ToolExecutionResult
from coke.turn.context import ToolProfile, TurnMode, TurnTrigger
from coke.turn.focus import FocusResolver, MessageSubject
from coke.turn.locks import ConversationLockManager
from coke.turn.output_protocol import OutputProtocolValidator
from coke.turn.pre_llm_gate import GateDecision, PreLLMGateService
from coke.turn.runner import TurnRunner
from coke.turn.semantic_interpreter import FollowUpAction, SemanticDecision
from coke.turn.staged_commands import StagedCommandMaterializer
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


def runner_with_close_boundary(harness, close_boundary_committer):
    return TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-close-boundary",
        ),
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=harness["semantic"],
        memory_port=harness["memory"],
        interaction_agent=harness["agent"],
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=harness["delivery"],
        tool_ports=AgentToolPorts(reminder_tool=harness["reminder_tool"]),
        now=harness["clock"].now,
        account_timezone=lambda _account_id: harness["gate_port"].account_timezone,
        close_boundary_committer=close_boundary_committer,
    )


def runner_with_claim_boundary(harness, claim_boundary_committer):
    return TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-claim-boundary",
        ),
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=harness["semantic"],
        memory_port=harness["memory"],
        interaction_agent=harness["agent"],
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=harness["delivery"],
        tool_ports=AgentToolPorts(reminder_tool=harness["reminder_tool"]),
        now=harness["clock"].now,
        account_timezone=lambda _account_id: harness["gate_port"].account_timezone,
        claim_boundary_committer=claim_boundary_committer,
    )


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


class FakeReminderFireFacts:
    def __init__(self) -> None:
        self.calls = []

    def reminder_fire_render_facts(
        self,
        *,
        owner_account_id,
        fire_ids,
        viewer_account_id=None,
    ):
        self.calls.append(
            {
                "owner_account_id": owner_account_id,
                "fire_ids": list(fire_ids),
                "viewer_account_id": viewer_account_id,
            }
        )
        return [
            SimpleNamespace(
                fire_id="fire_1",
                reminder_id="reminder_1",
                title="和Oliver喝咖啡",
                owner_account_id="account_1",
                viewer_account_id="account_1",
                due_at="2026-06-06T06:00:00+00:00",
                local_due_at="2026-06-06T14:00:00+08:00",
                timezone="Asia/Shanghai",
                duration_minutes=45,
                kind="shared_projection",
                shared_reminder_id="shared_1",
                participant_names=("Oliver",),
            )
        ]


class FakeSocialSchedulingTool:
    def __init__(self, social_scheduling_service=None) -> None:
        self.social_scheduling_service = social_scheduling_service

    def execute(self, command, guard):
        return ToolExecutionResult(
            ok=True, facts={"operation": command.get("operation")}
        )


class FakeSocialReachability(ParticipantReachabilityPort):
    def __init__(self, reachable: set[str] | None = None) -> None:
        self.reachable = reachable or set()

    def has_usable_channel(self, account_id: str) -> bool:
        return account_id in self.reachable


class FakeSocialAvailability(ReminderAvailabilityPort):
    def personal_busy_intervals(
        self,
        account_id,
        start,
        end,
        requester_timezone,
    ):
        return []


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

    async def ainvoke(self, request):
        return self.invoke(request)

    async def cancel(self, run_id: str) -> bool:
        return True

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
        self.events = []
        self.render_failures = []

    def record_delivery(self, *, trigger, request, outcome):
        self.calls.append((trigger, request, outcome))
        self.events.append("record_delivery")

    def record_inbound_reply_completed(
        self,
        *,
        trigger,
        delivered,
        onboarding_guidance_delivered=False,
    ):
        self.events.append(
            (
                "record_inbound_reply_completed",
                delivered,
                onboarding_guidance_delivered,
            )
        )

    def record_render_failure(self, *, trigger, turn_id, reason_code):
        self.render_failures.append((trigger, turn_id, reason_code))
        self.events.append(("record_render_failure", reason_code))


class RecordingV2Pipeline:
    def __init__(self, *, segments: tuple[str, ...] = ("v2 hello",)) -> None:
        self.segments = segments
        self.calls = []

    async def run(self, request, guard, delivery=None):
        self.calls.append((request, guard, delivery))
        return SimpleNamespace(
            segments=self.segments,
            close_result=SimpleNamespace(
                committed=True,
                disposition=SimpleNamespace(
                    disposition="replied",
                    reason_code="reply_ready",
                ),
                error=None,
            ),
            streamed=False,
        )


class ExplodingV2Pipeline:
    async def run(self, request, guard, delivery=None):
        raise AssertionError("v2 pipeline should not be invoked")


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
    reminder_fire_facts = FakeReminderFireFacts()
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
        reminder_fire_facts=reminder_fire_facts,
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
        "reminder_fire_facts": reminder_fire_facts,
        "agent": agent,
        "delivery": delivery,
        "runner": runner,
        "trigger": trigger,
        "clock": clock,
    }


def test_inbound_turn_emits_latency_phase_events(harness, caplog):
    with caplog.at_level(logging.INFO, logger="coke.observability.turn_latency"):
        result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    records = [
        record
        for record in caplog.records
        if getattr(record, "event_name", None) == "turn_latency_event"
    ]
    phases = {record.phase for record in records}
    assert {
        "turn.semantic_interpreter",
        "turn.context_assembly",
        "agent.primary",
        "turn.total",
    } <= phases
    for record in records:
        assert record.turn_id == result.turn_id
        assert record.trigger_type in {"InboundTurn", None}
        assert not hasattr(record, "content")
        assert not hasattr(record, "prompt")


def test_inbound_turn_with_flag_unset_uses_existing_path(harness, monkeypatch):
    monkeypatch.delenv("COKE_TURN_PIPELINE", raising=False)
    harness["runner"].turn_pipeline = ExplodingV2Pipeline()

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert result.visible_text == "hello"
    assert harness["semantic"].calls == 1
    assert harness["agent"].invocations == 1


def test_inbound_turn_with_v2_flag_invokes_pipeline(harness, monkeypatch):
    monkeypatch.setenv("COKE_TURN_PIPELINE", "v2")
    pipeline = RecordingV2Pipeline()
    harness["runner"].turn_pipeline = pipeline

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert result.visible_text == "v2 hello"
    assert harness["semantic"].calls == 0
    assert harness["agent"].invocations == 0
    assert len(pipeline.calls) == 1
    request, guard, delivery = pipeline.calls[0]
    assert request.turn_id == result.turn_id
    assert request.account_id == "account_1"
    assert request.conversation_id == harness["trigger"].conversation_id
    assert request.payload == {"text": "hello"}
    assert request.source_input_window == (1, 1)
    assert guard is not None
    assert delivery is not None


@pytest.mark.asyncio
async def test_async_inbound_turn_with_v2_flag_invokes_pipeline(
    harness, monkeypatch
):
    monkeypatch.setenv("COKE_TURN_PIPELINE", "v2")
    pipeline = RecordingV2Pipeline(segments=("async v2",))
    harness["runner"].turn_pipeline = pipeline

    result = await harness["runner"].run_inbound_turn_async(harness["trigger"])

    assert result.disposition == "replied"
    assert result.visible_text == "async v2"
    assert harness["semantic"].calls == 0
    assert harness["agent"].invocations == 0
    assert len(pipeline.calls) == 1


def test_render_turn_with_v2_flag_stays_on_existing_path(harness, monkeypatch):
    monkeypatch.setenv("COKE_TURN_PIPELINE", "v2")
    harness["runner"].turn_pipeline = ExplodingV2Pipeline()
    trigger = TurnTrigger(
        trigger_id="notification:flag-gate",
        trigger_type="NotificationTurn",
        mode=TurnMode.RENDER,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        payload={"notification": {"kind": "shared_reminder_created"}},
    )

    result = harness["runner"].run_render_turn(trigger)

    assert result.disposition == "replied"
    assert result.visible_text == "hello"
    assert harness["agent"].invocations == 1


def test_protocol_retry_emits_retry_latency_phase(harness, caplog):
    harness["agent"].queued_results = [
        AgentResult.completed({"invalid": "shape"}),
        AgentResult.completed({"type": "reply", "segments": ["retried"]}),
    ]

    with caplog.at_level(logging.INFO, logger="coke.observability.turn_latency"):
        result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    retry_records = [
        record
        for record in caplog.records
        if getattr(record, "event_name", None) == "turn_latency_event"
        and record.phase == "agent.protocol_retry"
    ]
    assert len(retry_records) == 1
    assert retry_records[0].turn_id == result.turn_id
    assert retry_records[0].retry_attempt == 1


def test_render_turn_emits_latency_phase_events(harness, caplog):
    trigger = TurnTrigger(
        trigger_id="notification:latency-test",
        trigger_type="NotificationTurn",
        mode=TurnMode.RENDER,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        payload={"notification": {"kind": "shared_reminder_created"}},
    )

    with caplog.at_level(logging.INFO, logger="coke.observability.turn_latency"):
        result = harness["runner"].run_render_turn(trigger)

    assert result.disposition == "replied"
    phases = {
        record.phase
        for record in caplog.records
        if getattr(record, "event_name", None) == "turn_latency_event"
    }
    assert {"turn.total", "turn.context_assembly", "agent.primary"} <= phases


def test_semantic_intentional_no_reply_still_reaches_interaction_agent(harness):
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="intentional_no_reply",
        intent_family="chit_chat",
        intent_action="chit_chat",
        ambiguity="clear",
        required_clarification="none",
        language_hint="en",
    )

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert result.visible_text == "hello"
    assert harness["agent"].invocations == 1
    request = harness["agent"].requests[-1]
    assert request.trusted_facts["semantic_decision"]["reply_necessity"] == (
        "reply_needed"
    )
    disposition = harness["runtime"].get_disposition(result.turn_id)
    assert disposition.disposition == "replied"


def _make_social_service(
    *,
    names: dict[str, str] | None = None,
    reachable: set[str] | None = None,
):
    repo = InMemorySocialSchedulingRepository()
    service = SocialSchedulingService(
        repository=repo,
        reachability=FakeSocialReachability(reachable or {"account_1"}),
        reminder_availability=FakeSocialAvailability(),
        now=lambda: NOW,
        id_factory=lambda prefix: f"{prefix}_{len(repo.generated_ids) + 1}",
        token_factory=lambda prefix: f"{prefix}_token",
        display_name_resolver=lambda account_id: (names or {}).get(
            account_id, account_id
        ),
    )
    return service, repo


def _add_social_friend(
    repo: InMemorySocialSchedulingRepository,
    account_id: str,
    friend_account_id: str,
) -> None:
    low, high = sorted((account_id, friend_account_id))
    repo.add_friendship(
        Friendship(
            id=f"friendship_{account_id}_{friend_account_id}",
            account_low_id=low,
            account_high_id=high,
            lifecycle="active",
            established_at=NOW,
            removed_at=None,
            created_at=NOW,
            updated_at=NOW,
        )
    )


def _open_recoverable_intent(
    repo: InMemorySocialSchedulingRepository,
    *,
    conversation_id: str,
    facts_hash: str = "facts_hash_1",
) -> RecoverableSchedulingIntent:
    intent = RecoverableSchedulingIntent(
        id="recoverable_intent_1",
        conversation_id=conversation_id,
        creator_account_id="account_1",
        operation="shared_reminder_create",
        status="open",
        blocker="unmatched_friend",
        title="Morning run",
        local_trigger_at=datetime(2029, 1, 1, 8, 30),
        captured_timezone="Asia/Shanghai",
        duration_minutes=45,
        unresolved_reference_text="zihao",
        source_turn_id="turn_source",
        source_input_from_seq=1,
        source_input_to_seq=1,
        source_message_ids=("message_source",),
        facts={"title": "Morning run", "unresolved_reference_text": "zihao"},
        facts_hash=facts_hash,
        expires_at=NOW + timedelta(minutes=15),
        consumed_turn_id=None,
        created_at=NOW,
        updated_at=NOW,
    )
    repo.save_recoverable_intent(intent)
    return intent


def _social_runner(harness, social_tool):
    return TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-social-recovery",
        ),
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=harness["semantic"],
        memory_port=harness["memory"],
        interaction_agent=harness["agent"],
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=harness["delivery"],
        tool_ports=AgentToolPorts(
            reminder_tool=harness["reminder_tool"],
            social_scheduling_tool=social_tool,
        ),
        staged_command_materializer=StagedCommandMaterializer(
            reminder_tool=None,
            social_scheduling_tool=social_tool,
            calendar_import_tool=None,
            identity_access_tool=None,
            settings_tool=None,
        ),
        now=harness["clock"].now,
        account_timezone=lambda _account_id: harness["gate_port"].account_timezone,
    )


def _assert_truthful_recovery_copy(text: str) -> None:
    assert "没能" in text or "couldn't" in text.lower()
    for banned in ("已建好", "已经建好", "约好了", "done"):
        assert banned not in text
    assert "invalid_output_protocol" not in text


def test_inbound_reply_completion_lifecycle_runs_after_delivery(harness):
    lifecycle = FakeDeliveryLifecycle()
    harness["runner"].delivery_lifecycle = lifecycle

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert lifecycle.events == [
        "record_delivery",
        ("record_inbound_reply_completed", True, False),
    ]


def test_visible_onboarding_reply_records_first_guidance_after_delivery(harness):
    lifecycle = FakeDeliveryLifecycle()
    harness["runner"].delivery_lifecycle = lifecycle
    harness["gate_port"].activation_guidance_required = True
    harness["gate_port"].trust_facts.update(
        {
            "assistant_name": "Coke",
            "user_address_name": "Eva",
            "memory_enabled": True,
            "proactive_enabled": True,
        }
    )

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    request = harness["agent"].requests[-1]
    guidance = request.trusted_facts["onboarding_guidance"]
    assert guidance["user_address_name"] == "Eva"
    assert "reminders" in guidance["supported_capabilities"]
    assert "shared_reminders_with_friends" in guidance["supported_capabilities"]
    assert "availability_checks" in guidance["supported_capabilities"]
    assert "long_term_memory_preferences" in guidance["supported_capabilities"]
    assert lifecycle.events[-1] == (
        "record_inbound_reply_completed",
        True,
        True,
    )


def test_onboarding_reply_delivery_failure_does_not_mark_first_guidance(harness):
    lifecycle = FakeDeliveryLifecycle()
    harness["runner"].delivery_lifecycle = lifecycle
    harness["gate_port"].activation_guidance_required = True
    harness["delivery"].outcomes = [
        SimpleNamespace(status="failed", error_code="provider_network_error")
    ]

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert lifecycle.events[-1] == (
        "record_inbound_reply_completed",
        False,
        False,
    )


def test_pending_async_waiting_does_not_mark_first_guidance_until_final_reply(harness):
    lifecycle = FakeDeliveryLifecycle()
    harness["runner"].delivery_lifecycle = lifecycle
    harness["gate_port"].activation_guidance_required = True
    harness["agent"].next_result = AgentResult.timeout(task_id="async-1")
    harness["agent"].next_async_result = AgentResult.completed(
        {"type": "reply", "segments": ["onboarding final"]}
    )

    pending = harness["runner"].run_inbound_turn(harness["trigger"])

    assert pending.disposition == "pending_async_reply"
    assert lifecycle.events == []

    final = harness["runner"].complete_async_reply(pending.async_task_id)

    assert final.disposition == "replied"
    assert lifecycle.events[-1] == (
        "record_inbound_reply_completed",
        True,
        True,
    )


def test_interaction_agent_can_still_intentionally_no_reply(harness):
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="intentional_no_reply",
        intent_family="chit_chat",
        intent_action="chit_chat",
        ambiguity="clear",
        required_clarification="none",
        language_hint="en",
    )
    harness["agent"].next_result = AgentResult.completed(
        {"type": "no_reply", "reason": "intentional_no_reply"}
    )

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "no_reply"
    assert result.reason_code == "intentional_no_reply"
    assert harness["agent"].invocations == 1


@pytest.mark.asyncio
async def test_async_inbound_turn_uses_async_interaction_agent_path(harness):
    class AsyncOnlyAgent(FakeAgent):
        def invoke(self, request):
            raise AssertionError("async inbound turns must not call invoke")

        async def ainvoke(self, request):
            self.invocations += 1
            self.requests.append(request)
            return self.next_result

    agent = AsyncOnlyAgent()
    runner = TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-async",
        ),
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=harness["semantic"],
        memory_port=harness["memory"],
        interaction_agent=agent,
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=harness["delivery"],
        tool_ports=AgentToolPorts(reminder_tool=harness["reminder_tool"]),
        now=harness["clock"].now,
        account_timezone=lambda _account_id: harness["gate_port"].account_timezone,
    )

    trigger = replace(harness["trigger"], agent_run_id="agent-run:provider-message-1")

    result = await runner.run_inbound_turn_async(trigger)

    assert result.disposition == "replied"
    assert agent.invocations == 1
    assert agent.requests[-1].run_id == "agent-run:provider-message-1"


@pytest.mark.asyncio
async def test_async_inbound_turn_waits_for_held_conversation_lock(harness):
    redis = FakeRedis()
    lock_manager = ConversationLockManager(
        redis_client=redis,
        ttl_ms=30_000,
        token_factory=lambda: "owner-shared-lock",
    )
    held_lock = lock_manager.acquire(harness["trigger"].conversation_id)
    assert held_lock is not None
    runner = TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=lock_manager,
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=harness["semantic"],
        memory_port=harness["memory"],
        interaction_agent=harness["agent"],
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=harness["delivery"],
        tool_ports=AgentToolPorts(reminder_tool=harness["reminder_tool"]),
        now=harness["clock"].now,
        account_timezone=lambda _account_id: harness["gate_port"].account_timezone,
    )

    task = asyncio.create_task(runner.run_inbound_turn_async(harness["trigger"]))
    try:
        await asyncio.sleep(0.02)
        assert task.done() is False
    finally:
        held_lock.release()

    result = await asyncio.wait_for(task, timeout=1)
    assert result.disposition == "replied"
    assert harness["runtime"].get_disposition(result.turn_id).disposition == "replied"


@pytest.mark.asyncio
async def test_async_inbound_turn_does_not_block_event_loop_on_semantic_interpreter(
    harness,
):
    class BlockingSemanticInterpreter(FakeSemanticInterpreter):
        def __init__(self) -> None:
            super().__init__()
            self.release = threading.Event()

        def interpret(self, request):
            self.release.wait(timeout=0.2)
            return super().interpret(request)

    semantic = BlockingSemanticInterpreter()
    runner = TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-async-semantic",
        ),
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=semantic,
        memory_port=harness["memory"],
        interaction_agent=harness["agent"],
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=harness["delivery"],
        tool_ports=AgentToolPorts(reminder_tool=harness["reminder_tool"]),
        now=harness["clock"].now,
        account_timezone=lambda _account_id: harness["gate_port"].account_timezone,
    )
    task = asyncio.create_task(runner.run_inbound_turn_async(harness["trigger"]))
    started_at = time.monotonic()

    try:
        await asyncio.sleep(0.02)
        assert time.monotonic() - started_at < 0.1
    finally:
        semantic.release.set()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_cancelled_async_inbound_turn_records_superseded_disposition(harness):
    class BlockingAgent(FakeAgent):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.requests = []

        def invoke(self, request):
            raise AssertionError("async cancellation test must not call invoke")

        async def ainvoke(self, request):
            self.requests.append(request)
            self.started.set()
            await asyncio.Event().wait()
            return self.next_result

    agent = BlockingAgent()
    runner = TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-cancelled",
        ),
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=harness["semantic"],
        memory_port=harness["memory"],
        interaction_agent=agent,
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=harness["delivery"],
        tool_ports=AgentToolPorts(reminder_tool=harness["reminder_tool"]),
        now=harness["clock"].now,
        account_timezone=lambda _account_id: harness["gate_port"].account_timezone,
        close_boundary_committer=lambda: None,
    )
    task = asyncio.create_task(runner.run_inbound_turn_async(harness["trigger"]))
    await agent.started.wait()
    harness["runtime"].record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="second",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    task.cancel("replaced_by_newer_inbound")
    with pytest.raises(asyncio.CancelledError):
        await task

    turn_id = agent.requests[-1].turn_id
    disposition = harness["runtime"].get_disposition(turn_id)
    turn = harness["repository"].get_turn(turn_id)
    assert disposition.disposition == "superseded"
    assert disposition.reason_code == "interrupted_by_newer_inbound"
    assert turn is not None
    assert turn.completed_at is not None
    assert turn.superseded_by_inbound_seq == 2
    assert (
        harness["repository"].active_interactive_turns(
            harness["trigger"].conversation_id
        )
        == []
    )


@pytest.mark.asyncio
async def test_shutdown_cancelled_async_inbound_turn_does_not_mark_superseded(harness):
    class BlockingAgent(FakeAgent):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.requests = []

        def invoke(self, request):
            raise AssertionError("async cancellation test must not call invoke")

        async def ainvoke(self, request):
            self.requests.append(request)
            self.started.set()
            await asyncio.Event().wait()
            return self.next_result

    agent = BlockingAgent()
    runner = TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-shutdown-cancelled",
        ),
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=harness["semantic"],
        memory_port=harness["memory"],
        interaction_agent=agent,
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=harness["delivery"],
        tool_ports=AgentToolPorts(reminder_tool=harness["reminder_tool"]),
        now=harness["clock"].now,
        account_timezone=lambda _account_id: harness["gate_port"].account_timezone,
        close_boundary_committer=lambda: None,
    )
    task = asyncio.create_task(runner.run_inbound_turn_async(harness["trigger"]))
    await agent.started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    turn_id = agent.requests[-1].turn_id
    with pytest.raises(ConversationRuntimeError, match="disposition_not_found"):
        harness["runtime"].get_disposition(turn_id)
    turn = harness["repository"].get_turn(turn_id)
    assert turn is not None
    assert turn.completed_at is None
    assert turn.superseded_by_inbound_seq is None


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


def test_inbound_turn_sends_ordered_input_window_to_agent(harness):
    harness["runtime"].record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="second",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    request = harness["agent"].requests[0]
    assert [message.seq for message in request.current_input_messages] == [1, 2]
    assert [message.text for message in request.current_input_messages] == [
        "hello",
        "second",
    ]


def test_reply_segments_deliver_as_separate_ordered_messages(harness):
    harness["agent"].next_result = AgentResult.completed(
        {"type": "reply", "segments": ["先这样", "明天再看"]}
    )

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert result.visible_text == "先这样\n明天再看"
    assert [request.visible_text for request in harness["delivery"].deliveries] == [
        "先这样",
        "明天再看",
    ]
    assert [request.segments for request in harness["delivery"].deliveries] == [
        ("先这样",),
        ("明天再看",),
    ]
    assert [request.idempotency_key for request in harness["delivery"].deliveries] == [
        f"{result.turn_id}:reply:1",
        f"{result.turn_id}:reply:2",
    ]
    outbound_messages = [
        message
        for message in harness["runtime"].outbound_messages_for_turn(result.turn_id)
        if (message.segment_index or 0) > 0
    ]
    assert [request.message_id for request in harness["delivery"].deliveries] == [
        outbound_messages[0].id,
        outbound_messages[1].id,
    ]


def test_malformed_inbound_after_retry_recovers_from_input_text_without_rewrite(
    harness,
):
    harness["agent"].next_result = AgentResult.completed({"invalid": "shape"})

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "recovered"
    assert result.reason_code == "grounded_failure_recovery"
    assert result.visible_text is not None
    assert "hello" in result.visible_text
    _assert_truthful_recovery_copy(result.visible_text)
    assert harness["runner"].output_protocol.rewrite_invocations == 0
    assert [request.visible_text for request in harness["delivery"].deliveries] == [
        result.visible_text
    ]
    disposition = harness["runtime"].get_disposition(result.turn_id)
    assert disposition.disposition == "recovered"
    conversation = harness["repository"].get_conversation(
        harness["trigger"].conversation_id
    )
    assert conversation is not None
    assert conversation.last_closed_inbound_seq == 1


def test_invalid_inbound_recovery_uses_structured_blocker_fact(harness):
    harness["agent"].queued_results = [
        AgentResult.completed(
            {"invalid": "shape"},
            tool_events=(
                {
                    "ok": False,
                    "facts": {
                        "status": "needs_time",
                        "follow_up_facts": {"missing": "time"},
                        "social_scheduling_outcome": {
                            "outcome_id": "outcome-1",
                            "operation": "create_shared_reminder",
                            "status": "needs_time",
                            "title": "健身",
                            "local_trigger_at": None,
                            "captured_timezone": "Asia/Shanghai",
                            "duration_minutes": 45,
                            "participant_account_ids": ["friend_oliver"],
                            "blocker": None,
                        },
                    },
                },
            ),
        ),
        AgentResult.completed({"invalid": "shape"}),
    ]

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "recovered"
    assert result.visible_text is not None
    assert "健身" in result.visible_text
    assert "具体时间" in result.visible_text
    assert "Oliver 不是你的好友" not in result.visible_text
    _assert_truthful_recovery_copy(result.visible_text)
    assert [request.visible_text for request in harness["delivery"].deliveries] == [
        result.visible_text
    ]


def test_serialized_tool_call_recovery_treats_markup_as_opaque_and_uses_input_text(
    harness,
):
    harness["agent"].queued_results = [
        AgentResult.completed(
            {
                "type": "invalid_output_protocol",
                "reason": "serialized_tool_call_output",
                "content": "<tool_call>Oliver is not your friend</tool_call>",
            },
            tool_events=(
                {
                    "ok": False,
                    "serialized_tool_call_output": (
                        "<tool_call>Oliver is not your friend</tool_call>"
                    ),
                },
            ),
        ),
        AgentResult.completed(
            {
                "type": "invalid_output_protocol",
                "reason": "serialized_tool_call_output",
                "content": "<tool_call>Oliver is not your friend</tool_call>",
            }
        ),
    ]

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "recovered"
    assert result.visible_text is not None
    assert "hello" in result.visible_text
    assert "Oliver is not your friend" not in result.visible_text
    _assert_truthful_recovery_copy(result.visible_text)


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


def test_short_affirmative_missing_context_keeps_interactive_tools(harness):
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="chit_chat",
        intent_action="chit_chat",
        ambiguity="missing_context",
        required_clarification="ask_context",
        language_hint="zh",
    )
    trigger = TurnTrigger(
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        payload={"text": "是的"},
    )

    result = harness["runner"].run_inbound_turn(trigger)

    assert result.disposition == "replied"
    request = harness["agent"].requests[-1]
    assert "required_clarification" not in request.trusted_facts
    assert request.context.semantic_decision == SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="chit_chat",
        intent_action="chit_chat",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
    )
    assert request.tool_profile.intent_tools_enabled is True
    assert request.tool_profile.tool_names == ("reminder",)


def test_concise_clarification_answer_keeps_interactive_tools(harness):
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="friend_op",
        intent_action="none",
        ambiguity="missing_context",
        required_clarification="ask_context",
        language_hint="zh",
    )
    trigger = TurnTrigger(
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        payload={"text": "lizihao"},
    )

    result = harness["runner"].run_inbound_turn(trigger)

    assert result.disposition == "replied"
    request = harness["agent"].requests[-1]
    assert "required_clarification" not in request.trusted_facts
    assert request.context.semantic_decision == SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="friend_op",
        intent_action="none",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
    )
    assert request.tool_profile.intent_tools_enabled is True
    assert request.tool_profile.tool_names == ("reminder",)


def test_blocked_unmatched_friend_close_creates_recoverable_intent(harness):
    service, repo = _make_social_service()
    social_tool = FakeSocialSchedulingTool(service)
    runner = _social_runner(harness, social_tool)
    outcome = {
        "outcome_id": "outcome-1",
        "operation": "create_shared_reminder",
        "status": "blocked_unmatched_friend",
        "title": "Morning run",
        "local_trigger_at": "2029-01-01T08:30:00",
        "captured_timezone": "Asia/Shanghai",
        "duration_minutes": 45,
        "participant_account_ids": [],
        "blocker": "unmatched_friend",
        "facts_hash": None,
        "recoverable_scheduling_intent_id": None,
    }
    harness["agent"].next_result = AgentResult.completed(
        {
            "type": "reply",
            "segments": ["我没找到 zihao 这个好友。"],
            "domain_claim": {
                "domain": "social_scheduling",
                "outcome_id": "outcome-1",
                "status": "blocked_unmatched_friend",
                "claim": "blocked_unmatched_friend",
                "blocker": "unmatched_friend",
            },
        },
        tool_events=(
            {
                "ok": False,
                "facts": {
                    "status": "needs_participants",
                    "follow_up_facts": {
                        "reason": "unmatched_friend",
                        "unresolved_reference_text": "zihao",
                    },
                    "social_scheduling_outcome": outcome,
                },
                "reason_code": "needs_participants",
            },
        ),
    )

    result = runner.run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    intent = repo.open_recoverable_intent_for_conversation(
        harness["trigger"].conversation_id,
        now=NOW,
    )
    assert intent is not None
    assert intent.blocker == "unmatched_friend"
    assert intent.title == "Morning run"
    assert intent.unresolved_reference_text == "zihao"


def test_shared_reminder_retry_false_duplicate_without_active_row_fails_closed(
    harness,
):
    service, repo = _make_social_service(
        names={"friend_olivers": "Olivers"},
        reachable={"account_1", "friend_olivers"},
    )
    _add_social_friend(repo, "account_1", "friend_olivers")
    social_tool = SocialSchedulingToolAdapter(service)
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="scheduling",
        intent_action="create_shared_reminder",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
    )

    class StagesThenInvalidAgent(FakeAgent):
        def invoke(self, request):
            self.invocations += 1
            self.requests.append(request)
            if self.invocations == 1:
                request.tool_profile.social_scheduling_tool.execute(
                    {
                        "operation": "create_shared_reminder",
                        "creator_account_id": "account_1",
                        "receiver_account_ids": ["friend_olivers"],
                        "title": "吃饭",
                        "local_trigger_at": "2026-06-06T12:30:00",
                        "captured_timezone": "Asia/Shanghai",
                        "duration_minutes": 15,
                        "context": {"source": "retry_false_success_regression"},
                    },
                    request.freshness_guard,
                )
            return AgentResult.completed(
                {
                    "type": "invalid_output_protocol",
                    "reason": "serialized_tool_call_output",
                }
            )

    harness["agent"] = StagesThenInvalidAgent()
    first_runner = _social_runner(harness, social_tool)

    recovered = first_runner.run_inbound_turn(harness["trigger"])

    assert recovered.disposition == "recovered"
    assert recovered.reason_code == "grounded_failure_recovery"
    assert recovered.visible_text is not None
    assert "吃饭" in recovered.visible_text
    _assert_truthful_recovery_copy(recovered.visible_text)
    assert repo.list_shared_reminders_for_participant("account_1") == []
    assert [
        command.status
        for command in harness["repository"].staged_commands_for_turn(recovered.turn_id)
    ] == ["superseded"]
    conversation = harness["repository"].get_conversation(
        harness["trigger"].conversation_id
    )
    assert conversation is not None
    assert conversation.last_closed_inbound_seq == 1

    retry_inbound = harness["runtime"].record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="约olivers 12:30吃饭",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    retry_trigger = TurnTrigger(
        trigger_id="inbound:provider:message-2",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=retry_inbound.conversation.id,
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        payload={"text": "约olivers 12:30吃饭"},
    )
    harness["agent"] = FakeAgent()
    harness["agent"].next_result = AgentResult.completed(
        {
            "type": "reply",
            "segments": ["这个已经约过了～olivers 12:30吃饭的共享提醒已经建好了"],
        }
    )
    retry_runner = _social_runner(harness, social_tool)

    retry = retry_runner.run_inbound_turn(retry_trigger)

    assert retry.disposition == "recovered"
    assert retry.reason_code == "grounded_failure_recovery"
    assert retry.visible_text is not None
    _assert_truthful_recovery_copy(retry.visible_text)
    assert repo.list_shared_reminders_for_participant("account_1") == []
    assert "已经建好了" not in "\n".join(
        request.visible_text for request in harness["delivery"].deliveries
    )
    conversation = harness["repository"].get_conversation(retry_trigger.conversation_id)
    assert conversation.last_closed_inbound_seq == 2
    assert [
        message.seq for message in harness["agent"].requests[-1].current_input_messages
    ] == [2]


def test_staged_social_scheduling_reply_without_claim_materializes_on_clean_close(
    harness,
):
    service, repo = _make_social_service(
        names={"friend_lizihao": "lizihao"},
        reachable={"account_1", "friend_lizihao"},
    )
    _add_social_friend(repo, "account_1", "friend_lizihao")
    social_tool = SocialSchedulingToolAdapter(service)
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="scheduling",
        intent_action="create_shared_reminder",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
    )

    class StagesThenRepliesWithoutClaim(FakeAgent):
        def invoke(self, request):
            self.invocations += 1
            self.requests.append(request)
            tool_result = request.tool_profile.social_scheduling_tool.execute(
                {
                    "operation": "create_shared_reminder",
                    "creator_account_id": "account_1",
                    "receiver_account_ids": ["friend_lizihao"],
                    "title": "健身",
                    "local_trigger_at": "2026-06-06T11:00:00",
                    "captured_timezone": "Asia/Shanghai",
                    "duration_minutes": 60,
                    "context": {"source": "staged_claim_derivation_regression"},
                },
                request.freshness_guard,
            )
            return AgentResult.completed(
                {"type": "reply", "segments": ["我会继续确认这次安排。"]},
                tool_events=(
                    {
                        "ok": tool_result.ok,
                        "facts": dict(tool_result.facts),
                        "reason_code": tool_result.reason_code,
                    },
                ),
            )

    harness["agent"] = StagesThenRepliesWithoutClaim()
    runner = _social_runner(harness, social_tool)

    result = runner.run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert result.visible_text == "我会继续确认这次安排。"
    commands = harness["repository"].staged_commands_for_turn(result.turn_id)
    assert [command.status for command in commands] == ["materialized"]
    shared = repo.list_shared_reminders_for_participant("account_1")
    assert len(shared) == 1
    assert shared[0].title == "健身"


def test_recovery_from_detect_shared_reminder_uses_raw_text_not_participant_uuid(
    harness,
):
    participant_account_id = "635d3bdc4a5f67890123456789abcdef"
    raw_text = "上午11点约 lizihao 健身"
    service, repo = _make_social_service(
        names={participant_account_id: "lizihao"},
        reachable={"account_1", participant_account_id},
    )
    _add_social_friend(repo, "account_1", participant_account_id)
    social_tool = SocialSchedulingToolAdapter(service)
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="scheduling",
        intent_action="create_shared_reminder",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
    )

    class StagesDetectThenInvalid(FakeAgent):
        def invoke(self, request):
            self.invocations += 1
            self.requests.append(request)
            request.tool_profile.social_scheduling_tool.execute(
                {
                    "operation": "detect_and_create_shared_reminder",
                    "creator_account_id": "account_1",
                    "receiver_account_ids": [participant_account_id],
                    "raw_text": raw_text,
                    "title": None,
                    "captured_timezone": "Asia/Shanghai",
                    "duration_minutes": 60,
                    "context": {"source": "recovery_uuid_grounding_regression"},
                },
                request.freshness_guard,
            )
            return AgentResult.completed(
                {
                    "type": "invalid_output_protocol",
                    "reason": "serialized_tool_call_output",
                }
            )

    harness["agent"] = StagesDetectThenInvalid()
    runner = _social_runner(harness, social_tool)

    result = runner.run_inbound_turn(harness["trigger"])

    assert result.disposition == "recovered"
    assert result.visible_text is not None
    assert raw_text in result.visible_text
    assert re.search(r"[0-9a-f]{32}", result.visible_text) is None
    _assert_truthful_recovery_copy(result.visible_text)
    assert repo.list_shared_reminders_for_participant("account_1") == []


def test_duplicate_active_reply_allowed_when_active_shared_reminder_exists(harness):
    service, repo = _make_social_service(
        names={"friend_olivers": "Olivers"},
        reachable={"account_1", "friend_olivers"},
    )
    _add_social_friend(repo, "account_1", "friend_olivers")
    created = service.create_shared_reminder(
        creator_account_id="account_1",
        receiver_account_ids=["friend_olivers"],
        title="吃饭",
        local_trigger_at=datetime(2026, 6, 6, 12, 30),
        captured_timezone="Asia/Shanghai",
        duration_minutes=15,
        context={"source": "duplicate_active_regression"},
    )
    outcome = {
        "outcome_id": "duplicate-outcome-1",
        "operation": "create_shared_reminder",
        "status": "duplicate_active",
        "staged_command_id": None,
        "shared_reminder_id": created.shared_reminder.id,
        "title": "吃饭",
        "local_trigger_at": "2026-06-06T12:30:00",
        "captured_timezone": "Asia/Shanghai",
        "duration_minutes": 15,
        "participant_account_ids": ["friend_olivers"],
        "blocker": None,
        "facts_hash": None,
        "recoverable_scheduling_intent_id": None,
    }
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="scheduling",
        intent_action="create_shared_reminder",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
    )
    harness["agent"].next_result = AgentResult.completed(
        {
            "type": "reply",
            "segments": ["这个共享提醒已经存在了。"],
            "domain_claim": {
                "domain": "social_scheduling",
                "outcome_id": "duplicate-outcome-1",
                "status": "duplicate_active",
                "claim": "active_duplicate",
            },
        },
        tool_events=({"ok": True, "facts": {"social_scheduling_outcome": outcome}},),
    )
    runner = _social_runner(harness, SocialSchedulingToolAdapter(service))

    result = runner.run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert result.visible_text == "这个共享提醒已经存在了。"
    assert repo.get_shared_reminder(created.shared_reminder.id).status == "active"


def test_friend_alias_correction_injects_recoverable_intent_fact(harness):
    service, repo = _make_social_service(names={"friend_oliver": "Olivers"})
    _add_social_friend(repo, "account_1", "friend_oliver")
    intent = _open_recoverable_intent(
        repo,
        conversation_id=harness["trigger"].conversation_id,
    )
    social_tool = FakeSocialSchedulingTool(service)
    runner = _social_runner(harness, social_tool)
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="scheduling",
        intent_action="create_shared_reminder",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
        follow_up_action=FollowUpAction(
            type="resolve_friend_reference_correction",
            prior_reference_text="zihao",
            corrected_friend_text="olivers",
            scope="immediately_preceding_unresolved_intent",
        ),
    )

    result = runner.run_inbound_turn(harness["trigger"])

    assert result.disposition == "recovered"
    assert result.visible_text is not None
    _assert_truthful_recovery_copy(result.visible_text)
    request = harness["agent"].requests[-1]
    recovery = request.trusted_facts["recoverable_scheduling_intent"]
    assert recovery["id"] == intent.id
    assert recovery["facts_hash"] == intent.facts_hash
    assert recovery["resolved_friend_account_id"] == "friend_oliver"
    assert request.tool_profile.social_scheduling_tool is social_tool
    assert "pending_clarification_resolution" not in request.trusted_facts


def test_friend_alias_correction_materializes_and_consumes_recoverable_intent(harness):
    service, repo = _make_social_service(
        names={"friend_oliver": "Olivers"},
        reachable={"account_1", "friend_oliver"},
    )
    _add_social_friend(repo, "account_1", "friend_oliver")
    intent = _open_recoverable_intent(
        repo,
        conversation_id=harness["trigger"].conversation_id,
    )
    social_tool = SocialSchedulingToolAdapter(service)

    class RecoveringAgent(FakeAgent):
        def invoke(self, request):
            self.invocations += 1
            self.requests.append(request)
            recovery = request.trusted_facts["recoverable_scheduling_intent"]
            request.tool_profile.social_scheduling_tool.execute(
                {
                    "operation": "create_shared_reminder",
                    "creator_account_id": "account_1",
                    "receiver_account_ids": [recovery["resolved_friend_account_id"]],
                    "title": recovery["title"],
                    "local_trigger_at": recovery["local_trigger_at"],
                    "captured_timezone": recovery["captured_timezone"],
                    "duration_minutes": recovery["duration_minutes"],
                    "context": {"source": "recoverable_intent"},
                    "recoverable_scheduling_intent_id": recovery["id"],
                    "facts_hash": recovery["facts_hash"],
                },
                request.freshness_guard,
            )
            return AgentResult.completed(
                {"type": "reply", "segments": ["已约好和 Olivers 的 Morning run。"]}
            )

    agent = RecoveringAgent()
    runner = TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-social-consume",
        ),
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=harness["semantic"],
        memory_port=harness["memory"],
        interaction_agent=agent,
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=harness["delivery"],
        tool_ports=AgentToolPorts(
            reminder_tool=harness["reminder_tool"],
            social_scheduling_tool=social_tool,
        ),
        staged_command_materializer=StagedCommandMaterializer(
            reminder_tool=None,
            social_scheduling_tool=social_tool,
            calendar_import_tool=None,
            identity_access_tool=None,
            settings_tool=None,
        ),
        now=harness["clock"].now,
        account_timezone=lambda _account_id: harness["gate_port"].account_timezone,
    )
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="scheduling",
        intent_action="create_shared_reminder",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
        follow_up_action=FollowUpAction(
            type="resolve_friend_reference_correction",
            prior_reference_text="zihao",
            corrected_friend_text="olivers",
            scope="immediately_preceding_unresolved_intent",
        ),
    )

    result = runner.run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert repo.get_recoverable_intent(intent.id).status == "consumed"
    staged = harness["repository"].staged_commands_for_turn(result.turn_id)
    assert [command.status for command in staged] == ["materialized"]
    assert repo.list_shared_reminders_for_participant("account_1")


def test_unrelated_friend_correction_does_not_inject_recovery(harness):
    service, repo = _make_social_service(names={"friend_oliver": "Olivers"})
    _add_social_friend(repo, "account_1", "friend_oliver")
    _open_recoverable_intent(
        repo,
        conversation_id=harness["trigger"].conversation_id,
    )
    runner = _social_runner(harness, FakeSocialSchedulingTool(service))
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="scheduling",
        intent_action="create_shared_reminder",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
        follow_up_action=FollowUpAction(
            type="resolve_friend_reference_correction",
            prior_reference_text="other-name",
            corrected_friend_text="olivers",
            scope="immediately_preceding_unresolved_intent",
        ),
    )

    result = runner.run_inbound_turn(harness["trigger"])

    assert result.disposition == "recovered"
    assert result.visible_text is not None
    _assert_truthful_recovery_copy(result.visible_text)
    request = harness["agent"].requests[-1]
    assert "recoverable_scheduling_intent" not in request.trusted_facts
    assert "recoverable_scheduling_intent_resolution" not in request.trusted_facts


def test_ambiguous_friend_correction_asks_one_agent_confirmation(harness):
    service, repo = _make_social_service(
        names={
            "friend_oliver_a": "Oliver S",
            "friend_oliver_b": "Olivers",
        }
    )
    _add_social_friend(repo, "account_1", "friend_oliver_a")
    _add_social_friend(repo, "account_1", "friend_oliver_b")
    _open_recoverable_intent(
        repo,
        conversation_id=harness["trigger"].conversation_id,
    )
    runner = _social_runner(harness, FakeSocialSchedulingTool(service))
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="scheduling",
        intent_action="create_shared_reminder",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
        follow_up_action=FollowUpAction(
            type="resolve_friend_reference_correction",
            prior_reference_text="zihao",
            corrected_friend_text="olivers",
            scope="immediately_preceding_unresolved_intent",
        ),
    )

    result = runner.run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    request = harness["agent"].requests[-1]
    resolution = request.trusted_facts["recoverable_scheduling_intent_resolution"]
    assert resolution["status"] == "ambiguous"
    assert resolution["corrected_friend_text"] == "olivers"
    assert resolution["candidate_account_ids"] == [
        "friend_oliver_a",
        "friend_oliver_b",
    ]
    assert request.tool_profile.intent_tools_enabled is False
    assert request.tool_profile.constrained is True


def test_superseded_consuming_turn_does_not_consume_recoverable_intent(harness):
    service, repo = _make_social_service(
        names={"friend_oliver": "Olivers"},
        reachable={"account_1", "friend_oliver"},
    )
    _add_social_friend(repo, "account_1", "friend_oliver")
    intent = _open_recoverable_intent(
        repo,
        conversation_id=harness["trigger"].conversation_id,
    )
    social_tool = SocialSchedulingToolAdapter(service)

    class RecoveringAgent(FakeAgent):
        def invoke(self, request):
            self.invocations += 1
            self.requests.append(request)
            harness["runtime"].record_inbound(
                account_id="account_1",
                channel_identity_id="channel_identity_1",
                causal_inbound_event_id="provider:message-2",
                text="newer",
                payload={"provider": "whatsapp_evolution"},
                traceparent=TRACEPARENT,
            )
            request.tool_profile.social_scheduling_tool.execute(
                {
                    "operation": "create_shared_reminder",
                    "creator_account_id": "account_1",
                    "receiver_account_ids": ["friend_oliver"],
                    "title": intent.title,
                    "local_trigger_at": intent.local_trigger_at.isoformat(),
                    "captured_timezone": intent.captured_timezone,
                    "duration_minutes": intent.duration_minutes,
                    "context": {"source": "recoverable_intent"},
                    "recoverable_scheduling_intent_id": intent.id,
                    "facts_hash": intent.facts_hash,
                },
                request.freshness_guard,
            )
            return self.next_result

    agent = RecoveringAgent()
    runner = TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-social-superseded",
        ),
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=harness["semantic"],
        memory_port=harness["memory"],
        interaction_agent=agent,
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=harness["delivery"],
        tool_ports=AgentToolPorts(
            reminder_tool=harness["reminder_tool"],
            social_scheduling_tool=social_tool,
        ),
        staged_command_materializer=StagedCommandMaterializer(
            reminder_tool=None,
            social_scheduling_tool=social_tool,
            calendar_import_tool=None,
            identity_access_tool=None,
            settings_tool=None,
        ),
        now=harness["clock"].now,
        account_timezone=lambda _account_id: harness["gate_port"].account_timezone,
    )
    harness["semantic"].next_decision = SemanticDecision(
        reply_necessity="reply_needed",
        intent_family="scheduling",
        intent_action="create_shared_reminder",
        ambiguity="clear",
        required_clarification="none",
        language_hint="zh",
        follow_up_action=FollowUpAction(
            type="resolve_friend_reference_correction",
            prior_reference_text="zihao",
            corrected_friend_text="olivers",
            scope="immediately_preceding_unresolved_intent",
        ),
    )

    result = runner.run_inbound_turn(harness["trigger"])

    assert result.disposition == "superseded"
    assert repo.get_recoverable_intent(intent.id).status == "open"


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


def test_invalid_agent_output_retry_still_invalid_recovers(harness):
    harness["agent"].queued_results = [
        AgentResult.completed(None),
        AgentResult.completed({"invalid": "shape"}),
    ]

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "recovered"
    assert result.reason_code == "grounded_failure_recovery"
    assert result.visible_text is not None
    _assert_truthful_recovery_copy(result.visible_text)
    assert harness["agent"].invocations == 2
    assert [request.visible_text for request in harness["delivery"].deliveries] == [
        result.visible_text
    ]


def test_invalid_agent_output_retry_does_not_loop(harness):
    harness["agent"].queued_results = [
        AgentResult.completed(None),
        AgentResult.completed(None),
        AgentResult.completed({"type": "reply", "segments": ["would be bad"]}),
    ]

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "recovered"
    assert result.reason_code == "grounded_failure_recovery"
    assert result.visible_text is not None
    _assert_truthful_recovery_copy(result.visible_text)
    assert harness["agent"].invocations == 2
    assert [request.visible_text for request in harness["delivery"].deliveries] == [
        result.visible_text
    ]


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


def test_covered_inbound_turn_is_ackable_without_agent_or_delivery(harness):
    first = harness["runner"].run_inbound_turn(harness["trigger"])
    agent_invocations = harness["agent"].invocations
    delivery_count = len(harness["delivery"].deliveries)
    covered_trigger = TurnTrigger(
        trigger_id="inbound:provider:message-1:covered",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        payload={"text": "hello"},
    )

    covered = harness["runner"].run_inbound_turn(covered_trigger)

    assert first.disposition == "replied"
    assert covered.turn_id == covered_trigger.trigger_id
    assert covered.disposition == "superseded"
    assert covered.reason_code == "input_window_already_closed"
    assert covered.visible_text is None
    assert harness["agent"].invocations == agent_invocations
    assert len(harness["delivery"].deliveries) == delivery_count


def test_covered_inbound_bypasses_denied_gate(harness):
    first = harness["runner"].run_inbound_turn(harness["trigger"])
    harness["gate_port"].allowed = False
    agent_invocations = harness["agent"].invocations
    delivery_count = len(harness["delivery"].deliveries)
    covered_trigger = TurnTrigger(
        trigger_id="inbound:provider:message-1:covered-denied",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        payload={"text": "hello"},
    )

    covered = harness["runner"].run_inbound_turn(covered_trigger)

    assert first.disposition == "replied"
    assert covered.turn_id == covered_trigger.trigger_id
    assert covered.disposition == "superseded"
    assert covered.reason_code == "input_window_already_closed"
    assert covered.visible_text is None
    assert harness["agent"].invocations == agent_invocations
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
    assert result.reason_code == "interrupted_by_newer_inbound"
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
                harness["runtime"].guard_state_change(start.turn.id)
                return
            harness["runtime"].record_inbound(
                account_id="account_1",
                channel_identity_id="channel_identity_1",
                causal_inbound_event_id="provider:message-3",
                text="newer instruction",
                payload={"provider": "whatsapp_evolution"},
                traceparent=TRACEPARENT,
            )
            harness["runtime"].guard_state_change(start.turn.id)

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


def test_superseded_interactive_turn_leaves_no_active_reminder(harness):
    reminder_repository = InMemoryReminderRepository()
    reminder_service = ReminderService(
        repository=reminder_repository,
        now=lambda: NOW,
        id_factory=id_factory(),
    )
    adapter = ReminderToolAdapter(reminder_service)

    class ReminderThenSupersedeAgent:
        def invoke(self, request):
            request.tool_profile.reminder_tool.execute(
                {
                    "operation": "create",
                    "owner_account_id": request.account_id,
                    "content": "pay rent",
                    "trigger_time": NOW.isoformat(),
                    "captured_timezone": "UTC",
                },
                request.freshness_guard,
            )
            harness["runtime"].record_inbound(
                account_id="account_1",
                channel_identity_id="channel_identity_1",
                causal_inbound_event_id="provider:message-2",
                text="actually make it 10",
                payload={"provider": "whatsapp_evolution"},
                traceparent=TRACEPARENT,
            )
            return AgentResult.completed(
                {"type": "reply", "segments": ["I will remind you."]}
            )

        def complete_async(self, task_id: str):
            raise AssertionError("reminder turn should complete synchronously")

    runner = TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-superseded-reminder",
        ),
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=harness["semantic"],
        memory_port=harness["memory"],
        interaction_agent=ReminderThenSupersedeAgent(),
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=harness["delivery"],
        tool_ports=AgentToolPorts(reminder_tool=adapter),
        now=harness["clock"].now,
        account_timezone=lambda _account_id: "UTC",
    )

    result = runner.run_inbound_turn(harness["trigger"])

    assert result.disposition == "superseded"
    assert reminder_repository.list_active_reminders("account_1") == []
    staged = harness["repository"].staged_commands_for_turn(result.turn_id)
    assert [command.status for command in staged] == ["superseded"]


def test_reminder_tool_list_reminders_returns_active_count_without_write_guard():
    reminder_repository = InMemoryReminderRepository()
    reminder_service = ReminderService(
        repository=reminder_repository,
        now=lambda: NOW,
        id_factory=id_factory(),
    )
    reminder_service.execute_batch(
        owner_account_id="account_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="pay rent",
                trigger_time=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
                captured_timezone="Asia/Shanghai",
                duration_minutes=15,
            ),
            ReminderBatchItem(
                operation="create",
                content="buy milk",
                captured_timezone="Asia/Shanghai",
                duration_minutes=15,
            ),
        ],
    )
    adapter = ReminderToolAdapter(reminder_service)

    class ReadOnlyGuard:
        def guard_state_change(self):
            raise AssertionError("list_reminders must not open a write guard")

    result = adapter.execute(
        {
            "operation": "list_reminders",
            "owner_account_id": "account_1",
            "captured_timezone": "Asia/Shanghai",
        },
        ReadOnlyGuard(),
    )

    assert result.ok is True
    assert result.reason_code is None
    assert result.facts["owner_account_id"] == "account_1"
    assert result.facts["display_timezone"] == "Asia/Shanghai"
    assert result.facts["count"] == 2
    assert [item["content"] for item in result.facts["reminders"]] == [
        "pay rent",
        "buy milk",
    ]
    assert result.facts["reminders"][0]["next_fire_at"] == ("2026-05-30T12:00:00+00:00")
    assert result.facts["reminders"][0]["display_time_label"] == (
        "2026-05-30 20:00 Asia/Shanghai"
    )
    assert result.facts["display_lines"] == [
        "1. pay rent (2026-05-30 20:00 Asia/Shanghai)",
        "2. buy milk (unscheduled)",
    ]
    assert result.domain_result is not None
    assert result.domain_result.action == "list_reminders"
    assert result.domain_result.intent_fulfilled is True
    assert result.domain_result.reply_contract == "render_reminder_list"
    assert "Active reminder count: 2." in result.domain_result.visible_summary
    assert "1. pay rent (2026-05-30 20:00 Asia/Shanghai)" in (
        result.domain_result.visible_summary
    )


def test_reminder_service_hydrates_fire_ids_for_render_facts():
    now = datetime(2026, 6, 6, 4, 0, tzinfo=UTC)
    reminder_repository = InMemoryReminderRepository()
    reminder_service = ReminderService(
        repository=reminder_repository,
        now=lambda: now,
        friend_identifiers=(
            lambda shared_id, viewer_id: (
                ["Oliver"]
                if shared_id == "shared_1" and viewer_id == "account_1"
                else []
            )
        ),
    )
    reminder = Reminder(
        id="reminder_1",
        owner_account_id="account_1",
        content="和Oliver喝咖啡",
        content_hash="hash_1",
        kind="shared_projection",
        next_fire_at=datetime(2026, 6, 6, 6, 0, tzinfo=UTC),
        recurrence_rule={},
        captured_timezone="Asia/Shanghai",
        duration_minutes=45,
        lifecycle="active",
        hidden_from_calendar=False,
        shared_reminder_id="shared_1",
        created_at=now,
        updated_at=now,
    )
    fire = ReminderFire(
        id="fire_1",
        reminder_id="reminder_1",
        occurrence_key="2026-06-06T06:00:00+00:00",
        due_at=datetime(2026, 6, 6, 6, 0, tzinfo=UTC),
        fire_state="claimed",
        delivery_result=None,
        handled_at=None,
        completed_at=None,
        missed_catch_up=False,
        created_at=now,
        updated_at=now,
    )
    reminder_repository.add_reminder(reminder)
    reminder_repository.add_fire(fire)

    facts = reminder_service.reminder_fire_render_facts(
        owner_account_id="account_1",
        fire_ids=["fire_1"],
        viewer_account_id="account_1",
    )

    assert facts[0].fire_id == "fire_1"
    assert facts[0].reminder_id == "reminder_1"
    assert facts[0].title == "和Oliver喝咖啡"
    assert facts[0].local_due_at == "2026-06-06T14:00:00+08:00"
    assert facts[0].timezone == "Asia/Shanghai"
    assert facts[0].duration_minutes == 45
    assert facts[0].kind == "shared_projection"
    assert facts[0].participant_names == ("Oliver",)


def test_reminder_tool_list_reminders_accepts_keyword_kind_and_time_filters():
    reminder_repository = InMemoryReminderRepository()
    reminder_service = ReminderService(
        repository=reminder_repository,
        now=lambda: NOW,
        id_factory=id_factory(),
    )
    reminder_service.execute_batch(
        owner_account_id="account_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="call mom",
                trigger_time=NOW + timedelta(hours=1),
                captured_timezone="UTC",
            ),
            ReminderBatchItem(
                operation="create",
                content="call dentist",
                captured_timezone="UTC",
            ),
            ReminderBatchItem(
                operation="create",
                content="buy milk",
                trigger_time=NOW + timedelta(days=1),
                captured_timezone="UTC",
            ),
        ],
    )
    adapter = ReminderToolAdapter(reminder_service)

    result = adapter.execute(
        {
            "operation": "list_reminders",
            "owner_account_id": "account_1",
            "keyword": "call",
            "kind": "timed",
            "trigger_after": NOW.isoformat(),
            "trigger_before": (NOW + timedelta(hours=2)).isoformat(),
            "captured_timezone": "UTC",
        },
        object(),
    )

    assert result.ok is True
    assert result.facts["count"] == 1
    assert result.facts["reminders"][0]["content"] == "call mom"


def test_reminder_tool_complete_reminder_accepts_unambiguous_keyword():
    reminder_repository = InMemoryReminderRepository()
    reminder_service = ReminderService(
        repository=reminder_repository,
        now=lambda: NOW,
        id_factory=id_factory(),
    )
    reminder_service.execute_batch(
        owner_account_id="account_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="pay rent",
                trigger_time=NOW + timedelta(hours=1),
                captured_timezone="UTC",
            ),
            ReminderBatchItem(
                operation="create",
                content="buy milk",
                trigger_time=NOW + timedelta(hours=2),
                captured_timezone="UTC",
            ),
        ],
    )
    adapter = ReminderToolAdapter(reminder_service)

    class WriteGuard:
        def guard_state_change(self):
            return None

    result = adapter.execute(
        {
            "operation": "complete_reminder",
            "owner_account_id": "account_1",
            "keyword": "rent",
        },
        WriteGuard(),
    )

    assert result.ok is True
    assert result.facts["state"] == "succeeded"
    assert [
        reminder.content
        for reminder in reminder_repository.list_active_reminders("account_1")
    ] == ["buy milk"]


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
        staged_command_materializer=StagedCommandMaterializer(
            reminder_tool=adapter,
            social_scheduling_tool=None,
            calendar_import_tool=None,
            identity_access_tool=None,
            settings_tool=None,
        ),
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
    staged = harness["repository"].staged_commands_for_turn(result.turn_id)
    assert [command.status for command in staged] == ["materialized"]
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
        reminder_fire_facts=harness["reminder_fire_facts"],
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


def test_notification_render_collapses_segments_into_single_delivery(harness):
    # A product notification rendered as multiple segments must be delivered as
    # one outbound message. Each segment is otherwise a separate provider send
    # subject to the WeChat per-send context-token window; losing the second
    # send (ilink ret_-2) would strand the content and leave the recipient with
    # a contentless header. See docs/issues/2026-06-09-shared-reminder-invite-
    # content-segment-lost.md.
    harness["agent"].next_result = AgentResult.completed(
        {
            "type": "reply",
            "segments": [
                "olivers 和你共享了一个提醒",
                "6月11日 15:00「和 eva 约Peter演讲」，时长15分钟",
            ],
        }
    )

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

    assert result.disposition == "replied"
    assert [request.visible_text for request in harness["delivery"].deliveries] == [
        "olivers 和你共享了一个提醒\n6月11日 15:00「和 eva 约Peter演讲」，时长15分钟"
    ]
    assert [request.idempotency_key for request in harness["delivery"].deliveries] == [
        f"{result.turn_id}:reply:1"
    ]
    outbound = [
        message
        for message in harness["runtime"].outbound_messages_for_turn(result.turn_id)
        if (message.segment_index or 0) > 0
    ]
    assert len(outbound) == 1


def test_notification_turn_invalid_output_settles_recipients_failed(harness):
    lifecycle = FakeDeliveryLifecycle()
    harness["runner"].delivery_lifecycle = lifecycle
    harness["agent"].queued_results = [
        AgentResult.completed({"type": "no_reply", "reason": "intentional_no_reply"}),
        AgentResult.completed({"type": "no_reply", "reason": "intentional_no_reply"}),
    ]

    result = harness["runner"].run_render_turn(
        TurnTrigger(
            trigger_id="notification:fact-invalid",
            trigger_type="NotificationTurn",
            mode=TurnMode.RENDER,
            conversation_id=harness["trigger"].conversation_id,
            account_id="account_1",
            payload={
                "notification_fact_id": "fact_1",
                "recipient_account_ids": ["account_1", "account_2"],
            },
        )
    )

    assert result.disposition == "failed"
    assert lifecycle.render_failures == [
        (
            lifecycle.render_failures[0][0],
            result.turn_id,
            "notification_requires_visible_reply",
        )
    ]
    assert lifecycle.render_failures[0][0].payload["recipient_account_ids"] == [
        "account_1",
        "account_2",
    ]


def test_notification_turn_lock_failure_settles_recipients_failed(harness):
    lifecycle = FakeDeliveryLifecycle()
    redis = FakeRedis()
    lock_manager = ConversationLockManager(
        redis_client=redis,
        ttl_ms=30_000,
        token_factory=lambda: "owner-notification-lock",
    )
    held = lock_manager.acquire(harness["trigger"].conversation_id)
    assert held is not None
    runner = TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=lock_manager,
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=harness["semantic"],
        memory_port=harness["memory"],
        interaction_agent=harness["agent"],
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=harness["delivery"],
        tool_ports=AgentToolPorts(reminder_tool=harness["reminder_tool"]),
        delivery_lifecycle=lifecycle,
        now=harness["clock"].now,
    )

    result = runner.run_render_turn(
        TurnTrigger(
            trigger_id="notification:fact-lock-failed",
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

    assert result.disposition == "failed"
    assert lifecycle.render_failures == [
        (
            lifecycle.render_failures[0][0],
            result.turn_id,
            "conversation_lock_unavailable",
        )
    ]


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
    conversation = harness["repository"].get_conversation(
        harness["trigger"].conversation_id
    )
    assert conversation is not None
    assert conversation.last_closed_inbound_seq == 1


@pytest.mark.asyncio
async def test_async_denied_access_gate_uses_async_agent_path(harness):
    class AsyncOnlyAgent(FakeAgent):
        def invoke(self, request):
            raise AssertionError("async access-denied turns must not call invoke")

        async def ainvoke(self, request):
            self.invocations += 1
            self.requests.append(request)
            return self.next_result

    agent = AsyncOnlyAgent()
    agent.next_result = AgentResult.completed(
        {"type": "reply", "segments": ["Your access needs attention."]}
    )
    harness["gate_port"].allowed = False
    runner = TurnRunner(
        conversation_runtime=harness["runtime"],
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-async-denied",
        ),
        pre_llm_gate=PreLLMGateService(harness["gate_port"]),
        semantic_interpreter=harness["semantic"],
        memory_port=harness["memory"],
        interaction_agent=agent,
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=harness["delivery"],
        tool_ports=AgentToolPorts(reminder_tool=harness["reminder_tool"]),
        now=harness["clock"].now,
        account_timezone=lambda _account_id: harness["gate_port"].account_timezone,
    )

    trigger = replace(harness["trigger"], agent_run_id="agent-run:provider-message-1")

    result = await runner.run_inbound_turn_async(trigger)

    assert result.disposition == "replied"
    assert result.trigger_type == "AccessDeniedTurn"
    assert agent.invocations == 1
    request = agent.requests[-1]
    assert request.mode == TurnMode.RENDER
    assert request.tool_profile == ToolProfile.render(constrained=True)
    assert request.run_id == "agent-run:provider-message-1"


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


def test_reminder_fire_render_turn_injects_trusted_domain_result(harness):
    result = harness["runner"].run_render_turn(_reminder_fire_trigger(harness))

    assert result.disposition == "replied"
    request = harness["agent"].requests[-1]
    domain_result = request.trusted_facts["domain_result"]
    assert domain_result["reply_contract"] == "render_reminder_fire"
    assert domain_result["facts"]["fire_ids"] == ["fire_1"]
    assert domain_result["facts"]["reminders"][0]["title"] == "和Oliver喝咖啡"
    assert (
        domain_result["facts"]["reminders"][0]["local_due_at"]
        == "2026-06-06T14:00:00+08:00"
    )
    assert harness["reminder_fire_facts"].calls[-1]["viewer_account_id"] == (
        "account_1"
    )


def test_reminder_fire_wrong_title_falls_back_to_trusted_fact(harness):
    harness["agent"].queued_results = [
        AgentResult.completed({"type": "reply", "segments": ["11:40咖啡快到了"]}),
        AgentResult.completed({"type": "reply", "segments": ["11:40咖啡快到了"]}),
    ]

    result = harness["runner"].run_render_turn(_reminder_fire_trigger(harness))

    assert result.disposition == "replied"
    assert result.visible_text == "和Oliver喝咖啡 2026-06-06 14:00 Asia/Shanghai"
    assert harness["agent"].invocations == 2


def test_reminder_fire_wrong_time_falls_back_to_trusted_fact(harness):
    harness["agent"].queued_results = [
        AgentResult.completed({"type": "reply", "segments": ["和Oliver喝咖啡 11:40"]}),
        AgentResult.completed({"type": "reply", "segments": ["和Oliver喝咖啡 11:40"]}),
    ]

    result = harness["runner"].run_render_turn(_reminder_fire_trigger(harness))

    assert result.disposition == "replied"
    assert result.visible_text == "和Oliver喝咖啡 2026-06-06 14:00 Asia/Shanghai"


def test_reminder_fire_serialized_tool_call_falls_back_to_trusted_fact(harness):
    harness["agent"].queued_results = [
        AgentResult.completed(
            {"type": "reply", "segments": ["<tool_call>query_reminder</tool_call>"]}
        ),
        AgentResult.completed(
            {"type": "reply", "segments": ["<tool_call>query_reminder</tool_call>"]}
        ),
    ]

    result = harness["runner"].run_render_turn(_reminder_fire_trigger(harness))

    assert result.disposition == "replied"
    assert result.visible_text == "和Oliver喝咖啡 2026-06-06 14:00 Asia/Shanghai"


def test_reminder_fire_no_reply_falls_back_to_trusted_fact(harness):
    harness["agent"].queued_results = [
        AgentResult.completed({"type": "no_reply", "reason": "intentional_no_reply"}),
        AgentResult.completed({"type": "no_reply", "reason": "intentional_no_reply"}),
    ]

    result = harness["runner"].run_render_turn(_reminder_fire_trigger(harness))

    assert result.disposition == "replied"
    assert result.visible_text == "和Oliver喝咖啡 2026-06-06 14:00 Asia/Shanghai"


def _reminder_fire_trigger(harness):
    return TurnTrigger(
        trigger_id="reminder_fire:account_1:2026-06-06T06:00:00+00:00",
        trigger_type="ReminderFireTurn",
        mode=TurnMode.RENDER,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        payload={"fire_ids": ["fire_1"]},
    )


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
    assert harness["delivery"].deliveries[0].visible_text == "我还在处理，稍等一下。"
    assert harness["delivery"].deliveries[0].idempotency_key == (
        f"{pending.turn_id}:waiting:1"
    )
    assert harness["delivery"].deliveries[0].delivery_source == "waiting_sync_timeout"
    assert harness["delivery"].deliveries[0].delivery_intent == (
        f"{pending.turn_id}:waiting:1"
    )
    assert harness["delivery"].deliveries[0].retry_attempt == 1
    assert final.disposition == "replied"
    assert final.visible_text == "final answer"
    assert harness["runtime"].get_disposition(final.turn_id).disposition == "replied"


def test_close_boundary_commits_before_reply_delivery(harness):
    events = []
    runner = runner_with_close_boundary(
        harness,
        close_boundary_committer=lambda: events.append("close_commit"),
    )

    def deliver(request):
        events.append(f"deliver:{request.message_type}")
        harness["delivery"].deliveries.append(request)
        return None

    harness["delivery"].deliver = deliver

    result = runner.run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert events == ["close_commit", "deliver:reply"]


def test_close_boundary_commits_before_waiting_text_delivery(harness):
    events = []
    harness["agent"].next_result = AgentResult.timeout(task_id="async-1")
    runner = runner_with_close_boundary(
        harness,
        close_boundary_committer=lambda: events.append("close_commit"),
    )

    def deliver(request):
        events.append(f"deliver:{request.message_type}")
        harness["delivery"].deliveries.append(request)
        return None

    harness["delivery"].deliver = deliver

    result = runner.run_inbound_turn(harness["trigger"])

    assert result.disposition == "pending_async_reply"
    assert events == ["close_commit", "deliver:waiting"]


def test_pending_async_state_survives_waiting_delivery_failure_and_replay(harness):
    initial_closed_seq = (
        harness["repository"]
        .get_conversation(harness["trigger"].conversation_id)
        .last_closed_inbound_seq
    )
    harness["agent"].next_result = AgentResult.timeout(task_id="async-1")
    harness["agent"].next_async_result = AgentResult.completed(
        {"type": "reply", "segments": ["final answer"]}
    )

    def deliver(request):
        harness["delivery"].deliveries.append(request)
        raise RuntimeError("provider_down")

    harness["delivery"].deliver = deliver

    pending = harness["runner"].run_inbound_turn(harness["trigger"])

    assert pending.disposition == "pending_async_reply"
    assert pending.async_task_id == "async-1"
    assert harness["delivery"].deliveries[0].message_type == "waiting"
    assert harness["runtime"].get_disposition(pending.turn_id).disposition == (
        "pending_async_reply"
    )
    assert (
        harness["repository"]
        .get_conversation(harness["trigger"].conversation_id)
        .last_closed_inbound_seq
        == initial_closed_seq
    )

    final = harness["runner"].complete_async_reply(pending.async_task_id)

    assert final.disposition == "replied"
    assert final.visible_text == "final answer"


def test_claim_boundary_commits_before_gate_and_again_before_agent_work(harness):
    events = []
    runner = runner_with_claim_boundary(
        harness,
        claim_boundary_committer=lambda: events.append("claim_commit"),
    )

    original_evaluate = harness["gate_port"].evaluate

    def evaluate(trigger):
        events.append("gate")
        return original_evaluate(trigger)

    def before_agent():
        events.append("agent")

    harness["gate_port"].evaluate = evaluate
    harness["agent"].before_tool = before_agent

    result = runner.run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert events[:4] == ["claim_commit", "gate", "claim_commit", "agent"]


@pytest.mark.asyncio
async def test_async_claim_boundary_commits_again_before_agent_work(harness):
    events = []
    runner = runner_with_claim_boundary(
        harness,
        claim_boundary_committer=lambda: events.append("claim_commit"),
    )

    original_evaluate = harness["gate_port"].evaluate

    def evaluate(trigger):
        events.append("gate")
        return original_evaluate(trigger)

    def before_agent():
        events.append("agent")

    harness["gate_port"].evaluate = evaluate
    harness["agent"].before_tool = before_agent

    result = await runner.run_inbound_turn_async(harness["trigger"])

    assert result.disposition == "replied"
    assert events[:4] == ["claim_commit", "gate", "claim_commit", "agent"]
