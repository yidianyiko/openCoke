from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from coke.composition import ReminderAvailabilityAdapter, SocialSchedulingToolAdapter
from coke.domains.reminder.models import Reminder
from coke.domains.social_scheduling.availability import (
    AvailabilityWindow,
    FriendAvailability,
)
from coke.domains.social_scheduling.models import FriendLinkView, SocialSchedulingError


@dataclass
class FakeGuard:
    calls: int = 0

    def guard_state_change(self) -> None:
        self.calls += 1


class FakeStagingGuard:
    def __init__(
        self,
        *,
        turn_id: str,
        input_from_seq: int,
        input_to_seq: int,
    ) -> None:
        self.turn_id = turn_id
        self.input_from_seq = input_from_seq
        self.input_to_seq = input_to_seq
        self.staged: list[dict[str, Any]] = []
        self.calls = 0

    def guard_state_change(self) -> None:
        self.calls += 1

    def stage_command(self, **kwargs):
        self.staged.append(kwargs)
        raise AssertionError("stage_command must not be called")


class FakeSocialSchedulingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.error: SocialSchedulingError | None = None
        self.shared_reminder_error: Exception | None = None
        self.shared_reminder_result: Any | None = None
        self.detect_shared_reminder_result: Any | None = None

    def get_or_create_friend_link(
        self,
        owner_account_id: str,
        commit_guard=None,
    ) -> FriendLinkView:
        self.calls.append(
            ("get_or_create_friend_link", {"owner_account_id": owner_account_id})
        )
        if self.error is not None:
            raise self.error
        return _friend_link_view(owner_account_id, "active")

    def reset_friend_link(
        self, owner_account_id: str, commit_guard=None
    ) -> FriendLinkView:
        self.calls.append(("reset_friend_link", {"owner_account_id": owner_account_id}))
        return _friend_link_view(
            owner_account_id,
            "active",
            token="reset_token",
            code="reset_code",
        )

    def disable_friend_link(
        self,
        owner_account_id: str,
        commit_guard=None,
    ) -> FriendLinkView:
        self.calls.append(
            ("disable_friend_link", {"owner_account_id": owner_account_id})
        )
        return _friend_link_view(
            owner_account_id,
            "disabled",
            token=None,
            code=None,
            qr_payload=None,
        )

    def query_availability(self, **kwargs):
        self.calls.append(("query_availability", kwargs))
        return FriendAvailability(
            friend_account_id="friend_1",
            friend_display_name="Oliver",
            windows=[
                AvailabilityWindow(
                    start=datetime.fromisoformat("2026-06-01T09:00:00"),
                    end=datetime.fromisoformat("2026-06-01T10:00:00"),
                    state="free",
                )
            ],
        )

    def establish_friendship_from_code(
        self,
        joiner_account_id: str,
        link_code: str,
        commit_guard=None,
    ):
        self.calls.append(
            (
                "establish_friendship_from_code",
                {
                    "joiner_account_id": joiner_account_id,
                    "link_code": link_code,
                },
            )
        )
        return FakeFriendshipResult()

    def create_shared_reminder(self, **kwargs):
        kwargs.pop("commit_guard", None)
        self.calls.append(("create_shared_reminder", kwargs))
        if self.shared_reminder_error is not None:
            raise self.shared_reminder_error
        if self.shared_reminder_result is not None:
            return self.shared_reminder_result
        return SimpleNamespace(
            status="created",
            shared_reminder=SimpleNamespace(id="shared_1"),
            breakdown={},
            follow_up_facts={},
        )

    def detect_and_create_shared_reminder(self, **kwargs):
        kwargs.pop("commit_guard", None)
        self.calls.append(("detect_and_create_shared_reminder", kwargs))
        if self.shared_reminder_error is not None:
            raise self.shared_reminder_error
        if self.detect_shared_reminder_result is not None:
            return self.detect_shared_reminder_result
        return SimpleNamespace(
            status="created",
            shared_reminder=SimpleNamespace(id="shared_1"),
            breakdown={},
            follow_up_facts={},
        )

    def update_shared_reminder(self, **kwargs):
        kwargs.pop("commit_guard", None)
        self.calls.append(("update_shared_reminder", kwargs))
        if self.shared_reminder_error is not None:
            raise self.shared_reminder_error
        if self.shared_reminder_result is not None:
            return self.shared_reminder_result
        return SimpleNamespace(
            status="rescheduled",
            shared_reminder=SimpleNamespace(
                id=kwargs["shared_reminder_id"],
                title="Dinner",
                local_trigger_at=kwargs["local_trigger_at"],
                captured_timezone=kwargs["captured_timezone"],
                duration_minutes=kwargs["duration_minutes"],
                participant_account_ids=("creator_1", "friend_1"),
            ),
            breakdown={},
            follow_up_facts={},
        )


