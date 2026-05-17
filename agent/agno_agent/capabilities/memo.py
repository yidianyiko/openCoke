from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from agent.agno_agent.runtime.result import CapabilityResult

DEFAULT_MEMO_SEARCH_LIMIT = 5


class RuntimeOwnerMapper:
    def owner_id(self, run_context: Any) -> str:
        trusted_user = getattr(run_context, "user", None)
        return str(getattr(trusted_user, "id", "") or "").strip()


class MemoCapabilityPort:
    def __init__(
        self,
        *,
        contract_factory: Callable[[Any], Any] | None = None,
        owner_mapper: RuntimeOwnerMapper | None = None,
    ) -> None:
        self.contract_factory = contract_factory or _default_contract_factory
        self.owner_mapper = owner_mapper or RuntimeOwnerMapper()

    def run(
        self,
        input_message: str,
        run_context: Any,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        request_args = args or {}
        owner_id = self.owner_mapper.owner_id(run_context)
        if not owner_id:
            return CapabilityResult(
                name="memo",
                ok=False,
                content={"summary": "Memo owner identity is missing."},
                error="memo_owner_required",
                metadata={"durable_write": False},
            )

        from memo_runtime.contract import SearchMemoCardsRequest

        query = str(request_args.get("query") or input_message or "").strip()
        request = SearchMemoCardsRequest(
            owner_id=owner_id,
            query=query,
            tags=_string_tuple(request_args.get("tags")),
            kinds=_string_tuple(request_args.get("kinds")),
            include_private=False,
            limit=_positive_limit(request_args.get("limit")),
        )
        result = self.contract_factory(run_context).search_cards(request)
        return CapabilityResult(
            name="memo",
            ok=True,
            content={"hits": getattr(result, "hits", ())},
            metadata={
                "durable_write": False,
                "requires_response_synthesis": True,
            },
        )


def _default_contract_factory(_run_context: Any) -> Any:
    from memo_runtime.contract import MemoRuntimeContract

    return MemoRuntimeContract()


def _positive_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MEMO_SEARCH_LIMIT
    if limit <= 0:
        return DEFAULT_MEMO_SEARCH_LIMIT
    return limit


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        item = value.strip()
        return (item,) if item else ()
    if not isinstance(value, Iterable):
        item = str(value).strip()
        return (item,) if item else ()
    return tuple(
        item for item in (str(candidate).strip() for candidate in value) if item
    )
