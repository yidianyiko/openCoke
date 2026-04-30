from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TrustedUserContext:
    id: str
    nickname: str | None
    timezone: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrustedCharacterContext:
    id: str
    nickname: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrustedConversationContext:
    id: str
    platform: str
    route_key: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrustedRelationContext:
    uid: str
    cid: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentRunContext:
    user: TrustedUserContext
    character: TrustedCharacterContext
    conversation: TrustedConversationContext
    relation: TrustedRelationContext
    platform: str
    recent_chat_history: str
    current_time: datetime
    runtime_metadata: dict[str, Any] = field(default_factory=dict)
