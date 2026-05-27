from __future__ import annotations

from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent.reminder.errors import InvalidSchedule
from agent.reminder.models import AgentOutputTarget, ReminderSchedule


def _reminder(**overrides):
    schedule = overrides.pop(
        "schedule",
        ReminderSchedule(
            anchor_at=datetime(2026, 5, 13, 0, 30, tzinfo=UTC),
            local_date=date(2026, 5, 13),
            local_time=time(9, 30),
            timezone="Asia/Tokyo",
            rrule=None,
        ),
    )
    target = overrides.pop(
        "agent_output_target",
        AgentOutputTarget(
            conversation_id="conv-1",
            character_id="char-1",
            route_key="route-1",
        ),
    )
    values = {
        "id": "rem-1",
        "owner_user_id": "customer-1",
        "title": "standup",
        "schedule": schedule,
        "agent_output_target": target,
        "created_by_system": "agent",
        "metadata": {},
        "lifecycle_state": "active",
        "next_fire_at": datetime(2026, 5, 13, 0, 30, tzinfo=UTC),
        "last_fired_at": None,
        "last_event_ack_at": None,
        "last_error": None,
        "created_at": datetime(2026, 5, 12, 8, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 5, 12, 8, 0, tzinfo=UTC),
        "completed_at": None,
        "cancelled_at": None,
        "failed_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _service(*, reminder_runtime=None, conversation_dao=None, now=None):
    from connector.clawscale_bridge.reminder_management_service import (
        ReminderManagementService,
    )

    runtime_contract = reminder_runtime or MagicMock()
    return ReminderManagementService(
        reminder_runtime=runtime_contract,
        conversation_dao=conversation_dao or MagicMock(),
        character_id_provider=lambda: "char-1",
        now_provider=lambda: now or datetime(2026, 5, 12, 0, 0, tzinfo=UTC),
    )


def test_list_reminders_calls_runtime_contract_with_date_range_and_states():
    runtime_contract = MagicMock()
    runtime_contract.list_visible_reminders_in_local_date_range.return_value = [
        _reminder()
    ]

    result = _service(reminder_runtime=runtime_contract).list_reminders(
        customer_id="customer-1",
        from_date="2026-05-13",
        to_date="2026-05-19",
        lifecycle_states=["active", "completed"],
    )

    runtime_contract.list_visible_reminders_in_local_date_range.assert_called_once_with(
        owner_user_id="customer-1",
        from_date=date(2026, 5, 13),
        to_date=date(2026, 5, 19),
        lifecycle_states=["active", "completed"],
    )
    assert result[0]["id"] == "rem-1"
    assert result[0]["schedule"]["anchorAt"] == "2026-05-13T00:30:00+00:00"
    assert result[0]["schedule"]["localDate"] == "2026-05-13"
    assert result[0]["schedule"]["localTime"] == "09:30:00"
    assert result[0]["lifecycleState"] == "active"


@pytest.mark.parametrize(
    ("from_date", "to_date", "lifecycle_states"),
    [
        ("2026-05-19", "2026-05-13", ["active"]),
        ("2026-05-01", "2026-06-01", ["active"]),
        ("bad-date", "2026-05-13", ["active"]),
        ("2026-05-13", "2026-05-19", ["archived"]),
        ("2026-05-13", "2026-05-19", ["active", "archived"]),
    ],
)
def test_list_reminders_rejects_invalid_range_or_states(
    from_date,
    to_date,
    lifecycle_states,
):
    runtime_contract = MagicMock()

    with pytest.raises(ValueError) as exc:
        _service(reminder_runtime=runtime_contract).list_reminders(
            customer_id="customer-1",
            from_date=from_date,
            to_date=to_date,
            lifecycle_states=lifecycle_states,
        )

    assert str(exc.value) == "invalid_body"
    runtime_contract.list_visible_reminders_in_local_date_range.assert_not_called()


def test_list_reminders_allows_31_day_inclusive_range():
    runtime_contract = MagicMock()
    runtime_contract.list_visible_reminders_in_local_date_range.return_value = []

    _service(reminder_runtime=runtime_contract).list_reminders(
        customer_id="customer-1",
        from_date="2026-05-01",
        to_date="2026-05-31",
        lifecycle_states=["active", "completed", "cancelled", "failed"],
    )

    runtime_contract.list_visible_reminders_in_local_date_range.assert_called_once_with(
        owner_user_id="customer-1",
        from_date=date(2026, 5, 1),
        to_date=date(2026, 5, 31),
        lifecycle_states=["active", "completed", "cancelled", "failed"],
    )


def test_list_calendar_facts_returns_busy_intervals_without_private_details():
    runtime_contract = MagicMock()
    runtime_contract.list_occupied_reminder_occurrences_in_local_date_range.return_value = [
        SimpleNamespace(
            owner_user_id="coach",
            start_at=datetime(2026, 5, 25, 1, 0, tzinfo=UTC),
            end_at=datetime(2026, 5, 25, 2, 0, tzinfo=UTC),
            timezone="Asia/Tokyo",
        )
    ]

    result = _service(reminder_runtime=runtime_contract).list_calendar_facts(
        customer_id="coach",
        from_date="2026-05-25",
        to_date="2026-05-31",
        timezone="Asia/Tokyo",
    )

    assert result == {
        "targetAccountId": "coach",
        "range": {
            "from": "2026-05-25",
            "to": "2026-05-31",
            "timezone": "Asia/Tokyo",
        },
        "busyIntervals": [
            {
                "startAt": "2026-05-25T01:00:00+00:00",
                "endAt": "2026-05-25T02:00:00+00:00",
                "localStart": "2026-05-25 10:00",
                "localEnd": "2026-05-25 11:00",
            }
        ],
        "privacy": {"eventDetailsIncluded": False},
    }
    runtime_contract.list_occupied_reminder_occurrences_in_local_date_range.assert_called_once_with(
        owner_user_id="coach",
        from_date=date(2026, 5, 25),
        to_date=date(2026, 5, 31),
        timezone="Asia/Tokyo",
        lifecycle_states=["active"],
    )


def test_list_calendar_facts_clips_busy_intervals_to_requested_range():
    runtime_contract = MagicMock()
    runtime_contract.list_occupied_reminder_occurrences_in_local_date_range.return_value = [
        SimpleNamespace(
            owner_user_id="coach",
            start_at=datetime(2026, 5, 25, 14, 30, tzinfo=UTC),
            end_at=datetime(2026, 5, 25, 16, 30, tzinfo=UTC),
            timezone="Asia/Tokyo",
        )
    ]

    result = _service(reminder_runtime=runtime_contract).list_calendar_facts(
        customer_id="coach",
        from_date="2026-05-26",
        to_date="2026-05-26",
        timezone="Asia/Tokyo",
    )

    assert result["busyIntervals"] == [
        {
            "startAt": "2026-05-25T15:00:00+00:00",
            "endAt": "2026-05-25T16:30:00+00:00",
            "localStart": "2026-05-26 00:00",
            "localEnd": "2026-05-26 01:30",
        }
    ]


def test_calendar_facts_route_forwards_query_to_reminder_service(monkeypatch):
    from connector.clawscale_bridge.app import create_app

    app = create_app(testing=True)
    service = MagicMock()
    service.list_calendar_facts.return_value = {
        "targetAccountId": "coach",
        "busyIntervals": [],
        "privacy": {"eventDetailsIncluded": False},
    }
    monkeypatch.setitem(app.config, "REMINDER_MANAGEMENT_SERVICE", service)

    response = app.test_client().get(
        "/bridge/internal/reminder-calendar-facts"
        "?customer_id=coach"
        "&from=2026-05-25"
        "&to=2026-05-31"
        "&timezone=Asia/Tokyo",
        headers={"Authorization": "Bearer test-bridge-key"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "data": {
            "targetAccountId": "coach",
            "busyIntervals": [],
            "privacy": {"eventDetailsIncluded": False},
        },
    }
    service.list_calendar_facts.assert_called_once_with(
        customer_id="coach",
        from_date="2026-05-25",
        to_date="2026-05-31",
        timezone="Asia/Tokyo",
    )


def test_create_reminder_resolves_latest_conversation_and_passes_output_target():
    runtime_contract = MagicMock()
    runtime_contract.create_visible_reminder.return_value = _reminder()
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1",
        "route_key": "stored-route",
    }

    result = _service(
        reminder_runtime=runtime_contract,
        conversation_dao=conversation_dao,
    ).create_reminder(
        customer_id="customer-1",
        body={
            "title": "standup",
            "localDate": "2026-05-13",
            "localTime": "09:30",
            "timezone": "Asia/Tokyo",
            "routeKey": "caller-route-ignored",
        },
    )

    conversation_dao.find_latest_private_conversation_by_db_user_ids.assert_called_once_with(
        "customer-1",
        "char-1",
    )
    kwargs = runtime_contract.create_visible_reminder.call_args.kwargs
    assert kwargs["owner_user_id"] == "customer-1"
    assert kwargs["title"] == "standup"
    assert kwargs["target"] == AgentOutputTarget(
        conversation_id="conv-1",
        character_id="char-1",
        route_key="stored-route",
    )
    assert kwargs["schedule"].anchor_at == datetime(2026, 5, 13, 0, 30, tzinfo=UTC)
    assert result["id"] == "rem-1"


def test_create_reminder_passes_metadata_to_runtime_and_serializes_it():
    metadata = {
        "shared_reminder_id": "sr_1",
        "projection_role": "creator",
    }
    runtime_contract = MagicMock()
    runtime_contract.create_visible_reminder.return_value = _reminder(metadata=metadata)
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1",
        "route_key": "stored-route",
    }

    result = _service(
        reminder_runtime=runtime_contract,
        conversation_dao=conversation_dao,
    ).create_reminder(
        customer_id="customer-1",
        body={
            "title": "standup",
            "localDate": "2026-05-13",
            "localTime": "09:30",
            "timezone": "Asia/Tokyo",
            "metadata": metadata,
        },
    )

    assert (
        runtime_contract.create_visible_reminder.call_args.kwargs["metadata"]
        == metadata
    )
    assert result["metadata"] == metadata


