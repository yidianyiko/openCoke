from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from coke.turn.agent import AgentResult
from coke.turn.context import TurnMode, TurnTrigger
from coke.worker.interactive_supervisor import InteractiveTurnSupervisor

NOW = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


class FakeRedis:
    def __init__(self) -> None:
        self.tokens: dict[str, str] = {}

    def acquire_lock(self, name, token, ttl_ms):
        if name in self.tokens:
            return False
        self.tokens[name] = token
        return True

    def get_token(self, name):
        return self.tokens.get(name)

    def extend_if_owned(self, name, token, ttl_ms):
        return self.tokens.get(name) == token

    def release_if_owned(self, name, token):
        if self.tokens.get(name) == token:
            del self.tokens[name]
            return True
        return False


class FakeMemory:
    def recent_context(self, conversation_id: str):
        return ()

    def long_term_context(self, account_id: str):
        return ()


class RecordingOutbound:
    def __init__(self) -> None:
        self.requests = []

    def deliver(self, request):
        self.requests.append(request)
        return SimpleNamespace(status="delivered", error_code=None)


class CancellableAgent:
    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.cancelled_run_ids = []
        self.output = {"type": "reply", "segments": ["I set it for 10."]}

    async def ainvoke(self, request):
        raise AssertionError("inbound turn pipeline must not invoke the render agent")

    async def cancel(self, run_id: str) -> bool:
        self.cancelled_run_ids.append(run_id)
        self.release.set()
        return True

    def invoke(self, request):
        raise AssertionError("inbound turn pipeline must not invoke the render agent")

    def complete_async(self, task_id: str):
        return AgentResult.completed(self.output)


class SlowTurnExpress:
    def __init__(self, release: asyncio.Event) -> None:
        self.started = asyncio.Event()
        self.release = release
        self.requests = []

    def render(self, request):
        raise AssertionError("read-only inbound turn should stream")

    async def render_streaming(self, request):
        self.requests.append(request)
        self.started.set()
        await self.release.wait()
        yield "I set it for 10."


@pytest.fixture
def composed():
    from coke.composition import compose_coke_runtime

    agent = CancellableAgent()
    express = SlowTurnExpress(agent.release)
    outbound = RecordingOutbound()
    runtime = compose_coke_runtime(
        interaction_agent=agent,
        redis_client=FakeRedis(),
        outbound_delivery=outbound,
        turn_express=express,
        memory_port=FakeMemory(),
        now=lambda: NOW,
        id_factory=lambda prefix: f"{prefix}_{runtime_counter.next()}",
        lock_token_factory=lambda: "lock-owner",
    )
    identity = runtime.identity_access_service.resolve_or_create_channel_identity(
        provider_type="whatsapp_evolution",
        provider_subject="sender-1",
    )
    runtime.identity_access_service.observe_usable_channel(identity.account.id)
    return runtime, agent, express, outbound, identity


class runtime_counter:
    value = 0

    @classmethod
    def next(cls) -> int:
        cls.value += 1
        return cls.value


def _record_inbound(runtime, identity, event_id: str, text: str):
    return runtime.conversation_runtime_service.record_inbound(
        account_id=identity.account.id,
        channel_identity_id=identity.channel_identity.id,
        causal_inbound_event_id=event_id,
        text=text,
        payload={"text": text, "provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )


def _trigger(inbound, identity, event_id: str, text: str) -> TurnTrigger:
    return TurnTrigger(
        trigger_id=f"inbound:{event_id}",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=inbound.conversation.id,
        account_id=identity.account.id,
        channel_identity_id=identity.channel_identity.id,
        payload={"text": text},
    )


@pytest.mark.asyncio
async def test_two_inbounds_during_slow_express_produce_one_coalesced_reply(
    composed,
):
    runtime, agent, express, _outbound, identity = composed
    supervisor = InteractiveTurnSupervisor(
        turn_runner=runtime.turn_runner,
        interaction_agent=agent,
    )

    first = _record_inbound(runtime, identity, "provider:1", "remind me at 9")
    await supervisor.submit(_trigger(first, identity, "provider:1", "remind me at 9"))
    await asyncio.wait_for(express.started.wait(), timeout=1)

    second = _record_inbound(runtime, identity, "provider:2", "actually 10")
    await supervisor.submit(_trigger(second, identity, "provider:2", "actually 10"))
    agent.release.set()

    completed = []
    for _ in range(20):
        completed.extend(await supervisor.drain_completed())
        if completed:
            break
        await asyncio.sleep(0.01)

    turns = runtime.repositories.conversation_runtime.latest_turn_ids(
        first.conversation.id, limit=10
    )
    dispositions = [
        runtime.conversation_runtime_service.get_disposition(turn_id).disposition
        for turn_id in turns
    ]
    result = completed[-1][1]

    assert "superseded" in dispositions
    assert "replied" in dispositions
    assert [
        message["content"] for message in express.requests[-1].current_input_messages
    ] == [
        "remind me at 9",
        "actually 10",
    ]
    assert result.visible_text == "I set it for 10."
    assert result.latest_causal_inbound_event_id == "provider:2"
    assert result.coalesced_causal_inbound_event_ids == ("provider:1",)
