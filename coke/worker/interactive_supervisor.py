from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any, Callable

from coke.turn.context import TurnTrigger
from coke.turn.runner import (
    INTERRUPTED_BY_NEWER_INBOUND_CANCEL_REASON,
    close_boundary_observer,
)


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


@dataclass(slots=True)
class ProviderCancelTask:
    trigger: TurnTrigger | None
    run_id: str
    task: asyncio.Task[Any]


@dataclass(frozen=True, slots=True)
class InteractiveTurnFailure:
    trigger: TurnTrigger | None
    error: Exception
    source: str

    def __iter__(self):
        yield self.trigger
        yield self.error


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
        self._pending: dict[str, TurnTrigger] = {}
        self._retired: list[RetiredInteractiveTurn] = []
        self._cancel_tasks: list[ProviderCancelTask] = []
        self._completed: list[tuple[TurnTrigger, Any]] = []
        self._failures: list[InteractiveTurnFailure] = []

    async def submit(self, trigger: TurnTrigger) -> None:
        run_id = trigger.agent_run_id or trigger.trigger_id
        trigger = replace(trigger, agent_run_id=run_id)
        existing = self._active.get(trigger.conversation_id)
        if existing is not None:
            if existing.task.done():
                self._collect_completed(trigger.conversation_id, existing)
                existing = self._active.get(trigger.conversation_id)
            if existing is not None:
                if existing.lifecycle.close_committed:
                    self._pending[trigger.conversation_id] = trigger
                    return
                existing.task.cancel(INTERRUPTED_BY_NEWER_INBOUND_CANCEL_REASON)
                self._retired.append(
                    RetiredInteractiveTurn(existing, publish_completion=False)
                )
                self._cancel_tasks.append(
                    ProviderCancelTask(
                        existing.trigger,
                        existing.run_id,
                        asyncio.create_task(
                            self.interaction_agent.cancel(existing.run_id)
                        ),
                    )
                )
                self._active.pop(trigger.conversation_id, None)

        self._start_trigger(trigger, run_id)

    async def cancel_provider_runs(
        self,
        run_ids: tuple[str, ...],
        trigger: TurnTrigger | None = None,
    ) -> None:
        self._collect_done_cancel_tasks()
        for run_id in run_ids:
            if not isinstance(run_id, str) or not run_id:
                continue
            self._cancel_tasks.append(
                ProviderCancelTask(
                    trigger,
                    run_id,
                    asyncio.create_task(self.interaction_agent.cancel(run_id)),
                )
            )

    async def submit_if_idle(self, trigger: TurnTrigger) -> bool:
        self._collect_done_retired()
        self._collect_done_cancel_tasks()
        existing = self._active.get(trigger.conversation_id)
        if existing is not None:
            if not existing.task.done():
                return False
            self._collect_completed(trigger.conversation_id, existing)
        if (
            trigger.conversation_id in self._active
            or trigger.conversation_id in self._pending
        ):
            return False
        if any(
            completed_trigger.conversation_id == trigger.conversation_id
            for completed_trigger, _result in self._completed
        ):
            return False
        await self.submit(trigger)
        return True

    def _start_trigger(self, trigger: TurnTrigger, run_id: str | None = None) -> None:
        run_id = run_id or trigger.agent_run_id or trigger.trigger_id
        trigger = replace(trigger, agent_run_id=run_id)
        lifecycle = InteractiveTurnLifecycle()
        task = asyncio.create_task(self._run_trigger(trigger, lifecycle))
        self._active[trigger.conversation_id] = ActiveInteractiveTurn(
            trigger=trigger,
            task=task,
            run_id=run_id,
            lifecycle=lifecycle,
        )

    def _start_pending_if_any(self, conversation_id: str) -> None:
        pending = self._pending.pop(conversation_id, None)
        if pending is not None:
            self._start_trigger(pending)

    async def drain_completed(self) -> list[tuple[TurnTrigger, Any]]:
        self._collect_done_retired()
        self._collect_done_cancel_tasks()
        for conversation_id, active in list(self._active.items()):
            if active.task.done():
                self._collect_completed(conversation_id, active)
        completed = list(self._completed)
        self._completed.clear()
        return completed

    async def restore_completed(self, completed: list[tuple[TurnTrigger, Any]]) -> None:
        self._completed = list(completed) + self._completed

    async def drain_failures(self) -> list[InteractiveTurnFailure]:
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
        self._start_pending_if_any(conversation_id)

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
        pending: list[ProviderCancelTask] = []
        for cancel_task in self._cancel_tasks:
            if cancel_task.task.done():
                try:
                    cancel_task.task.result()
                except asyncio.CancelledError:
                    pass
                except Exception as error:
                    self._failures.append(
                        InteractiveTurnFailure(
                            trigger=cancel_task.trigger,
                            error=error,
                            source="provider_cancel",
                        )
                    )
            else:
                pending.append(cancel_task)
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
            self._failures.append(
                InteractiveTurnFailure(
                    trigger=active.trigger,
                    error=error,
                    source="turn_task",
                )
            )
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