def test_create_reminder_reuses_existing_runtime_idempotency_key():
    metadata = {
        "shared_reminder_id": "sr_1",
        "projection_role": "creator",
    }
    existing = _reminder(
        id="rem-existing",
        metadata={**metadata, "runtime_idempotency_key": "shared-reminder:sr_1:creator"},
    )
    runtime_contract = MagicMock()
    runtime_contract.find_visible_reminder_by_metadata_key.return_value = existing

    result = _service(reminder_runtime=runtime_contract).create_reminder(
        customer_id="customer-1",
        body={
            "title": "standup",
            "localDate": "2026-05-13",
            "localTime": "09:30",
            "timezone": "Asia/Tokyo",
            "idempotencyKey": "shared-reminder:sr_1:creator",
            "metadata": metadata,
        },
    )

    runtime_contract.find_visible_reminder_by_metadata_key.assert_called_once_with(
        owner_user_id="customer-1",
        key="runtime_idempotency_key",
        value="shared-reminder:sr_1:creator",
    )
    runtime_contract.create_visible_reminder.assert_not_called()
    assert result["id"] == "rem-existing"
    assert result["metadata"]["runtime_idempotency_key"] == "shared-reminder:sr_1:creator"


def test_create_reminder_accepts_duration_minutes_and_serializes_schedule():
    runtime_contract = MagicMock()
    runtime_contract.create_visible_reminder.return_value = _reminder(
        schedule=ReminderSchedule(
            anchor_at=datetime(2026, 5, 13, 0, 30, tzinfo=UTC),
            local_date=date(2026, 5, 13),
            local_time=time(9, 30),
            timezone="Asia/Tokyo",
            rrule=None,
            duration_minutes=60,
        )
    )
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1",
        "route_key": "stored-route",
    }

    result = _service(
        reminder_runtime=runtime_contract,
        conversation_dao=conversation_dao,
    ).create_reminder(
        customer_id="customer-1",
        body={
            "title": "lesson",
            "localDate": "2026-05-13",
            "localTime": "09:30",
            "timezone": "Asia/Tokyo",
            "durationMinutes": 60,
        },
    )

    schedule = runtime_contract.create_visible_reminder.call_args.kwargs["schedule"]
    assert schedule.duration_minutes == 60
    assert result["schedule"]["durationMinutes"] == 60


