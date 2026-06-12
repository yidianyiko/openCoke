from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal, Mapping

Category = Literal[
    "done",
    "needs_choice",
    "needs_input",
    "needs_confirmation",
    "not_possible",
    "nothing",
]
ReplyNecessity = Literal["reply_needed", "intentional_no_reply"]


def _frozen_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True, slots=True)
class ProposedAction:
    domain: str
    operation: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", _frozen_mapping(self.params))


@dataclass(frozen=True, slots=True)
class TurnPlan:
    actions: tuple[ProposedAction, ...]
    reply_necessity: ReplyNecessity = "reply_needed"

    def __post_init__(self) -> None:
        object.__setattr__(self, "actions", tuple(self.actions))


@dataclass(frozen=True, slots=True)
class CompiledAction:
    action: ProposedAction | None = None
    category: Category | None = None
    status: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _frozen_mapping(self.data))


@dataclass(frozen=True, slots=True)
class CompiledPlan:
    actions: tuple[CompiledAction, ...]
    reply_necessity: ReplyNecessity = "reply_needed"

    def __post_init__(self) -> None:
        object.__setattr__(self, "actions", tuple(self.actions))


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    category: Category
    status: str
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _frozen_mapping(self.data))


@dataclass(frozen=True, slots=True)
class SettledOutcome:
    outcomes: tuple[ActionOutcome, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcomes", tuple(self.outcomes))


@dataclass(frozen=True, slots=True)
class PendingClarification:
    unresolved_action_fingerprint: str
    candidates: tuple[Mapping[str, Any], ...]
    source_input_window: tuple[int, int]
    expires_at: datetime
    status: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidates",
            tuple(_frozen_mapping(candidate) for candidate in self.candidates),
        )
