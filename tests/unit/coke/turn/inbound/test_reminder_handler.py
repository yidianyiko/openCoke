from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from coke.domains.reminder.models import (
    DetectedReminderFields,
    Reminder,
    ReminderBatchResult,
    ReminderItemResult,
)
from coke.domains.reminder.repository import InMemoryReminderRepository
from coke.domains.reminder.service import ReminderService
from coke.llm.json_completion import AgnoJSONCompletionClient, LLMOutputError
from coke.llm.reminder_detector import SiliconFlowReminderDetector
from coke.turn.inbound.contracts import ActionOutcome, CompiledAction, ProposedAction
from coke.turn.inbound.handlers.reminder import (
    ReminderActionHandler,
    _optional_datetime,
)

NOW = datetime(2026, 6, 10, 1, 0, tzinfo=UTC)
SHANGHAI_NOW = datetime(2026, 6, 14, 13, 26, tzinfo=UTC)
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


class FakeJSONModel:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []
        self.id = "fake-detector"

    def response(self, messages, response_format):
        self.calls.append(
            {
                "messages": messages,
                "response_format": response_format,
            }
        )
        return SimpleNamespace(content=self.content)


class RelativeOffsetJSONClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, *, system: str, user: dict, schema_name: str):
        self.calls.append({"system": system, "user": user, "schema_name": schema_name})
        if "待会" in user["text"]:
            return {
                "content": "看一下锅里的汤",
                "trigger_time": None,
                "recurrence_rule": {},
                "duration_minutes": None,
                "kind": "no_trigger_time",
            }
        if "determinate relative offset" not in system:
            return {
                "content": "看一下锅里的汤",
                "trigger_time": None,
                "recurrence_rule": {},
                "duration_minutes": None,
                "kind": "no_trigger_time",
            }
        trigger_time = datetime.fromisoformat(user["now"]) + timedelta(minutes=10)
        return {
            "content": "看一下锅里的汤",
            "trigger_time": trigger_time.isoformat(),
            "recurrence_rule": {},
            "duration_minutes": 5,
            "kind": "timed",
        }


class RaisingDetector:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls: list[tuple[str, str, datetime]] = []

    def extract(
        self,
        text: str,
        captured_timezone: str,
        now: datetime,
    ) -> DetectedReminderFields:
        self.calls.append((text, captured_timezone, now))
        raise self.error


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


class RecordingGuard:
    def __init__(self) -> None:
        self.state_change_calls = 0
        self.staged: list[dict[str, Any]] = []

    def guard_state_change(self) -> None:
        self.state_change_calls += 1

    def stage_command(self, **kwargs: Any) -> Any:
        self.staged.append(kwargs)
        raise AssertionError("reminder handler must not stage commands")


def _compiled(operation: str, params: dict[str, Any]) -> CompiledAction:
    return CompiledAction(
        action=ProposedAction(
            domain="reminder",
            operation=operation,
            params=params,
        )
    )


