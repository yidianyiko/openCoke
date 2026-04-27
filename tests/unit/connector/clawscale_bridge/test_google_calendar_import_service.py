from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest


def test_preflight_returns_target_conversation_identity_and_timezone():
    from connector.clawscale_bridge.google_calendar_import_service import (
        GoogleCalendarImportService,
    )

    conversation_dao = MagicMock(
        find_latest_private_conversation_by_db_user_ids=MagicMock(
            return_value={
                "_id": "conv-1",
                "talkers": [
                    {"db_user_id": "ck_1", "nickname": "Alice"},
                    {"db_user_id": "char_1", "nickname": "coke"},
                ],
                "conversation_info": {},
            }
        )
    )
    user_dao = MagicMock(
        get_user_by_id=MagicMock(return_value={"_id": "ck_1", "timezone": "Asia/Tokyo"})
    )

    service = GoogleCalendarImportService(
        conversation_dao=conversation_dao,
        deferred_action_service=MagicMock(),
        character_id_provider=lambda: "char_1",
        user_dao=user_dao,
    )

    result = service.preflight(customer_id="ck_1")

    assert result == {
        "conversation_id": "conv-1",
        "user_id": "ck_1",
        "character_id": "char_1",
        "timezone": "Asia/Tokyo",
    }


def test_preflight_prefers_whatsapp_business_conversation_key_when_present():
    from connector.clawscale_bridge.google_calendar_import_service import (
        GoogleCalendarImportService,
    )

    conversation_dao = MagicMock()
    conversation_dao.get_private_conversation.return_value = {
        "_id": "conv-whatsapp",
        "conversation_info": {},
    }
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-web",
        "conversation_info": {},
    }
    user_dao = MagicMock(
        get_user_by_id=MagicMock(return_value={"_id": "ck_email", "timezone": "Asia/Tokyo"})
    )

    service = GoogleCalendarImportService(
        conversation_dao=conversation_dao,
        deferred_action_service=MagicMock(),
        character_id_provider=lambda: "char_1",
        user_dao=user_dao,
    )

    result = service.preflight(
        customer_id="ck_email",
        business_conversation_key="bc_1",
        gateway_conversation_id="gw_1",
    )

    assert result == {
        "conversation_id": "conv-whatsapp",
        "user_id": "ck_email",
        "character_id": "char_1",
        "timezone": "Asia/Tokyo",
    }
    conversation_dao.get_private_conversation.assert_called_once_with(
        "business",
        "clawscale:bc_1",
        "clawscale-character:char_1",
    )
    conversation_dao.find_latest_private_conversation_by_db_user_ids.assert_not_called()


def test_preflight_raises_conversation_required_when_missing():
    from connector.clawscale_bridge.google_calendar_import_service import (
        GoogleCalendarImportService,
    )

    service = GoogleCalendarImportService(
        conversation_dao=MagicMock(
            find_latest_private_conversation_by_db_user_ids=MagicMock(return_value=None)
        ),
        deferred_action_service=MagicMock(),
        character_id_provider=lambda: "char_1",
        user_dao=MagicMock(get_user_by_id=MagicMock(return_value={"_id": "ck_1"})),
    )

    with pytest.raises(ValueError) as exc:
        service.preflight(customer_id="ck_1")

    assert str(exc.value) == "conversation_required"


def test_import_events_creates_future_single_event_with_event_timezone_override():
    from connector.clawscale_bridge.google_calendar_import_service import (
        GoogleCalendarImportService,
    )

    deferred_action_service = MagicMock()
    deferred_action_service.action_dao = MagicMock(
        find_imported_reminder_duplicate=MagicMock(return_value=None)
    )
    deferred_action_service.create_imported_future_reminder.return_value = {
        "_id": "action-1"
    }

    service = GoogleCalendarImportService(
        conversation_dao=MagicMock(),
        deferred_action_service=deferred_action_service,
        character_id_provider=lambda: "char_1",
        user_dao=MagicMock(),
        now_provider=lambda: datetime(2026, 4, 22, 0, 0, tzinfo=UTC),
    )

    result = service.import_events(
        target={
            "conversation_id": "conv-1",
            "user_id": "ck_1",
            "character_id": "char_1",
            "timezone": "Asia/Tokyo",
        },
        run_id="run-1",
        provider_account_email="alice@example.com",
        calendar_defaults={
            "timezone": "America/Los_Angeles",
            "default_reminders": [{"method": "popup", "minutes": 60}],
        },
        events=[
            {
                "id": "evt-1",
                "status": "confirmed",
                "summary": "Team sync",
                "start": {
                    "dateTime": "2026-04-23T09:00:00",
                    "timeZone": "America/New_York",
                },
                "end": {
                    "dateTime": "2026-04-23T10:00:00",
                    "timeZone": "America/New_York",
                },
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "popup", "minutes": 30}],
                },
            }
        ],
    )

    assert result["imported_count"] == 1
    assert result["skipped_count"] == 0
    assert result["warning_count"] == 0
    assert result["warnings"] == []
    deferred_action_service.create_imported_future_reminder.assert_called_once()
    kwargs = deferred_action_service.create_imported_future_reminder.call_args.kwargs
    assert kwargs["user_id"] == "ck_1"
    assert kwargs["character_id"] == "char_1"
    assert kwargs["conversation_id"] == "conv-1"
    assert kwargs["title"] == "Team sync"
    assert kwargs["timezone"] == "America/New_York"
    assert kwargs["dtstart"] == datetime(2026, 4, 23, 12, 30, tzinfo=UTC)
    assert kwargs["metadata"] == {
        "import_provider": "google_calendar",
        "import_run_id": "run-1",
        "provider_account_email": "alice@example.com",
        "source_event_id": "evt-1",
        "source_original_start_time": "2026-04-23T09:00:00",
    }


