from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime
from itertools import count
from types import SimpleNamespace
from typing import Any

import pytest

from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
)
from coke.domains.conversation_runtime.models import ConversationRuntimeError
from coke.domains.conversation_runtime.service import ConversationRuntimeService
from coke.turn.agent import AgentResult, AgentToolPorts
from coke.turn.context import TurnMode, TurnTrigger
from coke.turn.freshness import FreshnessGuard
from coke.turn.locks import ConversationLockManager
from coke.turn.output_protocol import OutputProtocolValidator
from coke.turn.pre_llm_gate import GateDecision, PreLLMGateService
from coke.turn.runner import INTERRUPTED_BY_NEWER_INBOUND_CANCEL_REASON, TurnRunner

NOW = datetime(2026, 5, 30, 10, 0, tzinfo=UTC)
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def test_turn_runner_constructor_has_no_staged_materializer_wiring() -> None:
    signature = inspect.signature(TurnRunner)
    assert "staged_command_materializer" not in signature.parameters


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


class FakeAgent:
    def __init__(self) -> None:
        self.result = AgentResult.completed({"type": "reply", "segments": ["render"]})
        self.requests = []

    def invoke(self, request):
        self.requests.append(request)
        return self.result

    async def ainvoke(self, request):
        return self.invoke(request)

    async def cancel(self, run_id: str) -> bool:
        return True

    def complete_async(self, task_id: str):
        return self.result


class FakeDelivery:
    def __init__(self) -> None:
        self.deliveries = []

    def deliver(self, request):
        self.deliveries.append(request)
        return None


class RecordingTurnPipeline:
    def __init__(self, *, segments: tuple[str, ...] = ("pipeline hello",)) -> None:
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


class RecordingRenderExpress:
    def __init__(self, segments: tuple[str, ...] = ("rendered notification",)) -> None:
        self.segments = segments
        self.requests = []

    def render(self, request):
        self.requests.append(request)
        return self.segments

    async def render_streaming(self, request):
        self.requests.append(request)
        for segment in self.segments:
            yield segment


class ExplodingTurnPipeline:
    async def run(self, request, guard, delivery=None):
        raise AssertionError("turn pipeline should not be invoked")


class RaisingTurnPipeline:
    async def run(self, request, guard, delivery=None):
        raise RuntimeError("planner exploded")


class RuntimeErrorCloseTurnPipeline:
    async def run(self, request, guard, delivery=None):
        return SimpleNamespace(
            segments=(),
            close_result=SimpleNamespace(
                committed=False,
                disposition=None,
                error=ConversationRuntimeError("invalid_segment_count"),
                reason_code="invalid_segment_count",
            ),
            streamed=False,
        )


class NewerInboundCancelledTurnPipeline:
    async def run(self, request, guard, delivery=None):
        raise asyncio.CancelledError(INTERRUPTED_BY_NEWER_INBOUND_CANCEL_REASON)


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
    agent = FakeAgent()
    delivery = FakeDelivery()
    pipeline = RecordingTurnPipeline()
    close_commits = []
    runner = TurnRunner(
        conversation_runtime=runtime,
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-1",
        ),
        pre_llm_gate=PreLLMGateService(gate_port),
        memory_port=None,
        interaction_agent=agent,
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=delivery,
        tool_ports=AgentToolPorts(),
        now=clock.now,
        account_timezone=lambda _account_id: gate_port.account_timezone,
        close_boundary_committer=lambda: close_commits.append("close"),
        turn_pipeline=pipeline,
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
        "agent": agent,
        "delivery": delivery,
        "pipeline": pipeline,
        "close_commits": close_commits,
        "runner": runner,
        "trigger": trigger,
    }


