from __future__ import annotations

from dataclasses import replace

import pytest

from coke.domains.calendar_import.models import (
    CalendarAuthorizationState,
    CalendarImportItem,
    CalendarImportRun,
)
from coke.domains.calendar_import.service import (
    InMemoryCalendarImportRepository,
    PostgresCalendarImportRepository,
)

from .conftest import ACCOUNT_A, AUTH_ARTIFACT_A, NOW, REMINDER_A, seed_account, seed_reminder


def _run() -> CalendarImportRun:
    return CalendarImportRun(
        "b0000000000000000000000000000001",
        ACCOUNT_A,
        "google_calendar",
        "google-user",
        AUTH_ARTIFACT_A,
        "in_progress",
        0,
        0,
        0,
        0,
        NOW,
        None,
        NOW,
        NOW,
    )


def _item(item_id: str = "b1000000000000000000000000000001") -> CalendarImportItem:
    return CalendarImportItem(
        item_id,
        "b0000000000000000000000000000001",
        "primary",
        "event-1",
        "event-1-instance",
        "imported",
        None,
        {"etag": "abc"},
        REMINDER_A,
        NOW,
    )


@pytest.fixture(params=["memory", "postgres"])
def repository(request, postgres_session):
    if request.param == "memory":
        return InMemoryCalendarImportRepository()
    seed_reminder(postgres_session, ACCOUNT_A, REMINDER_A)
    postgres_session.execute(
        __import__("coke.schema").schema.auth_artifact.insert().values(
            id=AUTH_ARTIFACT_A,
            account_id=ACCOUNT_A,
            target_account_id=None,
            type="calendar_authorization",
            purpose="google_calendar",
            delivery="oauth",
            token_hash="google-oauth-token",
            browser_session=None,
            continuation={},
            expires_at=NOW,
            consumed_at=None,
            delivery_state="active",
            resend_count=0,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    return PostgresCalendarImportRepository(postgres_session)


def test_calendar_run_item_and_authorization_round_trip(repository) -> None:
    run = _run()
    item = _item()
    repository.add_run(run)
    repository.add_item(item)
    repository.save_authorization_state(
        CalendarAuthorizationState(ACCOUNT_A, "google-oauth-token", "stopped", NOW)
    )

    completed = replace(run, status="completed", imported_count=1, completed_at=NOW)
    repository.save_run(completed)

    assert repository.get_run(run.id) == completed
    assert repository.get_item_by_source_occurrence(
        "primary", "event-1", "event-1-instance"
    ) == item
    assert repository.list_items_for_run(run.id) == [item]
    assert repository.get_authorization_state(
        ACCOUNT_A, "google-oauth-token"
    ) == CalendarAuthorizationState(ACCOUNT_A, "google-oauth-token", "stopped", NOW)


def test_calendar_uniqueness_and_missing_errors_match_in_memory(repository) -> None:
    repository.add_run(_run())
    repository.add_item(_item())

    with pytest.raises(ValueError, match="duplicate_calendar_import_run_id"):
        repository.add_run(_run())

    with pytest.raises(ValueError, match="calendar_import_run_not_found"):
        repository.save_run(replace(_run(), id="b0000000000000000000000000000002"))

    with pytest.raises(ValueError, match="duplicate_calendar_import_source_occurrence"):
        repository.add_item(_item("b1000000000000000000000000000002"))
