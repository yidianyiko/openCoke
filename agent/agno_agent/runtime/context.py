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


def _optional_relation_id(relation: Mapping[str, Any], key: str) -> str:
    value = relation.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _trusted_relation_id(
    relation: Mapping[str, Any],
    key: str,
    trusted_id: str,
    label: str,
) -> str:
    relation_id = _optional_relation_id(relation, key)
    if not relation_id:
        return trusted_id
    if relation_id != trusted_id:
        raise ValueError(f"relation {label} conflicts with trusted {label} id")
    return relation_id


def _nickname(value: Mapping[str, Any], fallback: str) -> str:
    return str(
        value.get("display_name")
        or value.get("nickname")
        or value.get("name")
        or fallback
    )


def _metadata_from_raw(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Reserved for explicitly validated metadata; never smuggle untrusted dicts."""
    return {}


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
    relation_uid = _trusted_relation_id(relation, "uid", user_id, "user")
    relation_cid = _trusted_relation_id(relation, "cid", character_id, "character")
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
            metadata=_metadata_from_raw(user),
        ),
        character=TrustedCharacterContext(
            id=character_id,
            nickname=_nickname(character, "Coke"),
            metadata=_metadata_from_raw(character),
        ),
        conversation=TrustedConversationContext(
            id=conversation_id,
            platform=platform,
            route_key=conversation.get("route_key"),
            metadata=_metadata_from_raw(conversation),
        ),
        relation=TrustedRelationContext(
            uid=relation_uid,
            cid=relation_cid,
            metadata=_metadata_from_raw(relation),
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