def _execute(
    handler: ReminderActionHandler,
    compiled: CompiledAction,
    guard: RecordingGuard,
    *,
    action_index: int = 0,
    turn_id: str = "turn-1",
) -> ActionOutcome:
    return handler.execute(
        compiled,
        guard,
        action_index=action_index,
        turn_id=turn_id,
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
    duration_minutes: int | None = 20,
) -> DetectedReminderFields:
    return DetectedReminderFields(
        content=content,
        trigger_time=trigger_time,
        recurrence_rule={},
        duration_minutes=duration_minutes,
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


def _sequence_factory(kind: str):
    counter = count(1)
    return lambda prefix: f"{prefix}_{kind}_{next(counter)}"


def _real_handler_for_shanghai_now() -> ReminderActionHandler:
    service = ReminderService(
        repository=InMemoryReminderRepository(),
        now=lambda: SHANGHAI_NOW,
        id_factory=_sequence_factory("list"),
    )
    return ReminderActionHandler(
        service,
        StubDetector(_detected()),
        now=lambda: SHANGHAI_NOW,
    )


def _add_list_reminder(
    service: ReminderService,
    *,
    reminder_id: str,
    content: str,
    next_fire_at: datetime,
    kind: str = "timed",
    recurrence_rule: dict[str, Any] | None = None,
    lifecycle: str = "active",
) -> None:
    service.repository.add_reminder(
        Reminder(
            id=reminder_id,
            owner_account_id="acct-1",
            content=content,
            content_hash=f"hash-{reminder_id}",
            kind=kind,
            next_fire_at=next_fire_at,
            recurrence_rule=dict(recurrence_rule or {}),
            captured_timezone="Asia/Shanghai",
            duration_minutes=30,
            lifecycle=lifecycle,
            hidden_from_calendar=False,
            shared_reminder_id=None,
            created_at=SHANGHAI_NOW,
            updated_at=SHANGHAI_NOW,
        )
    )


def _succeeded_item(reminder_id: str = "r1") -> ReminderItemResult:
    return ReminderItemResult(
        state="succeeded",
        reminder_id=reminder_id,
        time_state="valid_future",
        fact={
            "kind": "timed",
            "content": "take meds",
            "trigger_time": "2026-06-11T00:00:00+00:00",
            "duration_minutes": 20,
        },
    )


def test_list_reminders_returns_listed_without_staging() -> None:
    service = StubReminderService()
    service.filter_result = [_reminder("r1", "take meds")]
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service),
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
    assert not hasattr(outcome, "staged_command_id")
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


def test_list_reminders_resolves_tomorrow_date_phrase_to_trigger_window() -> None:
    service = StubReminderService()
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service),
        _compiled(
            "list",
            {
                "owner_account_id": "acct-1",
                "date_phrase": "明天",
                "captured_timezone": "Asia/Shanghai",
                "display_timezone": "Asia/Shanghai",
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert service.calls[0] == (
        "filter_reminders",
        {
            "owner_account_id": "acct-1",
            "keyword": None,
            "lifecycle": "active",
            "kind": None,
            "trigger_after": datetime(2026, 6, 10, 16, 0, tzinfo=UTC),
            "trigger_before": datetime(2026, 6, 11, 16, 0, tzinfo=UTC),
        },
    )


def test_tomorrow_schedule_list_is_date_scoped_and_deterministic() -> None:
    handler = _real_handler_for_shanghai_now()
    service = handler.reminder_service
    guard = RecordingGuard()
    _add_list_reminder(
        service,
        reminder_id="past-today",
        content="出门",
        next_fire_at=datetime(2026, 6, 14, 5, 41, tzinfo=UTC),
    )
    _add_list_reminder(
        service,
        reminder_id="tomorrow-dinner",
        content="晚饭",
        next_fire_at=datetime(2026, 6, 15, 11, 30, tzinfo=UTC),
    )
    _add_list_reminder(
        service,
        reminder_id="daily-review",
        content="复盘今天",
        next_fire_at=datetime(2026, 6, 14, 14, 0, tzinfo=UTC),
        kind="recurring",
        recurrence_rule={"frequency": "daily", "interval": 1},
    )
    _add_list_reminder(
        service,
        reminder_id="after-tomorrow",
        content="后天事项",
        next_fire_at=datetime(2026, 6, 16, 1, 0, tzinfo=UTC),
    )
    _add_list_reminder(
        service,
        reminder_id="completed-tomorrow",
        content="已完成",
        next_fire_at=datetime(2026, 6, 15, 2, 0, tzinfo=UTC),
        lifecycle="completed",
    )
    compiled = _compiled(
        "list",
        {
            "owner_account_id": "acct-1",
            "date_phrase": "明天",
            "captured_timezone": "Asia/Shanghai",
            "display_timezone": "Asia/Shanghai",
        },
    )

    first = _execute(handler, compiled, guard)
    second = _execute(handler, compiled, guard)

    first_reminders = list(first.data["reminders"])
    second_reminders = list(second.data["reminders"])
    assert [reminder["content"] for reminder in first_reminders] == [
        "晚饭",
        "复盘今天",
    ]
    assert first_reminders == second_reminders
    assert first_reminders[1]["next_fire_at"] == "2026-06-15T14:00:00+00:00"
    assert first.data["count"] == 2
    assert second.data["count"] == 2


def test_optional_datetime_handles_absent_iso_datetime_and_natural_text() -> None:
    dt = datetime(2026, 6, 12, 9, 0, tzinfo=UTC)

    assert _optional_datetime("this Friday") is None
    assert _optional_datetime(None) is None
    assert _optional_datetime("2026-06-12T09:00:00+00:00") == dt
    assert _optional_datetime(dt) is dt


def test_create_executes_batch_and_returns_real_service_outcome() -> None:
    service = StubReminderService()
    service.batch_result = ReminderBatchResult(
        owner_account_id="acct-1",
        items=[_succeeded_item("real-r1")],
    )
    detector = StubDetector(_detected())
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service, detector),
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
        action_index=3,
        turn_id="turn-99",
    )

    assert outcome == ActionOutcome(
        category="done",
        status="created",
        data={
            "owner_account_id": "acct-1",
            "items": [
                {
                    "state": "succeeded",
                    "reminder_id": "real-r1",
                    "reason": None,
                    "time_state": "valid_future",
                    "fact": {
                        "kind": "timed",
                        "content": "take meds",
                        "trigger_time": "2026-06-11T00:00:00+00:00",
                        "duration_minutes": 20,
                    },
                }
            ],
        },
    )
    assert detector.calls == [("take meds tomorrow 9", "Asia/Tokyo", NOW)]
    assert [call[0] for call in service.calls] == ["execute_batch"]
    call = service.calls[0][1]
    assert call["owner_account_id"] == "acct-1"
    assert call["commit_guard"] == guard.guard_state_change
    assert len(call["items"]) == 1
    item = call["items"][0]
    assert item.turn_id == "turn-99"
    assert item.item_index == 4
    assert item.content == "take meds"
    assert item.trigger_time == datetime(2026, 6, 11, 0, 0, tzinfo=UTC)
    assert item.duration_minutes == 20
    assert service.mutation_calls == ["execute_batch"]
    assert guard.staged == []


