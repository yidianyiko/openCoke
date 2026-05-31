from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count
from zoneinfo import ZoneInfo

import pytest

from coke.domains.reminder.models import (
    DetectedReminderFields,
    ReminderBatchItem,
    ReminderError,
)
from coke.domains.reminder.repository import InMemoryReminderRepository
from coke.domains.reminder.service import ReminderService
from coke.llm.semantic_interpreter import LLMOutputError

NOW = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)


def sequence_factory(kind: str):
    counter = count(1)
    return lambda prefix: f"{prefix}_{kind}_{next(counter)}"


class FakeDetector:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls: list[tuple[str, str, datetime]] = []

    def extract(self, text, captured_timezone, now):
        self.calls.append((text, captured_timezone, now))
        return self.outputs.pop(0)


class FakeDelivery:
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def send_reminder_turn(self, owner_account_id, fire_ids, idempotency_key):
        self.calls.append((owner_account_id, tuple(fire_ids)))
        if self.outcomes:
            return self.outcomes.pop(0)
        return "delivered"


@pytest.fixture
def repository() -> InMemoryReminderRepository:
    return InMemoryReminderRepository()


@pytest.fixture
def service(repository) -> ReminderService:
    return ReminderService(
        repository=repository,
        now=lambda: NOW,
        id_factory=sequence_factory("reminder"),
    )


def test_timed_and_no_trigger_create_use_owner_timezone_and_default_duration(service):
    timed_at = NOW + timedelta(hours=1)

    result = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="pay rent",
                trigger_time=timed_at,
                captured_timezone="Asia/Tokyo",
            ),
            ReminderBatchItem(
                operation="create",
                content="buy batteries",
                captured_timezone="Asia/Tokyo",
            ),
        ],
    )

    assert [item.state for item in result.items] == ["succeeded", "succeeded"]
    reminders = service.repository.list_active_reminders("acct_1")
    assert [reminder.kind for reminder in reminders] == ["timed", "no_trigger_time"]
    assert reminders[0].next_fire_at == timed_at
    assert reminders[0].duration_minutes == 15
    assert reminders[0].captured_timezone == "Asia/Tokyo"
    assert reminders[1].next_fire_at is None
    assert reminders[1].hidden_from_calendar is False


def test_personal_reminder_create_writes_outbox_event(service):
    result = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="pay rent",
                trigger_time=NOW + timedelta(hours=1),
                captured_timezone="UTC",
                turn_id="turn_1",
                item_index=1,
            )
        ],
    )

    assert result.items[0].state == "succeeded"
    outbox = service.repository.outbox_records
    assert len(outbox) == 1
    assert outbox[0].topic == "reminder.lifecycle"
    assert outbox[0].idempotency_key == "reminder:create:turn_1:1"
    assert outbox[0].payload["operation"] == "create"
    assert outbox[0].payload["reminder_id"] == result.items[0].reminder_id


def test_personal_reminder_lifecycle_writes_outbox_events(service):
    created = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="stretch",
                trigger_time=NOW + timedelta(hours=1),
                captured_timezone="UTC",
            )
        ],
    )
    reminder_id = created.items[0].reminder_id

    service.reschedule_reminder(
        owner_account_id="acct_1",
        reminder_id=reminder_id,
        trigger_time=NOW + timedelta(hours=2),
        captured_timezone="UTC",
    )
    service.complete_reminder("acct_1", reminder_id)
    deleted = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="delete me",
                trigger_time=NOW + timedelta(hours=3),
                captured_timezone="UTC",
            )
        ],
    )
    service.delete_reminder("acct_1", deleted.items[0].reminder_id)

    operations = [
        record.payload["operation"] for record in service.repository.outbox_records
    ]
    assert operations == ["create", "reschedule", "complete", "create", "delete"]


