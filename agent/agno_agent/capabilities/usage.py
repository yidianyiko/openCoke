from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from agent.agno_agent.runtime.result import CapabilityResult
from dao.usage_dao import UsageDAO


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
    def __init__(
        self,
        *,
        contract_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self.contract_factory = contract_factory or _default_contract_factory

    def record(
        self,
        record: UsageRecord,
        *,
        persist_enabled: bool = True,
    ) -> UsageRecord:
        if persist_enabled:
            self.contract_factory(None).record_usage(record)
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
        if persist_enabled:
            self.contract_factory(run_context).record_usage(record)
        return CapabilityResult(
            name="usage",
            ok=True,
            content={"record": record.to_dict(), "persist_enabled": persist_enabled},
            metadata={"durable_write": persist_enabled},
        )


class UsageDomainContract:
    def __init__(self, *, usage_dao: UsageDAO | None = None) -> None:
        self.usage_dao = usage_dao or UsageDAO()

    def record_usage(self, record: UsageRecord) -> None:
        self.usage_dao.insert_usage_record(record.to_dict())


def _default_contract_factory(_run_context: Any) -> UsageDomainContract:
    return UsageDomainContract()
