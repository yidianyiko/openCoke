from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coke.domains.social_scheduling.availability import (
    BusyInterval,
    ParticipantReachabilityPort,
    ReminderAvailabilityPort,
)
from coke.domains.social_scheduling.repository import (
    InMemorySocialSchedulingRepository,
)
from coke.domains.social_scheduling.service import SocialSchedulingService
from coke.domains.social_scheduling.models import SocialSchedulingError

NOW = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)


class FakeReachability(ParticipantReachabilityPort):
    def __init__(self, reachable: set[str] | None = None) -> None:
        self.reachable = reachable or set()

    def has_usable_channel(self, account_id: str) -> bool:
        return account_id in self.reachable


class FakeReminderAvailability(ReminderAvailabilityPort):
    def __init__(self) -> None:
        self.intervals: dict[str, list[BusyInterval]] = {}

    def personal_busy_intervals(
        self,
        account_id: str,
        start: datetime,
        end: datetime,
        requester_timezone: str,
    ) -> list[BusyInterval]:
        return [
            interval
            for interval in self.intervals.get(account_id, [])
            if interval.start < end and interval.end > start
        ]


def make_service(reachable: set[str] | None = None):
    repo = InMemorySocialSchedulingRepository()
    reachability = FakeReachability(reachable)
    reminder_availability = FakeReminderAvailability()
    service = SocialSchedulingService(
        repository=repo,
        reachability=reachability,
        reminder_availability=reminder_availability,
        now=lambda: NOW,
        id_factory=lambda prefix: f"{prefix}_{len(repo.generated_ids) + 1}",
        token_factory=lambda prefix: f"{prefix}_token_{len(repo.generated_tokens) + 1}",
    )
    return service, repo, reachability, reminder_availability


def create_active_friendship(service, owner: str, joiner: str):
    link = service.get_or_create_friend_link(owner)
    return service.establish_friendship_from_token(joiner, link.public_token)


def test_direct_friendship_is_active_and_has_no_pending_request_model():
    service, repo, _, _ = make_service({"owner", "joiner"})

    result = create_active_friendship(service, "owner", "joiner")

    assert result.status == "created"
    assert result.friendship is not None
    assert result.friendship.lifecycle == "active"
    assert {friend.account_id for friend in service.list_friends("owner")} == {"joiner"}
    assert {friend.account_id for friend in service.list_friends("joiner")} == {"owner"}
    assert not hasattr(repo, "friend_requests")


def test_deferred_self_completion_when_joiner_has_no_usable_channel():
    service, repo, reachability, _ = make_service({"owner"})
    link = service.get_or_create_friend_link("owner")

    result = service.establish_friendship_from_token("joiner", link.public_token)

    assert result.status == "deferred_channel_required"
    assert result.friendship is None
    assert result.continuation == {"friend_link_id": link.id}
    assert repo.list_active_friends("owner") == []

    reachability.reachable.add("joiner")
    completed = service.complete_deferred_friend_link(
        joiner_account_id="joiner",
        friend_link_id=link.id,
    )

    assert completed.status == "created"
    assert {friend.account_id for friend in service.list_friends("owner")} == {"joiner"}


def test_friendship_establishment_requires_owner_still_has_usable_channel():
    service, repo, reachability, _ = make_service({"owner"})
    link = service.get_or_create_friend_link("owner")
    reachability.reachable = {"joiner"}

    with pytest.raises(SocialSchedulingError) as error:
        service.establish_friendship_from_token("joiner", link.public_token)

    assert error.value.code == "owner_channel_required"
    assert repo.list_active_friends("owner") == []