def test_commit_guard_blocks_personal_reminder_write(service):
    class StaleCommitGuard:
        def __call__(self):
            raise RuntimeError("turn_superseded")

    with pytest.raises(RuntimeError, match="turn_superseded"):
        service.execute_batch(
            owner_account_id="acct_1",
            items=[
                ReminderBatchItem(
                    operation="create",
                    content="pay rent",
                    trigger_time=NOW + timedelta(hours=1),
                    captured_timezone="UTC",
                )
            ],
            commit_guard=StaleCommitGuard(),
        )

    assert service.repository.list_active_reminders("acct_1") == []
    assert service.repository.outbox_records == []


def test_duplicate_prevention_uses_schema_key_not_duration_or_entry_point(service):
    trigger_time = NOW + timedelta(hours=2)
    created = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="Call Alice",
                trigger_time=trigger_time,
                captured_timezone="UTC",
                duration_minutes=15,
                entry_point="conversation",
            )
        ],
    )

    duplicate = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="Call Alice",
                trigger_time=trigger_time,
                captured_timezone="UTC",
                duration_minutes=90,
                entry_point="calendar",
            ),
            ReminderBatchItem(
                operation="create",
                content="Call Alice",
                trigger_time=trigger_time + timedelta(minutes=1),
                captured_timezone="UTC",
            ),
        ],
    )

    assert created.items[0].state == "succeeded"
    assert duplicate.items[0].state == "failed"
    assert duplicate.items[0].reason == "duplicate_reminder"
    assert duplicate.items[1].state == "succeeded"

    service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create", content="unscheduled", captured_timezone="UTC"
            )
        ],
    )
    no_trigger_duplicate = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="unscheduled",
                captured_timezone="UTC",
                duration_minutes=60,
            )
        ],
    )

    assert no_trigger_duplicate.items[0].state == "failed"
    assert no_trigger_duplicate.items[0].reason == "duplicate_reminder"


def test_batch_items_commit_independently_and_detector_output_is_trusted_or_invalid(
    repository,
):
    detector = FakeDetector(
        [
            DetectedReminderFields(
                content="book dentist",
                trigger_time=NOW + timedelta(days=1),
                recurrence_rule={},
                duration_minutes=None,
            ),
            DetectedReminderFields(
                content=None,
                trigger_time=NOW + timedelta(days=2),
                recurrence_rule={},
                duration_minutes=None,
            ),
        ]
    )
    service = ReminderService(
        repository=repository,
        detector=detector,
        now=lambda: NOW,
        id_factory=sequence_factory("detector"),
    )

    result = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="detect_and_create",
                raw_text="remind me tomorrow to book dentist",
                captured_timezone="UTC",
            ),
            ReminderBatchItem(
                operation="detect_and_create",
                raw_text="call mom tomorrow",
                captured_timezone="UTC",
            ),
            ReminderBatchItem(
                operation="create",
                content="missing date",
                captured_timezone="UTC",
                time_state="needs_incomplete_date_clarification",
            ),
        ],
    )

    assert [item.state for item in result.items] == [
        "succeeded",
        "failed",
        "needs-follow-up",
    ]
    assert result.items[1].reason == "invalid_detector_output"
    assert result.items[2].time_state == "needs_incomplete_date_clarification"
    assert [
        reminder.content for reminder in repository.list_active_reminders("acct_1")
    ] == ["book dentist"]
    assert [(text, timezone) for text, timezone, _ in detector.calls] == [
        ("remind me tomorrow to book dentist", "UTC"),
        ("call mom tomorrow", "UTC"),
    ]