def test_import_events_skips_duplicate_and_uses_all_day_target_timezone():
    from connector.clawscale_bridge.google_calendar_import_service import (
        GoogleCalendarImportService,
    )

    deferred_action_service = MagicMock()
    deferred_action_service.action_dao = MagicMock(
        find_imported_reminder_duplicate=MagicMock(
            side_effect=[{"_id": "existing-1"}, None]
        )
    )

    service = GoogleCalendarImportService(
        conversation_dao=MagicMock(),
        deferred_action_service=deferred_action_service,
        character_id_provider=lambda: "char_1",
        user_dao=MagicMock(),
        now_provider=lambda: datetime(2026, 4, 22, 0, 0, tzinfo=UTC),
    )

    result = service.import_events(
        target={
            "conversation_id": "conv-1",
            "user_id": "ck_1",
            "character_id": "char_1",
            "timezone": "Asia/Tokyo",
        },
        run_id="run-2",
        provider_account_email=None,
        calendar_defaults={"timezone": "UTC", "default_reminders": []},
        events=[
            {
                "id": "evt-dup",
                "status": "confirmed",
                "summary": "Existing import",
                "start": {"date": "2026-04-23"},
                "end": {"date": "2026-04-24"},
            },
            {
                "id": "evt-all-day",
                "status": "confirmed",
                "summary": "Holiday",
                "start": {"date": "2026-04-24"},
                "end": {"date": "2026-04-25"},
            },
        ],
    )

    assert result["imported_count"] == 1
    assert result["skipped_count"] == 1
    assert result["warning_count"] == 1
    deferred_action_service.create_imported_future_reminder.assert_called_once()
    kwargs = deferred_action_service.create_imported_future_reminder.call_args.kwargs
    assert kwargs["timezone"] == "Asia/Tokyo"
    assert kwargs["dtstart"] == datetime(2026, 4, 24, 0, 0, tzinfo=UTC)
    assert kwargs["metadata"]["source_event_id"] == "evt-all-day"
    assert result["warnings"] == [
        {"event_id": "evt-dup", "reason": "duplicate_existing_reminder"}
    ]


def test_import_events_skips_exception_bearing_recurring_series_with_warning():
    from connector.clawscale_bridge.google_calendar_import_service import (
        GoogleCalendarImportService,
    )

    deferred_action_service = MagicMock()
    deferred_action_service.action_dao = MagicMock(
        find_imported_reminder_duplicate=MagicMock(return_value=None)
    )

    service = GoogleCalendarImportService(
        conversation_dao=MagicMock(),
        deferred_action_service=deferred_action_service,
        character_id_provider=lambda: "char_1",
        user_dao=MagicMock(),
        now_provider=lambda: datetime(2026, 4, 22, 0, 0, tzinfo=UTC),
    )

    result = service.import_events(
        target={
            "conversation_id": "conv-1",
            "user_id": "ck_1",
            "character_id": "char_1",
            "timezone": "UTC",
        },
        run_id="run-3",
        provider_account_email=None,
        calendar_defaults={"timezone": "UTC", "default_reminders": []},
        events=[
            {
                "id": "evt-series",
                "status": "confirmed",
                "summary": "Daily standup",
                "start": {"dateTime": "2026-04-20T09:00:00Z"},
                "end": {"dateTime": "2026-04-20T09:30:00Z"},
                "recurrence": ["RRULE:FREQ=DAILY"],
            },
            {
                "id": "evt-series_20260422",
                "status": "cancelled",
                "summary": "Cancelled standup",
                "recurringEventId": "evt-series",
                "originalStartTime": {"dateTime": "2026-04-22T09:00:00Z"},
                "start": {"dateTime": "2026-04-22T09:00:00Z"},
            },
        ],
    )

    assert result["imported_count"] == 0
    assert result["skipped_count"] == 1
    assert result["warning_count"] == 1
    assert result["warnings"] == [
        {"event_id": "evt-series", "reason": "unsupported_recurring_exceptions"}
    ]
    deferred_action_service.create_imported_recurring_reminder.assert_not_called()