def test_social_scheduling_tool_routes_friend_link_operations_to_service():
    service = FakeSocialSchedulingService()
    adapter = SocialSchedulingToolAdapter(service)
    guard = FakeGuard()

    get_result = adapter.execute(
        {"operation": "get_friend_link", "owner_account_id": "owner_1"}, guard
    )
    reset_result = adapter.execute(
        {"operation": "reset_friend_link", "owner_account_id": "owner_1"}, guard
    )
    disable_result = adapter.execute(
        {"operation": "disable_friend_link", "owner_account_id": "owner_1"}, guard
    )

    assert get_result.ok is True
    assert get_result.facts == {
        "friend_link_id": "link_owner_1",
        "owner_account_id": "owner_1",
        "lifecycle": "active",
        "public_token": "public_token",
        "link_code": "invite_code",
        "public_link_url": "http://localhost:4040/u/invite_code",
        "qr_payload": "http://localhost:4040/u/invite_code",
    }
    assert reset_result.ok is True
    assert reset_result.facts["public_token"] == "reset_token"
    assert reset_result.facts["public_link_url"] == "http://localhost:4040/u/reset_code"
    assert disable_result.ok is True
    assert disable_result.facts["lifecycle"] == "disabled"
    assert disable_result.facts["public_token"] is None
    assert disable_result.facts["link_code"] is None
    assert disable_result.facts["public_link_url"] is None
    assert service.calls == [
        ("get_or_create_friend_link", {"owner_account_id": "owner_1"}),
        ("reset_friend_link", {"owner_account_id": "owner_1"}),
        ("disable_friend_link", {"owner_account_id": "owner_1"}),
    ]
    assert guard.calls == 3


def test_social_scheduling_tool_maps_domain_errors_to_reason_codes():
    service = FakeSocialSchedulingService()
    service.error = SocialSchedulingError(
        "owner_channel_required",
        fact={"type": "owner_channel_required", "account_id": "owner_1"},
    )
    adapter = SocialSchedulingToolAdapter(service)

    result = adapter.execute(
        {"operation": "get_friend_link", "owner_account_id": "owner_1"},
        FakeGuard(),
    )

    assert result.ok is False
    assert result.reason_code == "owner_channel_required"
    assert result.facts == {"type": "owner_channel_required", "account_id": "owner_1"}


def test_social_scheduling_tool_exposes_privacy_safe_availability_query():
    service = FakeSocialSchedulingService()
    adapter = SocialSchedulingToolAdapter(service)
    guard = FakeGuard()

    result = adapter.execute(
        {
            "operation": "query_availability",
            "requester_account_id": "owner_1",
            "friend_account_ids": ["friend_1"],
            "local_start": "2026-06-01T09:00:00",
            "local_end": "2026-06-01T10:00:00",
            "requester_timezone": "Asia/Tokyo",
        },
        guard,
    )

    assert result.ok is True
    assert result.facts == {
        "availability": [
            {
                "friend_account_id": "friend_1",
                "friend_display_name": "Oliver",
                "windows": [
                    {
                        "start": "2026-06-01T09:00:00",
                        "end": "2026-06-01T10:00:00",
                        "state": "free",
                    }
                ],
            }
        ]
    }
    serialized = result.facts["availability"][0]
    assert set(serialized) == {"friend_account_id", "friend_display_name", "windows"}
    assert set(serialized["windows"][0]) == {"start", "end", "state"}
    assert service.calls == [
        (
            "query_availability",
            {
                "requester_account_id": "owner_1",
                "friend_account_ids": ["friend_1"],
                "local_start": datetime.fromisoformat("2026-06-01T09:00:00"),
                "local_end": datetime.fromisoformat("2026-06-01T10:00:00"),
                "requester_timezone": "Asia/Tokyo",
            },
        )
    ]
    assert guard.calls == 0


def test_reminder_availability_maps_utc_reminders_to_requester_local_wall_clock():
    repository = SimpleNamespace(
        list_active_reminders=lambda _account_id: [
            Reminder(
                id="reminder_1",
                owner_account_id="friend_1",
                content="private title",
                content_hash="hash",
                kind="timed",
                next_fire_at=datetime(2029, 2, 21, 2, 0, tzinfo=UTC),
                recurrence_rule={},
                captured_timezone="Asia/Shanghai",
                duration_minutes=30,
                lifecycle="active",
                hidden_from_calendar=False,
                shared_reminder_id=None,
                created_at=datetime(2026, 5, 30, tzinfo=UTC),
                updated_at=datetime(2026, 5, 30, tzinfo=UTC),
            )
        ]
    )

    intervals = ReminderAvailabilityAdapter(repository).personal_busy_intervals(
        "friend_1",
        datetime(2029, 2, 21, 9, 30),
        datetime(2029, 2, 21, 10, 30),
        "Asia/Shanghai",
    )

    assert len(intervals) == 1
    assert intervals[0].start == datetime(2029, 2, 21, 10, 0)
    assert intervals[0].end == datetime(2029, 2, 21, 10, 30)
    assert intervals[0].detail_id == "reminder_1"


