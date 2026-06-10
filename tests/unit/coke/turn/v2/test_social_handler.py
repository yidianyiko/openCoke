from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from coke.domains.social_scheduling.availability import (
    AvailabilityWindow,
    FriendAvailability,
)
from coke.domains.social_scheduling.models import (
    FriendResolutionResult,
    SharedReminder,
    SharedReminderCancellationResult,
    SharedReminderCreateResult,
)
from coke.turn.v2.contracts import ActionOutcome, CompiledAction, ProposedAction
from coke.turn.v2.handlers.social import SocialSchedulingActionHandler

NOW = datetime(2026, 6, 10, 1, 0, tzinfo=UTC)
LOCAL_TRIGGER = datetime(2026, 6, 11, 9, 0)


class StubSocialSchedulingService:
    def __init__(self) -> None:
        self.resolutions: dict[str, FriendResolutionResult] = {
            "Amy": FriendResolutionResult(
                status="matched",
                matched_account_id="friend-amy",
                candidates=("friend-amy",),
            ),
            "Bob": FriendResolutionResult(
                status="matched",
                matched_account_id="friend-bob",
                candidates=("friend-bob",),
            ),
        }
        self.create_result: Any = SharedReminderCreateResult(
            status="created",
            shared_reminder=_shared_reminder("sr-1"),
        )
        self.cancel_result = SharedReminderCancellationResult(
            status="cancelled",
            shared_reminder=_shared_reminder("sr-1"),
            projections=[],
        )
        self.shared_reminders = [_shared_reminder("sr-1")]
        self.availability_result: Any = FriendAvailability(
            friend_account_id="friend-amy",
            friend_display_name="Amy",
            windows=[
                AvailabilityWindow(
                    start=datetime(2026, 6, 11, 9, 0),
                    end=datetime(2026, 6, 11, 10, 0),
                    state="free",
                )
            ],
        )
        self.calls: list[tuple[str, dict[str, Any]]] = []

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
        return self.resolutions.get(text, FriendResolutionResult(status="unmatched"))

    def create_shared_reminder(self, **kwargs: Any) -> Any:
        self.calls.append(("create_shared_reminder", kwargs))
        return self.create_result

    def detect_and_create_shared_reminder(self, **kwargs: Any) -> Any:
        self.calls.append(("detect_and_create_shared_reminder", kwargs))
        return self.create_result

    def list_shared_reminders(self, account_id: str) -> list[SharedReminder]:
        self.calls.append(("list_shared_reminders", {"account_id": account_id}))
        return self.shared_reminders

    def cancel_shared_reminder(self, **kwargs: Any) -> SharedReminderCancellationResult:
        self.calls.append(("cancel_shared_reminder", kwargs))
        return self.cancel_result

    def query_availability(self, **kwargs: Any) -> Any:
        self.calls.append(("query_availability", kwargs))
        return self.availability_result


class RecordingGuard:
    def __init__(self) -> None:
        self.turn_id = "turn-1"
        self.staged: list[dict[str, Any]] = []
        self.state_change_calls = 0

    def guard_state_change(self) -> None:
        self.state_change_calls += 1

    def stage_command(self, **kwargs: Any) -> Any:
        self.staged.append(kwargs)
        return SimpleNamespace(id=f"stage-{len(self.staged)}")


def _compiled(operation: str, params: dict[str, Any]) -> CompiledAction:
    return CompiledAction(
        action=ProposedAction(
            domain="social_scheduling",
            operation=operation,
            params=params,
        )
    )


