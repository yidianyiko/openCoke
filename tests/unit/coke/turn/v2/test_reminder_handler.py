from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from coke.domains.reminder.models import (
    DetectedReminderFields,
    Reminder,
    ReminderBatchResult,
    ReminderItemResult,
)
from coke.turn.v2.contracts import ActionOutcome, CompiledAction, ProposedAction
from coke.turn.v2.handlers.reminder import ReminderActionHandler, _optional_datetime

NOW = datetime(2026, 6, 10, 1, 0, tzinfo=UTC)
TRIGGER_TIME = datetime(2026, 6, 11, 9, 0)


class StubDetector:
    def __init__(self, fields: DetectedReminderFields) -> None:
        self.fields = fields
        self.calls: list[tuple[str, str, datetime]] = []

    def extract(
        self,
        text: str,
        captured_timezone: str,
        now: datetime,
    ) -> DetectedReminderFields:
        self.calls.append((text, captured_timezone, now))
        return self.fields


class StubReminderService:
    def __init__(self) -> None:
        self.filter_result: list[Reminder] = []
        self.batch_result = ReminderBatchResult(owner_account_id="acct-1", items=[])
        self.resolve_result = ReminderItemResult(state="succeeded", reminder_id="r1")
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.mutation_calls: list[str] = []

    def filter_reminders(self, **kwargs: Any) -> list[Reminder]:
        self.calls.append(("filter_reminders", kwargs))
        return self.filter_result

    def resolve_user_mutable_keyword(self, **kwargs: Any) -> ReminderItemResult:
        self.calls.append(("resolve_user_mutable_keyword", kwargs))
        return self.resolve_result

    def execute_batch(self, **kwargs: Any) -> ReminderBatchResult:
        self.calls.append(("execute_batch", kwargs))
        self.mutation_calls.append("execute_batch")
        return self.batch_result

    def update_reminder_by_keyword(self, **kwargs: Any) -> ReminderItemResult:
        self.calls.append(("update_reminder_by_keyword", kwargs))
        self.mutation_calls.append("update_reminder_by_keyword")
        return self.resolve_result

    def delete_reminder_by_keyword(self, **kwargs: Any) -> ReminderItemResult:
        self.calls.append(("delete_reminder_by_keyword", kwargs))
        self.mutation_calls.append("delete_reminder_by_keyword")
        return self.resolve_result

    def complete_reminder_by_keyword(self, **kwargs: Any) -> ReminderItemResult:
        self.calls.append(("complete_reminder_by_keyword", kwargs))
        self.mutation_calls.append("complete_reminder_by_keyword")
        return self.resolve_result

    def update_reminder(self, **kwargs: Any) -> ReminderItemResult:
        self.calls.append(("update_reminder", kwargs))
        self.mutation_calls.append("update_reminder")
        return self.resolve_result

    def delete_reminder(self, **kwargs: Any) -> ReminderItemResult:
        self.calls.append(("delete_reminder", kwargs))
        self.mutation_calls.append("delete_reminder")
        return self.resolve_result

    def complete_reminder(self, **kwargs: Any) -> ReminderItemResult:
        self.calls.append(("complete_reminder", kwargs))
        self.mutation_calls.append("complete_reminder")
        return self.resolve_result


class RecordingGuard:
    def __init__(self) -> None:
        self.turn_id = "turn-1"
        self.staged: list[dict[str, Any]] = []
        self.state_change_calls = 0

    def guard_state_change(self) -> None:
        self.state_change_calls += 1

    def stage_command(self, **kwargs: Any) -> Any:
        self.staged.append(kwargs)
        return SimpleNamespace(
            id=f"stage-{len(self.staged)}",
            preview_facts=dict(kwargs["preview_facts"]),
        )


def _compiled(operation: str, params: dict[str, Any]) -> CompiledAction:
    return CompiledAction(
        action=ProposedAction(
            domain="reminder",
            operation=operation,
            params=params,
        )
    )


def _handler(
    service: StubReminderService,
    detector: StubDetector | None = None,
) -> ReminderActionHandler:
    return ReminderActionHandler(
        service,
        detector or StubDetector(_detected()),
        now=lambda: NOW,
    )


def _detected(
    *,
    content: str | None = "take meds",
    trigger_time: datetime | None = TRIGGER_TIME,
) -> DetectedReminderFields:
    return DetectedReminderFields(
        content=content,
        trigger_time=trigger_time,
        recurrence_rule={},
        duration_minutes=20,
        kind="timed",
    )


def _reminder(reminder_id: str, content: str) -> Reminder:
    return Reminder(
        id=reminder_id,
        owner_account_id="acct-1",
        content=content,
        content_hash=f"hash-{reminder_id}",
        kind="timed",
        next_fire_at=datetime(2026, 6, 11, 1, 0, tzinfo=UTC),
        recurrence_rule={},
        captured_timezone="Asia/Tokyo",
        duration_minutes=15,
        lifecycle="active",
        hidden_from_calendar=False,
        shared_reminder_id=None,
        created_at=NOW,
        updated_at=NOW,
    )


