from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from itertools import count
from typing import Any

import pytest

from coke.domains.conversation_runtime.repository import (
    InMemoryConversationRuntimeRepository,
)
from coke.domains.conversation_runtime.service import ConversationRuntimeService
from coke.turn.agent import AgentResult
from coke.turn.context import TurnMode, TurnTrigger
from coke.turn.locks import ConversationLockManager
from coke.turn.output_protocol import OutputProtocolValidator
from coke.turn.pre_llm_gate import GateDecision, PreLLMGateService
from coke.turn.runner import TurnRunner
from coke.turn.semantic_interpreter import SemanticDecision

NOW = datetime(2026, 6, 9, 10, 0, tzinfo=UTC)


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
    def evaluate(self, trigger: TurnTrigger) -> GateDecision:
        return GateDecision.allowed(trust_facts={"account_id": trigger.account_id})


class FakeSemanticInterpreter:
    def __init__(self) -> None:
        self.next_decision = SemanticDecision(
            reply_necessity="reply_needed",
            intent_family="chit_chat",
            intent_action="chit_chat",
            ambiguity="clear",
            required_clarification="none",
        )

    def interpret(self, request):
        return self.next_decision


class FakeMemoryPort:
    def recent_context(self, conversation_id: str):
        return ()

    def long_term_context(self, account_id: str):
        return ()


class PausingStreamingAgent:
    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.streaming_requests = []
        self.ainvoke_requests = []

    async def ainvoke_streaming(self, request):
        self.streaming_requests.append(request)
        yield "Hello there"
        await self.release.wait()
        yield "How can I help?"
        yield AgentResult.completed(
            {"type": "reply", "segments": ["Hello there", "How can I help?"]}
        )

    async def ainvoke(self, request):
        self.ainvoke_requests.append(request)
        return AgentResult.completed(
            {"type": "reply", "segments": ["Hello there", "How can I help?"]}
        )

    async def cancel(self, run_id: str) -> bool:
        return True

    def complete_async(self, task_id: str):
        raise AssertionError("streaming test does not use async completion")


class EventedDelivery:
    def __init__(self) -> None:
        self.deliveries = []
        self.first_delivery = asyncio.Event()

    def deliver(self, request):
        self.deliveries.append(request)
        self.first_delivery.set()
        return None


@pytest.mark.asyncio
async def test_eligible_chat_streams_first_segment_before_close_and_skips_duplicate(
    caplog,
):
    runtime, trigger = _runtime_and_trigger()
    agent = PausingStreamingAgent()
    delivery = EventedDelivery()
    runner = TurnRunner(
        conversation_runtime=runtime,
        lock_manager=ConversationLockManager(
            redis_client=FakeRedis(),
            ttl_ms=30_000,
            token_factory=lambda: "owner-streaming",
        ),
        pre_llm_gate=PreLLMGateService(FakeGatePort()),
        semantic_interpreter=FakeSemanticInterpreter(),
        memory_port=FakeMemoryPort(),
        interaction_agent=agent,
        output_protocol=OutputProtocolValidator(),
        outbound_delivery=delivery,
        now=lambda: NOW,
    )

    with caplog.at_level(logging.INFO, logger="coke.observability.turn_latency"):
        task = asyncio.create_task(runner.run_inbound_turn_async(trigger))
        await asyncio.wait_for(delivery.first_delivery.wait(), timeout=1)

        assert not task.done()
        assert [request.visible_text for request in delivery.deliveries] == [
            "Hello there"
        ]

        agent.release.set()
        result = await task

    outbound_texts = [
        message.text for message in runtime.outbound_messages_for_turn(result.turn_id)
    ]
    primary_event = next(
        record
        for record in caplog.records
        if getattr(record, "event_name", None) == "turn_latency_event"
        and getattr(record, "phase", None) == "agent.primary"
    )

    assert result.disposition == "replied"
    assert result.visible_text == "Hello there\nHow can I help?"
    assert outbound_texts == ["Hello there", "How can I help?"]
    assert [request.visible_text for request in delivery.deliveries] == [
        "Hello there",
        "How can I help?",
    ]
    assert agent.streaming_requests
    assert agent.ainvoke_requests == []
    assert getattr(primary_event, "streamed") is True
    assert isinstance(getattr(primary_event, "first_segment_ms"), int)


def _runtime_and_trigger() -> tuple[ConversationRuntimeService, TurnTrigger]:
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
        traceparent=None,
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
    return runtime, trigger
