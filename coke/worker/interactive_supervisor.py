from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any, Callable

from coke.turn.context import TurnTrigger
from coke.turn.runner import close_boundary_observer


@dataclass(slots=True)
class InteractiveTurnLifecycle:
    close_committed: bool = False


@dataclass(slots=True)
class ActiveInteractiveTurn:
    trigger: TurnTrigger
    task: asyncio.Task[Any]
    run_id: str
    lifecycle: InteractiveTurnLifecycle


@dataclass(slots=True)
class RetiredInteractiveTurn:
    active: ActiveInteractiveTurn
    publish_completion: bool


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
        self._retired: list[RetiredInteractiveTurn] = []
        self._cancel_tasks: list[asyncio.Task[Any]] = []
        self._completed: list[tuple[TurnTrigger, Any]] = []
        self._failures: list[tuple[TurnTrigger | None, Exception]] = []

    async def submit(self, trigger: TurnTrigger) -> None:
        run_id = trigger.agent_run_id or trigger.trigger_id
        trigger = replace(trigger, agent_run_id=run_id)
        existing = self._active.get(trigger.conversation_id)
        if existing is not None:
            if existing.task.done():
                self._collect_completed(trigger.conversation_id, existing)
            elif existing.lifecycle.close_committed:
                self._retired.append(
                    RetiredInteractiveTurn(existing, publish_completion=True)
                )
            else:
                existing.task.cancel()
                self._retired.append(
                    RetiredInteractiveTurn(existing, publish_completion=False)
                )
                self._cancel_tasks.append(
                    asyncio.create_task(self.interaction_agent.cancel(existing.run_id))
                )

        lifecycle = InteractiveTurnLifecycle()
        task = asyncio.create_task(self._run_trigger(trigger, lifecycle))
        self._active[trigger.conversation_id] = ActiveInteractiveTurn(
            trigger=trigger,
            task=task,
            run_id=run_id,
            lifecycle=lifecycle,
        )

    async def drain_completed(self) -> list[tuple[TurnTrigger, Any]]:
        self._collect_done_retired()
        self._collect_done_cancel_tasks()
        for conversation_id, active in list(self._active.items()):
            if active.task.done():
                self._collect_completed(conversation_id, active)
        completed = list(self._completed)
        self._completed.clear()
        return completed

    async def drain_failures(self) -> list[tuple[TurnTrigger | None, Exception]]:
        self._collect_done_retired()
        self._collect_done_cancel_tasks()
        for conversation_id, active in list(self._active.items()):
            if active.task.done():
                self._collect_completed(conversation_id, active)
        failures = list(self._failures)
        self._failures.clear()
        return failures

    def _collect_completed(
        self, conversation_id: str, active: ActiveInteractiveTurn
    ) -> None:
        self._active.pop(conversation_id, None)
        self._collect_task_result(active, publish_completion=True)

    def _collect_done_retired(self) -> None:
        pending: list[RetiredInteractiveTurn] = []
        for retired in self._retired:
            if retired.active.task.done():
                self._collect_task_result(
                    retired.active,
                    publish_completion=retired.publish_completion,
                )
            else:
                pending.append(retired)
        self._retired = pending

    def _collect_done_cancel_tasks(self) -> None:
        pending: list[asyncio.Task[Any]] = []
        for task in self._cancel_tasks:
            if task.done():
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except Exception as error:
                    self._failures.append((None, error))
            else:
                pending.append(task)
        self._cancel_tasks = pending

    def _collect_task_result(
        self,
        active: ActiveInteractiveTurn,
        *,
        publish_completion: bool,
    ) -> None:
        try:
            result = active.task.result()
        except asyncio.CancelledError:
            return
        except Exception as error:
            self._failures.append((active.trigger, error))
            return
        if publish_completion:
            self._completed.append((active.trigger, result))

    async def _run_trigger(
        self,
        trigger: TurnTrigger,
        lifecycle: InteractiveTurnLifecycle,
    ) -> Any:
        def mark_close_committed() -> None:
            lifecycle.close_committed = True

        with close_boundary_observer(mark_close_committed):
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
