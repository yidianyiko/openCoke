from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coke.domains.identity_access.models import Account
from coke.domains.reminder.models import ReminderBatchItem
from coke.domains.reminder.repository import InMemoryReminderRepository
from coke.domains.reminder.service import ReminderService
from coke.domains.settings.models import SettingsError
from coke.domains.settings.repository import InMemorySettingsRepository
from coke.domains.settings.service import SettingsService

NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


def test_global_timezone_switch_persists_and_does_not_rewrite_existing_reminders():
    settings_service, settings_repo, reminder_service, reminder_repo = _services()

    old_result = reminder_service.execute_batch(
        "acct_1",
        [
            ReminderBatchItem(
                operation="create",
                content="pay rent",
                trigger_time=NOW + timedelta(hours=1),
                captured_timezone="UTC",
                duration_minutes=15,
            )
        ],
    )
    old_id = old_result.items[0].reminder_id
    old_reminder = reminder_repo.get_reminder(old_id)

    view = settings_service.update_settings(
        "acct_1",
        default_timezone="Asia/Tokyo",
    )
    new_result = reminder_service.execute_batch(
        "acct_1",
        [
            ReminderBatchItem(
                operation="create",
                content="stretch",
                trigger_time=NOW + timedelta(hours=2),
                captured_timezone=view.default_timezone,
                duration_minutes=15,
            )
        ],
    )

    assert settings_repo.get_account("acct_1").default_timezone == "Asia/Tokyo"
    assert view.default_timezone == "Asia/Tokyo"
    assert reminder_repo.get_reminder(old_id).next_fire_at == old_reminder.next_fire_at
    assert reminder_repo.get_reminder(old_id).captured_timezone == "UTC"
    assert (
        reminder_repo.get_reminder(new_result.items[0].reminder_id).captured_timezone
        == "Asia/Tokyo"
    )


def test_invalid_timezone_is_rejected_without_mutating_account():
    settings_service, settings_repo, _reminder_service, _reminder_repo = _services()

    with pytest.raises(SettingsError) as error:
        settings_service.update_settings("acct_1", default_timezone="Not/AZone")

    assert error.value.code == "invalid_timezone"
    assert settings_repo.get_account("acct_1").default_timezone == "UTC"


def test_settings_and_profile_update_and_reset_to_agent_defaults():
    settings_service, _settings_repo, _reminder_service, _reminder_repo = _services()

    settings_service.update_settings(
        "acct_1",
        default_timezone="Asia/Tokyo",
        assistant_name="Mina",
        user_address_name="Yuki",
        persona="direct partner",
        background="User is rebuilding Coke.",
        speaking_style="concise",
        extra_rules="Avoid unsupported claims.",
        proactive_enabled=False,
        memory_enabled=False,
    )
    settings_service.update_profile(
        "acct_1",
        real_name="Yuki Tanaka",
        nickname="Yuki",
        description="Backend engineer",
        relationship_description="works with Coke",
    )

    view = settings_service.view_settings("acct_1")
    assert view.default_timezone == "Asia/Tokyo"
    assert view.agent_settings.assistant_name == "Mina"
    assert view.agent_settings.user_address_name == "Yuki"
    assert view.agent_settings.memory_enabled is False
    assert view.user_profile.real_name == "Yuki Tanaka"

    reset = settings_service.reset_agent_settings("acct_1")
    assert reset.default_timezone == "Asia/Tokyo"
    assert reset.agent_settings.assistant_name == "Coke"
    assert reset.agent_settings.user_address_name is None
    assert reset.agent_settings.proactive_enabled is True
    assert reset.agent_settings.memory_enabled is True
    assert reset.user_profile.real_name == "Yuki Tanaka"


def test_proactive_off_discards_future_proactive_reminders_only():
    settings_service, _settings_repo, reminder_service, reminder_repo = _services()
    ordinary = (
        reminder_service.execute_batch(
            "acct_1",
            [
                ReminderBatchItem(
                    operation="create",
                    content="ordinary",
                    trigger_time=NOW + timedelta(hours=1),
                    captured_timezone="UTC",
                    duration_minutes=15,
                )
            ],
        )
        .items[0]
        .reminder_id
    )
    proactive = (
        reminder_service.execute_batch(
            "acct_1",
            [
                ReminderBatchItem(
                    operation="create",
                    content="proactive",
                    trigger_time=NOW + timedelta(hours=1),
                    captured_timezone="UTC",
                    kind="proactive",
                )
            ],
        )
        .items[0]
        .reminder_id
    )

    view = settings_service.update_settings("acct_1", proactive_enabled=False)

    assert view.agent_settings.proactive_enabled is False
    assert reminder_repo.get_reminder(ordinary).lifecycle == "active"
    assert reminder_repo.get_reminder(proactive).lifecycle == "deleted"


def test_memory_off_persists_without_deleting_explicit_profile_or_settings():
    settings_service, _settings_repo, _reminder_service, _reminder_repo = _services()
    settings_service.update_profile("acct_1", nickname="Yuki")
    settings_service.update_settings("acct_1", extra_rules="Use short replies.")

    view = settings_service.update_settings("acct_1", memory_enabled=False)

    assert view.agent_settings.memory_enabled is False
    assert view.agent_settings.extra_rules == "Use short replies."
    assert view.user_profile.nickname == "Yuki"


def _services():
    settings_repo = InMemorySettingsRepository(
        accounts={
            "acct_1": Account(
                id="acct_1",
                origin="messaging_first",
                default_timezone="UTC",
                lifecycle="active",
                created_at=NOW,
                updated_at=NOW,
            )
        }
    )
    reminder_repo = InMemoryReminderRepository()
    ids = _id_factory()
    reminder_service = ReminderService(
        reminder_repo,
        now=lambda: NOW,
        id_factory=ids,
    )
    settings_service = SettingsService(
        settings_repo,
        proactive_reminder_port=reminder_repo,
        now=lambda: NOW,
        id_factory=ids,
    )
    return settings_service, settings_repo, reminder_service, reminder_repo


def _id_factory():
    counters: dict[str, int] = {}

    def factory(prefix: str) -> str:
        counters[prefix] = counters.get(prefix, 0) + 1
        return f"{prefix}_{counters[prefix]}"

    return factory
