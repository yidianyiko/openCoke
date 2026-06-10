from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from coke.domains.social_scheduling.models import (
    FriendLinkView,
    FriendListEntry,
    FriendResolutionResult,
    Friendship,
    FriendshipResult,
    SocialSchedulingError,
)
from coke.turn.v2.contracts import ActionOutcome, CompiledAction, ProposedAction
from coke.turn.v2.handlers.friend import FriendshipActionHandler

NOW = datetime(2026, 6, 10, 1, 0, tzinfo=UTC)


class StubFriendshipService:
    def __init__(self) -> None:
        self.link = FriendLinkView(
            id="link-1",
            owner_account_id="acct-1",
            lifecycle="active",
            public_token="token-1",
            link_code="ABC123",
            qr_payload="https://coke.test/f/token-1",
        )
        self.add_result = FriendshipResult(
            status="created",
            friendship=_friendship(),
            counterpart_account_id="friend-1",
            counterpart_display_name="Amy",
        )
        self.friends = [
            FriendListEntry(
                account_id="friend-1",
                friendship_id="friendship-1",
                display_name="Amy",
            )
        ]
        self.resolution = FriendResolutionResult(
            status="matched",
            matched_account_id="friend-1",
            candidates=("friend-1",),
        )
        self.removed = _friendship(lifecycle="removed")
        self.error: SocialSchedulingError | None = None
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_or_create_friend_link(
        self,
        owner_account_id: str,
        commit_guard: Any = None,
    ) -> FriendLinkView:
        self.calls.append(
            (
                "get_or_create_friend_link",
                {"owner_account_id": owner_account_id, "commit_guard": commit_guard},
            )
        )
        if self.error is not None:
            raise self.error
        return self.link

    def establish_friendship_from_code(
        self,
        joiner_account_id: str,
        link_code: str,
        *,
        commit_guard: Any = None,
    ) -> FriendshipResult:
        self.calls.append(
            (
                "establish_friendship_from_code",
                {
                    "joiner_account_id": joiner_account_id,
                    "link_code": link_code,
                    "commit_guard": commit_guard,
                },
            )
        )
        if self.error is not None:
            raise self.error
        return self.add_result

    def list_friends(self, account_id: str) -> list[FriendListEntry]:
        self.calls.append(("list_friends", {"account_id": account_id}))
        return self.friends

    def resolve_active_friend_reference(
        self,
        account_id: str,
        text: str,
    ) -> FriendResolutionResult:
        self.calls.append(
            (
                "resolve_active_friend_reference",
                {"account_id": account_id, "text": text},
            )
        )
        return self.resolution

    def remove_friend(
        self,
        account_id: str,
        friend_account_id: str,
        commit_guard: Any = None,
    ) -> Friendship:
        self.calls.append(
            (
                "remove_friend",
                {
                    "account_id": account_id,
                    "friend_account_id": friend_account_id,
                    "commit_guard": commit_guard,
                },
            )
        )
        if self.error is not None:
            raise self.error
        return self.removed


class RecordingGuard:
    def __init__(self) -> None:
        self.staged: list[dict[str, Any]] = []
        self.state_change_calls = 0

    def guard_state_change(self) -> None:
        self.state_change_calls += 1

    def stage_command(self, **kwargs: Any) -> Any:
        self.staged.append(kwargs)
        return SimpleNamespace(id=f"stage-{len(self.staged)}")


def _compiled(operation: str, params: dict[str, Any]) -> CompiledAction:
    return CompiledAction(
        action=ProposedAction(domain="friendship", operation=operation, params=params)
    )


def _friendship(lifecycle: str = "active") -> Friendship:
    return Friendship(
        id="friendship-1",
        account_low_id="acct-1",
        account_high_id="friend-1",
        lifecycle=lifecycle,  # type: ignore[arg-type]
        established_at=NOW,
        removed_at=NOW if lifecycle == "removed" else None,
        created_at=NOW,
        updated_at=NOW,
    )


def test_get_friend_link_returns_link_and_stages_existing_social_operation() -> None:
    service = StubFriendshipService()
    guard = RecordingGuard()

    outcome = FriendshipActionHandler(service).resolve_and_stage(
        _compiled("get_friend_link", {"account_id": "acct-1"}),
        guard,
    )

    assert outcome == ActionOutcome(
        category="done",
        status="link",
        data={
            "friend_link_id": "link-1",
            "owner_account_id": "acct-1",
            "lifecycle": "active",
            "public_token": "token-1",
            "link_code": "ABC123",
            "public_link_url": "https://coke.test/f/token-1",
            "qr_payload": "https://coke.test/f/token-1",
        },
        staged_command_id="stage-1",
    )
    assert guard.staged[0]["domain"] == "social_scheduling"
    assert guard.staged[0]["operation"] == "get_friend_link"


