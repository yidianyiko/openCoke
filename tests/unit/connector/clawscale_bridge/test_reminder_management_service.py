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


def _service(*, reminder_service=None, conversation_dao=None, now=None):
    from connector.clawscale_bridge.reminder_management_service import (
        ReminderManagementService,
    )

    return ReminderManagementService(
        reminder_service=reminder_service or MagicMock(),
        conversation_dao=conversation_dao or MagicMock(),
        character_id_provider=lambda: "char-1",
        now_provider=lambda: now or datetime(2026, 5, 12, 0, 0, tzinfo=UTC),
    )


def test_list_reminders_calls_reminder_service_with_date_range_and_states():
    reminder_service = MagicMock()
    reminder_service.list_for_user_in_local_date_range.return_value = [_reminder()]

    result = _service(reminder_service=reminder_service).list_reminders(
        customer_id="customer-1",
        from_date="2026-05-13",
        to_date="2026-05-19",
        lifecycle_states=["active", "completed"],
    )

    reminder_service.list_for_user_in_local_date_range.assert_called_once_with(
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
    reminder_service = MagicMock()

    with pytest.raises(ValueError) as exc:
        _service(reminder_service=reminder_service).list_reminders(
            customer_id="customer-1",
            from_date=from_date,
            to_date=to_date,
            lifecycle_states=lifecycle_states,
        )

    assert str(exc.value) == "invalid_body"
    reminder_service.list_for_user_in_local_date_range.assert_not_called()


def test_list_reminders_allows_31_day_inclusive_range():
    reminder_service = MagicMock()
    reminder_service.list_for_user_in_local_date_range.return_value = []

    _service(reminder_service=reminder_service).list_reminders(
        customer_id="customer-1",
        from_date="2026-05-01",
        to_date="2026-05-31",
        lifecycle_states=["active", "completed", "cancelled", "failed"],
    )

    reminder_service.list_for_user_in_local_date_range.assert_called_once_with(
        owner_user_id="customer-1",
        from_date=date(2026, 5, 1),
        to_date=date(2026, 5, 31),
        lifecycle_states=["active", "completed", "cancelled", "failed"],
    )


def test_create_reminder_resolves_latest_conversation_and_passes_output_target():
    reminder_service = MagicMock()
    reminder_service.create.return_value = _reminder()
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1",
        "route_key": "stored-route",
    }

    result = _service(
        reminder_service=reminder_service,
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
    command = reminder_service.create.call_args.kwargs["command"]
    assert reminder_service.create.call_args.kwargs["owner_user_id"] == "customer-1"
    assert command.title == "standup"
    assert command.created_by_system == "agent"
    assert command.agent_output_target == AgentOutputTarget(
        conversation_id="conv-1",
        character_id="char-1",
        route_key="stored-route",
    )
    assert command.schedule.anchor_at == datetime(2026, 5, 13, 0, 30, tzinfo=UTC)
    assert result["id"] == "rem-1"


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
    reminder_service = MagicMock()
    reminder_service.create.return_value = _reminder()
    conversation_dao = MagicMock()
    conversation_dao.get_private_conversation.return_value = {
        "_id": "conv-explicit",
        "route_key": "stored-route",
    }

    _service(
        reminder_service=reminder_service,
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
    command = reminder_service.create.call_args.kwargs["command"]
    assert command.agent_output_target == AgentOutputTarget(
        conversation_id="conv-explicit",
        character_id="char-1",
        route_key="stored-route",
    )


def test_create_reminder_falls_back_to_latest_when_explicit_conversation_missing():
    reminder_service = MagicMock()
    reminder_service.create.return_value = _reminder()
    conversation_dao = MagicMock()
    conversation_dao.get_private_conversation.return_value = None
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-latest",
        "route_key": "latest-route",
    }

    _service(
        reminder_service=reminder_service,
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

    conversation_dao.find_latest_private_conversation_by_db_user_ids.assert_called_once_with(
        "customer-1",
        "char-1",
    )
    command = reminder_service.create.call_args.kwargs["command"]
    assert command.agent_output_target == AgentOutputTarget(
        conversation_id="conv-latest",
        character_id="char-1",
        route_key="latest-route",
    )


def test_create_reminder_does_not_require_route_key():
    reminder_service = MagicMock()
    reminder_service.create.return_value = _reminder(
        agent_output_target=AgentOutputTarget(
            conversation_id="conv-1",
            character_id="char-1",
            route_key=None,
        )
    )
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1"
    }

    _service(
        reminder_service=reminder_service,
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

    command = reminder_service.create.call_args.kwargs["command"]
    assert command.agent_output_target.route_key is None


def test_create_reminder_uses_conversation_info_route_key():
    reminder_service = MagicMock()
    reminder_service.create.return_value = _reminder()
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1",
        "conversation_info": {"delivery_route_key": "info-route"},
    }

    _service(
        reminder_service=reminder_service,
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

    command = reminder_service.create.call_args.kwargs["command"]
    assert command.agent_output_target.route_key == "info-route"


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
    reminder_service = MagicMock()
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1"
    }

    with pytest.raises(ValueError) as exc:
        _service(
            reminder_service=reminder_service,
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
    reminder_service.create.assert_not_called()


def test_update_complete_and_cancel_pass_owner_user_id():
    reminder_service = MagicMock()
    reminder_service.update.return_value = _reminder(title="updated")
    reminder_service.complete.return_value = _reminder(lifecycle_state="completed")
    reminder_service.cancel.return_value = _reminder(lifecycle_state="cancelled")
    service = _service(reminder_service=reminder_service)

    service.update_reminder(
        customer_id="customer-1",
        reminder_id="rem-1",
        body={"title": "updated"},
    )
    service.complete_reminder(customer_id="customer-1", reminder_id="rem-1")
    service.cancel_reminder(customer_id="customer-1", reminder_id="rem-1")

    assert reminder_service.update.call_args.kwargs["owner_user_id"] == "customer-1"
    assert reminder_service.update.call_args.kwargs["reminder_id"] == "rem-1"
    assert reminder_service.update.call_args.kwargs["patch"].title == "updated"
    reminder_service.complete.assert_called_once_with(
        owner_user_id="customer-1",
        reminder_id="rem-1",
    )
    reminder_service.cancel.assert_called_once_with(
        owner_user_id="customer-1",
        reminder_id="rem-1",
    )


def test_update_reminder_rejects_title_over_200_chars_as_invalid_body():
    reminder_service = MagicMock()

    with pytest.raises(ValueError) as exc:
        _service(reminder_service=reminder_service).update_reminder(
            customer_id="customer-1",
            reminder_id="rem-1",
            body={"title": "x" * 201},
        )

    assert str(exc.value) == "invalid_body"
    reminder_service.update.assert_not_called()


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
    reminder_service = MagicMock()
    reminder_service.create.side_effect = InvalidSchedule("past")
    conversation_dao = MagicMock()
    conversation_dao.find_latest_private_conversation_by_db_user_ids.return_value = {
        "_id": "conv-1"
    }

    with pytest.raises(ValueError) as exc:
        _service(
            reminder_service=reminder_service,
            conversation_dao=conversation_dao,
            now=datetime(2026, 5, 12, 9, 0, tzinfo=UTC),
        ).create_reminder(customer_id="customer-1", body=body)

    assert str(exc.value) == "invalid_schedule"