def test_inbound_turn_uses_turn_pipeline(harness):
    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert result.visible_text == "pipeline hello"
    assert harness["agent"].requests == []
    assert len(harness["pipeline"].calls) == 1
    request, guard, delivery = harness["pipeline"].calls[0]
    assert request.turn_id == result.turn_id
    assert request.account_id == "account_1"
    assert request.conversation_id == harness["trigger"].conversation_id
    assert request.payload == {"text": "hello"}
    assert request.source_input_window == (1, 1)
    assert guard is not None
    assert delivery is not None


@pytest.mark.asyncio
async def test_async_inbound_turn_uses_turn_pipeline(harness):
    harness["runner"].turn_pipeline = RecordingTurnPipeline(
        segments=("async pipeline",)
    )

    result = await harness["runner"].run_inbound_turn_async(harness["trigger"])

    assert result.disposition == "replied"
    assert result.visible_text == "async pipeline"
    assert harness["agent"].requests == []


@pytest.mark.asyncio
async def test_newer_inbound_cancellation_does_not_commit_close_boundary(harness):
    harness["runner"].turn_pipeline = NewerInboundCancelledTurnPipeline()

    with pytest.raises(asyncio.CancelledError):
        await harness["runner"].run_inbound_turn_async(harness["trigger"])

    turn = harness["repository"].get_turn_by_trigger_id(harness["trigger"].trigger_id)
    assert turn is not None
    assert harness["repository"].get_disposition(turn.id) is None
    assert harness["close_commits"] == []


def test_inbound_without_turn_pipeline_recovers_and_closes_window(harness):
    harness["runner"].turn_pipeline = None

    result = harness["runner"].run_inbound_turn(harness["trigger"])
    conversation = harness["repository"].get_conversation(
        harness["trigger"].conversation_id
    )

    assert result.disposition == "recovered"
    assert result.reason_code == "grounded_failure_recovery"
    assert result.visible_text
    assert conversation is not None
    assert conversation.last_closed_inbound_seq == conversation.latest_inbound_seq
    assert harness["agent"].requests == []


def test_inbound_pipeline_exception_recovers_and_closes_window(harness):
    harness["runner"].turn_pipeline = RaisingTurnPipeline()

    result = harness["runner"].run_inbound_turn(harness["trigger"])
    conversation = harness["repository"].get_conversation(
        harness["trigger"].conversation_id
    )

    assert result.disposition == "recovered"
    assert result.reason_code == "grounded_failure_recovery"
    assert "恢复会话状态" in result.visible_text
    assert conversation is not None
    assert conversation.last_closed_inbound_seq == conversation.latest_inbound_seq
    assert harness["agent"].requests == []


def test_inbound_pipeline_runtime_close_error_recovers_and_closes_window(harness):
    harness["runner"].turn_pipeline = RuntimeErrorCloseTurnPipeline()

    result = harness["runner"].run_inbound_turn(harness["trigger"])
    conversation = harness["repository"].get_conversation(
        harness["trigger"].conversation_id
    )

    assert result.disposition == "recovered"
    assert result.reason_code == "grounded_failure_recovery"
    assert conversation is not None
    assert conversation.last_closed_inbound_seq == conversation.latest_inbound_seq
    assert harness["agent"].requests == []


def test_async_reply_timeout_recovers_and_closes_window(harness):
    start = harness["runtime"].start_turn(
        conversation_id=harness["trigger"].conversation_id,
        trigger_id=harness["trigger"].trigger_id,
        trigger_type=harness["trigger"].trigger_type,
        mode=TurnMode.INTERACTIVE.value,
    )
    context = SimpleNamespace(
        freshness_guard=FreshnessGuard(
            conversation_runtime=harness["runtime"],
            turn_id=start.turn.id,
            input_from_seq=start.turn.input_from_seq,
            input_to_seq=start.turn.input_to_seq,
        ),
        current_input_messages=start.input_messages,
        onboarding_guidance_required=False,
    )
    harness["runner"]._record_pending_async(
        harness["trigger"],
        context,
        AgentResult.timeout("task_1"),
    )
    harness["agent"].result = AgentResult.timeout("task_2")

    result = harness["runner"].complete_async_reply("task_1")
    conversation = harness["repository"].get_conversation(
        harness["trigger"].conversation_id
    )

    assert result.disposition == "recovered"
    assert result.reason_code == "grounded_failure_recovery"
    assert conversation is not None
    assert conversation.last_closed_inbound_seq == conversation.latest_inbound_seq


