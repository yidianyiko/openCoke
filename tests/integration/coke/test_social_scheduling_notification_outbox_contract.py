from __future__ import annotations

from datetime import timedelta
from itertools import count

import sqlalchemy as sa

from coke import schema
from coke.domains.social_scheduling.availability import BusyInterval
from coke.domains.social_scheduling.repository import PostgresSocialSchedulingRepository
from coke.domains.social_scheduling.service import SocialSchedulingService

from .repositories.conftest import (
    ACCOUNT_A,
    ACCOUNT_B,
    NOW,
    postgres_session,
    seed_account,
)


class AlwaysReachable:
    def has_usable_channel(self, account_id: str) -> bool:
        return True


class NoBusyReminders:
    def personal_busy_intervals(
        self,
        account_id: str,
        start,
        end,
        requester_timezone: str,
    ) -> list[BusyInterval]:
        return []


def test_friendship_notification_fact_and_outbox_are_written_atomically(
    postgres_session,
) -> None:
    service = _service(postgres_session)
    seed_account(postgres_session, ACCOUNT_A)
    seed_account(postgres_session, ACCOUNT_B)

    link = service.get_or_create_friend_link(ACCOUNT_A)
    result = service.establish_friendship_from_code(ACCOUNT_B, link.link_code or "")

    assert result.status == "created"
    fact = _one_fact(postgres_session, object_type="friendship")
    outbox = _outbox(postgres_session, fact["outbox_id"])
    assert outbox is not None
    assert outbox["topic"] == "turn.notification"
    assert outbox["payload"]["notification_fact_id"] == str(fact["id"]).replace("-", "")
    assert outbox["payload"]["recipient_account_ids"] == [ACCOUNT_A, ACCOUNT_B]


def test_shared_reminder_persists_projection_reminders_notification_and_outbox(
    postgres_session,
) -> None:
    service = _service(postgres_session)
    seed_account(postgres_session, ACCOUNT_A)
    seed_account(postgres_session, ACCOUNT_B)

    link = service.get_or_create_friend_link(ACCOUNT_A)
    service.establish_friendship_from_code(ACCOUNT_B, link.link_code or "")
    result = service.create_shared_reminder(
        creator_account_id=ACCOUNT_A,
        receiver_account_ids=[ACCOUNT_B],
        title="Team sync",
        local_trigger_at=NOW.replace(tzinfo=None) + timedelta(days=1),
        captured_timezone="UTC",
        duration_minutes=30,
    )

    assert result.status == "created"
    shared = _one_row(
        postgres_session,
        schema.shared_reminder,
        schema.shared_reminder.c.id == result.shared_reminder.id,
    )
    assert shared["status"] == "active"
    projections = (
        postgres_session.execute(
            sa.select(schema.reminder_projection).where(
                schema.reminder_projection.c.shared_reminder_id
                == result.shared_reminder.id
            )
        )
        .mappings()
        .all()
    )
    assert {str(row["account_id"]).replace("-", "") for row in projections} == {
        ACCOUNT_A,
        ACCOUNT_B,
    }
    reminder_rows = (
        postgres_session.execute(
            sa.select(schema.reminder).where(
                schema.reminder.c.shared_reminder_id == result.shared_reminder.id
            )
        )
        .mappings()
        .all()
    )
    assert {str(row["owner_account_id"]).replace("-", "") for row in reminder_rows} == {
        ACCOUNT_A,
        ACCOUNT_B,
    }
    assert {row["kind"] for row in reminder_rows} == {"shared_projection"}

    fact = _one_fact(postgres_session, object_type="shared_reminder")
    outbox = _outbox(postgres_session, fact["outbox_id"])
    assert outbox is not None
    assert outbox["topic"] == "turn.notification"
    assert outbox["payload"]["notification_fact_id"] == str(fact["id"]).replace("-", "")
    assert outbox["payload"]["recipient_account_ids"] == [ACCOUNT_B]


def test_cancel_shared_reminder_deletes_projection_reminders(
    postgres_session,
) -> None:
    service = _service(postgres_session)
    seed_account(postgres_session, ACCOUNT_A)
    seed_account(postgres_session, ACCOUNT_B)

    link = service.get_or_create_friend_link(ACCOUNT_A)
    service.establish_friendship_from_code(ACCOUNT_B, link.link_code or "")
    result = service.create_shared_reminder(
        creator_account_id=ACCOUNT_A,
        receiver_account_ids=[ACCOUNT_B],
        title="Team sync",
        local_trigger_at=NOW.replace(tzinfo=None) + timedelta(days=1),
        captured_timezone="UTC",
        duration_minutes=30,
    )
    projection_reminder_ids = [
        projection.reminder_id for projection in result.projections
    ]

    service.cancel_shared_reminder(ACCOUNT_B, result.shared_reminder.id)

    reminder_rows = (
        postgres_session.execute(
            sa.select(schema.reminder).where(
                schema.reminder.c.id.in_(projection_reminder_ids)
            )
        )
        .mappings()
        .all()
    )
    assert len(reminder_rows) == len(projection_reminder_ids)
    assert {row["lifecycle"] for row in reminder_rows} == {"deleted"}


def test_notification_fact_fk_failure_is_not_reported_as_duplicate_idempotency(
    postgres_session,
) -> None:
    repository = PostgresSocialSchedulingRepository(postgres_session)
    from coke.domains.social_scheduling.models import NotificationFact

    seed_account(postgres_session, ACCOUNT_A)
    fact = NotificationFact(
        id="a4000000000000000000000000000999",
        type="shared_reminder_created",
        actor_account_id=ACCOUNT_A,
        object_type="shared_reminder",
        object_id="a2000000000000000000000000000999",
        status="created",
        facts={"title": "Team sync"},
        facts_hash="facts-hash",
        idempotency_key="notification-key-fk-check",
        outbox_id="70000000000000000000000000000999",
        created_at=NOW,
    )

    try:
        repository.add_notification_fact(fact)
    except ValueError as error:
        assert str(error) != "duplicate_notification_fact_idempotency"


def _service(postgres_session) -> SocialSchedulingService:
    ids = count(1000)
    return SocialSchedulingService(
        repository=PostgresSocialSchedulingRepository(postgres_session),
        reachability=AlwaysReachable(),
        reminder_availability=NoBusyReminders(),
        now=lambda: NOW,
        id_factory=lambda _prefix: f"{next(ids):032x}",
        token_factory=lambda prefix: f"{prefix}_{next(ids)}",
    )


def _one_fact(postgres_session, *, object_type: str):
    rows = (
        postgres_session.execute(
            sa.select(schema.notification_fact)
            .where(schema.notification_fact.c.object_type == object_type)
            .order_by(
                schema.notification_fact.c.created_at, schema.notification_fact.c.id
            )
        )
        .mappings()
        .all()
    )
    assert len(rows) == 1
    return rows[0]


def _outbox(postgres_session, outbox_id):
    return (
        postgres_session.execute(
            sa.select(schema.outbox).where(schema.outbox.c.id == outbox_id)
        )
        .mappings()
        .one_or_none()
    )


def _one_row(postgres_session, table, *where):
    return postgres_session.execute(sa.select(table).where(*where)).mappings().one()