def test_detected_local_wall_clock_times_are_persisted_as_account_timezone_instants(
    repository,
):
    detector = FakeDetector(
        [
            DetectedReminderFields(
                content="run",
                trigger_time=datetime(2026, 5, 31, 9, 0),
                recurrence_rule={},
                duration_minutes=None,
            ),
            DetectedReminderFields(
                content="run",
                trigger_time=datetime(2026, 5, 31, 9, 0),
                recurrence_rule={},
                duration_minutes=None,
            ),
        ]
    )
    service = ReminderService(
        repository=repository,
        detector=detector,
        now=lambda: datetime(2026, 5, 30, 10, 10, tzinfo=UTC),
        id_factory=sequence_factory("tz"),
    )

    for owner, timezone in [
        ("tokyo", "Asia/Tokyo"),
        ("new_york", "America/New_York"),
    ]:
        result = service.execute_batch(
            owner_account_id=owner,
            items=[
                ReminderBatchItem(
                    operation="detect_and_create",
                    raw_text="remind me tomorrow at 9",
                    captured_timezone=timezone,
                )
            ],
        )
        assert result.items[0].state == "succeeded"

    tokyo = repository.list_active_reminders("tokyo")[0]
    new_york = repository.list_active_reminders("new_york")[0]
    assert tokyo.next_fire_at == datetime(2026, 5, 31, 0, 0, tzinfo=UTC)
    assert new_york.next_fire_at == datetime(2026, 5, 31, 13, 0, tzinfo=UTC)
    assert tokyo.captured_timezone == "Asia/Tokyo"
    assert new_york.captured_timezone == "America/New_York"


@pytest.mark.parametrize(
    ("raw_text", "detected_time", "expected_fire_at"),
    [
        (
            "和我的好友约一个明天中午的午餐",
            datetime(2026, 6, 1, 12, 0),
            datetime(2026, 6, 1, 4, 0, tzinfo=UTC),
        ),
        (
            "提醒我明天早上9点跑步",
            datetime(2026, 6, 1, 9, 0),
            datetime(2026, 6, 1, 1, 0, tzinfo=UTC),
        ),
    ],
)
def test_detector_receives_account_local_now_for_relative_time_grounding(
    repository,
    raw_text,
    detected_time,
    expected_fire_at,
):
    detector = FakeDetector(
        [
            DetectedReminderFields(
                content="午餐" if "午餐" in raw_text else "跑步",
                trigger_time=detected_time,
                recurrence_rule={},
                duration_minutes=None,
            )
        ]
    )
    service = ReminderService(
        repository=repository,
        detector=detector,
        now=lambda: datetime(2026, 5, 31, 3, 44, tzinfo=UTC),
        id_factory=sequence_factory("relative"),
    )

    result = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="detect_and_create",
                raw_text=raw_text,
                captured_timezone="Asia/Shanghai",
            )
        ],
    )

    assert result.items[0].state == "succeeded"
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
    ) == (2026, 5, 31, 11, 44)
    reminder = repository.list_active_reminders("acct_1")[0]
    assert reminder.next_fire_at == expected_fire_at


def test_personal_reminder_tonight_uses_fixed_account_local_now(repository):
    detector = FakeDetector(
        [
            DetectedReminderFields(
                content="会议",
                trigger_time=datetime(2026, 5, 31, 22, 30),
                recurrence_rule={},
                duration_minutes=None,
            )
        ]
    )
    service = ReminderService(
        repository=repository,
        detector=detector,
        now=lambda: datetime(2026, 5, 31, 6, 2, tzinfo=UTC),
        id_factory=sequence_factory("tonight"),
    )

    result = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="detect_and_create",
                raw_text="今晚10:30提醒我开会",
                captured_timezone="Asia/Shanghai",
            )
        ],
    )

    assert result.items[0].state == "succeeded"
    detector_now = detector.calls[0][2]
    assert detector_now.tzinfo == ZoneInfo("Asia/Shanghai")
    assert (
        detector_now.year,
        detector_now.month,
        detector_now.day,
        detector_now.hour,
        detector_now.minute,
    ) == (2026, 5, 31, 14, 2)
    reminder = repository.list_active_reminders("acct_1")[0]
    assert reminder.next_fire_at == datetime(2026, 5, 31, 14, 30, tzinfo=UTC)


