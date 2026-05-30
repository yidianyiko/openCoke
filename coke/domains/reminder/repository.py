from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Protocol

from coke.domains.reminder.models import Reminder, ReminderFire


class ReminderRepository(Protocol):
    def add_reminder(self, reminder: Reminder) -> None: ...

    def save_reminder(self, reminder: Reminder) -> None: ...

    def get_reminder(self, reminder_id: str) -> Reminder | None: ...

    def list_active_reminders(self, owner_account_id: str) -> list[Reminder]: ...

    def list_due_reminders(self, due_at: datetime) -> list[Reminder]: ...

    def add_fire(self, fire: ReminderFire) -> None: ...

    def save_fire(self, fire: ReminderFire) -> None: ...

    def get_fire(self, fire_id: str) -> ReminderFire | None: ...

    def get_fire_by_occurrence(
        self,
        reminder_id: str,
        occurrence_key: str,
    ) -> ReminderFire | None: ...

    def list_fires_for_owner(self, owner_account_id: str) -> list[ReminderFire]: ...


class InMemoryReminderRepository:
    def __init__(self) -> None:
        self.reminders_by_id: dict[str, Reminder] = {}
        self.fires_by_id: dict[str, ReminderFire] = {}
        self.fires_by_occurrence: dict[tuple[str, str], ReminderFire] = {}

    def add_reminder(self, reminder: Reminder) -> None:
        if reminder.id in self.reminders_by_id:
            raise ValueError("duplicate_reminder_id")
        self._assert_no_duplicate(reminder)
        self.reminders_by_id[reminder.id] = reminder

    def save_reminder(self, reminder: Reminder) -> None:
        if reminder.id not in self.reminders_by_id:
            raise ValueError("reminder_not_found")
        self._assert_no_duplicate(reminder)
        self.reminders_by_id[reminder.id] = reminder

    def get_reminder(self, reminder_id: str) -> Reminder | None:
        return self.reminders_by_id.get(reminder_id)

    def list_active_reminders(self, owner_account_id: str) -> list[Reminder]:
        return [
            reminder
            for reminder in self.reminders_by_id.values()
            if reminder.owner_account_id == owner_account_id
            and reminder.lifecycle == "active"
        ]

    def list_due_reminders(self, due_at: datetime) -> list[Reminder]:
        return sorted(
            [
                reminder
                for reminder in self.reminders_by_id.values()
                if reminder.lifecycle == "active"
                and reminder.next_fire_at is not None
                and reminder.next_fire_at <= due_at
            ],
            key=lambda reminder: (
                reminder.owner_account_id,
                reminder.next_fire_at,
                reminder.id,
            ),
        )

    def add_fire(self, fire: ReminderFire) -> None:
        key = (fire.reminder_id, fire.occurrence_key)
        if fire.id in self.fires_by_id:
            raise ValueError("duplicate_fire_id")
        if key in self.fires_by_occurrence:
            raise ValueError("duplicate_fire_occurrence")
        self.fires_by_id[fire.id] = fire
        self.fires_by_occurrence[key] = fire

    def save_fire(self, fire: ReminderFire) -> None:
        existing = self.fires_by_id.get(fire.id)
        if existing is None:
            raise ValueError("fire_not_found")
        old_key = (existing.reminder_id, existing.occurrence_key)
        new_key = (fire.reminder_id, fire.occurrence_key)
        if old_key != new_key and new_key in self.fires_by_occurrence:
            raise ValueError("duplicate_fire_occurrence")
        self.fires_by_occurrence.pop(old_key, None)
        self.fires_by_id[fire.id] = fire
        self.fires_by_occurrence[new_key] = fire

    def get_fire(self, fire_id: str) -> ReminderFire | None:
        return self.fires_by_id.get(fire_id)

    def get_fire_by_occurrence(
        self,
        reminder_id: str,
        occurrence_key: str,
    ) -> ReminderFire | None:
        return self.fires_by_occurrence.get((reminder_id, occurrence_key))

    def list_fires_for_owner(self, owner_account_id: str) -> list[ReminderFire]:
        reminder_ids = {
            reminder.id
            for reminder in self.reminders_by_id.values()
            if reminder.owner_account_id == owner_account_id
        }
        return sorted(
            [
                fire
                for fire in self.fires_by_id.values()
                if fire.reminder_id in reminder_ids
            ],
            key=lambda fire: (fire.due_at, fire.id),
        )

    def _assert_no_duplicate(self, candidate: Reminder) -> None:
        if candidate.lifecycle != "active":
            return
        for reminder in self.reminders_by_id.values():
            if reminder.id == candidate.id or reminder.lifecycle != "active":
                continue
            if (
                reminder.owner_account_id != candidate.owner_account_id
                or reminder.content_hash != candidate.content_hash
            ):
                continue
            if candidate.next_fire_at is None and reminder.next_fire_at is None:
                raise ValueError("duplicate_reminder")
            if (
                candidate.next_fire_at is not None
                and reminder.next_fire_at == candidate.next_fire_at
            ):
                raise ValueError("duplicate_reminder")

    def discard_future_proactive(
        self, owner_account_id: str, discarded_at: datetime
    ) -> None:
        for reminder in list(self.reminders_by_id.values()):
            if (
                reminder.owner_account_id == owner_account_id
                and reminder.kind == "proactive"
                and reminder.lifecycle == "active"
                and reminder.next_fire_at is not None
                and reminder.next_fire_at > discarded_at
            ):
                self.reminders_by_id[reminder.id] = replace(
                    reminder,
                    lifecycle="deleted",
                    updated_at=discarded_at,
                )
