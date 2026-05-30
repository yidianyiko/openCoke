from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from collections.abc import Mapping
from typing import Callable, Protocol

import sqlalchemy as sa
from sqlalchemy.orm import Session

from coke import schema
from coke.domains._pg import (
    db_id,
    insert_row,
    json_value,
    many,
    one_or_none,
    update_row,
    write_with_integrity,
)
from coke.domains.reminder.models import Reminder, ReminderFire, ReminderOutboxEvent


class ReminderRepository(Protocol):
    @property
    def outbox_records(self) -> list[ReminderOutboxEvent]: ...

    def add_reminder(self, reminder: Reminder) -> None: ...

    def save_reminder(self, reminder: Reminder) -> None: ...

    def add_reminder_with_outbox(
        self,
        reminder: Reminder,
        outbox: ReminderOutboxEvent,
        before_write: Callable[[], None] | None = None,
    ) -> None: ...

    def save_reminder_with_outbox(
        self,
        reminder: Reminder,
        outbox: ReminderOutboxEvent,
        before_write: Callable[[], None] | None = None,
    ) -> None: ...

    def get_outbox_by_idempotency_key(
        self, idempotency_key: str
    ) -> ReminderOutboxEvent | None: ...

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
        self.outbox_by_id: dict[str, ReminderOutboxEvent] = {}
        self.outbox_by_idempotency_key: dict[str, ReminderOutboxEvent] = {}

    @property
    def outbox_records(self) -> list[ReminderOutboxEvent]:
        return list(self.outbox_by_id.values())

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

    def add_reminder_with_outbox(
        self,
        reminder: Reminder,
        outbox: ReminderOutboxEvent,
        before_write: Callable[[], None] | None = None,
    ) -> None:
        self._atomic_write(
            lambda: (
                before_write() if before_write is not None else None,
                self.add_reminder(reminder),
                self._add_outbox(outbox),
            )
        )

    def save_reminder_with_outbox(
        self,
        reminder: Reminder,
        outbox: ReminderOutboxEvent,
        before_write: Callable[[], None] | None = None,
    ) -> None:
        self._atomic_write(
            lambda: (
                before_write() if before_write is not None else None,
                self.save_reminder(reminder),
                self._add_outbox(outbox),
            )
        )

    def get_outbox_by_idempotency_key(
        self, idempotency_key: str
    ) -> ReminderOutboxEvent | None:
        return self.outbox_by_idempotency_key.get(idempotency_key)

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

    def _add_outbox(self, outbox: ReminderOutboxEvent) -> None:
        if outbox.id in self.outbox_by_id:
            raise ValueError("duplicate_reminder_outbox_id")
        if outbox.idempotency_key in self.outbox_by_idempotency_key:
            raise ValueError("duplicate_reminder_outbox_idempotency_key")
        self.outbox_by_id[outbox.id] = outbox
        self.outbox_by_idempotency_key[outbox.idempotency_key] = outbox

    def _atomic_write(self, operation: Callable[[], object]) -> None:
        reminders = dict(self.reminders_by_id)
        outbox = dict(self.outbox_by_id)
        outbox_by_key = dict(self.outbox_by_idempotency_key)
        try:
            operation()
        except Exception:
            self.reminders_by_id = reminders
            self.outbox_by_id = outbox
            self.outbox_by_idempotency_key = outbox_by_key
            raise

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


class PostgresReminderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @property
    def outbox_records(self) -> list[ReminderOutboxEvent]:
        return [_outbox(row) for row in many(self.session, schema.outbox)]

    def add_reminder(self, reminder: Reminder) -> None:
        insert_row(
            self.session,
            schema.reminder,
            _reminder_values(reminder),
            {
                "pk_reminder": "duplicate_reminder_id",
                "uq_reminder_active_timed_duplicate": "duplicate_reminder",
                "uq_reminder_active_no_trigger_duplicate": "duplicate_reminder",
            },
            default_error="duplicate_reminder",
        )

    def save_reminder(self, reminder: Reminder) -> None:
        if self.get_reminder(reminder.id) is None:
            raise ValueError("reminder_not_found")
        if (
            update_row(
                self.session,
                schema.reminder,
                _reminder_values(reminder),
                {
                    "uq_reminder_active_timed_duplicate": "duplicate_reminder",
                    "uq_reminder_active_no_trigger_duplicate": "duplicate_reminder",
                },
                default_error="duplicate_reminder",
            )
            == 0
        ):
            raise ValueError("reminder_not_found")

    def add_reminder_with_outbox(
        self,
        reminder: Reminder,
        outbox: ReminderOutboxEvent,
        before_write: Callable[[], None] | None = None,
    ) -> None:
        if before_write is not None:
            before_write()

        def _write() -> None:
            self.session.execute(
                schema.reminder.insert().values(**_reminder_values(reminder))
            )
            self.session.execute(
                schema.outbox.insert().values(**_outbox_values(outbox))
            )

        write_with_integrity(
            self.session,
            _write,
            {
                "pk_reminder": "duplicate_reminder_id",
                "uq_reminder_active_timed_duplicate": "duplicate_reminder",
                "uq_reminder_active_no_trigger_duplicate": "duplicate_reminder",
                "pk_outbox": "duplicate_reminder_outbox_id",
                "uq_outbox_idempotency_key": "duplicate_reminder_outbox_idempotency_key",
            },
            default_error="reminder_outbox_write_failed",
        )

    def save_reminder_with_outbox(
        self,
        reminder: Reminder,
        outbox: ReminderOutboxEvent,
        before_write: Callable[[], None] | None = None,
    ) -> None:
        if self.get_reminder(reminder.id) is None:
            raise ValueError("reminder_not_found")
        if before_write is not None:
            before_write()

        def _write() -> None:
            rowcount = self.session.execute(
                schema.reminder.update()
                .where(schema.reminder.c.id == reminder.id)
                .values(**_reminder_values(reminder))
            ).rowcount
            if not rowcount:
                raise ValueError("reminder_not_found")
            self.session.execute(
                schema.outbox.insert().values(**_outbox_values(outbox))
            )

        write_with_integrity(
            self.session,
            _write,
            {
                "uq_reminder_active_timed_duplicate": "duplicate_reminder",
                "uq_reminder_active_no_trigger_duplicate": "duplicate_reminder",
                "pk_outbox": "duplicate_reminder_outbox_id",
                "uq_outbox_idempotency_key": "duplicate_reminder_outbox_idempotency_key",
            },
            default_error="reminder_outbox_write_failed",
        )

    def get_outbox_by_idempotency_key(
        self, idempotency_key: str
    ) -> ReminderOutboxEvent | None:
        row = one_or_none(
            self.session,
            schema.outbox,
            schema.outbox.c.idempotency_key == idempotency_key,
        )
        return _outbox(row) if row else None

    def get_reminder(self, reminder_id: str) -> Reminder | None:
        row = one_or_none(
            self.session, schema.reminder, schema.reminder.c.id == reminder_id
        )
        return _reminder(row) if row else None

    def list_active_reminders(self, owner_account_id: str) -> list[Reminder]:
        return [
            _reminder(row)
            for row in many(
                self.session,
                schema.reminder,
                schema.reminder.c.owner_account_id == owner_account_id,
                schema.reminder.c.lifecycle == "active",
                order_by=(schema.reminder.c.created_at, schema.reminder.c.id),
            )
        ]

    def list_due_reminders(self, due_at: datetime) -> list[Reminder]:
        return [
            _reminder(row)
            for row in many(
                self.session,
                schema.reminder,
                schema.reminder.c.lifecycle == "active",
                schema.reminder.c.next_fire_at.is_not(None),
                schema.reminder.c.next_fire_at <= due_at,
                order_by=(
                    schema.reminder.c.owner_account_id,
                    schema.reminder.c.next_fire_at,
                    schema.reminder.c.id,
                ),
            )
        ]

    def add_fire(self, fire: ReminderFire) -> None:
        insert_row(
            self.session,
            schema.reminder_fire,
            _fire_values(fire),
            {
                "pk_reminder_fire": "duplicate_fire_id",
                "uq_reminder_fire_occurrence": "duplicate_fire_occurrence",
            },
            default_error="duplicate_fire_occurrence",
        )

    def save_fire(self, fire: ReminderFire) -> None:
        existing = self.get_fire(fire.id)
        if existing is None:
            raise ValueError("fire_not_found")
        if (
            update_row(
                self.session,
                schema.reminder_fire,
                _fire_values(fire),
                {"uq_reminder_fire_occurrence": "duplicate_fire_occurrence"},
                default_error="duplicate_fire_occurrence",
            )
            == 0
        ):
            raise ValueError("fire_not_found")

    def get_fire(self, fire_id: str) -> ReminderFire | None:
        row = one_or_none(
            self.session, schema.reminder_fire, schema.reminder_fire.c.id == fire_id
        )
        return _fire(row) if row else None

    def get_fire_by_occurrence(
        self,
        reminder_id: str,
        occurrence_key: str,
    ) -> ReminderFire | None:
        row = one_or_none(
            self.session,
            schema.reminder_fire,
            schema.reminder_fire.c.reminder_id == reminder_id,
            schema.reminder_fire.c.occurrence_key == occurrence_key,
        )
        return _fire(row) if row else None

    def list_fires_for_owner(self, owner_account_id: str) -> list[ReminderFire]:
        statement = (
            sa.select(schema.reminder_fire)
            .join(
                schema.reminder,
                schema.reminder_fire.c.reminder_id == schema.reminder.c.id,
            )
            .where(schema.reminder.c.owner_account_id == owner_account_id)
            .order_by(schema.reminder_fire.c.due_at, schema.reminder_fire.c.id)
        )
        return [_fire(dict(row)) for row in self.session.execute(statement).mappings()]

    def discard_future_proactive(
        self, owner_account_id: str, discarded_at: datetime
    ) -> None:
        self.session.execute(
            schema.reminder.update()
            .where(
                schema.reminder.c.owner_account_id == owner_account_id,
                schema.reminder.c.kind == "proactive",
                schema.reminder.c.lifecycle == "active",
                schema.reminder.c.next_fire_at.is_not(None),
                schema.reminder.c.next_fire_at > discarded_at,
            )
            .values(lifecycle="deleted", updated_at=discarded_at)
        )


