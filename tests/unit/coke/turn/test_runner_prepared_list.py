from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime
from itertools import count
from types import SimpleNamespace

import pytest

from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
)
from coke.domains.conversation_runtime.service import ConversationRuntimeService
from coke.turn.agent import (
    AgentResult,
    AgentToolPorts,
    DomainExecutionResult,
    ToolExecutionResult,
)
from coke.turn.context import TurnMode, TurnTrigger
from coke.turn.locks import ConversationLockManager
from coke.turn.output_protocol import OutputProtocolValidator
from coke.turn.pre_llm_gate import GateDecision, PreLLMGateService
from coke.turn.reminder_list_render import render_reminder_list_reply
from coke.turn.runner import TurnRunner
from coke.turn.semantic_interpreter import SemanticDecision

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
        self.account_timezone = "Asia/Tokyo"

    def evaluate(self, trigger: TurnTrigger) -> GateDecision:
        return GateDecision.allowed(
            trust_facts={
                "account_id": trigger.account_id,
                "memory_enabled": True,
            }
        )


class FakeSemanticInterpreter:
    def __init__(self, decision: SemanticDecision) -> None:
        self.decision = decision

    def interpret(self, request):
        return self.decision


class FakeMemoryPort:
    def recent_context(self, conversation_id: str):
        return ()

    def long_term_context(self, account_id: str):
        return ()


class PreparedReminderListTool:
    def __init__(self, facts: dict, *, before_return=None) -> None:
        self.facts = facts
        self.before_return = before_return
        self.calls = []

    def execute_without_staging(self, command, guard):
        self.calls.append((command, guard))
        if self.before_return is not None:
            self.before_return()
        return ToolExecutionResult(
            ok=True,
            facts=self.facts,
            domain_result=DomainExecutionResult(
                domain="reminder",
                intent="list reminders",
                action="list_reminders",
                effect="listed",
                intent_fulfilled=True,
                visible_summary="Active reminder count: 2.",
                reply_contract="render_reminder_list",
                privacy_notes=("Only describe reminders for this account.",),
            ),
        )

    def execute(self, command, guard):
        raise AssertionError("prepared list must not stage or mutate")


class ForbiddenAgent:
    def invoke(self, request):
        raise AssertionError("prepared list must skip sync interaction agent")

    async def ainvoke(self, request):
        raise AssertionError("prepared list must skip async interaction agent")

    async def cancel(self, run_id: str) -> bool:
        return True

    def complete_async(self, task_id: str):
        raise AssertionError("not used")


class CountingAgent:
    def __init__(self) -> None:
        self.invocations = 0
        self.async_invocations = 0

    def invoke(self, request):
        self.invocations += 1
        return AgentResult.completed({"type": "reply", "segments": ["agent path"]})

    async def ainvoke(self, request):
        self.async_invocations += 1
        return AgentResult.completed({"type": "reply", "segments": ["agent path"]})

    async def cancel(self, run_id: str) -> bool:
        return True

    def complete_async(self, task_id: str):
        raise AssertionError("not used")


class FakeDelivery:
    def __init__(self) -> None:
        self.deliveries = []

    def deliver(self, request):
        self.deliveries.append(request)
        return SimpleNamespace(status="sent", attempt=None)


def test_sync_plain_list_uses_prepared_reply_and_skips_interaction_agent(caplog):
    env = _prepared_env(agent=ForbiddenAgent())

    with caplog.at_level(logging.INFO, logger="coke.observability.turn_latency"):
        result = env.runner.run_inbound_turn(env.trigger)

    assert result.disposition == "replied"
    assert result.visible_text == env.expected_reply
    assert env.delivery.deliveries[-1].visible_text == env.expected_reply
    assert env.reminder_tool.calls[0][0] == {
        "operation": "list_reminders",
        "owner_account_id": "account_1",
        "display_timezone": "Asia/Tokyo",
    }
    _assert_prepared_latency_record(caplog, result.turn_id)


