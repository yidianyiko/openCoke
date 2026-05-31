from __future__ import annotations

import asyncio

import pytest

from coke.turn.agent import AgentResult
from coke.worker.interactive_supervisor import InteractiveTurnSupervisor
from tests.integration.coke.test_composition_turn_integration import (
    _record_inbound,
    _trigger,
    composed,
)


class SlowInterruptibleAgent:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.requests = []
        self.cancelled_run_ids = []
        self.output = {"type": "reply", "segments": ["I set it for 10."]}

    async def ainvoke(self, request):
        self.requests.append(request)
        self.started.set()
        await self.release.wait()
        return AgentResult.completed(self.output)

    async def cancel(self, run_id: str) -> bool:
        self.cancelled_run_ids.append(run_id)
        self.release.set()
        return True

    def invoke(self, request):
        raise AssertionError("interactive coalescing test must use ainvoke")

    def complete_async(self, task_id: str):
        return AgentResult.completed(self.output)


@pytest.mark.asyncio
async def test_two_inbounds_during_slow_agent_produce_one_coalesced_reply(composed):
    runtime, _semantic, _agent, _outbound, identity = composed
    slow_agent = SlowInterruptibleAgent()
    runtime.turn_runner.interaction_agent = slow_agent
    supervisor = InteractiveTurnSupervisor(
        turn_runner=runtime.turn_runner,
        interaction_agent=slow_agent,
    )

    first = _record_inbound(runtime, identity, "provider:1", "remind me at 9")
    await supervisor.submit(_trigger(first, identity, "provider:1", "remind me at 9"))
    await asyncio.wait_for(slow_agent.started.wait(), timeout=1)

    second = _record_inbound(runtime, identity, "provider:2", "actually 10")
    await supervisor.submit(_trigger(second, identity, "provider:2", "actually 10"))
    slow_agent.release.set()

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
        message.text for message in slow_agent.requests[-1].current_input_messages
    ] == [
        "remind me at 9",
        "actually 10",
    ]
    assert result.visible_text == "I set it for 10."
    assert result.latest_causal_inbound_event_id == "provider:2"
    assert result.coalesced_causal_inbound_event_ids == ("provider:1",)