def test_detector_invalid_shape_fails_item_without_tool_exception(repository):
    class InvalidDetector:
        def extract(self, text, captured_timezone, now):
            raise LLMOutputError("invalid recurrence_rule")

    service = ReminderService(
        repository=repository,
        detector=InvalidDetector(),
        now=lambda: NOW,
        id_factory=sequence_factory("detector"),
    )

    result = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="detect_and_create",
                raw_text="remind me tomorrow to run",
                captured_timezone="UTC",
            )
        ],
    )

    assert result.items[0].state == "failed"
    assert result.items[0].reason == "invalid_detector_output"
    assert repository.list_active_reminders("acct_1") == []


def test_time_validation_blocks_past_or_incomplete_times_before_commit(service):
    past = NOW - timedelta(minutes=1)
    incomplete_today_passed = NOW.replace(hour=9)

    result = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="past explicit",
                trigger_time=past,
                captured_timezone="UTC",
            ),
            ReminderBatchItem(
                operation="create",
                content="today nine",
                trigger_time=incomplete_today_passed,
                captured_timezone="UTC",
                incomplete_date=True,
            ),
            ReminderBatchItem(
                operation="create",
                content="bad timezone",
                trigger_time=NOW + timedelta(hours=1),
                captured_timezone="Mars/Base",
            ),
        ],
    )

    assert [item.state for item in result.items] == [
        "needs-follow-up",
        "needs-follow-up",
        "failed",
    ]
    assert [item.time_state for item in result.items] == [
        "needs_past_time_confirmation",
        "needs_incomplete_date_clarification",
        "invalid",
    ]
    assert service.repository.list_active_reminders("acct_1") == []
    assert service.repository.outbox_records == []


def test_trigger_time_conversion_is_explicit_domain_state(service):
    created = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="unscheduled task",
                captured_timezone="Asia/Tokyo",
            ),
            ReminderBatchItem(
                operation="create",
                content="daily stretch",
                trigger_time=NOW + timedelta(hours=1),
                captured_timezone="Asia/Tokyo",
                recurrence_rule={"frequency": "daily", "interval": 1},
            ),
        ],
    )
    unscheduled_id = created.items[0].reminder_id
    recurring_id = created.items[1].reminder_id

    scheduled = service.schedule_unscheduled(
        owner_account_id="acct_1",
        reminder_id=unscheduled_id,
        trigger_time=NOW + timedelta(days=1),
        captured_timezone="Asia/Tokyo",
    )
    cleared = service.clear_trigger_time(
        owner_account_id="acct_1",
        reminder_id=scheduled.reminder_id,
    )
    recurring_clear = service.clear_trigger_time(
        owner_account_id="acct_1",
        reminder_id=recurring_id,
    )

    assert scheduled.state == "succeeded"
    assert scheduled.fact["transition"] == "schedule_unscheduled"
    assert cleared.state == "succeeded"
    assert cleared.fact["transition"] == "clear_trigger_time"
    assert recurring_clear.state == "needs-follow-up"
    assert recurring_clear.fact["choices"] == [
        "convert_to_unscheduled",
        "delete_recurring_series",
    ]


def test_reschedule_reminder_updates_existing_timed_row_without_duplicate(service):
    created = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="stretch",
                trigger_time=NOW + timedelta(days=1),
                captured_timezone="Asia/Shanghai",
            )
        ],
    )

    rescheduled = service.reschedule_reminder(
        owner_account_id="acct_1",
        reminder_id=created.items[0].reminder_id,
        trigger_time=NOW + timedelta(days=1, hours=1),
        captured_timezone="Asia/Shanghai",
    )

    reminders = service.repository.list_active_reminders("acct_1")
    assert rescheduled.state == "succeeded"
    assert rescheduled.reminder_id == created.items[0].reminder_id
    assert len(reminders) == 1
    assert reminders[0].next_fire_at == NOW + timedelta(days=1, hours=1)
    assert reminders[0].captured_timezone == "Asia/Shanghai"


