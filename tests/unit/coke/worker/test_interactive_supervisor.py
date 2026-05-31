from __future__ import annotations

import asyncio

import pytest

from coke.turn.context import TurnMode, TurnTrigger
from coke.turn.runner import notify_close_boundary_committed
from coke.worker.interactive_supervisor import InteractiveTurnSupervisor


class FakeAgent:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    async def cancel(self, run_id: str) -> bool:
        self.cancelled.append(run_id)
        return True


class SlowCancelAgent:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def cancel(self, run_id: str) -> bool:
        self.started.set()
        await self.release.wait()
        return True


class FailingCancelAgent(FakeAgent):
    async def cancel(self, run_id: str) -> bool:
        self.cancelled.append(run_id)
        raise RuntimeError(f"cancel_failed:{run_id}")


class FakeRunner:
    def __init__(self) -> None:
        self.started: list[TurnTrigger] = []
        self.released = asyncio.Event()

    async def run_inbound_turn_async(self, trigger: TurnTrigger):
        self.started.append(trigger)
        await self.released.wait()
        return f"finished:{trigger.trigger_id}"


class CancelFailureRunner:
    def __init__(self) -> None:
        self.started: list[TurnTrigger] = []
        self.released = asyncio.Event()

    async def run_inbound_turn_async(self, trigger: TurnTrigger):
        self.started.append(trigger)
        try:
            await self.released.wait()
        except asyncio.CancelledError as error:
            raise RuntimeError(f"cleanup_failed:{trigger.trigger_id}") from error
        return f"finished:{trigger.trigger_id}"


class PostCloseRunner:
    def __init__(self) -> None:
        self.started: list[TurnTrigger] = []
        self.released = asyncio.Event()

    async def run_inbound_turn_async(self, trigger: TurnTrigger):
        self.started.append(trigger)
        notify_close_boundary_committed()
        await self.released.wait()
        return f"finished:{trigger.trigger_id}"


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class CompletingRunner:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def run_inbound_turn_async(self, trigger: TurnTrigger):
        return {"trigger_id": trigger.trigger_id, "session": self.session}


class Runtime:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.turn_runner = CompletingRunner(session)


@pytest.mark.asyncio
async def test_new_inbound_cancels_active_pre_close_turn():
    runner = FakeRunner()
    agent = FakeAgent()
    supervisor = InteractiveTurnSupervisor(
        turn_runner=runner,
        interaction_agent=agent,
    )
    first = _inbound_trigger("inbound:1", "provider:1")
    second = _inbound_trigger("inbound:2", "provider:2")

    await supervisor.submit(first)
    await asyncio.sleep(0)
    await supervisor.submit(second)
    await asyncio.sleep(0)

    assert agent.cancelled == ["inbound:1"]
    assert [trigger.trigger_id for trigger in runner.started] == [
        "inbound:1",
        "inbound:2",
    ]
    assert [trigger.agent_run_id for trigger in runner.started] == [
        "inbound:1",
        "inbound:2",
    ]


@pytest.mark.asyncio
async def test_new_inbound_submit_does_not_wait_for_provider_cancel():
    runner = FakeRunner()
    agent = SlowCancelAgent()
    supervisor = InteractiveTurnSupervisor(
        turn_runner=runner,
        interaction_agent=agent,
    )

    await supervisor.submit(_inbound_trigger("inbound:1", "provider:1"))
    await asyncio.sleep(0)
    await asyncio.wait_for(
        supervisor.submit(_inbound_trigger("inbound:2", "provider:2")),
        timeout=0.1,
    )
    await asyncio.sleep(0)

    assert agent.started.is_set()
    assert [trigger.trigger_id for trigger in runner.started] == [
        "inbound:1",
        "inbound:2",
    ]
    agent.release.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_replaced_task_failure_is_observed_without_becoming_completion():
    runner = CancelFailureRunner()
    supervisor = InteractiveTurnSupervisor(
        turn_runner=runner,
        interaction_agent=FakeAgent(),
    )

    await supervisor.submit(_inbound_trigger("inbound:1", "provider:1"))
    await asyncio.sleep(0)
    await supervisor.submit(_inbound_trigger("inbound:2", "provider:2"))
    await asyncio.sleep(0)
    runner.released.set()
    await asyncio.sleep(0)

    completed = await supervisor.drain_completed()
    failures = await supervisor.drain_failures()

    assert completed == [(runner.started[-1], "finished:inbound:2")]
    assert len(failures) == 1
    failure_trigger, failure = failures[0]
    assert failure_trigger == runner.started[0]
    assert str(failure) == "cleanup_failed:inbound:1"