@pytest.mark.parametrize("duration_minutes", [0, -1, True, 1.5, "60"])
def test_create_reminder_rejects_invalid_duration_minutes(duration_minutes):
    runtime_contract = MagicMock()
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1",
        "route_key": "stored-route",
    }

    with pytest.raises(ValueError) as exc:
        _service(
            reminder_runtime=runtime_contract,
            conversation_dao=conversation_dao,
        ).create_reminder(
            customer_id="customer-1",
            body={
                "title": "lesson",
                "localDate": "2026-05-13",
                "localTime": "09:30",
                "timezone": "Asia/Tokyo",
                "durationMinutes": duration_minutes,
            },
        )

    assert str(exc.value) == "invalid_body"
    runtime_contract.create_visible_reminder.assert_not_called()


@pytest.mark.parametrize("metadata", ["not-a-dict", ["bad"]])
def test_create_reminder_rejects_non_object_metadata(metadata):
    runtime_contract = MagicMock()
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1",
        "route_key": "stored-route",
    }

    with pytest.raises(ValueError) as exc:
        _service(
            reminder_runtime=runtime_contract,
            conversation_dao=conversation_dao,
        ).create_reminder(
            customer_id="customer-1",
            body={
                "title": "standup",
                "localDate": "2026-05-13",
                "localTime": "09:30",
                "timezone": "Asia/Tokyo",
                "metadata": metadata,
            },
        )

    assert str(exc.value) == "invalid_body"
    runtime_contract.create_visible_reminder.assert_not_called()


