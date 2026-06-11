from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from coke.domains.reminder.models import DetectedReminderFields
from coke.domains.social_scheduling.availability import (
    BusyInterval,
    ParticipantReachabilityPort,
    ReminderAvailabilityPort,
)
from coke.domains.social_scheduling.models import SocialSchedulingError
from coke.domains.social_scheduling.repository import (
    InMemorySocialSchedulingRepository,
)
from coke.domains.social_scheduling.service import SocialSchedulingService

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


class FakeDetector:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls: list[tuple[str, str, datetime]] = []

    def extract(self, text, captured_timezone, now):
        self.calls.append((text, captured_timezone, now))
        return self.outputs.pop(0)


def make_service(
    reachable: set[str] | None = None,
    now=None,
    detector=None,
    public_base_url: str = "http://localhost:4040",
):
    repo = InMemorySocialSchedulingRepository()
    reachability = FakeReachability(reachable)
    reminder_availability = FakeReminderAvailability()
    service = SocialSchedulingService(
        repository=repo,
        reachability=reachability,
        reminder_availability=reminder_availability,
        detector=detector,
        now=now or (lambda: NOW),
        id_factory=lambda prefix: f"{prefix}_{len(repo.generated_ids) + 1}",
        token_factory=lambda prefix: f"{prefix}_token_{len(repo.generated_tokens) + 1}",
        public_base_url=public_base_url,
    )
    return service, repo, reachability, reminder_availability


def create_active_friendship(service, owner: str, joiner: str):
    link = service.get_or_create_friend_link(owner)
    return service.establish_friendship_from_token(joiner, link.public_token)


def test_friend_link_payload_uses_public_base_url_and_link_code():
    service, _repo, _reachability, _availability = make_service(
        {"owner"},
        public_base_url="https://web.example.com",
    )

    link = service.get_or_create_friend_link("owner")

    assert link.public_token == "friend_link_token_1"
    assert link.link_code == "friend_code_token_2"
    assert link.qr_payload == "https://web.example.com/u/friend_code_token_2"


def test_resolve_public_friend_link_returns_active_reachable_owner_display_name():
    service, _repo, _reachability, _availability = make_service({"owner"})
    service.display_name_resolver = lambda account_id: {"owner": "Mina Owner"}[
        account_id
    ]
    link = service.get_or_create_friend_link("owner")

    resolved = service.resolve_public_friend_link(link.link_code)

    assert resolved is not None
    assert resolved.link_code == link.link_code
    assert resolved.status == "active"
    assert resolved.owner_display_name == "Mina Owner"


def test_resolve_public_friend_link_returns_none_for_missing_disabled_or_unreachable():
    service, _repo, reachability, _availability = make_service({"owner"})
    link = service.get_or_create_friend_link("owner")

    assert service.resolve_public_friend_link("missing-code") is None

    service.disable_friend_link("owner")
    assert service.resolve_public_friend_link(link.link_code) is None

    reset = service.reset_friend_link("owner")
    reachability.reachable.clear()
    assert service.resolve_public_friend_link(reset.link_code) is None


def test_resolve_public_friend_link_returns_none_when_display_name_missing():
    service, _repo, _reachability, _availability = make_service({"owner"})
    service.display_name_resolver = lambda _account_id: (_ for _ in ()).throw(
        RuntimeError("user_profile_not_found")
    )
    link = service.get_or_create_friend_link("owner")

    assert service.resolve_public_friend_link(link.link_code) is None


def test_direct_friendship_is_active_and_has_no_pending_request_model():
    service, repo, _, _ = make_service({"owner", "joiner"})

    result = create_active_friendship(service, "owner", "joiner")

    assert result.status == "created"
    assert result.friendship is not None
    assert result.friendship.lifecycle == "active"
    assert {friend.account_id for friend in service.list_friends("owner")} == {"joiner"}
    assert {friend.account_id for friend in service.list_friends("joiner")} == {"owner"}
    assert not hasattr(repo, "friend_requests")


