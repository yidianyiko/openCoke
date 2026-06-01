from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from coke.domains.reminder.models import Reminder, ReminderFire
from coke.domains.reminder.repository import (
    InMemoryReminderRepository,
    PostgresReminderRepository,
)

from .conftest import ACCOUNT_A, NOW, REMINDER_A, seed_account


def _reminder(
    reminder_id: str = REMINDER_A,
    *,
    content_hash: str = "call-alice",
    next_fire_at=NOW + timedelta(hours=1),
    kind: str = "timed",
) -> Reminder:
    return Reminder(
        reminder_id,
        ACCOUNT_A,
        "Call Alice",
        content_hash,
        kind,
        next_fire_at,
        {},
        "UTC",
        15,
        "active",
        False,
        None,
        NOW,
        NOW,
    )


def _fire(fire_id: str = "61000000000000000000000000000001") -> ReminderFire:
    return ReminderFire(
        fire_id,
        REMINDER_A,
        "2026-05-30T13:00:00+00:00",
        NOW + timedelta(hours=1),
        "pending",
        None,
        None,
        None,
        False,
        NOW,
        NOW,
    )


@pytest.fixture(params=["memory", "postgres"])
def repository(request, postgres_session):
    if request.param == "memory":
        return InMemoryReminderRepository()
    seed_account(postgres_session)
    return PostgresReminderRepository(postgres_session)


def test_reminder_and_fire_round_trip(repository) -> None:
    reminder = _reminder()
    fire = _fire()
    repository.add_reminder(reminder)
    repository.add_fire(fire)

    assert repository.get_reminder(reminder.id) == reminder
    assert repository.list_active_reminders(ACCOUNT_A) == [reminder]
    assert repository.list_due_reminders(NOW + timedelta(hours=2)) == [reminder]
    assert repository.get_fire(fire.id) == fire
    assert (
        repository.get_fire_by_occurrence(fire.reminder_id, fire.occurrence_key) == fire
    )
    assert repository.list_fires_for_owner(ACCOUNT_A) == [fire]

    completed_fire = replace(fire, fire_state="completed", completed_at=NOW)
    repository.save_fire(completed_fire)
    assert repository.get_fire(fire.id) == completed_fire


def test_reminder_duplicate_and_missing_errors_match_in_memory(repository) -> None:
    repository.add_reminder(_reminder())

    with pytest.raises(ValueError, match="duplicate_reminder"):
        repository.add_reminder(_reminder("60000000000000000000000000000002"))

    with pytest.raises(ValueError, match="duplicate_reminder"):
        repository.add_reminder(
            _reminder(
                "60000000000000000000000000000003",
                next_fire_at=None,
                kind="no_trigger_time",
            )
        )
        repository.add_reminder(
            _reminder(
                "60000000000000000000000000000004",
                next_fire_at=None,
                kind="no_trigger_time",
            )
        )

    with pytest.raises(ValueError, match="reminder_not_found"):
        repository.save_reminder(
            _reminder("60000000000000000000000000000005", content_hash="new")
        )

    repository.add_fire(_fire())
    with pytest.raises(ValueError, match="duplicate_fire_occurrence"):
        repository.add_fire(_fire("61000000000000000000000000000002"))


def test_discard_future_proactive(repository) -> None:
    proactive = _reminder(
        "60000000000000000000000000000006",
        content_hash="check-in",
        next_fire_at=NOW + timedelta(days=1),
        kind="proactive",
    )
    repository.add_reminder(proactive)

    repository.discard_future_proactive(ACCOUNT_A, NOW)

    assert repository.get_reminder(proactive.id).lifecycle == "deleted"