def test_create_with_current_input_text_trusts_detector_duration_over_split_params() -> (
    None
):
    service = StubReminderService()
    service.batch_result = ReminderBatchResult(
        owner_account_id="acct-1",
        items=[_succeeded_item("real-r1")],
    )
    detector = StubDetector(_detected(content="检查时间", duration_minutes=5))
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service, detector),
        _compiled(
            "create",
            {
                "owner_account_id": "acct-1",
                "content": "检查时间",
                "time_phrase": "明天晚上6点",
                "duration_minutes": 30,
                "captured_timezone": "Asia/Shanghai",
                "_current_input_text": "明天晚上6点提醒我检查时间，持续5分钟",
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert detector.calls == [
        ("明天晚上6点提醒我检查时间，持续5分钟", "Asia/Shanghai", NOW)
    ]
    call = service.calls[0][1]
    item = call["items"][0]
    assert item.duration_minutes == 5


def test_create_determinable_relative_offset_resolves_and_creates_without_needs_time() -> (
    None
):
    shanghai = ZoneInfo("Asia/Shanghai")
    now = datetime(2026, 6, 14, 15, 40, tzinfo=shanghai)
    repository = InMemoryReminderRepository()
    service = ReminderService(
        repository=repository,
        now=lambda: now,
        id_factory=_sequence_factory("relative_offset"),
    )
    client = RelativeOffsetJSONClient()
    detector = SiliconFlowReminderDetector(client)
    handler = ReminderActionHandler(service, detector, now=lambda: now)
    guard = RecordingGuard()

    outcome = _execute(
        handler,
        _compiled(
            "create",
            {
                "owner_account_id": "acct-1",
                "captured_timezone": "Asia/Shanghai",
                "_current_input_text": "过10分钟提醒我看一下锅里的汤",
            },
        ),
        guard,
        turn_id="turn-relative",
    )

    reminders = repository.list_reminders("acct-1")
    assert outcome.category == "done"
    assert outcome.status == "created"
    assert len(reminders) == 1
    assert reminders[0].content == "看一下锅里的汤"
    assert reminders[0].next_fire_at.astimezone(shanghai) == now + timedelta(minutes=10)
    assert reminders[0].duration_minutes == 5
    assert client.calls[0]["user"]["now"] == "2026-06-14T15:40:00+08:00"
    assert client.calls[0]["user"]["text"] == "过10分钟提醒我看一下锅里的汤"
    assert guard.staged == []


def test_create_vague_relative_time_still_clarifies_without_service_write() -> None:
    shanghai = ZoneInfo("Asia/Shanghai")
    now = datetime(2026, 6, 14, 15, 40, tzinfo=shanghai)
    repository = InMemoryReminderRepository()
    service = ReminderService(
        repository=repository,
        now=lambda: now,
        id_factory=_sequence_factory("vague_time"),
    )
    client = RelativeOffsetJSONClient()
    detector = SiliconFlowReminderDetector(client)
    handler = ReminderActionHandler(service, detector, now=lambda: now)
    guard = RecordingGuard()

    outcome = _execute(
        handler,
        _compiled(
            "create",
            {
                "owner_account_id": "acct-1",
                "captured_timezone": "Asia/Shanghai",
                "_current_input_text": "待会提醒我看一下锅里的汤",
            },
        ),
        guard,
    )

    assert outcome == ActionOutcome(
        category="needs_input",
        status="missing_trigger_time",
        data={"field": "trigger_time"},
    )
    assert repository.list_reminders("acct-1") == []
    assert client.calls[0]["user"]["text"] == "待会提醒我看一下锅里的汤"
    assert guard.staged == []


def test_create_with_two_object_detector_array_creates_each_reminder() -> None:
    shanghai = ZoneInfo("Asia/Shanghai")
    now = datetime(2026, 6, 14, 13, 28, tzinfo=shanghai)
    repository = InMemoryReminderRepository()
    service = ReminderService(
        repository=repository,
        now=lambda: now,
        id_factory=_sequence_factory("detector_array"),
    )
    model = FakeJSONModel("""
        [
          {
            "content": "看openCoke的测试结果",
            "trigger_time": "2026-06-15T09:00:00+08:00",
            "recurrence_rule": {},
            "duration_minutes": 30,
            "kind": "timed"
          },
          {
            "content": "续订服务",
            "trigger_time": "2026-07-03T14:00:00+08:00",
            "recurrence_rule": {},
            "duration_minutes": 45,
            "kind": "timed"
          }
        ]
        """)
    detector = SiliconFlowReminderDetector(AgnoJSONCompletionClient(model))
    handler = ReminderActionHandler(service, detector, now=lambda: now)
    guard = RecordingGuard()

    outcome = _execute(
        handler,
        _compiled(
            "create",
            {
                "owner_account_id": "acct-1",
                "captured_timezone": "Asia/Shanghai",
                "_current_input_text": (
                    "下周一早上9点提醒我看openCoke的测试结果\n"
                    "7月3号下午2点提醒我续订服务"
                ),
            },
        ),
        guard,
        turn_id="turn-array",
    )

    reminders = repository.list_reminders("acct-1")
    reminders_by_content = {reminder.content: reminder for reminder in reminders}
    assert outcome.category == "done"
    assert outcome.status == "created"
    assert set(reminders_by_content) == {"看openCoke的测试结果", "续订服务"}
    assert reminders_by_content["看openCoke的测试结果"].next_fire_at.astimezone(
        shanghai
    ) == datetime(2026, 6, 15, 9, 0, tzinfo=shanghai)
    assert reminders_by_content["看openCoke的测试结果"].duration_minutes == 30
    assert reminders_by_content["续订服务"].next_fire_at.astimezone(shanghai) == (
        datetime(2026, 7, 3, 14, 0, tzinfo=shanghai)
    )
    assert reminders_by_content["续订服务"].duration_minutes == 45
    assert model.calls[0]["response_format"] == {"type": "json_object"}
    assert guard.staged == []


def test_create_past_time_confirmation_is_real_outcome_not_staged_success() -> None:
    service = StubReminderService()
    service.batch_result = ReminderBatchResult(
        owner_account_id="acct-1",
        items=[
            ReminderItemResult(
                state="needs-follow-up",
                reason="needs_past_time_confirmation",
                time_state="needs_past_time_confirmation",
                fact={"local_trigger_at": "2026-06-10T08:00:00"},
            )
        ],
    )
    detector = StubDetector(_detected(trigger_time=datetime(2026, 6, 10, 8, 0)))
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service, detector),
        _compiled(
            "create",
            {
                "owner_account_id": "acct-1",
                "content": "exercise",
                "time_phrase": "today 8-9",
                "captured_timezone": "UTC",
            },
        ),
        guard,
    )

    assert outcome.category == "needs_confirmation"
    assert outcome.status == "needs_past_time_confirmation"
    assert outcome.data["items"][0]["state"] == "needs-follow-up"
    assert outcome.data["items"][0]["time_state"] == "needs_past_time_confirmation"
    assert [call[0] for call in service.calls] == ["execute_batch"]
    assert service.mutation_calls == ["execute_batch"]
    assert guard.staged == []