def _shared_reminder(reminder_id: str, title: str = "send deck") -> SharedReminder:
    return SharedReminder(
        id=reminder_id,
        creator_account_id="acct-1",
        participant_account_ids=("acct-1", "friend-amy"),
        participant_set_hash="participants-hash",
        title=title,
        title_hash=f"title-{reminder_id}",
        local_trigger_at=LOCAL_TRIGGER,
        captured_timezone="Asia/Tokyo",
        duration_minutes=15,
        status="active",
        cancelled_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def test_create_shared_reminder_resolves_participant_and_stages_created() -> None:
    service = StubSocialSchedulingService()
    guard = RecordingGuard()

    outcome = SocialSchedulingActionHandler(service).resolve_and_stage(
        _compiled(
            "create_shared_reminder",
            {
                "creator_account_id": "acct-1",
                "participant": "Amy",
                "content": "send deck",
                "local_trigger_at": LOCAL_TRIGGER,
                "captured_timezone": "Asia/Tokyo",
            },
        ),
        guard,
    )

    assert outcome == ActionOutcome(
        category="done",
        status="created",
        data={
            "status": "created",
            "shared_reminder": {
                "shared_reminder_id": "sr-1",
                "creator_account_id": "acct-1",
                "participant_account_ids": ["acct-1", "friend-amy"],
                "title": "send deck",
                "local_trigger_at": "2026-06-11T09:00:00",
                "captured_timezone": "Asia/Tokyo",
                "duration_minutes": 15,
                "status": "active",
            },
            "breakdown": {},
            "follow_up_facts": {},
        },
        staged_command_id="stage-1",
    )
    assert service.calls[0] == (
        "resolve_active_friend_reference",
        {"account_id": "acct-1", "text": "Amy"},
    )
    assert service.calls[1][0] == "create_shared_reminder"
    assert service.calls[1][1]["receiver_account_ids"] == ["friend-amy"]
    assert guard.staged[0]["domain"] == "social_scheduling"
    assert guard.staged[0]["operation"] == "create_shared_reminder"
    assert guard.staged[0]["command_payload"]["receiver_account_ids"] == ["friend-amy"]


def test_create_shared_reminder_time_phrase_uses_detector_text_and_title() -> None:
    service = StubSocialSchedulingService()
    guard = RecordingGuard()

    outcome = SocialSchedulingActionHandler(service).resolve_and_stage(
        _compiled(
            "create_shared_reminder",
            {
                "creator_account_id": "acct-1",
                "participant": "Amy",
                "content": "send deck",
                "time_phrase": "tomorrow 9",
                "captured_timezone": "Asia/Tokyo",
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert service.calls[1] == (
        "detect_and_create_shared_reminder",
        {
            "creator_account_id": "acct-1",
            "receiver_account_ids": ["friend-amy"],
            "raw_text": "send deck tomorrow 9",
            "title": "send deck",
            "captured_timezone": "Asia/Tokyo",
            "duration_minutes": None,
            "commit_guard": guard.guard_state_change,
        },
    )
    assert guard.staged[0]["command_payload"]["title"] == "send deck"


def test_create_shared_reminder_ambiguous_participant_needs_choice_without_stage() -> (
    None
):
    service = StubSocialSchedulingService()
    service.resolutions["Amy"] = FriendResolutionResult(
        status="ambiguous",
        candidates=("friend-amy-1", "friend-amy-2"),
    )
    guard = RecordingGuard()

    outcome = SocialSchedulingActionHandler(service).resolve_and_stage(
        _compiled(
            "create_shared_reminder",
            {
                "creator_account_id": "acct-1",
                "participant": "Amy",
                "content": "send deck",
                "local_trigger_at": LOCAL_TRIGGER,
            },
        ),
        guard,
    )

    assert outcome == ActionOutcome(
        category="needs_choice",
        status="ambiguous",
        data={
            "field": "participant",
            "reference": "Amy",
            "candidates": ["friend-amy-1", "friend-amy-2"],
        },
    )
    assert [call[0] for call in service.calls] == ["resolve_active_friend_reference"]
    assert guard.staged == []


def test_create_shared_reminder_missing_time_needs_input_without_stage() -> None:
    service = StubSocialSchedulingService()
    service.create_result = SharedReminderCreateResult(
        status="needs_time",
        shared_reminder=None,
        follow_up_facts={"missing": "time"},
    )
    guard = RecordingGuard()

    outcome = SocialSchedulingActionHandler(service).resolve_and_stage(
        _compiled(
            "create_shared_reminder",
            {
                "creator_account_id": "acct-1",
                "participant": "Amy",
                "content": "send deck",
            },
        ),
        guard,
    )

    assert outcome == ActionOutcome(
        category="needs_input",
        status="missing_time",
        data={"field": "time", "follow_up_facts": {"missing": "time"}},
    )
    assert guard.staged == []


def test_create_shared_reminder_duplicate_is_not_possible_without_stage() -> None:
    service = StubSocialSchedulingService()
    service.create_result = SharedReminderCreateResult(
        status="duplicate",
        shared_reminder=_shared_reminder("sr-duplicate"),
    )
    guard = RecordingGuard()

    outcome = SocialSchedulingActionHandler(service).resolve_and_stage(
        _compiled(
            "create_shared_reminder",
            {
                "creator_account_id": "acct-1",
                "participant": "Amy",
                "content": "send deck",
                "local_trigger_at": LOCAL_TRIGGER,
            },
        ),
        guard,
    )

    assert outcome.category == "not_possible"
    assert outcome.status == "duplicate_active"
    assert outcome.data["shared_reminder"]["shared_reminder_id"] == "sr-duplicate"
    assert outcome.staged_command_id is None
    assert guard.staged == []


def test_create_shared_reminder_partial_delivery_returns_partial_with_counts() -> None:
    service = StubSocialSchedulingService()
    service.create_result = SimpleNamespace(
        status="partial",
        shared_reminder=_shared_reminder("sr-partial"),
        breakdown={
            "succeeded": ["friend-amy"],
            "failed": [{"account_id": "friend-bob", "reason": "unreachable"}],
        },
        follow_up_facts={},
    )
    guard = RecordingGuard()

    outcome = SocialSchedulingActionHandler(service).resolve_and_stage(
        _compiled(
            "create_shared_reminder",
            {
                "creator_account_id": "acct-1",
                "participant": ["Amy", "Bob"],
                "content": "send deck",
                "local_trigger_at": LOCAL_TRIGGER,
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "partial"
    assert outcome.data["succeeded"] == ["friend-amy"]
    assert outcome.data["failed"] == [
        {"account_id": "friend-bob", "reason": "unreachable"}
    ]
    assert outcome.staged_command_id == "stage-1"


def test_cancel_shared_reminder_resolves_keyword_and_stages_cancel() -> None:
    service = StubSocialSchedulingService()
    guard = RecordingGuard()

    outcome = SocialSchedulingActionHandler(service).resolve_and_stage(
        _compiled(
            "cancel_shared_reminder",
            {"account_id": "acct-1", "participant": "Amy", "match": "deck"},
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "cancelled"
    assert outcome.data["shared_reminder_id"] == "sr-1"
    assert outcome.staged_command_id == "stage-1"
    assert service.calls[-1][0] == "cancel_shared_reminder"
    assert service.calls[-1][1]["shared_reminder_id"] == "sr-1"
    assert guard.staged[0]["operation"] == "cancel_shared_reminder"


def test_cancel_shared_reminder_generic_reference_with_two_same_friend_needs_choice_without_stage() -> (
    None
):
    service = StubSocialSchedulingService()
    service.shared_reminders = [
        _shared_reminder("sr-open", title="聊一下 openCoke"),
        _shared_reminder("sr-funding", title="聊融资"),
    ]
    guard = RecordingGuard()

    outcome = SocialSchedulingActionHandler(service).resolve_and_stage(
        _compiled(
            "cancel_shared_reminder",
            {
                "account_id": "acct-1",
                "participant": "Amy",
                "shared_reminder_id": "sr-open",
            },
        ),
        guard,
    )

    assert outcome.category == "needs_choice"
    assert outcome.status == "ambiguous"
    assert outcome.staged_command_id is None
    assert [
        candidate["shared_reminder_id"] for candidate in outcome.data["candidates"]
    ] == [
        "sr-open",
        "sr-funding",
    ]
    assert [call[0] for call in service.calls] == [
        "resolve_active_friend_reference",
        "list_shared_reminders",
    ]
    assert guard.staged == []


def test_cancel_shared_reminder_exact_title_reference_with_multiple_same_friend_stages_cancel() -> (
    None
):
    service = StubSocialSchedulingService()
    service.shared_reminders = [
        _shared_reminder("sr-open", title="聊一下 openCoke"),
        _shared_reminder("sr-funding", title="聊融资"),
    ]
    service.cancel_result = SharedReminderCancellationResult(
        status="cancelled",
        shared_reminder=_shared_reminder("sr-open", title="聊一下 openCoke"),
        projections=[],
    )
    guard = RecordingGuard()

    outcome = SocialSchedulingActionHandler(service).resolve_and_stage(
        _compiled(
            "cancel_shared_reminder",
            {
                "account_id": "acct-1",
                "participant": "Amy",
                "match": "openCoke",
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "cancelled"
    assert outcome.data["shared_reminder_id"] == "sr-open"
    assert service.calls[-1][0] == "cancel_shared_reminder"
    assert service.calls[-1][1]["shared_reminder_id"] == "sr-open"
    assert guard.staged[0]["operation"] == "cancel_shared_reminder"


def test_list_shared_returns_listed_without_staging() -> None:
    service = StubSocialSchedulingService()
    guard = RecordingGuard()

    outcome = SocialSchedulingActionHandler(service).resolve_and_stage(
        _compiled("list_shared", {"account_id": "acct-1"}),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "listed"
    assert outcome.data["count"] == 1
    assert outcome.data["shared_reminders"][0]["shared_reminder_id"] == "sr-1"
    assert outcome.staged_command_id is None
    assert guard.staged == []


def test_availability_query_resolves_participant_without_staging() -> None:
    service = StubSocialSchedulingService()
    guard = RecordingGuard()

    outcome = SocialSchedulingActionHandler(service).resolve_and_stage(
        _compiled(
            "availability_query",
            {
                "account_id": "acct-1",
                "participant": "Amy",
                "local_start": "2026-06-11T09:00:00",
                "local_end": "2026-06-11T10:00:00",
                "requester_timezone": "Asia/Tokyo",
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "availability"
    assert outcome.data["availability"][0]["friend_account_id"] == "friend-amy"
    assert outcome.data["availability"][0]["windows"][0]["state"] == "free"
    assert outcome.staged_command_id is None
    assert guard.staged == []


def test_availability_query_ambiguous_participant_needs_choice_without_query() -> None:
    service = StubSocialSchedulingService()
    service.resolutions["Oliver"] = FriendResolutionResult(
        status="ambiguous",
        candidates=("friend-oliver-chen", "friend-oliver-wang"),
    )
    guard = RecordingGuard()

    outcome = SocialSchedulingActionHandler(service).resolve_and_stage(
        _compiled(
            "availability_query",
            {
                "account_id": "lizihao",
                "participant": "Oliver",
                "local_start": "2026-06-11T00:00:00",
                "local_end": "2026-06-12T00:00:00",
                "requester_timezone": "Asia/Tokyo",
            },
        ),
        guard,
    )

    assert outcome == ActionOutcome(
        category="needs_choice",
        status="ambiguous",
        data={
            "field": "participant",
            "reference": "Oliver",
            "candidates": ["friend-oliver-chen", "friend-oliver-wang"],
        },
    )
    assert [call[0] for call in service.calls] == ["resolve_active_friend_reference"]
    assert guard.staged == []


def test_availability_query_today_token_uses_requester_local_day_without_staging() -> (
    None
):
    service = StubSocialSchedulingService()
    guard = RecordingGuard()

    outcome = SocialSchedulingActionHandler(
        service,
        now=lambda: datetime(2026, 6, 10, 15, 0, tzinfo=UTC),
    ).resolve_and_stage(
        _compiled(
            "availability_query",
            {
                "account_id": "acct-1",
                "participant": "Amy",
                "local_start": "今天",
                "requester_timezone": "Asia/Tokyo",
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "availability"
    assert outcome.data["availability"][0]["friend_account_id"] == "friend-amy"
    assert service.calls[-1] == (
        "query_availability",
        {
            "requester_account_id": "acct-1",
            "friend_account_ids": ["friend-amy"],
            "local_start": datetime(2026, 6, 11, 0, 0),
            "local_end": datetime(2026, 6, 12, 0, 0),
            "requester_timezone": "Asia/Tokyo",
        },
    )
    assert outcome.staged_command_id is None
    assert guard.staged == []


def test_availability_query_same_today_tokens_use_single_local_day() -> None:
    service = StubSocialSchedulingService()
    guard = RecordingGuard()

    outcome = SocialSchedulingActionHandler(
        service,
        now=lambda: datetime(2026, 6, 10, 1, 0, tzinfo=UTC),
    ).resolve_and_stage(
        _compiled(
            "availability_query",
            {
                "account_id": "acct-1",
                "participant": "Amy",
                "local_start": "今天",
                "local_end": "今天",
                "requester_timezone": "Asia/Tokyo",
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "availability"
    assert service.calls[-1][1]["local_start"] == datetime(2026, 6, 10, 0, 0)
    assert service.calls[-1][1]["local_end"] == datetime(2026, 6, 11, 0, 0)
    assert guard.staged == []


@pytest.mark.parametrize("datetime_field", ["local_start", "local_end"])
def test_availability_query_non_iso_datetime_needs_time_without_service_call(
    datetime_field: str,
) -> None:
    service = StubSocialSchedulingService()
    guard = RecordingGuard()
    params = {
        "account_id": "acct-1",
        "participant": "Amy",
        "local_start": "2026-06-11T09:00:00",
        "local_end": "2026-06-11T10:00:00",
        "requester_timezone": "Asia/Tokyo",
    }
    params[datetime_field] = "someday"

    outcome = SocialSchedulingActionHandler(service).resolve_and_stage(
        _compiled("availability_query", params),
        guard,
    )

    assert outcome == ActionOutcome(
        category="needs_input",
        status="missing_time",
        data={"field": "time"},
    )
    assert [call[0] for call in service.calls] == ["resolve_active_friend_reference"]
    assert guard.staged == []
