from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from agent.agno_agent.runtime.result import CapabilityResult


@dataclass
class UsageRecord:
    """Single agent invocation usage record."""

    timestamp: datetime
    agent_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    duration: float | None = None
    user_id: str | None = None
    session_id: str | None = None
    workflow_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UsageCapabilityPort:
    def record(
        self,
        record: UsageRecord,
        *,
        persist_enabled: bool = True,
    ) -> UsageRecord:
        del persist_enabled
        return record

    def run(
        self,
        input_message: str,
        run_context: Any,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        del input_message
        request_args = args or {}
        record = request_args.get("record")
        if not isinstance(record, UsageRecord):
            return CapabilityResult(
                name="usage",
                ok=False,
                content={"summary": "Usage record is missing."},
                error="usage_record_required",
                metadata={"durable_write": False},
            )
        persist_enabled = bool(request_args.get("persist_enabled", True))
        del run_context
        return CapabilityResult(
            name="usage",
            ok=True,
            content={"record": record.to_dict(), "persist_enabled": persist_enabled},
            metadata={"durable_write": False},
        )
