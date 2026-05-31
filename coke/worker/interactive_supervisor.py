from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any, Callable

from coke.turn.context import TurnTrigger


@dataclass(slots=True)
class ActiveInteractiveTurn:
    trigger: TurnTrigger
    task: asyncio.Task[Any]
    run_id: str


class InteractiveTurnSupervisor:
    def __init__(
        self,
        *,
        interaction_agent: Any,
        turn_runner: Any | None = None,
        runtime_factory: Callable[[], Any] | None = None,
    ) -> None:
        if turn_runner is None and runtime_factory is None:
            raise ValueError("turn_runner_or_runtime_factory_required")
        self.turn_runner = turn_runner
        self.interaction_agent = interaction_agent
        self.runtime_factory = runtime_factory
        self._active: dict[str, ActiveInteractiveTurn] = {}
        self._completed: list[tuple[TurnTrigger, Any]] = []

    async def submit(self, trigger: TurnTrigger) -> None:
        run_id = trigger.agent_run_id or trigger.trigger_id
        trigger = replace(trigger, agent_run_id=run_id)
        existing = self._active.get(trigger.conversation_id)
        if existing is not None:
            if existing.task.done():
                self._collect_completed(trigger.conversation_id, existing)
            else:
                await self.interaction_agent.cancel(existing.run_id)
                existing.task.cancel()

        task = asyncio.create_task(self._run_trigger(trigger))
        self._active[trigger.conversation_id] = ActiveInteractiveTurn(
            trigger=trigger,
            task=task,
            run_id=run_id,
        )

    async def drain_completed(self) -> list[tuple[TurnTrigger, Any]]:
        for conversation_id, active in list(self._active.items()):
            if active.task.done():
                self._collect_completed(conversation_id, active)
        completed = list(self._completed)
        self._completed.clear()
        return completed

    def _collect_completed(
        self, conversation_id: str, active: ActiveInteractiveTurn
    ) -> None:
        self._active.pop(conversation_id, None)
        try:
            result = active.task.result()
        except asyncio.CancelledError:
            return
        self._completed.append((active.trigger, result))

    async def _run_trigger(self, trigger: TurnTrigger) -> Any:
        if self.runtime_factory is None:
            return await self.turn_runner.run_inbound_turn_async(trigger)

        runtime = self.runtime_factory()
        session = getattr(runtime, "session", None)
        try:
            result = await runtime.turn_runner.run_inbound_turn_async(trigger)
            if session is not None and callable(getattr(session, "commit", None)):
                session.commit()
            return result
        except BaseException:
            if session is not None and callable(getattr(session, "rollback", None)):
                session.rollback()
            raise
        finally:
            if session is not None and callable(getattr(session, "close", None)):
                session.close()
