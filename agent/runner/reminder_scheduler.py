from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime
from typing import Any, Callable

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from agent.reminder.models import (
    AgentOutputTarget,
    Reminder,
    ReminderFiredEvent,
    ReminderSchedule,
)
from agent.reminder.schedule import compute_next_fire_after_success

_scheduler_instance: "ReminderScheduler | None" = None


def set_reminder_scheduler_instance(scheduler: "ReminderScheduler | None") -> None:
    global _scheduler_instance
    _scheduler_instance = scheduler


def get_reminder_scheduler_instance() -> "ReminderScheduler | None":
    return _scheduler_instance


def _normalize_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ReminderScheduler:
    def __init__(
        self,
        reminder_dao: Any,
        fire_event_handler: Any,
        scheduler: AsyncIOScheduler | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.reminder_dao = reminder_dao
        self.fire_event_handler = fire_event_handler
        self.scheduler = scheduler or AsyncIOScheduler(timezone=UTC)
        self.now_provider = now_provider or (lambda: datetime.now(UTC))

    def start(self) -> None:
        self.scheduler.start()
        self.load_from_storage()

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)

    def load_from_storage(self) -> None:
        for reminder in self.reminder_dao.list_due_active():
            self.register_reminder(reminder)

    def register_reminder(self, reminder: Reminder | dict[str, Any]) -> None:
        reminder_id = self._reminder_id(reminder)
        lifecycle_state = self._field(reminder, "lifecycle_state")
        next_fire_at = self._field(reminder, "next_fire_at")
        if not reminder_id or lifecycle_state != "active" or next_fire_at is None:
            return

        next_fire_at = _normalize_utc(next_fire_at, "next_fire_at")
        now = _normalize_utc(self.now_provider(), "now")
        run_date = next_fire_at if next_fire_at > now else now
        self.scheduler.add_job(
            self._execute_job,
            trigger="date",
            id=self._job_id(reminder_id),
            replace_existing=True,
            run_date=run_date,
            kwargs={
                "reminder_id": reminder_id,
                "next_fire_at": next_fire_at,
            },
            misfire_grace_time=None,
        )

    def reschedule_reminder(self, reminder: Reminder | dict[str, Any]) -> None:
        self.register_reminder(reminder)

    def remove_reminder(self, reminder_id: str) -> None:
        try:
            self.scheduler.remove_job(self._job_id(reminder_id))
        except JobLookupError:
            return

    async def _execute_job(self, reminder_id: str, next_fire_at: datetime) -> None:
        expected_next_fire_at = _normalize_utc(next_fire_at, "next_fire_at")
        document = self.reminder_dao.get_reminder(reminder_id)
        if not document:
            return

        reminder = self._map_reminder(document)
        stored_next_fire_at = reminder.next_fire_at
        if (
            reminder.lifecycle_state != "active"
            or stored_next_fire_at is None
            or _normalize_utc(stored_next_fire_at, "stored_next_fire_at")
            != expected_next_fire_at
        ):
            return

        fired_at = _normalize_utc(self.now_provider(), "now")
        fire_id = f"{reminder_id}:{expected_next_fire_at.isoformat()}"
        event = ReminderFiredEvent(
            event_type="reminder.fired",
            event_id=str(uuid.uuid4()),
            fire_id=fire_id,
            reminder_id=reminder_id,
            owner_user_id=reminder.owner_user_id,
            title=reminder.title,
            fire_at=fired_at,
            scheduled_for=expected_next_fire_at,
            agent_output_target=reminder.agent_output_target,
        )

        handle = getattr(self.fire_event_handler, "handle", None)
        if callable(handle) and "handle" in dir(type(self.fire_event_handler)):
            result = handle(event)
        else:
            result = self.fire_event_handler(event)
        if inspect.isawaitable(result):
            result = await result

        finished_at = _normalize_utc(self.now_provider(), "now")
        if not result.ok:
            updates = {
                "lifecycle_state": "failed",
                "next_fire_at": None,
                "last_fired_at": finished_at,
                "last_event_ack_at": None,
                "last_error": result.error_message
                or result.error_code
                or "reminder fire failed",
                "failed_at": finished_at,
                "updated_at": finished_at,
            }
            if self.reminder_dao.atomic_apply_fire_failure(
                reminder_id,
                expected_next_fire_at,
                updates,
            ):
                self.remove_reminder(reminder_id)
            return

        next_fire_after_success = compute_next_fire_after_success(
            reminder.schedule,
            scheduled_for=expected_next_fire_at,
            now=finished_at,
        )
        lifecycle_state = (
            "active" if next_fire_after_success is not None else "completed"
        )
        updates = {
            "lifecycle_state": lifecycle_state,
            "next_fire_at": next_fire_after_success,
            "last_fired_at": finished_at,
            "last_event_ack_at": finished_at,
            "last_error": None,
            "updated_at": finished_at,
        }
        if lifecycle_state == "completed":
            updates["completed_at"] = finished_at

        applied = self.reminder_dao.atomic_apply_fire_success(
            reminder_id,
            expected_next_fire_at,
            updates,
        )
        if not applied:
            return
        if next_fire_after_success is None:
            self.remove_reminder(reminder_id)
            return
        self.reschedule_reminder({**document, **updates})

    def _job_id(self, reminder_id: Any) -> str:
        return f"reminder:{reminder_id}"

    def _reminder_id(self, reminder: Reminder | dict[str, Any]) -> str | None:
        if isinstance(reminder, Reminder):
            return reminder.id
        value = reminder.get("id") or reminder.get("_id")
        return str(value) if value is not None else None

    def _field(self, reminder: Reminder | dict[str, Any], field_name: str) -> Any:
        if isinstance(reminder, Reminder):
            return getattr(reminder, field_name)
        return reminder.get(field_name)

    def _map_reminder(self, document: Reminder | dict[str, Any]) -> Reminder:
        if isinstance(document, Reminder):
            return document
        schedule = document["schedule"]
        target = document["agent_output_target"]
        return Reminder(
            id=str(document.get("id") or document["_id"]),
            owner_user_id=document["owner_user_id"],
            title=document["title"],
            schedule=ReminderSchedule(
                anchor_at=schedule["anchor_at"],
                local_date=schedule["local_date"],
                local_time=schedule["local_time"],
                timezone=schedule["timezone"],
                rrule=schedule.get("rrule"),
            ),
            agent_output_target=AgentOutputTarget(
                conversation_id=target["conversation_id"],
                character_id=target["character_id"],
                route_key=target.get("route_key"),
            ),
            created_by_system=document["created_by_system"],
            lifecycle_state=document["lifecycle_state"],
            next_fire_at=document.get("next_fire_at"),
            last_fired_at=document.get("last_fired_at"),
            last_event_ack_at=document.get("last_event_ack_at"),
            last_error=document.get("last_error"),
            created_at=document["created_at"],
            updated_at=document["updated_at"],
            completed_at=document.get("completed_at"),
            cancelled_at=document.get("cancelled_at"),
            failed_at=document.get("failed_at"),
        )
