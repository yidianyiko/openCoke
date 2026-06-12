from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from itertools import count
from uuid import NAMESPACE_URL, uuid5

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from coke import schema
from coke.domains.calendar_import.google import GoogleCalendarClientPort
from coke.domains.calendar_import.models import CalendarSourceEvent
from coke.domains.calendar_import.service import (
    CalendarImportService,
    PostgresCalendarImportRepository,
)
from coke.domains.reminder.models import ReminderBatchItem
from coke.domains.reminder.repository import PostgresReminderRepository
from coke.domains.reminder.service import ReminderService
from coke.domains.settings.repository import PostgresSettingsRepository
from coke.domains.settings.service import SettingsService
from coke.domains.social_scheduling.availability import BusyInterval
from coke.domains.social_scheduling.repository import PostgresSocialSchedulingRepository
from coke.domains.social_scheduling.service import SocialSchedulingService

NOW = datetime(2026, 6, 12, 12, 0, tzinfo=UTC)
ACCOUNT_ID = uuid5(NAMESPACE_URL, "coke:phase0-autonomous-commit:account").hex


@pytest.fixture
def pg_session() -> Iterator[tuple[Session, sa.Engine, list[str]]]:
    database_url = os.environ.get("COKE_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("COKE_TEST_DATABASE_URL is not set")

    engine = sa.create_engine(database_url, future=True)
    generated_ids: list[str] = []
    with engine.begin() as connection:
        _cleanup(connection, generated_ids)
        connection.execute(
            schema.account.insert().values(
                id=ACCOUNT_ID,
                origin="web_first",
                default_timezone="UTC",
                lifecycle="active",
                created_at=NOW,
                updated_at=NOW,
            )
        )

    session = Session(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield session, engine, generated_ids
    finally:
        session.rollback()
        session.close()
        with engine.begin() as connection:
            _cleanup(connection, generated_ids)
        engine.dispose()


def test_execute_writes_are_not_durable_until_close_boundary(
    pg_session: tuple[Session, sa.Engine, list[str]],
) -> None:
    session, engine, generated_ids = pg_session
    id_factory = _id_factory(generated_ids)

    reminder_service = ReminderService(
        repository=PostgresReminderRepository(session),
        now=lambda: NOW,
        id_factory=id_factory,
    )
    social_service = SocialSchedulingService(
        repository=PostgresSocialSchedulingRepository(session),
        reachability=_Reachability(),
        reminder_availability=_ReminderAvailability(),
        now=lambda: NOW,
        id_factory=id_factory,
        token_factory=_token_factory(),
    )
    settings_service = SettingsService(
        repository=PostgresSettingsRepository(session),
        now=lambda: NOW,
        id_factory=id_factory,
    )
    calendar_service = CalendarImportService(
        repository=PostgresCalendarImportRepository(session),
        google_client=_GoogleCalendarClient(
            [
                CalendarSourceEvent(
                    provider_calendar_id="primary",
                    source_event_id="phase0-event",
                    title="Imported workout",
                    description="Calendar import write",
                    start=NOW + timedelta(hours=3),
                    end=NOW + timedelta(hours=4),
                    all_day=False,
                    source_metadata={"source": "phase0"},
                )
            ]
        ),
        reminder_service=reminder_service,
        access_gate=_AccessGate(),
        now=lambda: NOW,
        id_factory=id_factory,
    )

    reminder_result = reminder_service.execute_batch(
        owner_account_id=ACCOUNT_ID,
        items=[
            ReminderBatchItem(
                operation="create",
                content="phase0 direct reminder",
                trigger_time=NOW + timedelta(hours=1),
                captured_timezone="UTC",
                duration_minutes=15,
                turn_id="turn-phase0",
                item_index=0,
            )
        ],
    )
    reminder_id = reminder_result.items[0].reminder_id
    assert reminder_id is not None
    assert _exists(session, schema.reminder, schema.reminder.c.id == reminder_id)
    assert not _fresh_exists(engine, schema.reminder, schema.reminder.c.id == reminder_id)

    friend_link = social_service.get_or_create_friend_link(
        ACCOUNT_ID,
        commit_guard=lambda: None,
    )
    assert _exists(
        session,
        schema.friend_link,
        schema.friend_link.c.id == friend_link.friend_link_id,
    )
    assert not _fresh_exists(
        engine,
        schema.friend_link,
        schema.friend_link.c.id == friend_link.friend_link_id,
    )

    settings_view = settings_service.update_settings(
        ACCOUNT_ID,
        default_timezone="Asia/Tokyo",
    )
    assert settings_view.default_timezone == "Asia/Tokyo"
    assert _scalar(
        session,
        sa.select(schema.account.c.default_timezone).where(
            schema.account.c.id == ACCOUNT_ID
        ),
    ) == "Asia/Tokyo"
    assert _fresh_scalar(
        engine,
        sa.select(schema.account.c.default_timezone).where(
            schema.account.c.id == ACCOUNT_ID
        ),
    ) == "UTC"
    assert not _fresh_exists(
        engine,
        schema.agent_settings,
        schema.agent_settings.c.account_id == ACCOUNT_ID,
    )

    calendar_summary = calendar_service.import_google_calendar(
        account_id=ACCOUNT_ID,
        auth_handle="phase0-auth",
        provider_account_id="phase0-google",
        visible_start=NOW,
        visible_end=NOW + timedelta(days=7),
        captured_timezone="UTC",
    )
    imported_item = calendar_summary.items[0]
    assert imported_item.reminder_id is not None
    assert _exists(
        session,
        schema.calendar_import_run,
        schema.calendar_import_run.c.id == calendar_summary.run_id,
    )
    assert _exists(
        session,
        schema.calendar_import_item,
        schema.calendar_import_item.c.id == imported_item.id,
    )
    assert _exists(
        session,
        schema.reminder,
        schema.reminder.c.id == imported_item.reminder_id,
    )
    assert not _fresh_exists(
        engine,
        schema.calendar_import_run,
        schema.calendar_import_run.c.id == calendar_summary.run_id,
    )
    assert not _fresh_exists(
        engine,
        schema.calendar_import_item,
        schema.calendar_import_item.c.id == imported_item.id,
    )
    assert not _fresh_exists(
        engine,
        schema.reminder,
        schema.reminder.c.id == imported_item.reminder_id,
    )


class _Reachability:
    def has_usable_channel(self, account_id: str) -> bool:
        return account_id == ACCOUNT_ID


class _ReminderAvailability:
    def personal_busy_intervals(
        self,
        account_id: str,
        start: datetime,
        end: datetime,
        requester_timezone: str,
    ) -> list[BusyInterval]:
        return []


class _GoogleCalendarClient(GoogleCalendarClientPort):
    def __init__(self, events: list[CalendarSourceEvent]) -> None:
        self.events = events

    def list_events(
        self,
        auth_handle: str,
        visible_start: datetime,
        visible_end: datetime,
    ) -> list[CalendarSourceEvent]:
        return list(self.events)

    def revoke_authorization(self, auth_handle: str) -> None:
        raise AssertionError("not used by this guard")


class _AccessGate:
    def check_access_for_action(self, account_id: str, action: str):
        return type("Decision", (), {"allowed": True, "fact": None})()


def _id_factory(generated_ids: list[str]):
    counter = count(1)

    def factory(prefix: str) -> str:
        value = uuid5(
            NAMESPACE_URL,
            f"coke:phase0-autonomous-commit:{prefix}:{next(counter)}",
        ).hex
        generated_ids.append(value)
        return value

    return factory


def _token_factory():
    counter = count(1)

    def factory(prefix: str) -> str:
        return f"phase0-{prefix}-{next(counter)}"

    return factory


def _exists(session: Session, table: sa.Table, *where) -> bool:
    return _scalar(session, sa.select(table.c.id).where(*where).limit(1)) is not None


def _fresh_exists(engine: sa.Engine, table: sa.Table, *where) -> bool:
    return _fresh_scalar(engine, sa.select(table.c.id).where(*where).limit(1)) is not None


def _scalar(session: Session, statement: sa.Select):
    return session.execute(statement).scalar_one_or_none()


def _fresh_scalar(engine: sa.Engine, statement: sa.Select):
    with Session(bind=engine, autoflush=False, expire_on_commit=False) as fresh:
        return fresh.execute(statement).scalar_one_or_none()


def _cleanup(connection, generated_ids: list[str]) -> None:
    generated = list(generated_ids)
    calendar_runs = sa.select(schema.calendar_import_run.c.id).where(
        schema.calendar_import_run.c.account_id == ACCOUNT_ID
    )
    reminder_ids = sa.select(schema.reminder.c.id).where(
        schema.reminder.c.owner_account_id == ACCOUNT_ID
    )
    connection.execute(
        schema.calendar_import_item.delete().where(
            schema.calendar_import_item.c.run_id.in_(calendar_runs)
        )
    )
    connection.execute(
        schema.reminder_fire.delete().where(
            schema.reminder_fire.c.reminder_id.in_(reminder_ids)
        )
    )
    connection.execute(
        schema.calendar_import_run.delete().where(
            schema.calendar_import_run.c.account_id == ACCOUNT_ID
        )
    )
    if generated:
        connection.execute(schema.outbox.delete().where(schema.outbox.c.id.in_(generated)))
    connection.execute(
        schema.reminder.delete().where(schema.reminder.c.owner_account_id == ACCOUNT_ID)
    )
    connection.execute(
        schema.friend_link.delete().where(
            schema.friend_link.c.owner_account_id == ACCOUNT_ID
        )
    )
    connection.execute(
        schema.agent_settings.delete().where(
            schema.agent_settings.c.account_id == ACCOUNT_ID
        )
    )
    connection.execute(
        schema.user_profile.delete().where(schema.user_profile.c.account_id == ACCOUNT_ID)
    )
    connection.execute(
        schema.auth_artifact.delete().where(
            sa.or_(
                schema.auth_artifact.c.account_id == ACCOUNT_ID,
                schema.auth_artifact.c.target_account_id == ACCOUNT_ID,
            )
        )
    )
    connection.execute(schema.account.delete().where(schema.account.c.id == ACCOUNT_ID))
