import agent.agno_agent.runtime.scheduling_types as scheduling_types
from agent.agno_agent.runtime.scheduling_types import (
    SharedReminderSchedulingArgs,
    _compact_scheduling_args,
)


def test_compact_scheduling_args_strips_none_and_empty_string():
    result = _compact_scheduling_args({"a": None, "b": "", "c": "val", "d": "x"})

    assert result == {"c": "val", "d": "x"}


def test_compact_scheduling_args_serializes_shared_reminder_args():
    args = SharedReminderSchedulingArgs(
        invitee_account_id="acct_a",
        title="meeting",
        fire_at="2026-05-22T07:00:00.000Z",
        timezone="Asia/Shanghai",
        idempotency_key="shared-1",
    )

    result = _compact_scheduling_args({"shared_reminder": args, "reason": None})

    assert result == {
        "shared_reminder": {
            "invitee_account_id": "acct_a",
            "title": "meeting",
            "fire_at": "2026-05-22T07:00:00.000Z",
            "timezone": "Asia/Shanghai",
            "request_id": None,
            "friendship_id": None,
            "blocked_account_id": None,
            "idempotency_key": "shared-1",
        }
    }


def test_compact_scheduling_args_passes_through_primitives():
    result = _compact_scheduling_args({"target_account_id": "abc", "timezone": "UTC"})

    assert result == {"target_account_id": "abc", "timezone": "UTC"}


def test_shared_reminder_scheduling_args_round_trips():
    args = SharedReminderSchedulingArgs(
        invitee_account_id="acct_a",
        title="meeting",
        fire_at="2026-05-22T07:00:00.000Z",
        timezone="Asia/Shanghai",
        request_id="srr_1",
        friendship_id="fs_1",
        blocked_account_id="acct_c",
        idempotency_key="shared-1",
    )

    dumped = args.model_dump()

    assert dumped == {
        "invitee_account_id": "acct_a",
        "title": "meeting",
        "fire_at": "2026-05-22T07:00:00.000Z",
        "timezone": "Asia/Shanghai",
        "request_id": "srr_1",
        "friendship_id": "fs_1",
        "blocked_account_id": "acct_c",
        "idempotency_key": "shared-1",
    }


def test_scheduling_types_do_not_export_bookable_window_preview_models():
    assert not hasattr(scheduling_types, "SchedulingBookableWindowRule")
    assert not hasattr(scheduling_types, "SchedulingBookableWindowPreviewItem")
    assert not hasattr(scheduling_types, "SchedulingBookableWindowPreview")
