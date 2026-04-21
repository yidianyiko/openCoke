from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime
from typing import Any, Callable

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler


_scheduler_instance: "DeferredActionScheduler | None" = None


def set_deferred_action_scheduler_instance(
    scheduler: "DeferredActionScheduler | None",
) -> None:
    global _scheduler_instance
    _scheduler_instance = scheduler


def get_deferred_action_scheduler_instance() -> "DeferredActionScheduler | None":
    return _scheduler_instance


class DeferredActionScheduler:
    def __init__(
        self,
        action_dao: Any,
        executor: Callable[..., Any],
        scheduler: AsyncIOScheduler | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.action_dao = action_dao
        self.executor = executor
        self.scheduler = scheduler or AsyncIOScheduler(timezone=UTC)
        self.now_provider = now_provider or (lambda: datetime.now(UTC))

    def start(self) -> None:
        self.scheduler.start()
        self.load_from_storage()

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)

    def load_from_storage(self) -> None:
        now = self.now_provider()
        self.action_dao.reconcile_expired_leases(now)
        for action in self.action_dao.list_active_actions():
            self.register_action(action, now=now)

    def register_action(self, action: dict[str, Any], now: datetime | None = None) -> None:
        if action.get("lifecycle_state") != "active":
            return

        scheduled_for = action.get("next_run_at")
        if scheduled_for is None:
            return

        current_now = now or self.now_provider()
        run_date = scheduled_for if scheduled_for > current_now else current_now
        self.scheduler.add_job(
            self._execute_job,
            trigger="date",
            id=self._job_id(action["_id"]),
            replace_existing=True,
            run_date=run_date,
            kwargs={
                "action_id": str(action["_id"]),
                "scheduled_for": scheduled_for,
                "revision": action["revision"],
            },
            misfire_grace_time=None,
        )

    def remove_action(self, action_id: str) -> None:
        try:
            self.scheduler.remove_job(self._job_id(action_id))
        except JobLookupError:
            return

    def reschedule_action(self, action: dict[str, Any]) -> None:
        self.register_action(action)

    def _job_id(self, action_id: Any) -> str:
        return f"deferred-action:{action_id}"

    def _execute_job(
        self,
        action_id: str,
        scheduled_for: datetime,
        revision: int,
    ) -> None:
        result = self.executor(
            action_id=action_id,
            scheduled_for=scheduled_for,
            revision=revision,
        )
        if inspect.isawaitable(result):
            asyncio.create_task(result)