def test_friend_list_entries_include_profile_display_names():
    service, _repo, _, _ = make_service({"owner", "joiner"})
    service.display_name_resolver = lambda account_id: {
        "joiner": "Alice Push",
        "owner": "Owner Name",
    }[account_id]
    create_active_friendship(service, "owner", "joiner")

    friends = service.list_friends("owner")

    assert friends[0].account_id == "joiner"
    assert friends[0].display_name == "Alice Push"


def test_friend_list_and_reference_resolution_accept_dashed_account_id():
    creator = "635d3bdc1b024a08acf49940b91a9de5"
    dashed_creator = "635d3bdc-1b02-4a08-acf4-9940b91a9de5"
    friend = "ae02ff016fcd4d39a189e51c8c8a31e6"
    service, _repo, _, _ = make_service({creator, friend})
    service.display_name_resolver = lambda account_id: {
        creator: "Creator Name",
        friend: "Li Zihao",
    }[account_id]
    create_active_friendship(service, creator, friend)

    friends = service.list_friends(dashed_creator)
    resolved = service.resolve_active_friend_reference(dashed_creator, "Li Zihao")

    assert [entry.account_id for entry in friends] == [friend]
    assert resolved.status == "matched"
    assert resolved.matched_account_id == friend
    assert resolved.candidates == (friend,)


def test_resolve_active_friend_reference_reports_ambiguous_partial_name_match():
    service, _repo, _, _ = make_service({"lizihao", "oliver_chen", "oliver_wang"})
    service.display_name_resolver = lambda account_id: {
        "lizihao": "Li Zihao",
        "oliver_chen": "Oliver Chen",
        "oliver_wang": "Oliver Wang",
    }[account_id]
    create_active_friendship(service, "lizihao", "oliver_chen")
    create_active_friendship(service, "lizihao", "oliver_wang")

    result = service.resolve_active_friend_reference("lizihao", "Oliver")

    assert result.status == "ambiguous"
    assert result.matched_account_id is None
    assert result.candidates == ("oliver_chen", "oliver_wang")


def test_resolve_active_friend_reference_matches_single_partial_active_friend():
    service, _repo, _, _ = make_service({"lizihao", "oliver_chen"})
    service.display_name_resolver = lambda account_id: {
        "lizihao": "Li Zihao",
        "oliver_chen": "Oliver Chen",
    }[account_id]
    create_active_friendship(service, "lizihao", "oliver_chen")

    result = service.resolve_active_friend_reference("lizihao", "Oliver")

    assert result.status == "matched"
    assert result.matched_account_id == "oliver_chen"
    assert result.candidates == ("oliver_chen",)


def test_resolve_active_friend_reference_ignores_partial_non_friends():
    service, _repo, _, _ = make_service({"lizihao", "amy", "oliver_chen"})
    service.display_name_resolver = lambda account_id: {
        "lizihao": "Li Zihao",
        "amy": "Amy Jones",
        "oliver_chen": "Oliver Chen",
    }[account_id]
    create_active_friendship(service, "lizihao", "amy")

    result = service.resolve_active_friend_reference("lizihao", "Oliver")

    assert result.status == "unmatched"
    assert result.matched_account_id is None
    assert result.candidates == ()


