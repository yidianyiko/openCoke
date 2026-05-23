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
class AgentInstanceProfileContext:
    display_name: str | None = None
    nickname: str | None = None
    user_address_name: str | None = None
    persona: str | None = None
    background: str | None = None
    speaking_style: str | None = None
    extra_rules: str | None = None
    status_place: str | None = None
    status_action: str | None = None
    proactive_enabled: bool | None = None
    memory_enabled: bool | None = None

    def is_empty(self) -> bool:
        return all(
            value is None
            for value in (
                self.display_name,
                self.nickname,
                self.user_address_name,
                self.persona,
                self.background,
                self.speaking_style,
                self.extra_rules,
                self.status_place,
                self.status_action,
                self.proactive_enabled,
                self.memory_enabled,
            )
        )


@dataclass(frozen=True)
class AgentRunContext:
    user: TrustedUserContext
    character: TrustedCharacterContext
    conversation: TrustedConversationContext
    relation: TrustedRelationContext
    platform: str
    recent_chat_history: str
    current_time: datetime
    agent_instance_profile: AgentInstanceProfileContext = field(
        default_factory=AgentInstanceProfileContext
    )
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


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _build_agent_instance_profile(value: Any) -> AgentInstanceProfileContext:
    profile = _legacy_mapping(value)
    status = _legacy_mapping(profile.get("status"))
    proactive = _legacy_mapping(profile.get("proactive"))
    memory = _legacy_mapping(profile.get("memory"))
    return AgentInstanceProfileContext(
        display_name=_optional_str(profile.get("display_name")),
        nickname=_optional_str(profile.get("nickname")),
        user_address_name=_optional_str(profile.get("user_address_name")),
        persona=_optional_str(profile.get("persona")),
        background=_optional_str(profile.get("background")),
        speaking_style=_optional_str(profile.get("speaking_style")),
        extra_rules=_optional_str(profile.get("extra_rules")),
        status_place=_optional_str(status.get("place")),
        status_action=_optional_str(status.get("action")),
        proactive_enabled=_optional_bool(proactive.get("enabled")),
        memory_enabled=_optional_bool(memory.get("enabled")),
    )


def _build_character_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    user_info = _legacy_mapping(value.get("user_info"))
    description = _optional_str(user_info.get("description"))
    if not description:
        return {}
    return {"description": description}


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
            metadata=_build_character_metadata(character),
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
        agent_instance_profile=_build_agent_instance_profile(
            legacy_context.get("agent_instance_profile")
        ),
        runtime_metadata=runtime_metadata or {},
    )
