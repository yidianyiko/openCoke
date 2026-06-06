from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from coke.domains.social_scheduling.availability import (
    ParticipantReachabilityPort,
    ReminderAvailabilityPort,
)
from coke.domains.social_scheduling.models import (
    Friendship,
    RecoverableSchedulingIntent,
    SocialSchedulingOutcome,
)
from coke.domains.social_scheduling.repository import InMemorySocialSchedulingRepository
from coke.domains.social_scheduling.service import SocialSchedulingService

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)


class FakeReachability(ParticipantReachabilityPort):
    def has_usable_channel(self, account_id: str) -> bool:
        return True


class FakeReminderAvailability(ReminderAvailabilityPort):
    def personal_busy_intervals(
        self,
        account_id,
        start,
        end,
        requester_timezone,
    ):
        return []


def _intent(
    intent_id: str,
    *,
    conversation_id: str = "conversation-1",
    facts_hash: str = "hash-1",
    expires_at: datetime | None = None,
) -> RecoverableSchedulingIntent:
    return RecoverableSchedulingIntent(
        id=intent_id,
        conversation_id=conversation_id,
        creator_account_id="creator-1",
        operation="shared_reminder_create",
        status="open",
        blocker="unmatched_friend",
        title="planning",
        local_trigger_at=datetime(2026, 6, 8, 9, 30),
        captured_timezone="Asia/Tokyo",
        duration_minutes=30,
        unresolved_reference_text="zihao",
        source_turn_id="turn-1",
        source_input_from_seq=4,
        source_input_to_seq=4,
        source_message_ids=("message-1",),
        facts={"title": "planning", "friend_reference": "zihao"},
        facts_hash=facts_hash,
        expires_at=expires_at or NOW + timedelta(minutes=10),
        consumed_turn_id=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _service(
    repo: InMemorySocialSchedulingRepository | None = None,
    *,
    display_names: dict[str, str] | None = None,
) -> SocialSchedulingService:
    repo = repo or InMemorySocialSchedulingRepository()
    names = display_names or {}
    return SocialSchedulingService(
        repository=repo,
        reachability=FakeReachability(),
        reminder_availability=FakeReminderAvailability(),
        now=lambda: NOW,
        id_factory=lambda prefix: f"{prefix}-1",
        display_name_resolver=lambda account_id: names.get(account_id, account_id),
    )


def _add_friend(
    repo: InMemorySocialSchedulingRepository,
    account_id: str,
    friend_account_id: str,
    *,
    lifecycle: str = "active",
) -> None:
    low, high = sorted((account_id, friend_account_id))
    repo.add_friendship(
        Friendship(
            id=f"friendship-{account_id}-{friend_account_id}",
            account_low_id=low,
            account_high_id=high,
            lifecycle=lifecycle,
            established_at=NOW,
            removed_at=None if lifecycle == "active" else NOW,
            created_at=NOW,
            updated_at=NOW,
        )
    )


def test_recoverable_intent_open_supersedes_previous_open_for_conversation():
    repo = InMemorySocialSchedulingRepository()
    first = _intent("intent-1")
    second = _intent("intent-2")

    repo.save_recoverable_intent(first)
    repo.save_recoverable_intent(second)

    assert repo.get_recoverable_intent("intent-1") == replace(
        first,
        status="superseded",
        updated_at=second.updated_at,
    )
    assert (
        repo.open_recoverable_intent_for_conversation("conversation-1", now=NOW).id
        == "intent-2"
    )


def test_recoverable_intent_expires_on_read_after_expiry():
    repo = InMemorySocialSchedulingRepository()
    expired = _intent("intent-1", expires_at=NOW - timedelta(seconds=1))

    repo.save_recoverable_intent(expired)

    assert (
        repo.open_recoverable_intent_for_conversation("conversation-1", now=NOW) is None
    )
    assert repo.get_recoverable_intent("intent-1") == replace(
        expired,
        status="expired",
        updated_at=NOW,
    )


def test_recoverable_intent_consumes_only_matching_facts_hash():
    repo = InMemorySocialSchedulingRepository()
    intent = _intent("intent-1", facts_hash="matching-hash")

    repo.save_recoverable_intent(intent)

    with pytest.raises(ValueError, match="recoverable_intent_facts_hash_mismatch"):
        repo.consume_recoverable_intent(
            "intent-1",
            facts_hash="wrong-hash",
            consumed_turn_id="turn-2",
            now=NOW,
        )

    consumed = repo.consume_recoverable_intent(
        "intent-1",
        facts_hash="matching-hash",
        consumed_turn_id="turn-2",
        now=NOW,
    )

    assert consumed == replace(
        intent,
        status="consumed",
        consumed_turn_id="turn-2",
        updated_at=NOW,
    )


def test_create_recoverable_intent_from_blocked_unmatched_outcome():
    repo = InMemorySocialSchedulingRepository()
    service = _service(repo)
    outcome = SocialSchedulingOutcome(
        outcome_id="outcome-1",
        operation="create_shared_reminder",
        status="blocked_unmatched_friend",
        title="Morning run",
        local_trigger_at=datetime(2026, 6, 8, 8, 30),
        captured_timezone="Asia/Tokyo",
        duration_minutes=45,
        blocker="unmatched_friend",
    )

    intent = service.create_recoverable_intent_from_outcome(
        conversation_id="conversation-1",
        creator_account_id="account-1",
        outcome=outcome,
        unresolved_reference_text="zihao",
        source_turn_id="turn-1",
        source_input_from_seq=3,
        source_input_to_seq=3,
        source_message_ids=("message-3",),
    )

    assert intent.status == "open"
    assert intent.operation == "shared_reminder_create"
    assert intent.blocker == "unmatched_friend"
    assert intent.title == "Morning run"
    assert intent.local_trigger_at == datetime(2026, 6, 8, 8, 30)
    assert intent.captured_timezone == "Asia/Tokyo"
    assert intent.duration_minutes == 45
    assert intent.unresolved_reference_text == "zihao"
    assert intent.source_input_from_seq == 3
    assert intent.source_message_ids == ("message-3",)
    assert intent.expires_at == NOW + timedelta(minutes=15)
    assert intent.facts["title"] == "Morning run"
    assert intent.facts["unresolved_reference_text"] == "zihao"
    assert intent.facts_hash
    assert (
        repo.open_recoverable_intent_for_conversation(
            "conversation-1",
            now=NOW,
        )
        == intent
    )


def test_resolve_corrected_friend_text_returns_exact_single_match():
    repo = InMemorySocialSchedulingRepository()
    _add_friend(repo, "account-1", "friend-oliver")
    _add_friend(repo, "account-1", "friend-inactive", lifecycle="removed")
    service = _service(
        repo,
        display_names={
            "friend-oliver": "Olivers",
            "friend-inactive": "Olivers",
        },
    )

    result = service.resolve_active_friend_reference("account-1", "olivers")

    assert result.status == "matched"
    assert result.matched_account_id == "friend-oliver"
    assert result.candidates == ("friend-oliver",)


def test_resolve_corrected_friend_text_reports_ambiguous_matches():
    repo = InMemorySocialSchedulingRepository()
    _add_friend(repo, "account-1", "friend-oliver-a")
    _add_friend(repo, "account-1", "friend-oliver-b")
    service = _service(
        repo,
        display_names={
            "friend-oliver-a": "Oliver S",
            "friend-oliver-b": "Olivers",
        },
    )

    result = service.resolve_active_friend_reference("account-1", "olivers")

    assert result.status == "ambiguous"
    assert result.matched_account_id is None
    assert result.candidates == ("friend-oliver-a", "friend-oliver-b")