def test_establish_friendship_operation_accepts_visible_invite_code():
    service = FakeSocialSchedulingService()
    adapter = SocialSchedulingToolAdapter(service)
    guard = FakeGuard()

    result = adapter.execute(
        {
            "operation": "establish_friendship_from_token",
            "joiner_account_id": "joiner_1",
            "link_code": "invite_code",
        },
        guard,
    )

    assert result.ok is True
    assert result.facts == {
        "status": "created",
        "friendship_id": "friendship_1",
        "counterpart_account_id": "friend",
        "counterpart_display_name": "Alice Push",
        "continuation": {},
    }
    assert service.calls == [
        (
            "establish_friendship_from_code",
            {"joiner_account_id": "joiner_1", "link_code": "invite_code"},
        )
    ]
    assert guard.calls == 1


def test_detect_and_create_shared_reminder_routes_raw_text_to_service():
    service = FakeSocialSchedulingService()
    adapter = SocialSchedulingToolAdapter(service)
    guard = FakeGuard()

    result = adapter.execute(
        {
            "operation": "detect_and_create_shared_reminder",
            "creator_account_id": "creator_1",
            "receiver_account_ids": ["friend_1"],
            "raw_text": "帮我和 lizihao 约一个今天晚上10:30的会议",
            "captured_timezone": "Asia/Shanghai",
            "duration_minutes": 15,
        },
        guard,
    )

    assert result.ok is True
    assert result.reason_code is None
    assert {
        key: result.facts[key]
        for key in ("status", "shared_reminder_id", "breakdown", "follow_up_facts")
    } == {
        "status": "created",
        "shared_reminder_id": "shared_1",
        "breakdown": {},
        "follow_up_facts": {},
    }
    assert result.facts["social_scheduling_outcome"]["status"] == "created_active"
    assert (
        result.facts["social_scheduling_outcome"]["operation"]
        == "detect_and_create_shared_reminder"
    )
    assert service.calls == [
        (
            "detect_and_create_shared_reminder",
            {
                "creator_account_id": "creator_1",
                "receiver_account_ids": ["friend_1"],
                "raw_text": "帮我和 lizihao 约一个今天晚上10:30的会议",
                "title": None,
                "captured_timezone": "Asia/Shanghai",
                "duration_minutes": 15,
            },
        )
    ]
    assert guard.calls == 1


def test_update_shared_reminder_execute_passes_idempotent_replay_flag():
    service = FakeSocialSchedulingService()
    adapter = SocialSchedulingToolAdapter(service)

    result = adapter.execute(
        {
            "operation": "update_shared_reminder",
            "account_id": "creator_1",
            "shared_reminder_id": "shared_1",
            "local_trigger_at": "2026-06-01T19:00:00",
            "captured_timezone": "UTC",
            "duration_minutes": 30,
            "idempotent_replay": True,
        },
        FakeGuard(),
    )

    assert result.ok is True
    assert result.reason_code is None
    assert service.calls == [
        (
            "update_shared_reminder",
            {
                "account_id": "creator_1",
                "shared_reminder_id": "shared_1",
                "local_trigger_at": datetime(2026, 6, 1, 19, 0),
                "captured_timezone": "UTC",
                "duration_minutes": 30,
                "idempotent_replay": True,
            },
        )
    ]


def test_interactive_shared_reminder_tool_executes_before_close():
    service = FakeSocialSchedulingService()
    adapter = SocialSchedulingToolAdapter(service)
    guard = FakeStagingGuard(turn_id="turn_1", input_from_seq=1, input_to_seq=1)

    result = adapter.execute(
        {
            "operation": "create_shared_reminder",
            "creator_account_id": "account_1",
            "receiver_account_ids": ["account_2"],
            "title": "Dinner",
            "local_trigger_at": "2026-06-01T19:00:00",
            "captured_timezone": "UTC",
        },
        guard,
    )

    assert result.ok is True
    assert result.facts["status"] == "created"
    assert service.calls == [
        (
            "create_shared_reminder",
            {
                "creator_account_id": "account_1",
                "receiver_account_ids": ["account_2"],
                "title": "Dinner",
                "local_trigger_at": datetime(2026, 6, 1, 19, 0),
                "captured_timezone": "UTC",
                "duration_minutes": None,
            },
        )
    ]
    assert guard.calls == 1
    assert guard.staged == []


