from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.domains.identity_access.models import Account
from coke.domains.settings.models import (
    AgentSettings,
    SettingsError,
    SettingsView,
    UserProfile,
)
from coke.domains.settings.repository import SettingsRepository

_MISSING = object()


class ProactiveReminderPort(Protocol):
    def discard_future_proactive(
        self,
        owner_account_id: str,
        discarded_at: datetime,
    ) -> None: ...


class SettingsService:
    def __init__(
        self,
        repository: SettingsRepository,
        *,
        proactive_reminder_port: ProactiveReminderPort | None = None,
        now: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self.repository = repository
        self.proactive_reminder_port = proactive_reminder_port
        self._now = now or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda prefix: uuid4().hex)

    def view_settings(self, account_id: str) -> SettingsView:
        account = self._require_account(account_id)
        return SettingsView(
            account_id=account.id,
            default_timezone=account.default_timezone,
            agent_settings=self._ensure_agent_settings(account.id),
            user_profile=self._ensure_user_profile(account.id),
        )

    def update_settings(
        self,
        account_id: str,
        *,
        default_timezone: Any = _MISSING,
        assistant_name: Any = _MISSING,
        user_address_name: Any = _MISSING,
        persona: Any = _MISSING,
        background: Any = _MISSING,
        speaking_style: Any = _MISSING,
        extra_rules: Any = _MISSING,
        proactive_enabled: Any = _MISSING,
        memory_enabled: Any = _MISSING,
    ) -> SettingsView:
        account = self._require_account(account_id)
        current = self._ensure_agent_settings(account.id)
        now = self._now()

        if default_timezone is not _MISSING:
            timezone = _valid_timezone(default_timezone)
            if timezone != account.default_timezone:
                self.repository.save_account(
                    replace(account, default_timezone=timezone, updated_at=now)
                )

        updates: dict[str, Any] = {}
        if assistant_name is not _MISSING:
            updates["assistant_name"] = _required_text(
                assistant_name,
                "assistant_name",
                max_length=128,
            )
        if user_address_name is not _MISSING:
            updates["user_address_name"] = _optional_text(
                user_address_name,
                "user_address_name",
                max_length=128,
            )
        for field, value in (
            ("persona", persona),
            ("background", background),
            ("speaking_style", speaking_style),
            ("extra_rules", extra_rules),
        ):
            if value is not _MISSING:
                updates[field] = _optional_text(value, field, max_length=4000)
        if proactive_enabled is not _MISSING:
            updates["proactive_enabled"] = _required_bool(
                proactive_enabled,
                "proactive_enabled",
            )
        if memory_enabled is not _MISSING:
            updates["memory_enabled"] = _required_bool(
                memory_enabled,
                "memory_enabled",
            )

        if updates:
            updated = replace(current, **updates, updated_at=now)
            self.repository.save_agent_settings(updated)
            if (
                current.proactive_enabled
                and updated.proactive_enabled is False
                and self.proactive_reminder_port is not None
            ):
                self.proactive_reminder_port.discard_future_proactive(account.id, now)
        return self.view_settings(account.id)

    def set_timezone(self, account_id: str, default_timezone: str) -> SettingsView:
        return self.update_settings(
            account_id,
            default_timezone=default_timezone,
        )

    def update_profile(
        self,
        account_id: str,
        *,
        real_name: Any = _MISSING,
        nickname: Any = _MISSING,
        description: Any = _MISSING,
        relationship_description: Any = _MISSING,
    ) -> SettingsView:
        self._require_account(account_id)
        current = self._ensure_user_profile(account_id)
        updates: dict[str, Any] = {}
        for field, value, max_length in (
            ("real_name", real_name, 160),
            ("nickname", nickname, 160),
            ("description", description, 4000),
            ("relationship_description", relationship_description, 4000),
        ):
            if value is not _MISSING:
                updates[field] = _optional_text(value, field, max_length=max_length)
        if updates:
            self.repository.save_user_profile(
                replace(current, **updates, updated_at=self._now())
            )
        return self.view_settings(account_id)

    def reset_agent_settings(self, account_id: str) -> SettingsView:
        self._require_account(account_id)
        current = self._ensure_agent_settings(account_id)
        self.repository.save_agent_settings(
            _default_agent_settings(
                account_id=account_id,
                settings_id=current.id,
                created_at=current.created_at,
                updated_at=self._now(),
            )
        )
        return self.view_settings(account_id)

    def _require_account(self, account_id: str) -> Account:
        account = self.repository.get_account(account_id)
        if account is None:
            raise SettingsError(
                "account_not_found",
                fact={"type": "account_not_found", "account_id": account_id},
            )
        return account

    def _ensure_agent_settings(self, account_id: str) -> AgentSettings:
        settings = self.repository.get_agent_settings(account_id)
        if settings is not None:
            return settings
        now = self._now()
        settings = _default_agent_settings(
            account_id=account_id,
            settings_id=self._id_factory("agent_settings"),
            created_at=now,
            updated_at=now,
        )
        self.repository.save_agent_settings(settings)
        return settings

    def _ensure_user_profile(self, account_id: str) -> UserProfile:
        profile = self.repository.get_user_profile(account_id)
        if profile is not None:
            return profile
        now = self._now()
        profile = UserProfile(
            id=self._id_factory("user_profile"),
            account_id=account_id,
            real_name=None,
            nickname=None,
            description=None,
            relationship_description=None,
            created_at=now,
            updated_at=now,
        )
        self.repository.save_user_profile(profile)
        return profile


def _default_agent_settings(
    *,
    account_id: str,
    settings_id: str,
    created_at: datetime,
    updated_at: datetime,
) -> AgentSettings:
    return AgentSettings(
        id=settings_id,
        account_id=account_id,
        assistant_name="Coke",
        user_address_name=None,
        persona=None,
        background=None,
        speaking_style=None,
        extra_rules=None,
        proactive_enabled=True,
        memory_enabled=True,
        created_at=created_at,
        updated_at=updated_at,
    )


def _valid_timezone(value: Any) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise SettingsError(
            "invalid_timezone",
            fact={"type": "invalid_timezone", "reason": "timezone_string_required"},
        )
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise SettingsError(
            "invalid_timezone",
            fact={"type": "invalid_timezone", "timezone": value},
        ) from error
    return value


def _required_text(value: Any, field: str, *, max_length: int) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise SettingsError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "field": field,
                "reason": "non_empty_string_required",
            },
        )
    if len(value) > max_length:
        raise SettingsError(
            "invalid_request",
            fact={"type": "invalid_request", "field": field, "reason": "too_long"},
        )
    return value


def _optional_text(value: Any, field: str, *, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SettingsError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "field": field,
                "reason": "string_or_null_required",
            },
        )
    if value == "":
        return None
    if value != value.strip():
        raise SettingsError(
            "invalid_request",
            fact={"type": "invalid_request", "field": field, "reason": "untrimmed"},
        )
    if len(value) > max_length:
        raise SettingsError(
            "invalid_request",
            fact={"type": "invalid_request", "field": field, "reason": "too_long"},
        )
    return value


def _required_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise SettingsError(
            "invalid_request",
            fact={
                "type": "invalid_request",
                "field": field,
                "reason": "boolean_required",
            },
        )
    return value
