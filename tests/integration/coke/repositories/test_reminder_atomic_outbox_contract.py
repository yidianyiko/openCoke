from __future__ import annotations

from datetime import timedelta

import sqlalchemy as sa

from coke import schema
from coke.domains.reminder.models import ReminderBatchItem
from coke.domains.reminder.repository import PostgresReminderRepository
from coke.domains.reminder.service import ReminderService

from .conftest import ACCOUNT_A, NOW, OUTBOX_A, seed_account, seed_outbox


def test_postgres_reminder_create_commits_fact_and_outbox_together(postgres_session):
    seed_account(postgres_session)
    reminder_id = "60000000000000000000000000000010"
    outbox_id = "70000000000000000000000000000010"
    service = ReminderService(
        repository=PostgresReminderRepository(postgres_session),
        now=lambda: NOW,
        id_factory=_id_factory(reminder=reminder_id, outbox=outbox_id),
    )

    result = service.execute_batch(
        owner_account_id=ACCOUNT_A,
        items=[
            ReminderBatchItem(
                operation="create",
                content="pay rent",
                trigger_time=NOW + timedelta(hours=1),
                captured_timezone="UTC",
            )
        ],
    )

    reminder_row = (
        postgres_session.execute(
            sa.select(schema.reminder).where(schema.reminder.c.id == reminder_id)
        )
        .mappings()
        .one()
    )
    outbox_row = (
        postgres_session.execute(
            sa.select(schema.outbox).where(schema.outbox.c.id == outbox_id)
        )
        .mappings()
        .one()
    )

    assert result.items[0].state == "succeeded"
    assert str(reminder_row["id"]).replace("-", "") == reminder_id
    assert outbox_row["topic"] == "reminder.lifecycle"
    assert outbox_row["idempotency_key"] == f"reminder:create:{reminder_id}"
    assert outbox_row["payload"]["reminder_id"] == reminder_id
    assert outbox_row["payload"]["operation"] == "create"


def test_postgres_reminder_create_rolls_back_when_outbox_insert_fails(postgres_session):
    seed_account(postgres_session)
    seed_outbox(postgres_session, OUTBOX_A)
    reminder_id = "60000000000000000000000000000011"
    service = ReminderService(
        repository=PostgresReminderRepository(postgres_session),
        now=lambda: NOW,
        id_factory=_id_factory(reminder=reminder_id, outbox=OUTBOX_A),
    )

    result = service.execute_batch(
        owner_account_id=ACCOUNT_A,
        items=[
            ReminderBatchItem(
                operation="create",
                content="pay rent",
                trigger_time=NOW + timedelta(hours=1),
                captured_timezone="UTC",
            )
        ],
    )

    reminder_rows = (
        postgres_session.execute(
            sa.select(schema.reminder).where(schema.reminder.c.id == reminder_id)
        )
        .mappings()
        .all()
    )
    outbox_rows = (
        postgres_session.execute(
            sa.select(schema.outbox).where(schema.outbox.c.id == OUTBOX_A)
        )
        .mappings()
        .all()
    )

    assert result.items[0].state == "failed"
    assert result.items[0].reason == "duplicate_reminder_outbox_id"
    assert reminder_rows == []
    assert len(outbox_rows) == 1
    assert outbox_rows[0]["payload"] == {"seed": True}


def _id_factory(**ids: str):
    counters: dict[str, int] = {}

    def factory(prefix: str) -> str:
        counters[prefix] = counters.get(prefix, 0) + 1
        value = ids.get(prefix)
        if value is not None and counters[prefix] == 1:
            return value
        return f"900000000000000000000000{counters[prefix]:08d}"

    return factory