@pytest.mark.parametrize(
    ("hint_name", "hint_value"),
    [
        ("businessConversationKey", "bc-1"),
        ("business_conversation_key", "bc-2"),
        ("gatewayConversationId", "gw-1"),
        ("gateway_conversation_id", "gw-2"),
    ],
)
def test_create_reminder_resolves_explicit_business_conversation_before_latest(
    hint_name,
    hint_value,
):
    runtime_contract = MagicMock()
    runtime_contract.create_visible_reminder.return_value = _reminder()
    conversation_dao = MagicMock()
    conversation_dao.get_private_conversation.return_value = {
        "_id": "conv-explicit",
        "route_key": "stored-route",
    }

    _service(
        reminder_runtime=runtime_contract,
        conversation_dao=conversation_dao,
    ).create_reminder(
        customer_id="customer-1",
        body={
            "title": "standup",
            "localDate": "2026-05-13",
            "localTime": "09:30",
            "timezone": "Asia/Tokyo",
            hint_name: hint_value,
            "routeKey": "caller-route-ignored",
        },
    )

    conversation_dao.get_private_conversation.assert_called_once_with(
        "business",
        f"clawscale:{hint_value}",
        "clawscale-character:char-1",
    )
    conversation_dao.find_latest_private_conversation_by_db_user_ids.assert_not_called()
    assert runtime_contract.create_visible_reminder.call_args.kwargs[
        "target"
    ] == AgentOutputTarget(
        conversation_id="conv-explicit",
        character_id="char-1",
        route_key="stored-route",
    )


def test_create_reminder_rejects_missing_explicit_business_conversation():
    runtime_contract = MagicMock()
    conversation_dao = MagicMock()
    conversation_dao.get_private_conversation.return_value = None

    with pytest.raises(ValueError) as exc:
        _service(
            reminder_runtime=runtime_contract,
            conversation_dao=conversation_dao,
        ).create_reminder(
            customer_id="customer-1",
            body={
                "title": "standup",
                "localDate": "2026-05-13",
                "localTime": "09:30",
                "timezone": "Asia/Tokyo",
                "businessConversationKey": "missing-bc",
            },
        )

    assert str(exc.value) == "conversation_required"
    conversation_dao.find_latest_private_conversation_by_db_user_ids.assert_not_called()
    runtime_contract.create_visible_reminder.assert_not_called()


def test_create_reminder_requires_delivery_route_key():
    runtime_contract = MagicMock()
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1"
    }

    with pytest.raises(ValueError) as exc:
        _service(
            reminder_runtime=runtime_contract,
            conversation_dao=conversation_dao,
        ).create_reminder(
            customer_id="customer-1",
            body={
                "title": "standup",
                "localDate": "2026-05-13",
                "localTime": "09:30",
                "timezone": "Asia/Tokyo",
            },
        )

    assert str(exc.value) == "delivery_route_required"
    runtime_contract.create_visible_reminder.assert_not_called()


