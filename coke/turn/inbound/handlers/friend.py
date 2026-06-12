from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict
from typing import Any

from coke.domains.social_scheduling.models import (
    FriendLinkView,
    FriendResolutionResult,
    Friendship,
    SocialSchedulingError,
)
from coke.domains.social_scheduling.service import SocialSchedulingService
from coke.turn.inbound.contracts import ActionOutcome, CompiledAction

CommitGuard = Callable[[], None] | None


class FriendshipActionHandler:
    def __init__(self, social_scheduling_service: SocialSchedulingService) -> None:
        self.social_scheduling_service = social_scheduling_service

    def execute(
        self,
        compiled_action: CompiledAction,
        guard: Any,
        *,
        action_index: int,
        turn_id: str,
    ) -> ActionOutcome:
        action = compiled_action.action
        if action is None:
            return ActionOutcome(
                category="not_possible",
                status="invalid_compiled_action",
            )
        params = dict(action.params)
        if action.operation == "get_friend_link":
            return self._get_friend_link(params, guard)
        if action.operation == "add_via_code":
            return self._add_via_code(params, guard)
        if action.operation == "list_friends":
            return self._list_friends(params)
        if action.operation == "remove_friend":
            return self._remove_friend(params, guard)
        return ActionOutcome(
            category="not_possible",
            status="unsupported_operation",
            data={"domain": "friendship", "operation": action.operation},
        )

    def _get_friend_link(
        self,
        params: Mapping[str, Any],
        guard: Any,
    ) -> ActionOutcome:
        account_id = _account_id(params, "owner_account_id", "account_id")
        if account_id is None:
            return _missing_input("account_id")
        try:
            link = self.social_scheduling_service.get_or_create_friend_link(
                owner_account_id=account_id,
                commit_guard=_commit_guard(guard),
            )
        except (SocialSchedulingError, ValueError) as error:
            return _friend_error_outcome(error)
        return ActionOutcome(
            category="done",
            status="link",
            data=_friend_link_facts(link),
        )

    def _add_via_code(
        self,
        params: Mapping[str, Any],
        guard: Any,
    ) -> ActionOutcome:
        account_id = _account_id(
            params,
            "joiner_account_id",
            "account_id",
            "owner_account_id",
        )
        if account_id is None:
            return _missing_input("account_id")
        code = _optional_str(params.get("code"))
        if code is None:
            return _missing_input("code")
        try:
            result = self.social_scheduling_service.establish_friendship_from_code(
                joiner_account_id=account_id,
                link_code=code,
                commit_guard=_commit_guard(guard),
            )
        except (SocialSchedulingError, ValueError) as error:
            return _friend_error_outcome(error)
        return ActionOutcome(
            category="done",
            status="added",
            data={
                "status": result.status,
                "friendship_id": result.friendship.id if result.friendship else None,
                "counterpart_account_id": result.counterpart_account_id,
                "counterpart_display_name": result.counterpart_display_name,
                "continuation": dict(result.continuation),
            },
        )

    def _list_friends(self, params: Mapping[str, Any]) -> ActionOutcome:
        account_id = _account_id(params, "account_id", "owner_account_id")
        if account_id is None:
            return _missing_input("account_id")
        entries = self.social_scheduling_service.list_friends(account_id)
        facts = [asdict(entry) for entry in entries]
        return ActionOutcome(
            category="done",
            status="listed",
            data={"friends": facts, "count": len(facts)},
        )

    def _remove_friend(
        self,
        params: Mapping[str, Any],
        guard: Any,
    ) -> ActionOutcome:
        account_id = _account_id(params, "account_id", "owner_account_id")
        if account_id is None:
            return _missing_input("account_id")
        friend_account_id = _optional_str(params.get("friend_account_id"))
        if friend_account_id is None:
            resolved = self._resolve_friend(account_id, params)
            if isinstance(resolved, ActionOutcome):
                return resolved
            friend_account_id = resolved
        try:
            friendship = self.social_scheduling_service.remove_friend(
                account_id=account_id,
                friend_account_id=friend_account_id,
                commit_guard=_commit_guard(guard),
            )
        except (SocialSchedulingError, ValueError) as error:
            return _friend_error_outcome(error)
        return ActionOutcome(
            category="done",
            status="removed",
            data=_friendship_fact(friendship),
        )

    def _resolve_friend(
        self,
        account_id: str,
        params: Mapping[str, Any],
    ) -> str | ActionOutcome:
        reference = _optional_str(params.get("friend"))
        if reference is None:
            return _missing_input("friend")
        result = self.social_scheduling_service.resolve_active_friend_reference(
            account_id,
            reference,
        )
        if result.status == "ambiguous":
            return _ambiguous_friend(reference, result)
        if result.status != "matched" or not result.matched_account_id:
            return ActionOutcome(
                category="not_possible",
                status="not_found",
                data={"field": "friend", "reference": reference},
            )
        return result.matched_account_id


def _ambiguous_friend(reference: str, result: FriendResolutionResult) -> ActionOutcome:
    return ActionOutcome(
        category="needs_choice",
        status="ambiguous",
        data={
            "field": "friend",
            "reference": reference,
            "candidates": list(result.candidates),
        },
    )


def _friend_error_outcome(error: BaseException) -> ActionOutcome:
    if isinstance(error, SocialSchedulingError):
        status = _friend_error_status(error.code)
        return ActionOutcome(
            category="not_possible",
            status=status,
            data=error.fact or {"reason": error.code},
        )
    return ActionOutcome(
        category="not_possible",
        status=str(error) or "friendship_failed",
    )


def _friend_error_status(code: str) -> str:
    return {
        "friend_link_not_found": "invalid_code",
        "friend_link_disabled": "used_code",
        "friendship_not_found": "not_found",
        "owner_channel_required": "unreachable",
        "joiner_channel_required": "unreachable",
    }.get(code, code)


def _friend_link_facts(link: FriendLinkView) -> dict[str, Any]:
    return {
        "friend_link_id": link.id,
        "owner_account_id": link.owner_account_id,
        "lifecycle": link.lifecycle,
        "public_token": link.public_token,
        "link_code": link.link_code,
        "public_link_url": link.qr_payload,
        "qr_payload": link.qr_payload,
    }


def _friendship_fact(friendship: Friendship) -> dict[str, Any]:
    return {
        "friendship_id": friendship.id,
        "account_low_id": friendship.account_low_id,
        "account_high_id": friendship.account_high_id,
        "lifecycle": friendship.lifecycle,
        "established_at": friendship.established_at.isoformat(),
        "removed_at": (
            friendship.removed_at.isoformat()
            if friendship.removed_at is not None
            else None
        ),
    }


def _commit_guard(guard: Any) -> CommitGuard:
    value = getattr(guard, "guard_state_change", None)
    return value if callable(value) else None


def _account_id(params: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _optional_str(params.get(key))
        if value is not None:
            return value
    return None


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _missing_input(field: str) -> ActionOutcome:
    return ActionOutcome(
        category="needs_input",
        status=f"missing_{field}",
        data={"field": field},
    )