def test_create_missing_detector_time_needs_input_without_service_or_stage() -> None:
    service = StubReminderService()
    detector = StubDetector(_detected(trigger_time=None))
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service, detector),
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


def test_create_detector_output_error_returns_typed_failure_without_service_write() -> (
    None
):
    service = StubReminderService()
    detector = RaisingDetector(LLMOutputError("invalid detected_reminder_fields shape"))
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service, detector),  # type: ignore[arg-type]
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
        category="not_possible",
        status="invalid_detector_output",
        data={"reason": "invalid_detector_output"},
    )
    assert detector.calls == [("take meds tomorrow 9", "Asia/Tokyo", NOW)]
    assert service.calls == []
    assert service.mutation_calls == []
    assert guard.staged == []


def test_create_missing_duration_keeps_existing_guard_before_real_write() -> None:
    service = StubReminderService()
    detector = StubDetector(_detected(duration_minutes=None))
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service, detector),
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
        category="not_possible",
        status="missing_duration_minutes",
        data={"field": "duration_minutes"},
    )
    assert service.calls == []
    assert service.mutation_calls == []
    assert guard.staged == []


def test_create_maps_real_duplicate_detection_from_service() -> None:
    service = StubReminderService()
    service.batch_result = ReminderBatchResult(
        owner_account_id="acct-1",
        items=[ReminderItemResult(state="failed", reason="duplicate_reminder")],
    )
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service),
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

    assert outcome.category == "not_possible"
    assert outcome.status == "duplicate_reminder"
    assert outcome.data["items"][0]["reason"] == "duplicate_reminder"
    assert [call[0] for call in service.calls] == ["execute_batch"]
    assert service.mutation_calls == ["execute_batch"]
    assert guard.staged == []