def test_friend_link_join_creates_active_friendship_without_joiner_channel():
    service, repo, _reachability, _availability = make_service({"owner"})
    service.display_name_resolver = lambda account_id: {
        "owner": "Oliver",
        "joiner": "Eva",
    }[account_id]
    link = service.get_or_create_friend_link("owner")

    result = service.establish_friendship_from_token("joiner", link.public_token)

    assert result.status == "created"
    assert result.friendship is not None
    assert result.friendship.lifecycle == "active"
    assert result.continuation == {}
    assert result.counterpart_account_id == "owner"
    assert result.counterpart_display_name == "Oliver"
    assert {friend.account_id for friend in service.list_friends("owner")} == {"joiner"}
    assert {friend.account_id for friend in service.list_friends("joiner")} == {"owner"}
    assert repo.list_active_friends("owner") == ["joiner"]


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
    service.display_name_resolver = lambda account_id: {
        "owner": "Oliver",
        "joiner": "Eva",
    }[account_id]
    link = service.get_or_create_friend_link("owner")

    first = service.establish_friendship_from_token("joiner", link.public_token)
    second = service.establish_friendship_from_token("joiner", link.public_token)
    removed = service.remove_friend("owner", "joiner")
    third = service.establish_friendship_from_token("joiner", link.public_token)

    assert first.status == "created"
    assert second.status == "already_active"
    assert second.friendship.id == first.friendship.id
    assert second.counterpart_account_id == "owner"
    assert second.counterpart_display_name == "Oliver"
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
    service, repo, _, _ = make_service({"creator", "bob", "carol"})
    service.display_name_resolver = lambda account_id: {
        "bob": "Bob Chen",
        "carol": "Carol Wu",
        "creator": "Creator Name",
    }[account_id]
    create_active_friendship(service, "creator", "bob")
    create_active_friendship(service, "creator", "carol")

    created = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["carol", "bob"],
        title="team sync",
        local_trigger_at=datetime(2026, 6, 3, 10, 30),
        captured_timezone="Asia/Tokyo",
        duration_minutes=45,
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
    assert created.notification_facts[0].facts["actor_display_name"] == "Creator Name"
    assert created.notification_facts[0].facts["participants"] == [
        "bob",
        "carol",
        "creator",
    ]
    assert created.notification_facts[0].facts["delivery_recipients"] == [
        "bob",
        "carol",
    ]
    created_recipients = {
        recipient.recipient_account_id
        for recipient in repo.list_notification_recipients(
            created.notification_facts[0].id
        )
    }
    assert created_recipients == {"bob", "carol"}

    duplicate = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["bob", "carol"],
        title="team sync",
        local_trigger_at=datetime(2026, 6, 3, 10, 30),
        captured_timezone="Asia/Tokyo",
        duration_minutes=45,
    )

    assert duplicate.status == "duplicate"
    assert duplicate.shared_reminder.id == created.shared_reminder.id
    assert service.friend_identifiers_for_shared_reminder(
        created.shared_reminder.id,
        viewer_account_id="creator",
    ) == ["Bob Chen", "Carol Wu"]
    assert service.friend_identifiers_for_shared_reminder(
        created.shared_reminder.id,
        viewer_account_id="bob",
    ) == ["Carol Wu", "Creator Name"]
    assert (
        service.friend_identifiers_for_shared_reminder(
            created.shared_reminder.id,
            viewer_account_id="outsider",
        )
        == []
    )


def test_shared_reminder_creation_does_not_require_context():
    service, repo, _, _ = make_service({"creator", "friend"})
    create_active_friendship(service, "creator", "friend")

    created = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["friend"],
        title="planning",
        local_trigger_at=datetime(2026, 6, 3, 10, 30),
        captured_timezone="Asia/Tokyo",
        duration_minutes=30,
    )

    assert created.status == "created"
    assert created.shared_reminder is not None
    assert created.shared_reminder.id in repo.shared_reminders_by_id


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
    )

    assert created.status == "created"
    assert created.shared_reminder is not None
    assert created.shared_reminder.local_trigger_at == datetime(2029, 2, 19, 10, 0)
    assert created.shared_reminder.local_trigger_at.tzinfo is None
    assert len(repo.shared_reminders_by_id) == 1