def test_get_friend_link_missing_account_needs_input_without_stage() -> None:
    service = StubFriendshipService()
    guard = RecordingGuard()

    outcome = FriendshipActionHandler(service).resolve_and_stage(
        _compiled("get_friend_link", {}),
        guard,
    )

    assert outcome == ActionOutcome(
        category="needs_input",
        status="missing_account_id",
        data={"field": "account_id"},
    )
    assert service.calls == []
    assert guard.staged == []


def test_add_via_code_success_maps_to_added_and_stages_code_command() -> None:
    service = StubFriendshipService()
    guard = RecordingGuard()

    outcome = FriendshipActionHandler(service).resolve_and_stage(
        _compiled("add_via_code", {"account_id": "acct-1", "code": "ABC123"}),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "added"
    assert outcome.data["friendship_id"] == "friendship-1"
    assert outcome.data["counterpart_account_id"] == "friend-1"
    assert outcome.staged_command_id == "stage-1"
    assert guard.staged[0]["domain"] == "social_scheduling"
    assert guard.staged[0]["operation"] == "establish_friendship_from_token"
    assert guard.staged[0]["command_payload"]["link_code"] == "ABC123"


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("friend_link_not_found", "invalid_code"),
        ("friend_link_disabled", "used_code"),
    ],
)
def test_add_via_code_invalid_or_used_code_is_not_possible(
    code: str,
    status: str,
) -> None:
    service = StubFriendshipService()
    service.error = SocialSchedulingError(code, fact={"type": code})
    guard = RecordingGuard()

    outcome = FriendshipActionHandler(service).resolve_and_stage(
        _compiled("add_via_code", {"account_id": "acct-1", "code": "ABC123"}),
        guard,
    )

    assert outcome.category == "not_possible"
    assert outcome.status == status
    assert outcome.data == {"type": code}
    assert outcome.staged_command_id is None
    assert guard.staged == []


def test_list_friends_returns_listed_without_staging() -> None:
    service = StubFriendshipService()
    guard = RecordingGuard()

    outcome = FriendshipActionHandler(service).resolve_and_stage(
        _compiled("list_friends", {"account_id": "acct-1"}),
        guard,
    )

    assert outcome == ActionOutcome(
        category="done",
        status="listed",
        data={
            "friends": [
                {
                    "account_id": "friend-1",
                    "friendship_id": "friendship-1",
                    "display_name": "Amy",
                }
            ],
            "count": 1,
        },
    )
    assert guard.staged == []


def test_remove_friend_ambiguous_reference_needs_choice_without_stage() -> None:
    service = StubFriendshipService()
    service.resolution = FriendResolutionResult(
        status="ambiguous",
        candidates=("friend-1", "friend-2"),
    )
    guard = RecordingGuard()

    outcome = FriendshipActionHandler(service).resolve_and_stage(
        _compiled("remove_friend", {"account_id": "acct-1", "friend": "Amy"}),
        guard,
    )

    assert outcome == ActionOutcome(
        category="needs_choice",
        status="ambiguous",
        data={
            "field": "friend",
            "reference": "Amy",
            "candidates": ["friend-1", "friend-2"],
        },
    )
    assert [call[0] for call in service.calls] == ["resolve_active_friend_reference"]
    assert guard.staged == []


def test_remove_friend_unmatched_reference_is_not_found_without_stage() -> None:
    service = StubFriendshipService()
    service.resolution = FriendResolutionResult(status="unmatched")
    guard = RecordingGuard()

    outcome = FriendshipActionHandler(service).resolve_and_stage(
        _compiled("remove_friend", {"account_id": "acct-1", "friend": "Nobody"}),
        guard,
    )

    assert outcome == ActionOutcome(
        category="not_possible",
        status="not_found",
        data={"field": "friend", "reference": "Nobody"},
    )
    assert guard.staged == []


def test_remove_friend_success_maps_to_removed_and_stages_resolved_friend() -> None:
    service = StubFriendshipService()
    guard = RecordingGuard()

    outcome = FriendshipActionHandler(service).resolve_and_stage(
        _compiled("remove_friend", {"account_id": "acct-1", "friend": "Amy"}),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "removed"
    assert outcome.data["friendship_id"] == "friendship-1"
    assert outcome.staged_command_id == "stage-1"
    assert service.calls[-1][0] == "remove_friend"
    assert service.calls[-1][1]["friend_account_id"] == "friend-1"
    assert guard.staged[0]["operation"] == "remove_friend"
    assert guard.staged[0]["command_payload"]["friend_account_id"] == "friend-1"