def test_create_maps_real_time_conflict_from_service() -> None:
    service = StubReminderService()
    service.batch_result = ReminderBatchResult(
        owner_account_id="acct-1",
        items=[
            ReminderItemResult(
                state="needs-follow-up",
                reason="time_conflict",
                fact={"conflict": {"reminder_id": "busy-r1", "content": "meeting"}},
            )
        ],
    )
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service),
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

    assert outcome.category == "needs_input"
    assert outcome.status == "time_conflict"
    assert outcome.data["items"][0]["fact"]["conflict"]["reminder_id"] == "busy-r1"
    assert [call[0] for call in service.calls] == ["execute_batch"]
    assert guard.staged == []


def test_batch_create_executes_all_items_once() -> None:
    service = StubReminderService()
    service.batch_result = ReminderBatchResult(
        owner_account_id="acct-1",
        items=[_succeeded_item("real-r1"), _succeeded_item("real-r2")],
    )
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service),
        _compiled(
            "batch_create",
            {
                "owner_account_id": "acct-1",
                "items": [
                    {
                        "content": "take meds",
                        "trigger_time": "2026-06-11T09:00:00+00:00",
                        "duration_minutes": 15,
                    },
                    {
                        "content": "stretch",
                        "trigger_time": "2026-06-12T09:00:00+00:00",
                        "duration_minutes": 30,
                    },
                ],
            },
        ),
        guard,
        action_index=2,
        turn_id="turn-77",
    )

    assert outcome.category == "done"
    assert outcome.status == "created"
    assert [item["reminder_id"] for item in outcome.data["items"]] == [
        "real-r1",
        "real-r2",
    ]
    assert [call[0] for call in service.calls] == ["execute_batch"]
    call = service.calls[0][1]
    assert call["owner_account_id"] == "acct-1"
    assert call["commit_guard"] == guard.guard_state_change
    assert [(item.turn_id, item.item_index) for item in call["items"]] == [
        ("turn-77", 3),
        ("turn-77", 4),
    ]
    assert service.mutation_calls == ["execute_batch"]
    assert guard.staged == []