def test_active_friendship_is_unique_and_removed_pair_can_reestablish():
    service, repo, _, _ = make_service({"owner", "joiner"})
    link = service.get_or_create_friend_link("owner")

    first = service.establish_friendship_from_token("joiner", link.public_token)
    second = service.establish_friendship_from_token("joiner", link.public_token)
    removed = service.remove_friend("owner", "joiner")
    third = service.establish_friendship_from_token("joiner", link.public_token)

    assert first.status == "created"
    assert second.status == "already_active"
    assert second.friendship.id == first.friendship.id
    assert removed.lifecycle == "removed"
    assert third.status == "created"
    assert third.friendship.id != first.friendship.id
    assert (
        len([f for f in repo.friendships_by_id.values() if f.lifecycle == "active"])
        == 1
    )
    assert (
        len([f for f in repo.friendships_by_id.values() if f.lifecycle == "removed"])
        == 1
    )


def test_commit_guard_blocks_friendship_and_notification_fact():
    service, repo, _, _ = make_service({"owner", "joiner"})
    link = service.get_or_create_friend_link("owner")

    with pytest.raises(RuntimeError, match="turn_superseded"):
        service.establish_friendship_from_token(
            "joiner",
            link.public_token,
            commit_guard=lambda: (_ for _ in ()).throw(RuntimeError("turn_superseded")),
        )

    assert repo.friendships_by_id == {}
    assert repo.notification_facts_by_id == {}
    assert repo.notification_recipients_by_id == {}


def test_remove_friend_lifecycle_does_not_cancel_existing_shared_reminders():
    service, _, _, _ = make_service({"owner", "friend"})
    create_active_friendship(service, "owner", "friend")
    created = service.create_shared_reminder(
        creator_account_id="owner",
        receiver_account_ids=["friend"],
        title="planning",
        local_trigger_at=datetime(2026, 6, 1, 9, 0),
        captured_timezone="Asia/Tokyo",
        duration_minutes=30,
        context={"source": "test"},
    )

    service.remove_friend("owner", "friend")

    assert service.list_friends("owner") == []
    assert (
        service.view_shared_reminder("owner", created.shared_reminder.id).status
        == "active"
    )
    blocked = service.create_shared_reminder(
        creator_account_id="owner",
        receiver_account_ids=["friend"],
        title="new planning",
        local_trigger_at=datetime(2026, 6, 2, 9, 0),
        captured_timezone="Asia/Tokyo",
        duration_minutes=30,
        context={"source": "test"},
    )
    assert blocked.status == "needs_participants"
    assert blocked.follow_up_facts["reason"] == "receiver_not_active_friend"


def test_commit_guard_blocks_shared_reminder_and_notification_fact():
    service, repo, _, _ = make_service({"creator", "friend"})
    create_active_friendship(service, "creator", "friend")

    with pytest.raises(RuntimeError, match="turn_superseded"):
        service.create_shared_reminder(
            creator_account_id="creator",
            receiver_account_ids=["friend"],
            title="planning",
            local_trigger_at=datetime(2026, 6, 1, 9, 0),
            captured_timezone="Asia/Tokyo",
            duration_minutes=30,
            context={"source": "test"},
            commit_guard=lambda: (_ for _ in ()).throw(RuntimeError("turn_superseded")),
        )

    assert repo.shared_reminders_by_id == {}
    assert repo.projections_by_id == {}
    assert [
        fact
        for fact in repo.notification_facts_by_id.values()
        if fact.object_type == "shared_reminder"
    ] == []


def test_group_shared_reminder_creation_is_one_object_with_participant_projections():
    service, _, _, _ = make_service({"creator", "bob", "carol"})
    create_active_friendship(service, "creator", "bob")
    create_active_friendship(service, "creator", "carol")

    created = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["carol", "bob"],
        title="team sync",
        local_trigger_at=datetime(2026, 6, 3, 10, 30),
        captured_timezone="Asia/Tokyo",
        duration_minutes=45,
        context={"source": "agent"},
    )

    assert created.status == "created"
    assert created.shared_reminder.creator_account_id == "creator"
    assert created.shared_reminder.participant_account_ids == (
        "bob",
        "carol",
        "creator",
    )
    assert {projection.account_id for projection in created.projections} == {
        "creator",
        "bob",
        "carol",
    }
    assert len(created.notification_facts) == 1
    assert created.notification_facts[0].facts["participants"] == [
        "bob",
        "carol",
        "creator",
    ]

    duplicate = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["bob", "carol"],
        title="team sync",
        local_trigger_at=datetime(2026, 6, 3, 10, 30),
        captured_timezone="Asia/Tokyo",
        duration_minutes=45,
        context={"source": "agent"},
    )

    assert duplicate.status == "duplicate"
    assert duplicate.shared_reminder.id == created.shared_reminder.id


