from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from coke.composition import (
    CalendarImportToolAdapter,
    IdentityAccessToolAdapter,
    ReminderToolAdapter,
    SettingsToolAdapter,
    SocialSchedulingToolAdapter,
)


class RecordingStagingGuard:
    def __init__(self) -> None:
        self.turn_id = "turn_1"
        self.staged: list[dict[str, Any]] = []
        self.state_change_calls = 0

    def guard_state_change(self) -> None:
        self.state_change_calls += 1

    def stage_command(self, **kwargs):
        self.staged.append(kwargs)
        return SimpleNamespace(
            id=f"staged_{len(self.staged)}",
            preview_facts=dict(kwargs["preview_facts"]),
        )


@pytest.mark.parametrize(
    ("adapter", "command", "reason_code"),
    [
        (
            ReminderToolAdapter(object()),
            {
                "operation": "archive_reminder",
                "owner_account_id": "account_1",
            },
            "unsupported_reminder_operation",
        ),
        (
            SocialSchedulingToolAdapter(object()),
            {
                "operation": "approve_friend_request",
                "account_id": "account_1",
            },
            "unsupported_social_scheduling_operation",
        ),
        (
            CalendarImportToolAdapter(object()),
            {
                "operation": "sync_outlook_calendar",
                "account_id": "account_1",
            },
            "unsupported_calendar_import_operation",
        ),
        (
            IdentityAccessToolAdapter(object()),
            {
                "operation": "rotate_password",
                "account_id": "account_1",
            },
            "unsupported_identity_access_operation",
        ),
        (
            SettingsToolAdapter(object()),
            {
                "operation": "set_theme",
                "account_id": "account_1",
            },
            "unsupported_settings_operation",
        ),
    ],
)
def test_staging_guard_rejects_unsupported_write_operations(
    adapter,
    command,
    reason_code,
):
    guard = RecordingStagingGuard()

    result = adapter.execute(command, guard)

    assert result.ok is False
    assert result.reason_code == reason_code
    assert guard.staged == []


@pytest.mark.parametrize(
    ("adapter", "command", "reason_code"),
    [
        (
            ReminderToolAdapter(object()),
            {
                "operation": "create",
                "owner_account_id": "account_1",
            },
            "needs_content",
        ),
        (
            ReminderToolAdapter(object()),
            {
                "operation": "schedule_unscheduled",
                "owner_account_id": "account_1",
                "reminder_id": "reminder_1",
            },
            "trigger_time_required",
        ),
        (
            SocialSchedulingToolAdapter(object()),
            {
                "operation": "create_shared_reminder",
                "creator_account_id": "account_1",
                "receiver_account_ids": ["account_2"],
                "local_trigger_at": "2026-06-01T12:00:00",
                "context": {"source": "unit"},
            },
            "needs_title",
        ),
        (
            SocialSchedulingToolAdapter(object()),
            {
                "operation": "cancel_shared_reminder",
                "account_id": "account_1",
            },
            "shared_reminder_id_required",
        ),
        (
            CalendarImportToolAdapter(object()),
            {
                "operation": "import_google_calendar",
                "account_id": "account_1",
                "visible_start": "2026-06-01T00:00:00+00:00",
                "visible_end": "2026-06-02T00:00:00+00:00",
            },
            "auth_handle_required",
        ),
        (
            IdentityAccessToolAdapter(object()),
            {
                "operation": "issue_web_claim_code",
            },
            "browser_session_required",
        ),
        (
            SettingsToolAdapter(object()),
            {
                "operation": "set_timezone",
                "account_id": "account_1",
            },
            "default_timezone_required",
        ),
    ],
)
def test_staging_guard_rejects_write_operations_missing_required_fields(
    adapter,
    command,
    reason_code,
):
    guard = RecordingStagingGuard()

    result = adapter.execute(command, guard)

    assert result.ok is False
    assert result.reason_code == reason_code
    assert guard.staged == []
