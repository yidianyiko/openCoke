from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from coke.domains.social_scheduling.models import RecoverableSchedulingIntent
from coke.domains.social_scheduling.repository import InMemorySocialSchedulingRepository

NOW = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)


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

    assert repo.open_recoverable_intent_for_conversation("conversation-1", now=NOW) is None
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