def test_shared_reminder_accepts_aware_agent_datetime_as_local_wall_clock():
    service, repo, _, _ = make_service({"creator", "friend"})
    create_active_friendship(service, "creator", "friend")

    created = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["friend"],
        title="aware time",
        local_trigger_at=datetime(2029, 2, 19, 10, 0, tzinfo=UTC),
        captured_timezone="Asia/Shanghai",
        duration_minutes=15,
        context={"source": "conversation"},
    )

    assert created.status == "created"
    assert created.shared_reminder is not None
    assert created.shared_reminder.local_trigger_at == datetime(2029, 2, 19, 10, 0)
    assert created.shared_reminder.local_trigger_at.tzinfo is None
    assert len(repo.shared_reminders_by_id) == 1


def test_shared_reminder_view_cancel_and_completion_are_participant_scoped():
    service, _, _, _ = make_service({"creator", "friend", "outsider"})
    create_active_friendship(service, "creator", "friend")
    created = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["friend"],
        title="review",
        local_trigger_at=datetime(2026, 6, 4, 11, 0),
        captured_timezone="UTC",
        duration_minutes=15,
        context={"source": "test"},
    )

    with pytest.raises(SocialSchedulingError) as view_error:
        service.view_shared_reminder("outsider", created.shared_reminder.id)
    assert view_error.value.code == "shared_reminder_not_found"

    completed = service.complete_own_projection("friend", created.shared_reminder.id)
    assert completed.account_id == "friend"
    assert completed.completion_status == "completed"
    assert (
        service.view_shared_reminder("creator", created.shared_reminder.id).status
        == "active"
    )

    with pytest.raises(SocialSchedulingError) as cancel_error:
        service.cancel_shared_reminder("outsider", created.shared_reminder.id)
    assert cancel_error.value.code == "shared_reminder_not_found"

    cancelled = service.cancel_shared_reminder("friend", created.shared_reminder.id)
    assert cancelled.status == "cancelled"
    assert {projection.lifecycle for projection in cancelled.projections} == {
        "cancelled"
    }
    assert len(cancelled.notification_facts) == 1

    already = service.cancel_shared_reminder("creator", created.shared_reminder.id)
    assert already.status == "already_cancelled"
    assert already.notification_facts == []


def test_shared_reminder_pre_creation_checks_return_three_way_breakdown_without_mutation():
    service, repo, reachability, reminder_availability = make_service(
        {"creator", "busy_friend", "free_friend", "unreachable_friend"}
    )
    create_active_friendship(service, "creator", "busy_friend")
    create_active_friendship(service, "creator", "free_friend")
    create_active_friendship(service, "creator", "unreachable_friend")
    reminder_availability.intervals["busy_friend"] = [
        BusyInterval(
            account_id="busy_friend",
            start=datetime(2026, 6, 5, 9, 15),
            end=datetime(2026, 6, 5, 9, 45),
            source="personal",
        )
    ]
    reachability.reachable.discard("unreachable_friend")

    result = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["busy_friend", "free_friend", "unreachable_friend"],
        title="standup",
        local_trigger_at=datetime(2026, 6, 5, 9, 0),
        captured_timezone="Asia/Tokyo",
        duration_minutes=30,
        context={"source": "test"},
    )

    assert result.status == "blocked"
    assert result.breakdown == {
        "conflicting_participants": ["busy_friend"],
        "unreachable_participants": ["unreachable_friend"],
        "available_participants": ["free_friend"],
    }
    assert repo.shared_reminders_by_id == {}
    assert repo.projections_by_id == {}


