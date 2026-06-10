from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from itertools import count

import pytest

from coke.turn.v2.contracts import PendingClarification
from coke.turn.v2.pending import (
    InMemoryPendingClarificationStore,
    PostgresPendingClarificationRepository,
)

from .conftest import CONVERSATION_A, NOW, seed_conversation


def _pending(*, expires_delta=timedelta(minutes=10)) -> PendingClarification:
    return PendingClarification(
        unresolved_action_fingerprint="reminder.delete:gym",
        candidates=(
            {"id": "reminder-1", "title": "morning gym"},
            {"id": "reminder-2", "title": "evening gym"},
        ),
        source_input_window=(3, 4),
        expires_at=NOW + expires_delta,
        status="open",
    )


@pytest.fixture(params=["memory", "postgres"])
def repository(request, postgres_session):
    if request.param == "memory":
        return InMemoryPendingClarificationStore()
    seed_conversation(postgres_session, conversation_id=CONVERSATION_A)
    ids = count(10)
    return PostgresPendingClarificationRepository(
        postgres_session,
        now=lambda: NOW,
        id_factory=lambda _prefix: f"900000000000000000000000000000{next(ids):02d}",
    )


def test_pending_clarification_round_trips_open_consume_and_expire(repository):
    pending = _pending()

    saved = repository.save(CONVERSATION_A, pending)

    assert saved == pending
    assert repository.open_for_conversation(CONVERSATION_A, now=NOW) == pending
    assert (
        repository.consume(
            CONVERSATION_A,
            "not-the-fingerprint",
            now=NOW,
        )
        is None
    )
    assert repository.consume(
        CONVERSATION_A,
        pending.unresolved_action_fingerprint,
        now=NOW,
    ) == replace(pending, status="consumed")
    assert repository.open_for_conversation(CONVERSATION_A, now=NOW) is None

    stale = _pending(expires_delta=-timedelta(seconds=1))
    repository.save(CONVERSATION_A, stale)

    assert repository.open_for_conversation(CONVERSATION_A, now=NOW) is None
    assert repository.expire(NOW) == (replace(stale, status="expired"),)
