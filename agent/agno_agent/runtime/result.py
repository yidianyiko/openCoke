from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from agent.agno_agent.runtime._immutability import (
    freeze_mapping,
    freeze_sequence,
    freeze_value,
)


@dataclass(frozen=True)
class VisibleMessage:
    message_type: Literal["text"]
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True)
class CapabilityResult:
    name: str
    ok: bool
    content: Mapping[str, Any]
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", freeze_mapping(self.content))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True)
class OutputDisposition:
    status: Literal["ok", "empty", "rollback", "fallback"]
    output_references: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "output_references",
            freeze_sequence(self.output_references),
        )
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True)
class RuntimeErrorDisposition:
    code: str
    retryable: bool
    user_visible_fallback: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True)
class AgentRunResult:
    visible_messages: Sequence[VisibleMessage]
    post_analyze_input: Mapping[str, Any] | None
    tool_results: Sequence[CapabilityResult]
    metrics: Mapping[str, Any]
    trace: Mapping[str, Any]
    output_disposition: OutputDisposition
    error_disposition: RuntimeErrorDisposition | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "visible_messages",
            freeze_sequence(self.visible_messages),
        )
        object.__setattr__(
            self,
            "post_analyze_input",
            freeze_value(self.post_analyze_input),
        )
        object.__setattr__(self, "tool_results", freeze_sequence(self.tool_results))
        object.__setattr__(self, "metrics", freeze_mapping(self.metrics))
        object.__setattr__(self, "trace", freeze_mapping(self.trace))