def test_required_fields_are_validated_before_friend_or_channel_checks():
    service, repo, _, _ = make_service(set())

    result = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=[],
        title="",
        local_trigger_at=None,
        captured_timezone="UTC",
        duration_minutes=15,
        context=None,
    )

    assert result.status == "needs_participants"
    assert result.follow_up_facts == {"missing": "participants"}
    assert repo.shared_reminders_by_id == {}


def test_availability_query_is_authorized_bounded_and_privacy_safe():
    service, _, _, reminder_availability = make_service({"requester", "friend"})
    create_active_friendship(service, "requester", "friend")
    reminder_availability.intervals["friend"] = [
        BusyInterval(
            account_id="friend",
            start=datetime(2026, 6, 6, 13, 0),
            end=datetime(2026, 6, 6, 13, 30),
            source="personal",
            detail_id="private-reminder",
        )
    ]

    result = service.query_availability(
        requester_account_id="requester",
        friend_account_ids=["friend"],
        local_start=datetime(2026, 6, 6, 12, 0),
        local_end=datetime(2026, 6, 6, 14, 0),
        requester_timezone="Asia/Tokyo",
    )

    assert result.friend_account_id == "friend"
    assert [window.state for window in result.windows] == ["free", "busy", "free"]
    serialized = [window.to_public_dict() for window in result.windows]
    assert serialized == [
        {"start": "2026-06-06T12:00:00", "end": "2026-06-06T13:00:00", "state": "free"},
        {"start": "2026-06-06T13:00:00", "end": "2026-06-06T13:30:00", "state": "busy"},
        {"start": "2026-06-06T13:30:00", "end": "2026-06-06T14:00:00", "state": "free"},
    ]
    assert "private-reminder" not in str(serialized)
    assert "personal" not in str(serialized)


def test_availability_query_accepts_more_than_one_active_friend():
    service, _, _, reminder_availability = make_service({"requester", "bob", "carol"})
    create_active_friendship(service, "requester", "bob")
    create_active_friendship(service, "requester", "carol")
    reminder_availability.intervals["carol"] = [
        BusyInterval(
            account_id="carol",
            start=datetime(2026, 6, 6, 13, 0),
            end=datetime(2026, 6, 6, 13, 30),
            source="personal",
        )
    ]

    results = service.query_availability(
        requester_account_id="requester",
        friend_account_ids=["bob", "carol"],
        local_start=datetime(2026, 6, 6, 12, 0),
        local_end=datetime(2026, 6, 6, 14, 0),
        requester_timezone="Asia/Tokyo",
    )

    assert [result.friend_account_id for result in results] == ["bob", "carol"]
    assert all(
        set(window.to_public_dict()) == {"start", "end", "state"}
        for result in results
        for window in result.windows
    )


def test_notification_facts_store_structured_data_no_prose_and_partial_delivery_state():
    service, repo, _, _ = make_service({"owner", "joiner"})
    friendship = create_active_friendship(service, "owner", "joiner").friendship

    facts = repo.list_notification_facts()
    assert len(facts) == 1
    fact = facts[0]
    assert fact.type == "friendship_created"
    assert fact.status == "created"
    assert fact.object_id == friendship.id
    assert "text" not in fact.facts
    assert "payload" not in fact.facts
    assert "prose" not in fact.facts

    service.record_notification_delivery(
        notification_fact_id=fact.id,
        recipient_account_id="owner",
        delivery_state="delivered",
        error_facts={},
    )
    service.record_notification_delivery(
        notification_fact_id=fact.id,
        recipient_account_id="joiner",
        delivery_state="failed",
        error_facts={"type": "recipient_channel_unavailable"},
    )

    recipients = {
        recipient.recipient_account_id: recipient
        for recipient in repo.list_notification_recipients(fact.id)
    }
    assert recipients["owner"].delivery_state == "delivered"
    assert recipients["joiner"].delivery_state == "failed"
    assert recipients["joiner"].error_facts == {"type": "recipient_channel_unavailable"}
    assert "raw" not in str(recipients["joiner"].error_facts).lower()
