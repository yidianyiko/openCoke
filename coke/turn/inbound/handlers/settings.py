from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from coke.domains.settings.models import SettingsError, SettingsView
from coke.domains.settings.service import SettingsService
from coke.turn.inbound.contracts import ActionOutcome, CompiledAction

CommitGuard = Callable[[], None] | None


class SettingsActionHandler:
    def __init__(self, settings_service: SettingsService) -> None:
        self.settings_service = settings_service

    def resolve_and_stage(
        self,
        compiled_action: CompiledAction,
        guard: Any,
    ) -> ActionOutcome:
        action = compiled_action.action
        if action is None:
            return ActionOutcome(
                category="not_possible",
                status="invalid_compiled_action",
            )
        params = dict(action.params)
        if action.operation == "set_timezone":
            return self._set_timezone(params, guard)
        if action.operation == "update_settings":
            return self._update_settings(params, guard)
        if action.operation == "toggle_memory":
            return self._toggle_setting(
                params,
                guard,
                field="memory_enabled",
                status="memory_toggled",
            )
        if action.operation == "toggle_proactive":
            return self._toggle_setting(
                params,
                guard,
                field="proactive_enabled",
                status="proactive_toggled",
            )
        return ActionOutcome(
            category="not_possible",
            status="unsupported_operation",
            data={"domain": "settings", "operation": action.operation},
        )

    def _set_timezone(
        self,
        params: Mapping[str, Any],
        guard: Any,
    ) -> ActionOutcome:
        account_id = _account_id(params)
        if account_id is None:
            return _missing_input("account_id")
        timezone = _timezone_value(params)
        if timezone is None:
            return _missing_input("timezone")
        try:
            view = self.settings_service.set_timezone(account_id, timezone)
        except (SettingsError, ValueError) as error:
            return _settings_error_outcome(error)
        staged_id = _stage_settings_command(
            guard,
            operation="set_timezone",
            command_payload={
                "operation": "set_timezone",
                "account_id": account_id,
                "default_timezone": timezone,
            },
            preview_facts={
                "status": "staged",
                "operation": "set_timezone",
                "account_id": account_id,
            },
        )
        return ActionOutcome(
            category="done",
            status="timezone_set",
            data=_settings_view_facts(view),
            staged_command_id=staged_id,
        )

    def _update_settings(
        self,
        params: Mapping[str, Any],
        guard: Any,
    ) -> ActionOutcome:
        account_id = _account_id(params)
        if account_id is None:
            return _missing_input("account_id")
        fields = _settings_update_fields(params)
        if not fields:
            return _missing_input("preference")
        try:
            view = self.settings_service.update_settings(account_id, **fields)
        except (SettingsError, ValueError) as error:
            return _settings_error_outcome(error)
        staged_id = _stage_settings_command(
            guard,
            operation="update_settings",
            command_payload={
                "operation": "update_settings",
                "account_id": account_id,
                **fields,
            },
            preview_facts={
                "status": "staged",
                "operation": "update_settings",
                "account_id": account_id,
            },
        )
        return ActionOutcome(
            category="done",
            status="updated",
            data=_settings_view_facts(view),
            staged_command_id=staged_id,
        )

    def _toggle_setting(
        self,
        params: Mapping[str, Any],
        guard: Any,
        *,
        field: str,
        status: str,
    ) -> ActionOutcome:
        account_id = _account_id(params)
        if account_id is None:
            return _missing_input("account_id")
        enabled = params.get("enabled")
        if not isinstance(enabled, bool):
            return _missing_input("enabled")
        fields = {field: enabled}
        try:
            view = self.settings_service.update_settings(account_id, **fields)
        except (SettingsError, ValueError) as error:
            return _settings_error_outcome(error)
        staged_id = _stage_settings_command(
            guard,
            operation="update_settings",
            command_payload={
                "operation": "update_settings",
                "account_id": account_id,
                **fields,
            },
            preview_facts={
                "status": "staged",
                "operation": "update_settings",
                "account_id": account_id,
            },
        )
        return ActionOutcome(
            category="done",
            status=status,
            data=_settings_view_facts(view),
            staged_command_id=staged_id,
        )


def _settings_error_outcome(error: BaseException) -> ActionOutcome:
    if isinstance(error, SettingsError):
        return ActionOutcome(
            category="not_possible",
            status=error.code,
            data=error.fact or {"reason": error.code},
        )
    return ActionOutcome(
        category="not_possible",
        status=str(error) or "settings_error",
    )


def _stage_settings_command(
    guard: Any,
    *,
    operation: str,
    command_payload: Mapping[str, Any],
    preview_facts: Mapping[str, Any],
) -> str | None:
    stage_command = getattr(guard, "stage_command", None)
    if not callable(stage_command):
        return None
    staged = stage_command(
        domain="settings",
        operation=operation,
        command_payload=dict(command_payload),
        preview_facts=dict(preview_facts),
        item_index=1,
    )
    return getattr(staged, "id", None)


def _account_id(params: Mapping[str, Any]) -> str | None:
    for key in ("account_id", "owner_account_id"):
        value = _optional_str(params.get(key))
        if value is not None:
            return value
    return None


def _timezone_value(params: Mapping[str, Any]) -> str | None:
    return _optional_str(params.get("timezone_text"))


def _settings_update_fields(params: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "default_timezone",
        "assistant_name",
        "user_address_name",
        "persona",
        "background",
        "speaking_style",
        "extra_rules",
        "proactive_enabled",
        "memory_enabled",
    )
    updates = {field: params[field] for field in fields if field in params}
    raw_fields = params.get("fields")
    if isinstance(raw_fields, Mapping):
        updates.update(
            {field: raw_fields[field] for field in fields if field in raw_fields}
        )
    preference = _optional_str(params.get("preference"))
    if preference is not None and "extra_rules" not in updates:
        updates["extra_rules"] = preference
    return updates


def _settings_view_facts(view: SettingsView) -> dict[str, Any]:
    settings = view.agent_settings
    profile = view.user_profile
    agent_settings = {
        "assistant_name": settings.assistant_name,
        "user_address_name": settings.user_address_name,
        "persona": settings.persona,
        "background": settings.background,
        "speaking_style": settings.speaking_style,
        "extra_rules": settings.extra_rules,
        "proactive_enabled": settings.proactive_enabled,
        "memory_enabled": settings.memory_enabled,
    }
    user_profile = {
        "real_name": profile.real_name,
        "nickname": profile.nickname,
        "description": profile.description,
        "relationship_description": profile.relationship_description,
    }
    return {
        "account_id": view.account_id,
        "default_timezone": view.default_timezone,
        **agent_settings,
        "agent_settings": agent_settings,
        "user_profile": user_profile,
    }


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _missing_input(field: str) -> ActionOutcome:
    return ActionOutcome(
        category="needs_input",
        status=f"missing_{field}",
        data={"field": field},
    )
