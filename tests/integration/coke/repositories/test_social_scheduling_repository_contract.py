from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from coke.domains.social_scheduling.models import (
    FriendLink,
    Friendship,
    NotificationFact,
    NotificationRecipient,
    ReminderProjection,
    SharedReminder,
)
from coke.domains.social_scheduling.repository import (
    InMemorySocialSchedulingRepository,
    PostgresSocialSchedulingRepository,
)

from .conftest import (
    ACCOUNT_A,
    ACCOUNT_B,
    ACCOUNT_C,
    NOW,
    OUTBOX_A,
    seed_account,
    seed_outbox,
    seed_reminder,
)


def _link(owner_account_id: str = ACCOUNT_A) -> FriendLink:
    return FriendLink(
        "a0000000000000000000000000000001",
        owner_account_id,
        "friend-token-hash",
        "friend-code-hash",
        "active",
        None,
        None,
        NOW,
        NOW,
    )


def _friendship(friendship_id: str = "a1000000000000000000000000000001") -> Friendship:
    return Friendship(
        friendship_id, ACCOUNT_A, ACCOUNT_B, "active", NOW, None, NOW, NOW
    )


def _shared(shared_id: str = "a2000000000000000000000000000001") -> SharedReminder:
    return SharedReminder(
        shared_id,
        ACCOUNT_A,
        (ACCOUNT_A, ACCOUNT_B),
        "participants-hash",
        "Team sync",
        "title-hash",
        NOW.replace(tzinfo=None) + timedelta(days=1),
        "UTC",
        30,
        "active",
        None,
        NOW,
        NOW,
    )


def _projection(
    projection_id: str = "a3000000000000000000000000000001",
    account_id: str = ACCOUNT_A,
    reminder_id: str = "60000000000000000000000000000001",
) -> ReminderProjection:
    return ReminderProjection(
        projection_id,
        "a2000000000000000000000000000001",
        account_id,
        reminder_id,
        "active",
        "pending",
        NOW,
        NOW,
    )


def _fact(fact_id: str = "a4000000000000000000000000000001") -> NotificationFact:
    return NotificationFact(
        fact_id,
        "shared_reminder_created",
        ACCOUNT_A,
        "shared_reminder",
        "a2000000000000000000000000000001",
        "pending",
        {"title": "Team sync"},
        "facts-hash",
        "notification-key-1",
        OUTBOX_A,
        NOW,
    )


def _recipient(
    recipient_id: str = "a5000000000000000000000000000001",
) -> NotificationRecipient:
    return NotificationRecipient(
        recipient_id,
        "a4000000000000000000000000000001",
        ACCOUNT_B,
        "pending",
        {},
        NOW,
        NOW,
    )


@pytest.fixture(params=["memory", "postgres"])
def repository(request, postgres_session):
    if request.param == "memory":
        return InMemorySocialSchedulingRepository()
    seed_account(postgres_session, ACCOUNT_A)
    seed_account(postgres_session, ACCOUNT_B)
    seed_account(postgres_session, ACCOUNT_C)
    seed_reminder(postgres_session, ACCOUNT_A)
    seed_reminder(postgres_session, ACCOUNT_B, "60000000000000000000000000000002")
    seed_outbox(postgres_session)
    return PostgresSocialSchedulingRepository(postgres_session)


def test_social_scheduling_records_round_trip(repository) -> None:
    link = _link()
    friendship = _friendship()
    shared = _shared()
    projection = _projection()
    projection_b = _projection(
        "a3000000000000000000000000000002",
        ACCOUNT_B,
        "60000000000000000000000000000002",
    )
    fact = _fact()
    recipient = _recipient()

    repository.add_friend_link(link, public_token="public-token", link_code="123456")
    repository.add_friendship(friendship)
    repository.add_shared_reminder(shared)
    repository.add_projection(projection)
    repository.add_projection(projection_b)
    repository.add_notification_fact(fact)
    repository.add_notification_recipient(recipient)

    assert repository.get_friend_link(link.id) == link
    assert repository.get_friend_link_by_owner(ACCOUNT_A) == link
    assert repository.get_public_token(link.id) == "public-token"
    assert repository.get_link_code(link.id) == "123456"
    assert repository.get_active_friendship(ACCOUNT_A, ACCOUNT_B) == friendship
    assert repository.list_active_friendships(ACCOUNT_A) == [friendship]
    assert repository.get_shared_reminder(shared.id) == shared
    assert (
        repository.get_duplicate_active_shared_reminder(
            shared.creator_account_id,
            shared.participant_set_hash,
            shared.title_hash,
            shared.local_trigger_at,
            shared.captured_timezone,
            shared.duration_minutes,
        )
        == shared
    )
    assert repository.list_shared_reminders_for_participant(ACCOUNT_B) == [shared]
    assert repository.get_projection(shared.id, ACCOUNT_A) == projection
    assert repository.list_projections(shared.id) == [projection, projection_b]
    assert (
        repository.shared_busy_intervals(
            ACCOUNT_A,
            shared.local_trigger_at,
            shared.local_trigger_at + timedelta(hours=1),
        )[0].detail_id
        == shared.id
    )
    assert repository.list_notification_facts() == [fact]
    assert repository.get_notification_recipient(fact.id, ACCOUNT_B) == recipient
    assert repository.list_notification_recipients(fact.id) == [recipient]


def test_social_scheduling_uniqueness_errors_match_in_memory(repository) -> None:
    repository.add_friend_link(_link(), public_token="public-token", link_code="123456")
    with pytest.raises(ValueError, match="duplicate_friend_link_token_hash"):
        repository.add_friend_link(
            replace(_link(ACCOUNT_B), id="a0000000000000000000000000000002"),
            public_token="other",
            link_code="654321",
        )

    repository.add_friendship(_friendship())
    with pytest.raises(ValueError, match="duplicate_active_friendship"):
        repository.add_friendship(_friendship("a1000000000000000000000000000002"))

    repository.add_shared_reminder(_shared())
    with pytest.raises(ValueError, match="duplicate_active_shared_reminder"):
        repository.add_shared_reminder(_shared("a2000000000000000000000000000002"))

    repository.add_projection(_projection())
    with pytest.raises(ValueError, match="duplicate_projection_participant"):
        repository.add_projection(_projection("a3000000000000000000000000000003"))

    repository.add_notification_fact(_fact())
    with pytest.raises(ValueError, match="duplicate_notification_fact_idempotency"):
        repository.add_notification_fact(_fact("a4000000000000000000000000000002"))

    repository.add_notification_recipient(_recipient())
    with pytest.raises(
        ValueError, match="duplicate_notification_recipient_fact_account"
    ):
        repository.add_notification_recipient(
            _recipient("a5000000000000000000000000000002")
        )