def test_import_events_imports_recurring_master_when_only_exception_is_tombstone_cancel():
    from connector.clawscale_bridge.google_calendar_import_service import (
        GoogleCalendarImportService,
    )

    deferred_action_service = MagicMock()
    deferred_action_service.action_dao = MagicMock(
        find_imported_reminder_duplicate=MagicMock(return_value=None)
    )

    service = GoogleCalendarImportService(
        conversation_dao=MagicMock(),
        deferred_action_service=deferred_action_service,
        character_id_provider=lambda: "char_1",
        user_dao=MagicMock(),
        now_provider=lambda: datetime(2026, 4, 22, 0, 0, tzinfo=UTC),
    )

    result = service.import_events(
        target={
            "conversation_id": "conv-1",
            "user_id": "ck_1",
            "character_id": "char_1",
            "timezone": "UTC",
        },
        run_id="run-3b",
        provider_account_email=None,
        calendar_defaults={"timezone": "UTC", "default_reminders": []},
        events=[
            {
                "id": "evt-series",
                "status": "confirmed",
                "summary": "Daily standup",
                "start": {"dateTime": "2026-04-20T09:00:00Z"},
                "end": {"dateTime": "2026-04-20T09:30:00Z"},
                "recurrence": ["RRULE:FREQ=DAILY"],
            },
            {
                "id": "evt-series_20260422",
                "status": "cancelled",
                "recurringEventId": "evt-series",
                "originalStartTime": {"dateTime": "2026-04-22T09:00:00Z"},
            },
        ],
    )

    assert result["imported_count"] == 1
    assert result["skipped_count"] == 0
    assert result["warning_count"] == 0
    assert result["warnings"] == []
    deferred_action_service.create_imported_recurring_reminder.assert_called_once()


def test_import_events_ignores_tombstone_only_cancellation_artifacts():
    from connector.clawscale_bridge.google_calendar_import_service import (
        GoogleCalendarImportService,
    )

    deferred_action_service = MagicMock()
    deferred_action_service.action_dao = MagicMock(
        find_imported_reminder_duplicate=MagicMock(return_value=None)
    )

    service = GoogleCalendarImportService(
        conversation_dao=MagicMock(),
        deferred_action_service=deferred_action_service,
        character_id_provider=lambda: "char_1",
        user_dao=MagicMock(),
    )

    result = service.import_events(
        target={
            "conversation_id": "conv-1",
            "user_id": "ck_1",
            "character_id": "char_1",
            "timezone": "UTC",
        },
        run_id="run-4",
        provider_account_email=None,
        calendar_defaults={"timezone": "UTC", "default_reminders": []},
        events=[
            {
                "id": "evt-tombstone",
                "status": "cancelled",
                "recurringEventId": "evt-series",
                "originalStartTime": {"dateTime": "2026-04-22T09:00:00Z"},
            }
        ],
    )

    assert result == {
        "imported_count": 0,
        "skipped_count": 0,
        "warning_count": 0,
        "warnings": [],
    }


def test_import_events_does_not_use_calendar_defaults_when_use_default_false_without_overrides():
    from connector.clawscale_bridge.google_calendar_import_service import (
        GoogleCalendarImportService,
    )

    deferred_action_service = MagicMock()
    deferred_action_service.action_dao = MagicMock(
        find_imported_reminder_duplicate=MagicMock(return_value=None)
    )
    deferred_action_service.create_imported_future_reminder.return_value = {
        "_id": "action-2"
    }

    service = GoogleCalendarImportService(
        conversation_dao=MagicMock(),
        deferred_action_service=deferred_action_service,
        character_id_provider=lambda: "char_1",
        user_dao=MagicMock(),
        now_provider=lambda: datetime(2026, 4, 22, 0, 0, tzinfo=UTC),
    )

    result = service.import_events(
        target={
            "conversation_id": "conv-1",
            "user_id": "ck_1",
            "character_id": "char_1",
            "timezone": "UTC",
        },
        run_id="run-5",
        provider_account_email=None,
        calendar_defaults={
            "timezone": "UTC",
            "default_reminders": [{"method": "popup", "minutes": 60}],
        },
        events=[
            {
                "id": "evt-no-effective-reminders",
                "status": "confirmed",
                "summary": "No reminder override",
                "start": {"dateTime": "2026-04-23T09:00:00Z"},
                "end": {"dateTime": "2026-04-23T10:00:00Z"},
                "reminders": {
                    "useDefault": False,
                },
            }
        ],
    )

    assert result["imported_count"] == 1
    assert result["warning_count"] == 0
    kwargs = deferred_action_service.create_imported_future_reminder.call_args.kwargs
    assert kwargs["dtstart"] == datetime(2026, 4, 23, 9, 0, tzinfo=UTC)