def test_shared_reminder_past_trigger_requires_confirmation_without_mutation():
    service, repo, _, _ = make_service(
        {"creator", "friend"},
        now=lambda: datetime(2026, 5, 31, 11, 44, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    create_active_friendship(service, "creator", "friend")

    result = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["friend"],
        title="lunch",
        local_trigger_at=datetime(2025, 7, 11, 12, 0),
        captured_timezone="Asia/Shanghai",
        duration_minutes=60,
    )

    assert result.status == "needs_past_time_confirmation"
    assert result.shared_reminder is None
    assert result.follow_up_facts == {
        "time_state": "needs_past_time_confirmation",
        "local_trigger_at": "2025-07-11T12:00:00",
        "captured_timezone": "Asia/Shanghai",
    }
    assert repo.shared_reminders_by_id == {}
    assert repo.projections_by_id == {}
    assert [
        fact
        for fact in repo.notification_facts_by_id.values()
        if fact.object_type == "shared_reminder"
    ] == []


@pytest.mark.parametrize(
    ("raw_text", "detected_time"),
    [
        (
            "帮我和 lizihao 约一个今天晚上10:30的会议",
            datetime(2026, 5, 31, 22, 30),
        ),
        (
            "帮我和 olivers 约一个明天晚上十点半的会议",
            datetime(2026, 6, 1, 22, 30),
        ),
    ],
)
def test_detected_shared_reminder_uses_account_local_now_for_relative_time(
    raw_text,
    detected_time,
):
    detector = FakeDetector(
        [
            DetectedReminderFields(
                content="会议",
                trigger_time=detected_time,
                recurrence_rule={},
                duration_minutes=None,
            )
        ]
    )
    service, repo, _, _ = make_service(
        {"creator", "friend"},
        now=lambda: datetime(2026, 5, 31, 6, 2, tzinfo=UTC),
        detector=detector,
    )
    create_active_friendship(service, "creator", "friend")

    result = service.detect_and_create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["friend"],
        raw_text=raw_text,
        title=None,
        captured_timezone="Asia/Shanghai",
        duration_minutes=None,
    )

    assert result.status == "created"
    assert result.shared_reminder is not None
    assert result.shared_reminder.status == "active"
    assert result.shared_reminder.local_trigger_at == detected_time
    assert result.shared_reminder.captured_timezone == "Asia/Shanghai"
    assert len(repo.shared_reminders_by_id) == 1
    assert [(text, timezone) for text, timezone, _ in detector.calls] == [
        (raw_text, "Asia/Shanghai")
    ]
    detector_now = detector.calls[0][2]
    assert detector_now.tzinfo == ZoneInfo("Asia/Shanghai")
    assert (
        detector_now.year,
        detector_now.month,
        detector_now.day,
        detector_now.hour,
        detector_now.minute,
    ) == (2026, 5, 31, 14, 2)


def test_detected_shared_reminder_keeps_past_time_guard():
    detector = FakeDetector(
        [
            DetectedReminderFields(
                content="会议",
                trigger_time=datetime(2026, 5, 31, 13, 30),
                recurrence_rule={},
                duration_minutes=None,
            )
        ]
    )
    service, repo, _, _ = make_service(
        {"creator", "friend"},
        now=lambda: datetime(2026, 5, 31, 6, 2, tzinfo=UTC),
        detector=detector,
    )
    create_active_friendship(service, "creator", "friend")

    result = service.detect_and_create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["friend"],
        raw_text="帮我和 lizihao 约一个今天下午1:30的会议",
        title=None,
        captured_timezone="Asia/Shanghai",
        duration_minutes=None,
    )

    assert result.status == "needs_past_time_confirmation"
    assert result.shared_reminder is None
    assert result.follow_up_facts == {
        "time_state": "needs_past_time_confirmation",
        "local_trigger_at": "2026-05-31T13:30:00",
        "captured_timezone": "Asia/Shanghai",
    }
    assert repo.shared_reminders_by_id == {}
    assert repo.projections_by_id == {}


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


def test_cancel_shared_reminder_deletes_projection_reminders():
    service, repo, _, _ = make_service({"creator", "friend"})
    create_active_friendship(service, "creator", "friend")
    created = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["friend"],
        title="review",
        local_trigger_at=datetime(2026, 6, 4, 11, 0),
        captured_timezone="UTC",
        duration_minutes=15,
    )

    assert {
        repo.projection_reminders_by_id[projection.reminder_id].lifecycle
        for projection in created.projections
    } == {"active"}

    service.cancel_shared_reminder("friend", created.shared_reminder.id)

    assert {
        repo.projection_reminders_by_id[projection.reminder_id].lifecycle
        for projection in created.projections
    } == {"deleted"}