def _reminder_values(reminder: Reminder) -> dict:
    return {
        "id": reminder.id,
        "owner_account_id": reminder.owner_account_id,
        "content": reminder.content,
        "content_hash": reminder.content_hash,
        "kind": reminder.kind,
        "next_fire_at": reminder.next_fire_at,
        "recurrence_rule": json_value(reminder.recurrence_rule),
        "captured_timezone": reminder.captured_timezone,
        "duration_minutes": reminder.duration_minutes,
        "lifecycle": reminder.lifecycle,
        "hidden_from_calendar": reminder.hidden_from_calendar,
        "shared_reminder_id": reminder.shared_reminder_id,
        "created_at": reminder.created_at,
        "updated_at": reminder.updated_at,
    }


def _reminder(row: Mapping) -> Reminder:
    return Reminder(
        db_id(row["id"]),
        db_id(row["owner_account_id"]),
        row["content"],
        row["content_hash"],
        row["kind"],
        row["next_fire_at"],
        dict(row["recurrence_rule"]),
        row["captured_timezone"],
        row["duration_minutes"],
        row["lifecycle"],
        row["hidden_from_calendar"],
        (
            db_id(row["shared_reminder_id"])
            if row["shared_reminder_id"] is not None
            else None
        ),
        row["created_at"],
        row["updated_at"],
    )


def _fire_values(fire: ReminderFire) -> dict:
    return {
        "id": fire.id,
        "reminder_id": fire.reminder_id,
        "occurrence_key": fire.occurrence_key,
        "due_at": fire.due_at,
        "fire_state": fire.fire_state,
        "delivery_result": fire.delivery_result,
        "handled_at": fire.handled_at,
        "completed_at": fire.completed_at,
        "missed_catch_up": fire.missed_catch_up,
        "created_at": fire.created_at,
        "updated_at": fire.updated_at,
    }


def _fire(row: Mapping) -> ReminderFire:
    return ReminderFire(
        db_id(row["id"]),
        db_id(row["reminder_id"]),
        row["occurrence_key"],
        row["due_at"],
        row["fire_state"],
        row["delivery_result"],
        row["handled_at"],
        row["completed_at"],
        row["missed_catch_up"],
        row["created_at"],
        row["updated_at"],
    )


def _outbox_values(outbox: ReminderOutboxEvent) -> dict:
    return {
        "id": outbox.id,
        "topic": outbox.topic,
        "idempotency_key": outbox.idempotency_key,
        "payload": json_value(outbox.payload),
        "traceparent": outbox.traceparent,
        "status": outbox.status,
        "created_at": outbox.created_at,
        "published_at": outbox.published_at,
        "processed_at": outbox.processed_at,
        "acked_at": outbox.acked_at,
        "retry_count": outbox.retry_count,
        "last_error": outbox.last_error,
    }


def _outbox(row: Mapping) -> ReminderOutboxEvent:
    return ReminderOutboxEvent(
        db_id(row["id"]),
        row["topic"],
        row["idempotency_key"],
        dict(row["payload"]),
        row["traceparent"],
        row["status"],
        row["created_at"],
        row["published_at"],
        row["processed_at"],
        row["acked_at"],
        row["retry_count"],
        row["last_error"],
    )
