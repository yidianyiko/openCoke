from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from agent.agno_agent.runtime._immutability import (
    freeze_mapping,
    freeze_sequence,
    freeze_value,
)
from agent.agno_agent.runtime.domain_results import DomainExecutionResult

if TYPE_CHECKING:
    from agent.agno_agent.runtime.trace import AgentTurnTrace


@dataclass(frozen=True)
class VisibleMessage:
    message_type: Literal["text", "voice", "photo"]
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

    @property
    def visible_summary(self) -> str | None:
        keys = (
            ("visible_summary", "summary", "message")
            if self.ok
            else (
                "visible_summary",
                "summary",
            )
        )
        for key in keys:
            value = self.content.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @property
    def synthesis_context(self) -> Any:
        return self.content.get("synthesis_context")

    @property
    def durable_write(self) -> bool:
        return self.metadata.get("durable_write") is True

    @property
    def requires_response_synthesis(self) -> bool:
        return self.metadata.get("requires_response_synthesis") is True

    def to_manager_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "content": self.content,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class OutputDisposition:
    status: Literal["ok", "empty"]
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
    domain_results: Sequence[DomainExecutionResult]
    capability_results: Sequence[CapabilityResult]
    metrics: Mapping[str, Any]
    trace: "AgentTurnTrace | Mapping[str, Any]"
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
        object.__setattr__(
            self,
            "domain_results",
            freeze_sequence(self.domain_results),
        )
        object.__setattr__(
            self,
            "capability_results",
            freeze_sequence(self.capability_results),
        )
        object.__setattr__(self, "metrics", freeze_mapping(self.metrics))
        from agent.agno_agent.runtime.trace import coerce_agent_turn_trace

        object.__setattr__(self, "trace", coerce_agent_turn_trace(self.trace))


def with_output_references(
    result: AgentRunResult,
    output_references: Sequence[str],
) -> AgentRunResult:
    from dataclasses import replace

    return replace(
        result,
        output_disposition=OutputDisposition(
            status=result.output_disposition.status,
            output_references=tuple(output_references),
            metadata=dict(result.output_disposition.metadata),
        ),
    )
