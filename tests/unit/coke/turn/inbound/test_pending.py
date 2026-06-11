from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from coke.turn.inbound.contracts import PendingClarification
from coke.turn.inbound.pending import InMemoryPendingClarificationStore


def test_in_memory_pending_store_round_trips_open_record() -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    pending = PendingClarification(
        unresolved_action_fingerprint="delete:gym",
        candidates=({"id": "r1", "title": "morning gym"},),
        source_input_window=(3, 3),
        expires_at=now + timedelta(minutes=10),
        status="open",
    )
    store = InMemoryPendingClarificationStore()

    saved = store.save("conversation-1", pending)

    assert saved == pending
    assert store.open_for_conversation("conversation-1", now=now) == pending


def test_consume_matches_by_fingerprint_and_closes_open_record() -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    pending = PendingClarification(
        unresolved_action_fingerprint="delete:gym",
        candidates=({"id": "r1", "title": "morning gym"},),
        source_input_window=(3, 3),
        expires_at=now + timedelta(minutes=10),
        status="open",
    )
    store = InMemoryPendingClarificationStore()
    store.save("conversation-1", pending)

    assert store.consume("conversation-1", "other", now=now) is None
    consumed = store.consume("conversation-1", "delete:gym", now=now)

    assert consumed == replace(pending, status="consumed")
    assert store.open_for_conversation("conversation-1", now=now) is None


def test_open_for_conversation_expires_stale_record() -> None:
    now = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    pending = PendingClarification(
        unresolved_action_fingerprint="delete:gym",
        candidates=({"id": "r1", "title": "morning gym"},),
        source_input_window=(3, 3),
        expires_at=now - timedelta(seconds=1),
        status="open",
    )
    store = InMemoryPendingClarificationStore()
    store.save("conversation-1", pending)

    assert store.open_for_conversation("conversation-1", now=now) is None
    assert store.expire(now) == (replace(pending, status="expired"),)
