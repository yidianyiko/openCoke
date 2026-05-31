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

    def stage_command(self, **kwargs):
        self.staged.append(kwargs)
        return SimpleNamespace(
            id="staged_1",
            preview_facts=dict(kwargs["preview_facts"]),
        )


class FakeSocialSchedulingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.error: SocialSchedulingError | None = None
        self.shared_reminder_error: Exception | None = None

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
        return _friend_link_view(owner_account_id, "active", token="reset_token")

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
        return SimpleNamespace(
            status="created",
            shared_reminder=SimpleNamespace(id="shared_1"),
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
        "public_link_url": "https://coke.example/friends/public_token",
        "qr_payload": "https://coke.example/friends/public_token",
    }
    assert reset_result.ok is True
    assert reset_result.facts["public_token"] == "reset_token"
    assert (
        reset_result.facts["public_link_url"]
        == "https://coke.example/friends/reset_token"
    )
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
            "context": {"source": "unit"},
        },
        guard,
    )

    assert result.ok is True
    assert result.reason_code is None
    assert result.facts == {
        "status": "created",
        "shared_reminder_id": "shared_1",
        "breakdown": {},
        "follow_up_facts": {},
    }
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
                "context": {"source": "unit"},
            },
        )
    ]
    assert guard.calls == 1


def test_interactive_shared_reminder_tool_stages_before_close():
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
            "context": {"source": "unit"},
        },
        guard,
    )

    assert result.ok is True
    assert result.facts["status"] == "staged"
    assert service.calls == []
    assert guard.staged[0]["domain"] == "social_scheduling"
    assert guard.staged[0]["operation"] == "create_shared_reminder"


def test_create_shared_reminder_repository_failure_returns_clear_non_success_result():
    service = FakeSocialSchedulingService()
    service.shared_reminder_error = ValueError("notification_fact_write_failed")
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
            "context": {"source": "unit"},
        },
        FakeGuard(),
    )

    assert result.ok is False
    assert result.reason_code == "notification_fact_write_failed"
    assert result.facts == {"type": "notification_fact_write_failed"}
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
                "context": {"source": "unit"},
            },
        )
    ]


class FakeFriendship:
    id = "friendship_1"


class FakeFriendshipResult:
    status = "created"
    friendship = FakeFriendship()
    continuation: dict[str, Any] = {}


def _friend_link_view(
    owner_account_id: str,
    lifecycle: str,
    *,
    token: str | None = "public_token",
    code: str | None = "invite_code",
    qr_payload: str | None = None,
) -> FriendLinkView:
    if qr_payload is None and token is not None:
        qr_payload = f"https://coke.example/friends/{token}"
    return FriendLinkView(
        id=f"link_{owner_account_id}",
        owner_account_id=owner_account_id,
        lifecycle=lifecycle,
        public_token=token,
        link_code=code,
        qr_payload=qr_payload,
    )