def test_fire_lifecycle_is_occurrence_grain_idempotent_and_advances_recurring(service):
    trigger_time = NOW
    created = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="daily standup",
                trigger_time=trigger_time,
                captured_timezone="UTC",
                recurrence_rule={"frequency": "daily", "interval": 1},
            )
        ],
    )
    reminder_id = created.items[0].reminder_id

    first = service.claim_due_fire(reminder_id=reminder_id, due_at=trigger_time)
    replay = service.claim_due_fire(reminder_id=reminder_id, due_at=trigger_time)
    completed = service.complete_fire(first.id, completed_at=NOW + timedelta(minutes=1))
    reminder = service.repository.get_reminder(reminder_id)

    assert replay.id == first.id
    assert completed.completed_at == NOW + timedelta(minutes=1)
    assert completed.fire_state == "completed"
    assert reminder.lifecycle == "active"
    assert reminder.next_fire_at == trigger_time + timedelta(days=1)


def test_undelivered_resend_excludes_handled_deleted_and_proactive_discards(repository):
    delivery = FakeDelivery(outcomes=["failed", "failed", "delivered"])
    service = ReminderService(
        repository=repository,
        delivery=delivery,
        now=lambda: NOW,
        id_factory=sequence_factory("delivery"),
    )
    result = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="personal",
                trigger_time=NOW,
                captured_timezone="UTC",
            ),
            ReminderBatchItem(
                operation="create",
                content="proactive",
                trigger_time=NOW,
                captured_timezone="UTC",
                kind="proactive",
            ),
        ],
    )
    personal_id = result.items[0].reminder_id
    proactive_id = result.items[1].reminder_id

    personal_fire = service.claim_due_fire(personal_id, NOW)
    proactive_fire = service.claim_due_fire(proactive_id, NOW)
    service.deliver_fire_group("acct_1", NOW, [personal_fire.id])
    service.deliver_fire_group("acct_1", NOW, [proactive_fire.id])
    resend = service.undelivered_resend_turn("acct_1")
    service.mark_fire_handled(personal_fire.id, handled_at=NOW + timedelta(minutes=5))

    assert repository.get_fire(personal_fire.id).delivery_result == "undelivered"
    assert repository.get_fire(proactive_fire.id).fire_state == "discarded"
    assert repository.get_fire(proactive_fire.id).delivery_result is None
    assert resend.fire_ids == [personal_fire.id]
    assert service.undelivered_resend_turn("acct_1").fire_ids == []


def test_record_fire_delivery_marks_failed_outputs_by_class(service):
    result = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="personal",
                trigger_time=NOW,
                captured_timezone="UTC",
            ),
            ReminderBatchItem(
                operation="create",
                content="proactive",
                trigger_time=NOW,
                captured_timezone="UTC",
                kind="proactive",
            ),
        ],
    )
    personal_fire = service.claim_due_fire(result.items[0].reminder_id, NOW)
    proactive_fire = service.claim_due_fire(result.items[1].reminder_id, NOW)

    service.record_fire_delivery([personal_fire.id], delivered=False)
    service.record_proactive_delivery(proactive_fire.id, delivered=False)

    assert (
        service.repository.get_fire(personal_fire.id).delivery_result == "undelivered"
    )
    assert service.repository.get_fire(personal_fire.id).fire_state == "claimed"
    assert service.repository.get_fire(proactive_fire.id).delivery_result is None
    assert service.repository.get_fire(proactive_fire.id).fire_state == "discarded"


def test_user_cannot_mutate_proactive_reminders(service):
    created = service.execute_batch(
        owner_account_id="acct_1",
        items=[
            ReminderBatchItem(
                operation="create",
                content="hidden follow-up",
                trigger_time=NOW + timedelta(hours=1),
                captured_timezone="UTC",
                kind="proactive",
            )
        ],
    )

    with pytest.raises(ReminderError, match="proactive_user_immutable"):
        service.delete_reminder(
            owner_account_id="acct_1",
            reminder_id=created.items[0].reminder_id,
            user_initiated=True,
        )
