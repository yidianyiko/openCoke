from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any

import pytest

import coke.llm.agno_interaction_agent as agno_agent_module
from coke.llm.agno_interaction_agent import AgnoInteractionAgent
from tests.unit.coke.llm.test_interaction_agent import FakeAgentFactory, _request


pytestmark = pytest.mark.asyncio


class BlockingAsyncAgentInstance:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.calls: list[dict[str, Any]] = []

    def run(self, input, **kwargs):
        raise AssertionError("AgnoInteractionAgent.ainvoke must use Agent.arun")

    async def arun(self, input, **kwargs):
        self.calls.append({"method": "arun", "input": input, "kwargs": kwargs})
        self.started.set()
        await asyncio.Event().wait()


class TimeoutAsyncAgentInstance:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, input, **kwargs):
        raise AssertionError("AgnoInteractionAgent.ainvoke must use Agent.arun")

    async def arun(self, input, **kwargs):
        self.calls.append({"method": "arun", "input": input, "kwargs": kwargs})
        raise TimeoutError("provider timeout")


async def test_ainvoke_uses_async_arun_and_task_cancel_after_agno_cancel(
    monkeypatch,
):
    cancelled: list[str] = []

    async def fake_cancel_run(run_id: str) -> bool:
        cancelled.append(run_id)
        return True

    monkeypatch.setattr(agno_agent_module.Agent, "acancel_run", fake_cancel_run)
    fake_agno = BlockingAsyncAgentInstance()
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(fake_agno),
    )

    task = asyncio.create_task(
        agent.ainvoke(_request(memory_enabled=True, run_id="turn_cancel"))
    )
    try:
        await asyncio.wait_for(fake_agno.started.wait(), timeout=1)

        assert await agent.cancel("turn_cancel") is True
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    assert len(fake_agno.calls) == 1
    assert fake_agno.calls[0]["method"] == "arun"
    assert fake_agno.calls[0]["kwargs"]["run_id"] == "turn_cancel"
    assert cancelled == ["turn_cancel"]


async def test_provider_timeout_returns_timed_out_without_sync_fallback():
    fake_agno = TimeoutAsyncAgentInstance()
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(fake_agno),
    )

    started_at = monotonic()
    result = await agent.ainvoke(
        _request(memory_enabled=True, run_id="turn_timeout")
    )
    elapsed = monotonic() - started_at

    assert result.timed_out is True
    assert elapsed < 1.0
    assert fake_agno.calls[0]["method"] == "arun"
    assert fake_agno.calls[0]["kwargs"]["run_id"] == "turn_timeout"
