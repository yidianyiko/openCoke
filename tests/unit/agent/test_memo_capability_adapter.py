from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)


def _run_context(owner_id: str = "owner-1") -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id=owner_id, nickname="User", timezone="UTC"),
        character=TrustedCharacterContext(id="character-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conversation-1",
            platform="business",
            route_key=None,
        ),
        relation=TrustedRelationContext(uid=owner_id, cid="character-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 17, tzinfo=UTC),
    )


@dataclass(frozen=True)
class SearchResult:
    hits: tuple[Any, ...] = ()


class RecordingContract:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def search_cards(self, request: Any) -> SearchResult:
        self.calls.append(("search_cards", request))
        return SearchResult()


def test_memo_capability_adapter_calls_contract_search_with_trusted_owner():
    from agent.agno_agent.capabilities.memo import (
        MemoCapabilityPort,
        RuntimeOwnerMapper,
    )

    contract = RecordingContract()
    port = MemoCapabilityPort(
        contract_factory=lambda _context: contract,
        owner_mapper=RuntimeOwnerMapper(),
    )

    result = port.run(
        "what did I say about memo review?",
        run_context=_run_context("owner-1"),
        args={
            "query": "memo review",
            "tags": ["product"],
            "kinds": ["note"],
            "limit": 5,
        },
    )

    assert result.ok is True
    assert result.metadata["durable_write"] is False
    assert result.metadata["requires_response_synthesis"] is True
    assert contract.calls[0][0] == "search_cards"
    request = contract.calls[0][1]
    assert request.owner_id == "owner-1"
    assert request.query == "memo review"
    assert request.tags == ("product",)
    assert request.kinds == ("note",)
    assert request.include_private is False
    assert request.limit == 5


def test_memo_capability_adapter_fails_closed_without_owner():
    from agent.agno_agent.capabilities.memo import (
        MemoCapabilityPort,
        RuntimeOwnerMapper,
    )

    contract = RecordingContract()
    port = MemoCapabilityPort(
        contract_factory=lambda _context: contract,
        owner_mapper=RuntimeOwnerMapper(),
    )

    result = port.run(
        "memo review",
        run_context=type("Context", (), {})(),
        args={"query": "memo review"},
    )

    assert result.ok is False
    assert result.error == "memo_owner_required"
    assert contract.calls == []


def test_memo_capability_adapter_rejects_flat_user_id():
    from agent.agno_agent.capabilities.memo import (
        MemoCapabilityPort,
        RuntimeOwnerMapper,
    )

    contract = RecordingContract()
    port = MemoCapabilityPort(
        contract_factory=lambda _context: contract,
        owner_mapper=RuntimeOwnerMapper(),
    )

    result = port.run(
        "memo review",
        run_context=type("Context", (), {"user_id": "untrusted-flat-user"})(),
        args={"query": "memo review"},
    )

    assert result.ok is False
    assert result.error == "memo_owner_required"
    assert contract.calls == []


def test_memo_capability_adapter_ignores_caller_supplied_owner_and_defaults_limit():
    from agent.agno_agent.capabilities.memo import (
        MemoCapabilityPort,
        RuntimeOwnerMapper,
    )

    contract = RecordingContract()
    port = MemoCapabilityPort(
        contract_factory=lambda _context: contract,
        owner_mapper=RuntimeOwnerMapper(),
    )

    result = port.run(
        "memo review",
        run_context=_run_context("trusted-owner"),
        args={"owner_id": "caller-owner", "query": "memo review", "limit": 0},
    )

    assert result.ok is True
    request = contract.calls[0][1]
    assert request.owner_id == "trusted-owner"
    assert request.limit > 0
