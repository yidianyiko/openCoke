from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

ReminderKind = Literal[
    "timed",
    "no_trigger_time",
    "recurring",
    "proactive",
    "shared_projection",
]
ReminderLifecycle = Literal["active", "completed", "deleted"]
ReminderFireState = Literal["pending", "claimed", "completed", "discarded"]
DeliveryResult = Literal["delivered", "undelivered"]
BatchItemState = Literal["succeeded", "needs-follow-up", "failed"]
TimeValidationState = Literal[
    "valid_future",
    "needs_past_time_confirmation",
    "needs_incomplete_date_clarification",
    "invalid",
]


class ReminderError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        fact: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.fact = fact
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class Reminder:
    id: str
    owner_account_id: str
    content: str
    content_hash: str
    kind: ReminderKind
    next_fire_at: datetime | None
    recurrence_rule: dict[str, Any]
    captured_timezone: str
    duration_minutes: int
    lifecycle: ReminderLifecycle
    hidden_from_calendar: bool
    shared_reminder_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ReminderFire:
    id: str
    reminder_id: str
    occurrence_key: str
    due_at: datetime
    fire_state: ReminderFireState
    delivery_result: DeliveryResult | None
    handled_at: datetime | None
    completed_at: datetime | None
    missed_catch_up: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ReminderBatchItem:
    operation: str
    content: str | None = None
    raw_text: str | None = None
    reminder_id: str | None = None
    trigger_time: datetime | None = None
    captured_timezone: str = "UTC"
    recurrence_rule: dict[str, Any] = field(default_factory=dict)
    duration_minutes: int | None = None
    kind: ReminderKind | None = None
    entry_point: str | None = None
    time_state: TimeValidationState | None = None
    incomplete_date: bool = False
    shared_reminder_id: str | None = None
    turn_id: str | None = None
    item_index: int | None = None


@dataclass(frozen=True, slots=True)
class ReminderOutboxEvent:
    id: str
    topic: str
    idempotency_key: str
    payload: dict[str, Any]
    traceparent: str
    status: str
    created_at: datetime
    published_at: datetime | None
    processed_at: datetime | None
    acked_at: datetime | None
    retry_count: int
    last_error: str | None


@dataclass(frozen=True, slots=True)
class ReminderItemResult:
    state: BatchItemState
    reminder_id: str | None = None
    reason: str | None = None
    time_state: TimeValidationState | None = None
    fact: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReminderBatchResult:
    owner_account_id: str
    items: list[ReminderItemResult]


@dataclass(frozen=True, slots=True)
class DetectedReminderFields:
    content: str | None
    trigger_time: datetime | None
    recurrence_rule: dict[str, Any]
    duration_minutes: int | None
    kind: ReminderKind | None = None


class ReminderDetectorPort(Protocol):
    def extract(
        self,
        text: str,
        captured_timezone: str,
        now: datetime,
    ) -> DetectedReminderFields: ...


class ReminderDeliveryPort(Protocol):
    def send_reminder_turn(
        self,
        owner_account_id: str,
        fire_ids: list[str],
        idempotency_key: str,
    ) -> DeliveryResult: ...


@dataclass(frozen=True, slots=True)
class ReminderFireGroup:
    owner_account_id: str
    due_at: datetime
    fire_ids: list[str]
    trigger_id: str


@dataclass(frozen=True, slots=True)
class UndeliveredResendTurn:
    owner_account_id: str
    fire_ids: list[str]
    trigger_id: str


@dataclass(frozen=True, slots=True)
class NightlySummaryTurn:
    owner_account_id: str
    local_scheduled_at: datetime
    reminder_ids: list[str]
    trigger_id: str


@dataclass(frozen=True, slots=True)
class CalendarEntry:
    entry_type: str
    reminder_id: str | None
    fire_id: str | None
    display_start: datetime | None
    display_end: datetime | None
    content: str
    action_handles: list[str]
    friend_identifiers: list[str] = field(default_factory=list)
    member_reminder_ids: list[str] = field(default_factory=list)
    fact: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CalendarQueryResult:
    owner_account_id: str
    entries: list[CalendarEntry]
