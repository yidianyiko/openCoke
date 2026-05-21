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


def _legacy_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _entity_id(value: Mapping[str, Any]) -> str:
    return str(value.get("id") or value.get("_id") or "").strip()


def _required_id(value: str, label: str) -> str:
    if not value:
        raise ValueError(f"missing {label} id")
    return value


def _nickname(value: Mapping[str, Any], fallback: str) -> str:
    return str(
        value.get("display_name")
        or value.get("nickname")
        or value.get("name")
        or fallback
    )


def build_agent_run_context(
    legacy_context: dict[str, Any],
    *,
    current_time: datetime,
    runtime_metadata: dict[str, Any] | None = None,
) -> AgentRunContext:
    user = _legacy_mapping(legacy_context.get("user"))
    character = _legacy_mapping(legacy_context.get("character"))
    conversation = _legacy_mapping(legacy_context.get("conversation"))
    relation = _legacy_mapping(legacy_context.get("relation"))
    conversation_info = _legacy_mapping(conversation.get("conversation_info"))

    user_id = _required_id(_entity_id(user), "user")
    character_id = _required_id(_entity_id(character), "character")
    conversation_id = _required_id(
        str(
            conversation.get("id")
            or conversation.get("_id")
            or legacy_context.get("conversation_id")
            or ""
        ).strip(),
        "conversation",
    )
    relation_uid = user_id
    relation_cid = character_id
    platform = str(
        legacy_context.get("platform") or conversation.get("platform") or "business"
    )

    return AgentRunContext(
        user=TrustedUserContext(
            id=user_id,
            nickname=_nickname(user, "User"),
            timezone=str(
                user.get("effective_timezone") or user.get("timezone") or "UTC"
            ),
        ),
        character=TrustedCharacterContext(
            id=character_id,
            nickname=_nickname(character, "Coke"),
        ),
        conversation=TrustedConversationContext(
            id=conversation_id,
            platform=platform,
            route_key=conversation.get("route_key"),
        ),
        relation=TrustedRelationContext(
            uid=relation_uid,
            cid=relation_cid,
        ),
        platform=platform,
        recent_chat_history=str(
            legacy_context.get("recent_chat_history")
            or conversation_info.get("chat_history_str")
            or ""
        ),
        current_time=current_time,
        runtime_metadata=runtime_metadata or {},
    )