def test_shared_reminder_tool_result_returns_social_outcome():
    service = FakeSocialSchedulingService()
    adapter = SocialSchedulingToolAdapter(service)
    guard = FakeStagingGuard(turn_id="turn_1", input_from_seq=1, input_to_seq=1)

    result = adapter.execute(
        {
            "operation": "create_shared_reminder",
            "creator_account_id": "account_1",
            "receiver_account_ids": ["account_2"],
            "title": "Dinner",
            "local_trigger_at": "2026-06-01T19:00:00",
            "captured_timezone": "UTC",
        },
        guard,
    )

    outcome = result.facts["social_scheduling_outcome"]
    assert outcome["status"] == "created_active"
    assert outcome["operation"] == "create_shared_reminder"
    assert all("staged" not in key for key in outcome)
    assert outcome["title"] == "Dinner"
    assert guard.staged == []


def test_blocked_shared_reminder_tool_result_returns_blocked_outcome():
    service = FakeSocialSchedulingService()
    service.shared_reminder_result = SimpleNamespace(
        status="needs_participants",
        shared_reminder=None,
        breakdown={},
        follow_up_facts={
            "reason": "unmatched_friend",
            "unresolved_reference_text": "zihao",
        },
    )
    adapter = SocialSchedulingToolAdapter(service)

    result = adapter.execute(
        {
            "operation": "create_shared_reminder",
            "creator_account_id": "creator_1",
            "receiver_account_ids": [],
            "title": "Team sync",
            "local_trigger_at": "2026-06-01T09:00:00",
            "captured_timezone": "Asia/Tokyo",
            "duration_minutes": 30,
            "context": {
                "source": "unit",
                "friend_resolution_status": "unmatched",
                "unresolved_reference_text": "zihao",
            },
        },
        FakeGuard(),
    )

    assert result.ok is False
    assert result.reason_code == "needs_participants"
    assert result.facts["social_scheduling_outcome"] == {
        "outcome_id": "create_shared_reminder:blocked_unmatched_friend:creator_1:zihao",
        "operation": "create_shared_reminder",
        "status": "blocked_unmatched_friend",
        "shared_reminder_id": None,
        "title": "Team sync",
        "local_trigger_at": "2026-06-01T09:00:00",
        "captured_timezone": "Asia/Tokyo",
        "duration_minutes": 30,
        "participant_account_ids": [],
        "blocker": "unmatched_friend",
        "facts_hash": None,
    }


def test_create_shared_reminder_repository_failure_returns_clear_non_success_result():
    service = FakeSocialSchedulingService()
    service.shared_reminder_error = ValueError(
        'duplicate key value violates unique constraint "uq_internal"'
    )
    adapter = SocialSchedulingToolAdapter(service)

    result = adapter.execute(
        {
            "operation": "create_shared_reminder",
            "creator_account_id": "creator_1",
            "receiver_account_ids": ["friend_1"],
            "title": "Team sync",
            "local_trigger_at": "2026-06-01T09:00:00",
            "captured_timezone": "Asia/Tokyo",
            "duration_minutes": 30,
        },
        FakeGuard(),
    )

    assert result.ok is False
    assert result.reason_code == "social_scheduling_write_failed"
    assert result.facts == {"type": "social_scheduling_write_failed"}
    assert service.calls == [
        (
            "create_shared_reminder",
            {
                "creator_account_id": "creator_1",
                "receiver_account_ids": ["friend_1"],
                "title": "Team sync",
                "local_trigger_at": datetime.fromisoformat("2026-06-01T09:00:00"),
                "captured_timezone": "Asia/Tokyo",
                "duration_minutes": 30,
            },
        )
    ]


class FakeFriendship:
    id = "friendship_1"


class FakeFriendshipResult:
    status = "created"
    friendship = FakeFriendship()
    counterpart_account_id = "friend"
    counterpart_display_name = "Alice Push"
    continuation: dict[str, Any] = {}


def _friend_link_view(
    owner_account_id: str,
    lifecycle: str,
    *,
    token: str | None = "public_token",
    code: str | None = "invite_code",
    qr_payload: str | None = None,
) -> FriendLinkView:
    if qr_payload is None and code is not None:
        qr_payload = f"http://localhost:4040/u/{code}"
    return FriendLinkView(
        id=f"link_{owner_account_id}",
        owner_account_id=owner_account_id,
        lifecycle=lifecycle,
        public_token=token,
        link_code=code,
        qr_payload=qr_payload,
    )