def test_list_reminders_returns_listed_without_staging() -> None:
    service = StubReminderService()
    service.filter_result = [_reminder("r1", "take meds")]
    guard = RecordingGuard()

    outcome = _handler(service).resolve_and_stage(
        _compiled(
            "list",
            {
                "owner_account_id": "acct-1",
                "keyword": "meds",
                "display_timezone": "Asia/Tokyo",
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "listed"
    assert outcome.data["count"] == 1
    assert outcome.data["reminders"][0]["reminder_id"] == "r1"
    assert outcome.staged_command_id is None
    assert guard.staged == []
    assert service.calls[0] == (
        "filter_reminders",
        {
            "owner_account_id": "acct-1",
            "keyword": "meds",
            "lifecycle": "active",
            "kind": None,
            "trigger_after": None,
            "trigger_before": None,
        },
    )


def test_optional_datetime_handles_absent_iso_datetime_and_natural_text() -> None:
    dt = datetime(2026, 6, 12, 9, 0, tzinfo=UTC)

    assert _optional_datetime("this Friday") is None
    assert _optional_datetime(None) is None
    assert _optional_datetime("2026-06-12T09:00:00+00:00") == dt
    assert _optional_datetime(dt) is dt


def test_create_extracts_time_then_stages_execute_batch_without_mutating() -> None:
    service = StubReminderService()
    detector = StubDetector(_detected())
    guard = RecordingGuard()

    outcome = _handler(service, detector).resolve_and_stage(
        _compiled(
            "create",
            {
                "owner_account_id": "acct-1",
                "content": "take meds",
                "time_phrase": "tomorrow 9",
                "captured_timezone": "Asia/Tokyo",
            },
        ),
        guard,
    )

    assert outcome == ActionOutcome(
        category="done",
        status="created",
        data={
            "owner_account_id": "acct-1",
            "items": [
                {
                    "state": "succeeded",
                    "reminder_id": None,
                    "reason": None,
                    "time_state": None,
                    "fact": {
                        "content": "take meds",
                        "trigger_time": "2026-06-11T00:00:00+00:00",
                        "captured_timezone": "Asia/Tokyo",
                        "recurrence_rule": {},
                        "duration_minutes": 20,
                        "kind": "timed",
                        "entry_point": "turn_v2",
                    },
                }
            ],
        },
        staged_command_id="stage-1",
    )
    assert detector.calls == [("take meds tomorrow 9", "Asia/Tokyo", NOW)]
    assert service.calls == []
    assert service.mutation_calls == []
    assert guard.staged[0]["domain"] == "reminder"
    assert guard.staged[0]["operation"] == "execute_batch"
    assert guard.staged[0]["command_payload"]["operation"] == "execute_batch"
    assert guard.staged[0]["command_payload"]["owner_account_id"] == "acct-1"
    assert guard.staged[0]["command_payload"]["items"] == [
        {
            "operation": "create",
            "content": "take meds",
            "trigger_time": "2026-06-11T00:00:00+00:00",
            "captured_timezone": "Asia/Tokyo",
            "recurrence_rule": {},
            "duration_minutes": 20,
            "kind": "timed",
            "entry_point": "turn_v2",
        }
    ]


def test_create_missing_detector_time_needs_input_without_service_or_stage() -> None:
    service = StubReminderService()
    detector = StubDetector(_detected(trigger_time=None))
    guard = RecordingGuard()

    outcome = _handler(service, detector).resolve_and_stage(
        _compiled(
            "create",
            {
                "owner_account_id": "acct-1",
                "content": "take meds",
                "time_phrase": "later",
                "captured_timezone": "Asia/Tokyo",
            },
        ),
        guard,
    )

    assert outcome == ActionOutcome(
        category="needs_input",
        status="missing_trigger_time",
        data={"field": "trigger_time"},
    )
    assert [call[0] for call in service.calls] == []
    assert detector.calls == [("take meds later", "Asia/Tokyo", NOW)]
    assert guard.staged == []


def test_create_defers_duplicate_detection_to_close_materializer() -> None:
    service = StubReminderService()
    service.batch_result = ReminderBatchResult(
        owner_account_id="acct-1",
        items=[ReminderItemResult(state="failed", reason="duplicate_reminder")],
    )
    guard = RecordingGuard()

    outcome = _handler(service).resolve_and_stage(
        _compiled(
            "create",
            {
                "owner_account_id": "acct-1",
                "content": "take meds",
                "time_phrase": "tomorrow 9",
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "created"
    assert outcome.staged_command_id == "stage-1"
    assert service.calls == []
    assert service.mutation_calls == []
    assert guard.staged[0]["operation"] == "execute_batch"


@pytest.mark.parametrize(
    ("operation", "status", "staged_operation"),
    [
        ("update", "updated", "update_reminder"),
        ("delete", "cancelled", "delete_reminder"),
        ("complete", "completed", "complete_reminder"),
    ],
)
def test_keyword_mutations_resolve_then_stage_concrete_command_without_mutating(
    operation: str,
    status: str,
    staged_operation: str,
) -> None:
    service = StubReminderService()
    service.resolve_result = ReminderItemResult(
        state="succeeded",
        reminder_id="r1",
        fact={"matched": {"reminder_id": "r1", "content": "gym"}},
    )
    guard = RecordingGuard()

    outcome = _handler(service).resolve_and_stage(
        _compiled(
            operation,
            {
                "owner_account_id": "acct-1",
                "match": "gym",
                "content": "gym at 8",
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == status
    assert outcome.data["reminder_id"] == "r1"
    assert outcome.staged_command_id == "stage-1"
    assert service.calls == [
        (
            "resolve_user_mutable_keyword",
            {"owner_account_id": "acct-1", "keyword": "gym"},
        )
    ]
    assert service.mutation_calls == []
    assert guard.staged[0]["operation"] == staged_operation
    assert guard.staged[0]["command_payload"]["reminder_id"] == "r1"


def test_delete_resolves_once_and_stages_single_delete_for_resolved_id() -> None:
    service = StubReminderService()
    service.resolve_result = ReminderItemResult(
        state="succeeded",
        reminder_id="resolved-r1",
        fact={"matched": {"reminder_id": "resolved-r1", "content": "gym"}},
    )
    guard = RecordingGuard()

    outcome = _handler(service).resolve_and_stage(
        _compiled(
            "delete",
            {
                "owner_account_id": "acct-1",
                "match": "gym",
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "cancelled"
    assert service.calls == [
        (
            "resolve_user_mutable_keyword",
            {"owner_account_id": "acct-1", "keyword": "gym"},
        )
    ]
    assert service.mutation_calls == []
    assert len(guard.staged) == 1
    assert guard.staged[0]["operation"] == "delete_reminder"
    assert guard.staged[0]["command_payload"] == {
        "operation": "delete_reminder",
        "owner_account_id": "acct-1",
        "reminder_id": "resolved-r1",
    }


def test_update_with_time_phrase_extracts_new_trigger_time() -> None:
    service = StubReminderService()
    service.resolve_result = ReminderItemResult(
        state="succeeded",
        reminder_id="r1",
        fact={"matched": {"reminder_id": "r1", "content": "gym"}},
    )
    detector = StubDetector(_detected(content="gym", trigger_time=TRIGGER_TIME))
    guard = RecordingGuard()

    outcome = _handler(service, detector).resolve_and_stage(
        _compiled(
            "update",
            {
                "owner_account_id": "acct-1",
                "match": "gym",
                "time_phrase": "tomorrow 9",
                "captured_timezone": "Asia/Tokyo",
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert detector.calls == [("tomorrow 9", "Asia/Tokyo", NOW)]
    assert service.calls == [
        (
            "resolve_user_mutable_keyword",
            {"owner_account_id": "acct-1", "keyword": "gym"},
        )
    ]
    assert service.mutation_calls == []
    assert guard.staged[0]["command_payload"]["trigger_time"] == (
        "2026-06-11T00:00:00+00:00"
    )


@pytest.mark.parametrize(
    ("reason", "category", "status", "data_key"),
    [
        ("ambiguous_reminder_reference", "needs_choice", "ambiguous", "candidates"),
        ("no_matching_reminder", "not_possible", "not_found", "reason"),
        ("keyword_required", "needs_input", "missing_match", "field"),
    ],
)
def test_keyword_mutation_blockers_stage_nothing(
    reason: str,
    category: str,
    status: str,
    data_key: str,
) -> None:
    service = StubReminderService()
    service.resolve_result = ReminderItemResult(
        state="needs-follow-up",
        reason=reason,
        fact={
            "candidates": [
                {"reminder_id": "r1", "content": "gym"},
                {"reminder_id": "r2", "content": "gym shoes"},
            ]
        },
    )
    guard = RecordingGuard()

    outcome = _handler(service).resolve_and_stage(
        _compiled(
            "delete",
            {
                "owner_account_id": "acct-1",
                "match": "gym",
            },
        ),
        guard,
    )

    assert outcome.category == category
    assert outcome.status == status
    assert data_key in outcome.data
    assert outcome.staged_command_id is None
    assert service.calls == [
        (
            "resolve_user_mutable_keyword",
            {"owner_account_id": "acct-1", "keyword": "gym"},
        )
    ]
    assert service.mutation_calls == []
    assert guard.staged == []


def test_batch_create_stages_all_items_without_execute_time_mutation() -> None:
    service = StubReminderService()
    guard = RecordingGuard()

    outcome = _handler(service).resolve_and_stage(
        _compiled(
            "batch_create",
            {
                "owner_account_id": "acct-1",
                "items": [
                    {
                        "content": "take meds",
                        "trigger_time": "2026-06-11T09:00:00+00:00",
                    },
                    {
                        "content": "take meds",
                        "trigger_time": "2026-06-12T09:00:00+00:00",
                    },
                ],
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "created"
    assert [item["state"] for item in outcome.data["items"]] == [
        "succeeded",
        "succeeded",
    ]
    assert outcome.staged_command_id == "stage-1"
    assert service.calls == []
    assert service.mutation_calls == []
    assert guard.staged[0]["operation"] == "execute_batch"
    assert len(guard.staged[0]["command_payload"]["items"]) == 2