def test_async_timeout_missing_task_recovers_and_closes_window(harness):
    start = harness["runtime"].start_turn(
        conversation_id=harness["trigger"].conversation_id,
        trigger_id=harness["trigger"].trigger_id,
        trigger_type=harness["trigger"].trigger_type,
        mode=TurnMode.INTERACTIVE.value,
    )
    context = SimpleNamespace(
        freshness_guard=FreshnessGuard(
            conversation_runtime=harness["runtime"],
            turn_id=start.turn.id,
            input_from_seq=start.turn.input_from_seq,
            input_to_seq=start.turn.input_to_seq,
        ),
        current_input_messages=start.input_messages,
        onboarding_guidance_required=False,
    )

    result = harness["runner"]._record_pending_async(
        harness["trigger"],
        context,
        AgentResult(timed_out=True, task_id=None),
    )
    conversation = harness["repository"].get_conversation(
        harness["trigger"].conversation_id
    )

    assert result.disposition == "recovered"
    assert result.reason_code == "grounded_failure_recovery"
    assert conversation is not None
    assert conversation.last_closed_inbound_seq == conversation.latest_inbound_seq


def test_access_denied_invalid_output_recovers_and_closes_window(harness):
    harness["gate_port"].allowed = False
    harness["agent"].result = AgentResult.completed(None)
    harness["runner"].turn_pipeline = ExplodingTurnPipeline()

    result = harness["runner"].run_inbound_turn(harness["trigger"])
    conversation = harness["repository"].get_conversation(
        harness["trigger"].conversation_id
    )

    assert result.disposition == "recovered"
    assert result.reason_code == "grounded_failure_recovery"
    assert conversation is not None
    assert conversation.last_closed_inbound_seq == conversation.latest_inbound_seq


def test_notification_turn_uses_renderer_not_interaction_agent(harness):
    harness["runner"].turn_pipeline = ExplodingTurnPipeline()
    renderer = RecordingRenderExpress()
    harness["runner"].render_express = renderer
    trigger = TurnTrigger(
        trigger_id="notification:render",
        trigger_type="NotificationTurn",
        mode=TurnMode.RENDER,
        conversation_id=harness["trigger"].conversation_id,
        account_id="account_1",
        payload={
            "notification_fact_id": "notification_fact_1",
            "notification_fact": {
                "id": "notification_fact_1",
                "type": "shared_reminder_created",
                "facts": {
                    "actor_display_name": "Alice",
                    "title": "Lunch",
                    "status": "created",
                },
                "facts_hash": "hash_1",
            },
        },
    )

    result = harness["runner"].run_render_turn(trigger)

    assert result.disposition == "replied"
    assert result.visible_text == "rendered notification"
    assert harness["agent"].requests == []
    assert len(renderer.requests) == 1
    request = renderer.requests[0]
    assert request.turn_id == result.turn_id
    assert request.account_id == "account_1"
    assert request.payload["trigger_type"] == "NotificationTurn"
    assert request.settled_outcome.outcomes[0].status == "notification"


def test_access_denied_inbound_uses_render_agent_not_turn_pipeline(harness):
    harness["gate_port"].allowed = False
    harness["runner"].turn_pipeline = ExplodingTurnPipeline()

    result = harness["runner"].run_inbound_turn(harness["trigger"])

    assert result.disposition == "replied"
    assert result.visible_text == "render"
    assert len(harness["agent"].requests) == 1
    request = harness["agent"].requests[0]
    assert request.trigger_type == "AccessDeniedTurn"
    assert request.trusted_facts["denial_reason"] == "subscription_inactive"