def test_batch_create_with_time_phrase_trusts_detector_duration_over_plan_guess() -> (
    None
):
    service = StubReminderService()
    service.batch_result = ReminderBatchResult(
        owner_account_id="acct-1",
        items=[_succeeded_item("real-r1")],
    )
    detector = StubDetector(_detected(content="检查时间", duration_minutes=5))
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service, detector),
        _compiled(
            "batch_create",
            {
                "owner_account_id": "acct-1",
                "items": [
                    {
                        "content": "检查时间",
                        "time_phrase": "明天晚上6点",
                        "duration_minutes": 30,
                    }
                ],
            },
        ),
        guard,
        turn_id="turn-77",
    )

    assert outcome.category == "done"
    assert detector.calls == [("检查时间 明天晚上6点", "UTC", NOW)]
    call = service.calls[0][1]
    item = call["items"][0]
    assert item.duration_minutes == 5
    assert item.trigger_time == datetime(2026, 6, 11, 9, 0, tzinfo=UTC)


def test_batch_create_missing_duration_keeps_existing_guard_before_real_write() -> None:
    service = StubReminderService()
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service),
        _compiled(
            "batch_create",
            {
                "owner_account_id": "acct-1",
                "items": [
                    {
                        "content": "take meds",
                        "trigger_time": "2026-06-11T09:00:00+00:00",
                    }
                ],
            },
        ),
        guard,
    )

    assert outcome == ActionOutcome(
        category="not_possible",
        status="missing_duration_minutes",
        data={"field": "duration_minutes", "item_index": 1},
    )
    assert service.calls == []
    assert service.mutation_calls == []
    assert guard.staged == []


def test_update_with_time_phrase_executes_keyword_update_for_real() -> None:
    service = StubReminderService()
    service.resolve_result = ReminderItemResult(
        state="succeeded",
        reminder_id="r1",
        fact={"matched": {"reminder_id": "r1", "content": "gym"}},
    )
    detector = StubDetector(_detected(content="gym", trigger_time=TRIGGER_TIME))
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service, detector),
        _compiled(
            "update",
            {
                "owner_account_id": "acct-1",
                "match": "gym",
                "time_phrase": "tomorrow 9",
                "captured_timezone": "Asia/Tokyo",
                "duration_minutes": 45,
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "updated"
    assert detector.calls == [("tomorrow 9", "Asia/Tokyo", NOW)]
    assert service.calls == [
        (
            "update_reminder_by_keyword",
            {
                "owner_account_id": "acct-1",
                "keyword": "gym",
                "content": None,
                "trigger_time": datetime(2026, 6, 11, 0, 0, tzinfo=UTC),
                "captured_timezone": "Asia/Tokyo",
                "duration_minutes": 45,
                "commit_guard": guard.guard_state_change,
            },
        )
    ]
    assert service.mutation_calls == ["update_reminder_by_keyword"]
    assert guard.staged == []


def test_update_past_time_confirmation_is_real_outcome() -> None:
    service = StubReminderService()
    service.resolve_result = ReminderItemResult(
        state="needs-follow-up",
        reminder_id="r1",
        reason="needs_past_time_confirmation",
        time_state="needs_past_time_confirmation",
    )
    detector = StubDetector(
        _detected(content="gym", trigger_time=datetime(2026, 6, 9, 8, 0))
    )
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service, detector),
        _compiled(
            "update",
            {
                "owner_account_id": "acct-1",
                "match": "gym",
                "time_phrase": "yesterday 8",
                "captured_timezone": "UTC",
            },
        ),
        guard,
    )

    assert outcome.category == "needs_confirmation"
    assert outcome.status == "needs_past_time_confirmation"
    assert service.mutation_calls == ["update_reminder_by_keyword"]
    assert guard.staged == []