def test_update_shared_reminder_reschedules_existing_object_and_projection_reminders():
    service, repo, _, _ = make_service({"creator", "friend"})
    service.display_name_resolver = lambda account_id: {
        "creator": "Creator Name",
        "friend": "Friend Name",
    }[account_id]
    create_active_friendship(service, "creator", "friend")
    created = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["friend"],
        title="review",
        local_trigger_at=datetime(2026, 6, 4, 11, 0),
        captured_timezone="UTC",
        duration_minutes=15,
    )
    shared_id = created.shared_reminder.id

    result = service.update_shared_reminder(
        account_id="creator",
        shared_reminder_id=shared_id,
        local_trigger_at=datetime(2026, 6, 4, 12, 0),
        captured_timezone="UTC",
        duration_minutes=45,
    )

    assert result.status == "rescheduled"
    assert result.shared_reminder.id == shared_id
    assert len(repo.shared_reminders_by_id) == 1
    assert repo.shared_reminders_by_id[shared_id].local_trigger_at == datetime(
        2026, 6, 4, 12, 0
    )
    assert repo.shared_reminders_by_id[shared_id].duration_minutes == 45
    assert {
        (
            reminder.content,
            reminder.next_fire_at,
            reminder.duration_minutes,
            reminder.lifecycle,
        )
        for reminder in repo.projection_reminders_by_id.values()
    } == {
        ("review", datetime(2026, 6, 4, 12, 0, tzinfo=UTC), 45, "active"),
    }
    assert result.notification_facts[0].type == "shared_reminder_rescheduled"
    assert result.notification_facts[0].facts["delivery_recipients"] == ["friend"]


def test_update_shared_reminder_conflict_leaves_existing_rows_unchanged():
    service, repo, _, reminder_availability = make_service({"creator", "friend"})
    create_active_friendship(service, "creator", "friend")
    created = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["friend"],
        title="review",
        local_trigger_at=datetime(2026, 6, 4, 11, 0),
        captured_timezone="UTC",
        duration_minutes=15,
    )
    shared_id = created.shared_reminder.id
    original_projection_times = {
        projection.reminder_id: repo.projection_reminders_by_id[
            projection.reminder_id
        ].next_fire_at
        for projection in created.projections
    }
    reminder_availability.intervals["friend"] = [
        BusyInterval(
            account_id="friend",
            start=datetime(2026, 6, 4, 12, 10),
            end=datetime(2026, 6, 4, 12, 20),
            source="personal",
            detail_id="friend-busy",
        )
    ]

    result = service.update_shared_reminder(
        account_id="creator",
        shared_reminder_id=shared_id,
        local_trigger_at=datetime(2026, 6, 4, 12, 0),
        captured_timezone="UTC",
        duration_minutes=45,
    )

    assert result.status == "blocked"
    assert result.breakdown == {
        "conflicting_participants": ["friend"],
        "unreachable_participants": [],
        "available_participants": ["creator"],
    }
    assert repo.shared_reminders_by_id[shared_id].local_trigger_at == datetime(
        2026, 6, 4, 11, 0
    )
    assert {
        projection.reminder_id: repo.projection_reminders_by_id[
            projection.reminder_id
        ].next_fire_at
        for projection in created.projections
    } == original_projection_times


def test_update_shared_reminder_excludes_current_projection_from_conflict_check():
    service, repo, _, reminder_availability = make_service({"creator", "friend"})
    create_active_friendship(service, "creator", "friend")
    created = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["friend"],
        title="review",
        local_trigger_at=datetime(2026, 6, 4, 11, 0),
        captured_timezone="UTC",
        duration_minutes=15,
    )
    friend_projection = next(
        projection
        for projection in created.projections
        if projection.account_id == "friend"
    )
    reminder_availability.intervals["friend"] = [
        BusyInterval(
            account_id="friend",
            start=datetime(2026, 6, 4, 11, 0),
            end=datetime(2026, 6, 4, 11, 15),
            source="personal",
            detail_id=friend_projection.reminder_id,
        )
    ]

    result = service.update_shared_reminder(
        account_id="friend",
        shared_reminder_id=created.shared_reminder.id,
        local_trigger_at=datetime(2026, 6, 4, 11, 0),
        captured_timezone="UTC",
        duration_minutes=30,
    )

    assert result.status == "rescheduled"
    assert (
        repo.shared_reminders_by_id[created.shared_reminder.id].duration_minutes == 30
    )


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
    assert result.friend_display_name == "friend"
    assert [window.state for window in result.windows] == ["free", "busy", "free"]
    serialized = [window.to_public_dict() for window in result.windows]
    assert serialized == [
        {"start": "2026-06-06T12:00:00", "end": "2026-06-06T13:00:00", "state": "free"},
        {"start": "2026-06-06T13:00:00", "end": "2026-06-06T13:30:00", "state": "busy"},
        {"start": "2026-06-06T13:30:00", "end": "2026-06-06T14:00:00", "state": "free"},
    ]
    assert "private-reminder" not in str(serialized)
    assert "personal" not in str(serialized)


