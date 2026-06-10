from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from coke.domains.settings.models import (
    AgentSettings,
    SettingsError,
    SettingsView,
    UserProfile,
)
from coke.turn.v2.contracts import ActionOutcome, CompiledAction, ProposedAction
from coke.turn.v2.handlers.settings import SettingsActionHandler

NOW = datetime(2026, 6, 10, 1, 0, tzinfo=UTC)


class StubSettingsService:
    def __init__(self) -> None:
        self.view = _settings_view()
        self.error: SettingsError | None = None
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def set_timezone(self, account_id: str, default_timezone: str) -> SettingsView:
        self.calls.append(
            (
                "set_timezone",
                {"account_id": account_id, "default_timezone": default_timezone},
            )
        )
        if self.error is not None:
            raise self.error
        self.view = _settings_view(default_timezone=default_timezone)
        return self.view

    def update_settings(self, account_id: str, **kwargs: Any) -> SettingsView:
        self.calls.append(
            ("update_settings", {"account_id": account_id, "fields": kwargs})
        )
        if self.error is not None:
            raise self.error
        self.view = _settings_view(
            default_timezone=kwargs.get("default_timezone", "UTC"),
            memory_enabled=kwargs.get("memory_enabled", True),
            proactive_enabled=kwargs.get("proactive_enabled", True),
            extra_rules=kwargs.get("extra_rules"),
        )
        return self.view


class RecordingGuard:
    def __init__(self) -> None:
        self.staged: list[dict[str, Any]] = []
        self.state_change_calls = 0

    def guard_state_change(self) -> None:
        self.state_change_calls += 1

    def stage_command(self, **kwargs: Any) -> Any:
        self.staged.append(kwargs)
        return SimpleNamespace(id=f"stage-{len(self.staged)}")


def _compiled(operation: str, params: dict[str, Any]) -> CompiledAction:
    return CompiledAction(
        action=ProposedAction(domain="settings", operation=operation, params=params)
    )


def _settings_view(
    *,
    default_timezone: str = "UTC",
    memory_enabled: bool = True,
    proactive_enabled: bool = True,
    extra_rules: str | None = None,
) -> SettingsView:
    return SettingsView(
        account_id="acct-1",
        default_timezone=default_timezone,
        agent_settings=AgentSettings(
            id="agent-settings-1",
            account_id="acct-1",
            assistant_name="Coke",
            user_address_name=None,
            persona=None,
            background=None,
            speaking_style=None,
            extra_rules=extra_rules,
            proactive_enabled=proactive_enabled,
            memory_enabled=memory_enabled,
            created_at=NOW,
            updated_at=NOW,
        ),
        user_profile=UserProfile(
            id="profile-1",
            account_id="acct-1",
            real_name=None,
            nickname=None,
            description=None,
            relationship_description=None,
            created_at=NOW,
            updated_at=NOW,
        ),
    )


def test_set_timezone_updates_and_stages_timezone_command() -> None:
    service = StubSettingsService()
    guard = RecordingGuard()

    outcome = SettingsActionHandler(service).resolve_and_stage(
        _compiled(
            "set_timezone",
            {"account_id": "acct-1", "timezone_text": "Asia/Tokyo"},
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "timezone_set"
    assert outcome.data["default_timezone"] == "Asia/Tokyo"
    assert outcome.staged_command_id == "stage-1"
    assert service.calls == [
        (
            "set_timezone",
            {"account_id": "acct-1", "default_timezone": "Asia/Tokyo"},
        )
    ]
    assert guard.staged[0]["domain"] == "settings"
    assert guard.staged[0]["operation"] == "set_timezone"
    assert guard.staged[0]["command_payload"]["default_timezone"] == "Asia/Tokyo"


def test_set_timezone_missing_value_needs_input_without_service_or_stage() -> None:
    service = StubSettingsService()
    guard = RecordingGuard()

    outcome = SettingsActionHandler(service).resolve_and_stage(
        _compiled("set_timezone", {"account_id": "acct-1"}),
        guard,
    )

    assert outcome == ActionOutcome(
        category="needs_input",
        status="missing_timezone",
        data={"field": "timezone"},
    )
    assert service.calls == []
    assert guard.staged == []


def test_update_settings_maps_preference_to_extra_rules_and_stages_update() -> None:
    service = StubSettingsService()
    guard = RecordingGuard()

    outcome = SettingsActionHandler(service).resolve_and_stage(
        _compiled(
            "update_settings",
            {"account_id": "acct-1", "preference": "use concise replies"},
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "updated"
    assert outcome.data["extra_rules"] == "use concise replies"
    assert outcome.staged_command_id == "stage-1"
    assert service.calls == [
        (
            "update_settings",
            {
                "account_id": "acct-1",
                "fields": {"extra_rules": "use concise replies"},
            },
        )
    ]
    assert guard.staged[0]["operation"] == "update_settings"
    assert guard.staged[0]["command_payload"]["extra_rules"] == "use concise replies"


def test_toggle_memory_updates_boolean_and_stages_update_settings() -> None:
    service = StubSettingsService()
    guard = RecordingGuard()

    outcome = SettingsActionHandler(service).resolve_and_stage(
        _compiled("toggle_memory", {"account_id": "acct-1", "enabled": False}),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "memory_toggled"
    assert outcome.data["memory_enabled"] is False
    assert outcome.staged_command_id == "stage-1"
    assert service.calls[0][1]["fields"] == {"memory_enabled": False}
    assert guard.staged[0]["operation"] == "update_settings"
    assert guard.staged[0]["command_payload"]["memory_enabled"] is False


def test_toggle_proactive_updates_boolean_and_stages_update_settings() -> None:
    service = StubSettingsService()
    guard = RecordingGuard()

    outcome = SettingsActionHandler(service).resolve_and_stage(
        _compiled("toggle_proactive", {"account_id": "acct-1", "enabled": False}),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "proactive_toggled"
    assert outcome.data["proactive_enabled"] is False
    assert outcome.staged_command_id == "stage-1"
    assert service.calls[0][1]["fields"] == {"proactive_enabled": False}
    assert guard.staged[0]["operation"] == "update_settings"
    assert guard.staged[0]["command_payload"]["proactive_enabled"] is False


def test_invalid_settings_value_is_not_possible_without_stage() -> None:
    service = StubSettingsService()
    service.error = SettingsError(
        "invalid_timezone",
        fact={"type": "invalid_timezone", "timezone": "Mars/Base"},
    )
    guard = RecordingGuard()

    outcome = SettingsActionHandler(service).resolve_and_stage(
        _compiled(
            "set_timezone",
            {"account_id": "acct-1", "timezone_text": "Mars/Base"},
        ),
        guard,
    )

    assert outcome == ActionOutcome(
        category="not_possible",
        status="invalid_timezone",
        data={"type": "invalid_timezone", "timezone": "Mars/Base"},
    )
    assert guard.staged == []