def test_create_reminder_uses_conversation_info_route_key():
    runtime_contract = MagicMock()
    runtime_contract.create_visible_reminder.return_value = _reminder()
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1",
        "conversation_info": {"delivery_route_key": "info-route"},
    }

    _service(
        reminder_runtime=runtime_contract,
        conversation_dao=conversation_dao,
    ).create_reminder(
        customer_id="customer-1",
        body={
            "title": "standup",
            "localDate": "2026-05-13",
            "localTime": "09:30",
            "timezone": "Asia/Tokyo",
        },
    )

    assert (
        runtime_contract.create_visible_reminder.call_args.kwargs["target"].route_key
        == "info-route"
    )


def test_create_reminder_requires_latest_conversation():
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = None

    with pytest.raises(ValueError) as exc:
        _service(conversation_dao=conversation_dao).create_reminder(
            customer_id="customer-1",
            body={
                "title": "standup",
                "localDate": "2026-05-13",
                "localTime": "09:30",
                "timezone": "Asia/Tokyo",
            },
        )

    assert str(exc.value) == "conversation_required"


def test_create_reminder_rejects_title_over_200_chars_as_invalid_body():
    runtime_contract = MagicMock()
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1",
        "route_key": "stored-route",
    }

    with pytest.raises(ValueError) as exc:
        _service(
            reminder_runtime=runtime_contract,
            conversation_dao=conversation_dao,
        ).create_reminder(
            customer_id="customer-1",
            body={
                "title": "x" * 201,
                "localDate": "2026-05-13",
                "localTime": "09:30",
                "timezone": "Asia/Tokyo",
            },
        )

    assert str(exc.value) == "invalid_body"
    runtime_contract.create_visible_reminder.assert_not_called()


def test_update_complete_and_cancel_pass_owner_user_id():
    runtime_contract = MagicMock()
    runtime_contract.update_visible_reminder.return_value = _reminder(title="updated")
    runtime_contract.complete_visible_reminder.return_value = _reminder(
        lifecycle_state="completed"
    )
    runtime_contract.cancel_visible_reminder.return_value = _reminder(
        lifecycle_state="cancelled"
    )
    service = _service(reminder_runtime=runtime_contract)

    service.update_reminder(
        customer_id="customer-1",
        reminder_id="rem-1",
        body={"title": "updated"},
    )
    service.complete_reminder(customer_id="customer-1", reminder_id="rem-1")
    service.cancel_reminder(customer_id="customer-1", reminder_id="rem-1")

    assert (
        runtime_contract.update_visible_reminder.call_args.kwargs["owner_user_id"]
        == "customer-1"
    )
    assert (
        runtime_contract.update_visible_reminder.call_args.kwargs["reminder_id"]
        == "rem-1"
    )
    assert (
        runtime_contract.update_visible_reminder.call_args.kwargs["patch"].title
        == "updated"
    )
    runtime_contract.complete_visible_reminder.assert_called_once_with(
        owner_user_id="customer-1",
        reminder_id="rem-1",
    )
    runtime_contract.cancel_visible_reminder.assert_called_once_with(
        owner_user_id="customer-1",
        reminder_id="rem-1",
    )


def test_update_reminder_rejects_title_over_200_chars_as_invalid_body():
    runtime_contract = MagicMock()

    with pytest.raises(ValueError) as exc:
        _service(reminder_runtime=runtime_contract).update_reminder(
            customer_id="customer-1",
            reminder_id="rem-1",
            body={"title": "x" * 201},
        )

    assert str(exc.value) == "invalid_body"
    runtime_contract.update_visible_reminder.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        {
            "title": "bad timezone",
            "localDate": "2026-05-13",
            "localTime": "09:30",
            "timezone": "Invalid/Zone",
        },
        {
            "title": "past",
            "localDate": "2026-05-12",
            "localTime": "08:59",
            "timezone": "UTC",
        },
    ],
)
def test_create_reminder_maps_invalid_timezone_or_past_one_shot_to_invalid_schedule(
    body,
):
    runtime_contract = MagicMock()
    runtime_contract.create_visible_reminder.side_effect = InvalidSchedule("past")
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1",
        "route_key": "stored-route",
    }

    with pytest.raises(ValueError) as exc:
        _service(
            reminder_runtime=runtime_contract,
            conversation_dao=conversation_dao,
            now=datetime(2026, 5, 12, 9, 0, tzinfo=UTC),
        ).create_reminder(customer_id="customer-1", body=body)

    assert str(exc.value) == "invalid_schedule"
