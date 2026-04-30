from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class VisibleMessage:
    message_type: Literal["text"]
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityResult:
    name: str
    ok: bool
    content: dict[str, Any]
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OutputDisposition:
    status: Literal["ok", "empty", "rollback", "fallback"]
    output_references: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeErrorDisposition:
    code: str
    retryable: bool
    user_visible_fallback: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentRunResult:
    visible_messages: list[VisibleMessage]
    post_analyze_input: dict[str, Any] | None
    tool_results: list[CapabilityResult]
    metrics: dict[str, Any]
    trace: dict[str, Any]
    output_disposition: OutputDisposition
    error_disposition: RuntimeErrorDisposition | None = None
