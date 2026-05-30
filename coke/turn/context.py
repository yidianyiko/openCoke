from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class TurnMode(StrEnum):
    INTERACTIVE = "interactive"
    RENDER = "render"


ToolName = Literal[
    "reminder",
    "social_scheduling",
    "calendar_import",
    "identity_access",
    "settings",
]


@dataclass(frozen=True, slots=True)
class TurnTrigger:
    trigger_id: str
    trigger_type: str
    mode: TurnMode
    conversation_id: str
    account_id: str
    payload: dict[str, Any]
    channel_identity_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolProfile:
    intent_tools_enabled: bool
    tool_names: tuple[ToolName, ...]
    constrained: bool = False
    reminder_tool: Any | None = None
    social_scheduling_tool: Any | None = None
    calendar_import_tool: Any | None = None
    identity_access_tool: Any | None = None
    settings_tool: Any | None = None

    @classmethod
    def interactive(cls, tool_ports: Any) -> ToolProfile:
        names: list[ToolName] = []
        if getattr(tool_ports, "reminder_tool", None) is not None:
            names.append("reminder")
        if getattr(tool_ports, "social_scheduling_tool", None) is not None:
            names.append("social_scheduling")
        if getattr(tool_ports, "calendar_import_tool", None) is not None:
            names.append("calendar_import")
        if getattr(tool_ports, "identity_access_tool", None) is not None:
            names.append("identity_access")
        if getattr(tool_ports, "settings_tool", None) is not None:
            names.append("settings")
        return cls(
            intent_tools_enabled=True,
            tool_names=tuple(names),
            reminder_tool=getattr(tool_ports, "reminder_tool", None),
            social_scheduling_tool=getattr(tool_ports, "social_scheduling_tool", None),
            calendar_import_tool=getattr(tool_ports, "calendar_import_tool", None),
            identity_access_tool=getattr(tool_ports, "identity_access_tool", None),
            settings_tool=getattr(tool_ports, "settings_tool", None),
        )

    @classmethod
    def render(cls, constrained: bool = False) -> ToolProfile:
        return cls(
            intent_tools_enabled=False,
            tool_names=(),
            constrained=constrained,
        )


@dataclass(frozen=True, slots=True)
class TurnContext:
    trigger: TurnTrigger
    mode: TurnMode
    trusted_facts: dict[str, Any]
    semantic_decision: Any | None
    focus_subject: Any | None
    reference_resolution: Any | None
    memory_context: Any | None
    freshness_guard: Any
    tool_profile: ToolProfile
    onboarding_guidance_required: bool = False
    payload: dict[str, Any] = field(default_factory=dict)


class ContextAssembler:
    def build(
        self,
        *,
        trigger: TurnTrigger,
        trusted_facts: dict[str, Any],
        semantic_decision: Any | None,
        focus_subject: Any | None,
        reference_resolution: Any | None,
        memory_context: Any | None,
        freshness_guard: Any,
        tool_profile: ToolProfile,
        onboarding_guidance_required: bool = False,
    ) -> TurnContext:
        return TurnContext(
            trigger=trigger,
            mode=trigger.mode,
            trusted_facts=dict(trusted_facts),
            semantic_decision=semantic_decision,
            focus_subject=focus_subject,
            reference_resolution=reference_resolution,
            memory_context=memory_context,
            freshness_guard=freshness_guard,
            tool_profile=tool_profile,
            onboarding_guidance_required=onboarding_guidance_required,
            payload=dict(trigger.payload),
        )
