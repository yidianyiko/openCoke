from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Protocol

from sqlalchemy.orm import Session

from coke import schema
from coke.domains._pg import db_id, insert_row, one_or_none, update_row
from coke.domains.identity_access.models import Account
from coke.domains.settings.models import AgentSettings, UserProfile


class SettingsRepository(Protocol):
    def get_account(self, account_id: str) -> Account | None: ...

    def save_account(self, account: Account) -> None: ...

    def get_agent_settings(self, account_id: str) -> AgentSettings | None: ...

    def save_agent_settings(self, settings: AgentSettings) -> None: ...

    def get_user_profile(self, account_id: str) -> UserProfile | None: ...

    def save_user_profile(self, profile: UserProfile) -> None: ...


class InMemorySettingsRepository:
    def __init__(self, accounts: dict[str, Account] | None = None) -> None:
        self.accounts = accounts if accounts is not None else {}
        self.agent_settings_by_account: dict[str, AgentSettings] = {}
        self.user_profiles_by_account: dict[str, UserProfile] = {}

    def add_account(self, account: Account) -> None:
        if account.id in self.accounts:
            raise ValueError("duplicate_account_id")
        self.accounts[account.id] = account

    def get_account(self, account_id: str) -> Account | None:
        return self.accounts.get(account_id)

    def save_account(self, account: Account) -> None:
        if account.id not in self.accounts:
            raise ValueError("account_not_found")
        self.accounts[account.id] = replace(account)

    def get_agent_settings(self, account_id: str) -> AgentSettings | None:
        return self.agent_settings_by_account.get(account_id)

    def save_agent_settings(self, settings: AgentSettings) -> None:
        if settings.account_id not in self.accounts:
            raise ValueError("account_not_found")
        existing = self.agent_settings_by_account.get(settings.account_id)
        if existing is not None and existing.id != settings.id:
            raise ValueError("duplicate_agent_settings_account")
        self.agent_settings_by_account[settings.account_id] = settings

    def get_user_profile(self, account_id: str) -> UserProfile | None:
        return self.user_profiles_by_account.get(account_id)

    def save_user_profile(self, profile: UserProfile) -> None:
        if profile.account_id not in self.accounts:
            raise ValueError("account_not_found")
        existing = self.user_profiles_by_account.get(profile.account_id)
        if existing is not None and existing.id != profile.id:
            raise ValueError("duplicate_user_profile_account")
        self.user_profiles_by_account[profile.account_id] = profile


class PostgresSettingsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_account(self, account_id: str) -> Account | None:
        row = one_or_none(
            self.session,
            schema.account,
            schema.account.c.id == account_id,
        )
        return _account(row) if row else None

    def save_account(self, account: Account) -> None:
        if (
            update_row(
                self.session,
                schema.account,
                _account_values(account),
                {},
                default_error="account_write_failed",
            )
            == 0
        ):
            raise ValueError("account_not_found")

    def get_agent_settings(self, account_id: str) -> AgentSettings | None:
        row = one_or_none(
            self.session,
            schema.agent_settings,
            schema.agent_settings.c.account_id == account_id,
        )
        return _agent_settings(row) if row else None

    def save_agent_settings(self, settings: AgentSettings) -> None:
        existing = self.get_agent_settings(settings.account_id)
        if existing is None:
            insert_row(
                self.session,
                schema.agent_settings,
                _agent_settings_values(settings),
                {
                    "pk_agent_settings": "duplicate_agent_settings_id",
                    "uq_agent_settings_account": "duplicate_agent_settings_account",
                },
                default_error="duplicate_agent_settings_account",
            )
            return
        if settings.id != existing.id:
            raise ValueError("duplicate_agent_settings_account")
        if (
            update_row(
                self.session,
                schema.agent_settings,
                _agent_settings_values(settings),
                {"uq_agent_settings_account": "duplicate_agent_settings_account"},
                default_error="duplicate_agent_settings_account",
            )
            == 0
        ):
            raise ValueError("agent_settings_not_found")

    def get_user_profile(self, account_id: str) -> UserProfile | None:
        row = one_or_none(
            self.session,
            schema.user_profile,
            schema.user_profile.c.account_id == account_id,
        )
        return _user_profile(row) if row else None

    def save_user_profile(self, profile: UserProfile) -> None:
        existing = self.get_user_profile(profile.account_id)
        if existing is None:
            insert_row(
                self.session,
                schema.user_profile,
                _user_profile_values(profile),
                {
                    "pk_user_profile": "duplicate_user_profile_id",
                    "uq_user_profile_account": "duplicate_user_profile_account",
                },
                default_error="duplicate_user_profile_account",
            )
            return
        if profile.id != existing.id:
            raise ValueError("duplicate_user_profile_account")
        if (
            update_row(
                self.session,
                schema.user_profile,
                _user_profile_values(profile),
                {"uq_user_profile_account": "duplicate_user_profile_account"},
                default_error="duplicate_user_profile_account",
            )
            == 0
        ):
            raise ValueError("user_profile_not_found")


def _account_values(account: Account) -> dict:
    return {
        "id": account.id,
        "origin": account.origin,
        "default_timezone": account.default_timezone,
        "lifecycle": account.lifecycle,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
    }


def _account(row: Mapping) -> Account:
    return Account(
        id=db_id(row["id"]),
        origin=row["origin"],
        default_timezone=row["default_timezone"],
        lifecycle=row["lifecycle"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _agent_settings_values(settings: AgentSettings) -> dict:
    return {
        "id": settings.id,
        "account_id": settings.account_id,
        "assistant_name": settings.assistant_name,
        "user_address_name": settings.user_address_name,
        "persona": settings.persona,
        "background": settings.background,
        "speaking_style": settings.speaking_style,
        "extra_rules": settings.extra_rules,
        "proactive_enabled": settings.proactive_enabled,
        "memory_enabled": settings.memory_enabled,
        "created_at": settings.created_at,
        "updated_at": settings.updated_at,
    }


def _agent_settings(row: Mapping) -> AgentSettings:
    return AgentSettings(
        id=db_id(row["id"]),
        account_id=db_id(row["account_id"]),
        assistant_name=row["assistant_name"],
        user_address_name=row["user_address_name"],
        persona=row["persona"],
        background=row["background"],
        speaking_style=row["speaking_style"],
        extra_rules=row["extra_rules"],
        proactive_enabled=row["proactive_enabled"],
        memory_enabled=row["memory_enabled"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _user_profile_values(profile: UserProfile) -> dict:
    return {
        "id": profile.id,
        "account_id": profile.account_id,
        "real_name": profile.real_name,
        "nickname": profile.nickname,
        "description": profile.description,
        "relationship_description": profile.relationship_description,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def _user_profile(row: Mapping) -> UserProfile:
    return UserProfile(
        id=db_id(row["id"]),
        account_id=db_id(row["account_id"]),
        real_name=row["real_name"],
        nickname=row["nickname"],
        description=row["description"],
        relationship_description=row["relationship_description"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