def test_availability_result_includes_public_friend_display_name():
    service, _, _, reminder_availability = make_service({"requester", "friend"})
    create_active_friendship(service, "requester", "friend")
    service.display_name_resolver = lambda account_id: {"friend": "Oliver"}[account_id]
    reminder_availability.intervals["friend"] = []

    result = service.query_availability(
        requester_account_id="requester",
        friend_account_ids=["friend"],
        local_start=datetime(2026, 6, 1, 9, 0),
        local_end=datetime(2026, 6, 1, 10, 0),
        requester_timezone="Asia/Tokyo",
    )

    assert result.friend_display_name == "Oliver"


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


def test_shared_reminder_receiver_delivery_creates_creator_visible_receipt():
    service, repo, _, _ = make_service({"creator", "friend"})
    service.display_name_resolver = lambda account_id: {
        "creator": "Creator Name",
        "friend": "Friend Name",
    }[account_id]
    create_active_friendship(service, "creator", "friend")
    created = service.create_shared_reminder(
        creator_account_id="creator",
        receiver_account_ids=["friend"],
        title="brunch",
        local_trigger_at=datetime(2026, 6, 3, 10, 30),
        captured_timezone="Asia/Tokyo",
        duration_minutes=45,
    )
    created_fact = created.notification_facts[0]

    service.record_notification_delivery(
        notification_fact_id=created_fact.id,
        recipient_account_id="friend",
        delivery_state="delivered",
        error_facts={},
        turn_id="receiver_turn",
    )

    facts = repo.list_notification_facts()
    assert [fact.type for fact in facts] == [
        "friendship_created",
        "shared_reminder_created",
        "shared_reminder_delivery_confirmed",
    ]
    receipt = facts[-1]
    assert receipt.actor_account_id == "friend"
    assert receipt.object_id == created.shared_reminder.id
    assert receipt.facts["creator_account_id"] == "creator"
    assert receipt.facts["recipient_account_id"] == "friend"
    assert receipt.facts["recipient_display_name"] == "Friend Name"
    assert receipt.facts["title"] == "brunch"
    assert receipt.facts["delivery_state"] == "delivered"
    assert receipt.facts["delivery_recipients"] == ["creator"]
    receipt_recipients = repo.list_notification_recipients(receipt.id)
    assert [recipient.recipient_account_id for recipient in receipt_recipients] == [
        "creator"
    ]


def test_undelivered_notification_resend_turn_returns_only_undelivered_recipient_facts():
    service, repo, _, _ = make_service({"owner", "joiner"})
    create_active_friendship(service, "owner", "joiner")
    fact = repo.list_notification_facts()[0]
    service.record_notification_delivery(
        notification_fact_id=fact.id,
        recipient_account_id="owner",
        delivery_state="undelivered",
        error_facts={"type": "recipient_channel_unavailable"},
    )
    service.record_notification_delivery(
        notification_fact_id=fact.id,
        recipient_account_id="joiner",
        delivery_state="failed",
        error_facts={"type": "recipient_channel_unavailable"},
    )

    resend = service.undelivered_notification_resend_turn("owner")

    assert resend.notification_fact_ids == [fact.id]
    assert (
        service.undelivered_notification_resend_turn("joiner").notification_fact_ids
        == []
    )
