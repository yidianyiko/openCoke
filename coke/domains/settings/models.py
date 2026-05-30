from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


class SettingsError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        fact: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.fact = fact
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class AgentSettings:
    id: str
    account_id: str
    assistant_name: str
    user_address_name: str | None
    persona: str | None
    background: str | None
    speaking_style: str | None
    extra_rules: str | None
    proactive_enabled: bool
    memory_enabled: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class UserProfile:
    id: str
    account_id: str
    real_name: str | None
    nickname: str | None
    description: str | None
    relationship_description: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SettingsView:
    account_id: str
    default_timezone: str
    agent_settings: AgentSettings
    user_profile: UserProfile
