from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from agent.agno_agent.runtime.result import AgentRunResult, OutputDisposition


def with_output_references(
    result: AgentRunResult,
    output_references: Sequence[str],
) -> AgentRunResult:
    return replace(
        result,
        output_disposition=OutputDisposition(
            status=result.output_disposition.status,
            output_references=tuple(output_references),
            metadata=dict(result.output_disposition.metadata),
        ),
    )