@pytest.mark.asyncio
async def test_async_plain_list_uses_prepared_reply_and_skips_interaction_agent(
    caplog,
):
    env = _prepared_env(agent=ForbiddenAgent())

    with caplog.at_level(logging.INFO, logger="coke.observability.turn_latency"):
        result = await env.runner.run_inbound_turn_async(
            replace(env.trigger, agent_run_id="agent-run:provider-message-1")
        )

    assert result.disposition == "replied"
    assert result.visible_text == env.expected_reply
    assert env.delivery.deliveries[-1].visible_text == env.expected_reply
    assert len(env.reminder_tool.calls) == 1
    _assert_prepared_latency_record(caplog, result.turn_id)


@pytest.mark.asyncio
async def test_filtered_list_stays_on_full_agent_path():
    agent = CountingAgent()
    env = _prepared_env(
        agent=agent,
        decision=SemanticDecision(
            reply_necessity="reply_needed",
            intent_family="reminder_op",
            intent_action="list_reminders",
            ambiguity="clear",
            required_clarification="none",
            list_is_plain=False,
            language_hint="en",
        ),
    )

    result = await env.runner.run_inbound_turn_async(env.trigger)

    assert result.disposition == "replied"
    assert result.visible_text == "agent path"
    assert agent.async_invocations == 1
    assert env.reminder_tool.calls == []


def test_prepared_list_superseded_before_close_does_not_deliver_final_answer():
    env = _prepared_env(agent=ForbiddenAgent(), supersede_during_tool=True)

    result = env.runner.run_inbound_turn(env.trigger)

    assert result.disposition == "superseded"
    assert result.reason_code == "interrupted_by_newer_inbound"
    assert env.delivery.deliveries == []
    assert env.runtime.outbound_messages_for_turn(result.turn_id) == []


def _prepared_env(
    *,
    agent,
    decision: SemanticDecision | None = None,
    supersede_during_tool: bool = False,
):
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
        text="list my reminders",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    facts = {
        "count": 2,
        "reminders": [
            {"content": "pay rent", "display_time_label": "Today 6:00 PM"},
            {"content": "buy milk"},
        ],
    }
    gate_port = FakeGatePort()

    def record_newer_inbound() -> None:
        runtime.record_inbound(
            account_id="account_1",
            channel_identity_id="channel_identity_1",
            causal_inbound_event_id="provider:message-2",
            text="actually never mind",
            payload={"provider": "whatsapp_evolution"},
            traceparent=TRACEPARENT,
        )

    reminder_tool = PreparedReminderListTool(
        facts,
        before_return=record_newer_inbound if supersede_during_tool else None,
    )
    delivery = FakeDelivery()
    runner = TurnRunner(
        conversation_runtime=runtime,
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-prepared-list",
        ),
        pre_llm_gate=PreLLMGateService(gate_port),
        semantic_interpreter=FakeSemanticInterpreter(
            decision
            or SemanticDecision(
                reply_necessity="reply_needed",
                intent_family="reminder_op",
                intent_action="list_reminders",
                ambiguity="clear",
                required_clarification="none",
                list_is_plain=True,
                language_hint="en",
            )
        ),
        memory_port=FakeMemoryPort(),
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
        payload={"text": "list my reminders"},
    )
    expected_reply = render_reminder_list_reply(
        facts,
        user_text="list my reminders",
        account_id="account_1",
    )
    return SimpleNamespace(
        runner=runner,
        trigger=trigger,
        delivery=delivery,
        reminder_tool=reminder_tool,
        runtime=runtime,
        expected_reply=expected_reply,
    )


def _assert_prepared_latency_record(caplog, turn_id: str) -> None:
    records = [
        record
        for record in caplog.records
        if getattr(record, "event_name", None) == "turn_latency_event"
        and record.phase == "turn.prepared_action"
    ]
    assert len(records) == 1
    assert records[0].turn_id == turn_id
    assert records[0].route == "prepared_list"
    assert records[0].action == "list_reminders"