@pytest.mark.asyncio
async def test_provider_cancel_failure_is_reported_with_cancelled_trigger():
    runner = FakeRunner()
    agent = FailingCancelAgent()
    supervisor = InteractiveTurnSupervisor(
        turn_runner=runner,
        interaction_agent=agent,
    )

    await supervisor.submit(_inbound_trigger("inbound:1", "provider:1"))
    await asyncio.sleep(0)
    await supervisor.submit(_inbound_trigger("inbound:2", "provider:2"))
    await asyncio.sleep(0)

    failures = await supervisor.drain_failures()

    assert agent.cancelled == ["inbound:1"]
    assert len(failures) == 1
    failure_trigger, failure = failures[0]
    assert failure_trigger == runner.started[0]
    assert str(failure) == "cancel_failed:inbound:1"


@pytest.mark.asyncio
async def test_idle_retry_submission_does_not_cancel_newer_active_turn():
    runner = CancelFailureRunner()
    agent = FakeAgent()
    supervisor = InteractiveTurnSupervisor(
        turn_runner=runner,
        interaction_agent=agent,
    )

    failed = _inbound_trigger("inbound:1", "provider:1")
    newer = _inbound_trigger("inbound:2", "provider:2")
    await supervisor.submit(failed)
    await asyncio.sleep(0)
    await supervisor.submit(newer)
    await asyncio.sleep(0)

    failures = await supervisor.drain_failures()
    accepted = await supervisor.submit_if_idle(failed)
    runner.released.set()
    await asyncio.sleep(0)
    completed = await supervisor.drain_completed()

    assert accepted is False
    assert agent.cancelled == ["inbound:1"]
    assert [trigger.trigger_id for trigger in runner.started] == [
        "inbound:1",
        "inbound:2",
    ]
    assert len(failures) == 1
    assert [(trigger.trigger_id, result) for trigger, result in completed] == [
        ("inbound:2", "finished:inbound:2")
    ]


@pytest.mark.asyncio
async def test_post_close_running_turn_is_detached_without_provider_cancel():
    runner = PostCloseRunner()
    agent = FakeAgent()
    supervisor = InteractiveTurnSupervisor(
        turn_runner=runner,
        interaction_agent=agent,
    )

    await supervisor.submit(_inbound_trigger("inbound:1", "provider:1"))
    await asyncio.sleep(0)
    await supervisor.submit(_inbound_trigger("inbound:2", "provider:2"))
    await asyncio.sleep(0)
    runner.released.set()
    await asyncio.sleep(0)

    completed = await supervisor.drain_completed()

    assert agent.cancelled == []
    assert [trigger.trigger_id for trigger in runner.started] == [
        "inbound:1",
        "inbound:2",
    ]
    assert [(trigger.trigger_id, result) for trigger, result in completed] == [
        ("inbound:1", "finished:inbound:1"),
        ("inbound:2", "finished:inbound:2"),
    ]


@pytest.mark.asyncio
async def test_drain_completed_returns_finished_turns_and_drops_cancelled_tasks():
    runner = FakeRunner()
    agent = FakeAgent()
    supervisor = InteractiveTurnSupervisor(
        turn_runner=runner,
        interaction_agent=agent,
    )
    first = _inbound_trigger("inbound:1", "provider:1")
    second = _inbound_trigger("inbound:2", "provider:2")

    await supervisor.submit(first)
    await asyncio.sleep(0)
    await supervisor.submit(second)
    await asyncio.sleep(0)
    runner.released.set()
    await asyncio.sleep(0)

    assert await supervisor.drain_completed() == [
        (runner.started[-1], "finished:inbound:2")
    ]
    assert await supervisor.drain_completed() == []


@pytest.mark.asyncio
async def test_runtime_factory_uses_fresh_session_per_interactive_task():
    sessions: list[FakeSession] = []

    def runtime_factory() -> Runtime:
        session = FakeSession()
        sessions.append(session)
        return Runtime(session)

    supervisor = InteractiveTurnSupervisor(
        runtime_factory=runtime_factory,
        interaction_agent=FakeAgent(),
    )

    await supervisor.submit(
        _inbound_trigger("inbound:1", "provider:1", conversation_id="conversation_1")
    )
    await supervisor.submit(
        _inbound_trigger("inbound:2", "provider:2", conversation_id="conversation_2")
    )
    await asyncio.sleep(0)

    completed = await supervisor.drain_completed()

    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]
    assert [session.commits for session in sessions] == [1, 1]
    assert [session.closed for session in sessions] == [True, True]
    assert [result["session"] for _, result in completed] == sessions


def _inbound_trigger(
    trigger_id: str,
    causal_id: str,
    *,
    conversation_id: str = "conversation_1",
) -> TurnTrigger:
    return TurnTrigger(
        trigger_id=trigger_id,
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id=conversation_id,
        account_id="account_1",
        payload={"causal_inbound_event_id": causal_id},
    )
