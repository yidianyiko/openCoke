from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agent.agno_agent.runtime._immutability import freeze_mapping


@dataclass(frozen=True)
class TrustedUserContext:
    id: str
    nickname: str | None
    timezone: str | None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True)
class TrustedCharacterContext:
    id: str
    nickname: str | None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True)
class TrustedConversationContext:
    id: str
    platform: str
    route_key: str | None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True)
class TrustedRelationContext:
    uid: str
    cid: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True)
class AgentRunContext:
    user: TrustedUserContext
    character: TrustedCharacterContext
    conversation: TrustedConversationContext
    relation: TrustedRelationContext
    platform: str
    recent_chat_history: str
    current_time: datetime
    runtime_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "runtime_metadata",
            freeze_mapping(self.runtime_metadata),
        )
