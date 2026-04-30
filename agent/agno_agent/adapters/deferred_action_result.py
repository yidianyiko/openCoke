from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from agent.agno_agent.runtime import AgentRunResult
from agent.agno_agent.runtime._immutability import freeze_sequence


@dataclass(frozen=True)
class DeferredActionFireResult:
    status: Literal["succeeded", "failed", "skipped", "rollback", "no_output"]
    output_references: Sequence[str] = field(default_factory=tuple)
    retryable: bool = False
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "output_references",
            freeze_sequence(self.output_references),
        )


def map_agent_result_to_deferred_status(
    result: AgentRunResult,
) -> DeferredActionFireResult:
    output_disposition = result.output_disposition
    output_references = output_disposition.output_references

    if output_disposition.status == "ok":
        return DeferredActionFireResult(
            status="succeeded",
            output_references=output_references,
        )

    if output_disposition.status == "empty":
        return DeferredActionFireResult(status="no_output", retryable=True)

    if output_disposition.status == "rollback":
        return DeferredActionFireResult(
            status="rollback",
            output_references=output_references,
            retryable=True,
        )

    if output_disposition.status == "fallback":
        return _failed_from_runtime_error(result)

    return DeferredActionFireResult(
        status="failed",
        retryable=True,
        error_code="agent_runtime_failed",
    )


def _failed_from_runtime_error(result: AgentRunResult) -> DeferredActionFireResult:
    error_disposition = result.error_disposition
    if error_disposition is None:
        return DeferredActionFireResult(
            status="failed",
            retryable=True,
            error_code="agent_runtime_failed",
        )

    return DeferredActionFireResult(
        status="failed",
        retryable=error_disposition.retryable,
        error_code=error_disposition.code,
        error_message=error_disposition.user_visible_fallback,
    )