def test_delete_resolves_and_executes_single_delete_for_real() -> None:
    service = StubReminderService()
    service.resolve_result = ReminderItemResult(
        state="succeeded",
        reminder_id="resolved-r1",
        fact={"matched": {"reminder_id": "resolved-r1", "content": "gym"}},
    )
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service),
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
            "delete_reminder_by_keyword",
            {
                "owner_account_id": "acct-1",
                "keyword": "gym",
                "commit_guard": guard.guard_state_change,
            },
        )
    ]
    assert service.mutation_calls == ["delete_reminder_by_keyword"]
    assert guard.staged == []


def test_date_scoped_delete_cancels_today_reminders_without_match() -> None:
    handler = _real_handler_for_shanghai_now()
    service = handler.reminder_service
    guard = RecordingGuard()
    _add_list_reminder(
        service,
        reminder_id="today-morning",
        content="早上复盘",
        next_fire_at=datetime(2026, 6, 14, 5, 0, tzinfo=UTC),
    )
    _add_list_reminder(
        service,
        reminder_id="today-evening",
        content="晚上检查",
        next_fire_at=datetime(2026, 6, 14, 14, 0, tzinfo=UTC),
    )
    _add_list_reminder(
        service,
        reminder_id="tomorrow",
        content="明天会议",
        next_fire_at=datetime(2026, 6, 15, 2, 0, tzinfo=UTC),
    )

    outcome = _execute(
        handler,
        _compiled(
            "delete",
            {
                "owner_account_id": "acct-1",
                "date_phrase": "今天",
                "captured_timezone": "Asia/Shanghai",
                "display_timezone": "Asia/Shanghai",
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "cancelled"
    assert outcome.data["count"] == 2
    assert [
        item["reminder_id"]
        for item in outcome.data["items"]
        if item["state"] == "succeeded"
    ] == ["today-morning", "today-evening"]
    assert service.repository.get_reminder("today-morning").lifecycle == "deleted"
    assert service.repository.get_reminder("today-evening").lifecycle == "deleted"
    assert service.repository.get_reminder("tomorrow").lifecycle == "active"
    assert guard.staged == []


def test_complete_executes_keyword_completion_for_real() -> None:
    service = StubReminderService()
    service.resolve_result = ReminderItemResult(state="succeeded", reminder_id="r1")
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service),
        _compiled(
            "complete",
            {
                "owner_account_id": "acct-1",
                "match": "gym",
            },
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "completed"
    assert service.calls == [
        (
            "complete_reminder_by_keyword",
            {
                "owner_account_id": "acct-1",
                "keyword": "gym",
                "commit_guard": guard.guard_state_change,
            },
        )
    ]
    assert service.mutation_calls == ["complete_reminder_by_keyword"]
    assert guard.staged == []


def test_keyword_mutation_blockers_stage_nothing() -> None:
    service = StubReminderService()
    service.resolve_result = ReminderItemResult(
        state="needs-follow-up",
        reason="ambiguous_reminder_reference",
        fact={
            "candidates": [
                {"reminder_id": "r1", "content": "gym"},
                {"reminder_id": "r2", "content": "gym shoes"},
            ]
        },
    )
    guard = RecordingGuard()

    outcome = _execute(
        _handler(service),
        _compiled(
            "delete",
            {
                "owner_account_id": "acct-1",
                "match": "gym",
            },
        ),
        guard,
    )

    assert outcome.category == "needs_choice"
    assert outcome.status == "ambiguous"
    assert outcome.data["candidates"][0]["reminder_id"] == "r1"
    assert service.mutation_calls == ["delete_reminder_by_keyword"]
    assert guard.staged == []
