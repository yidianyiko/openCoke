from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

CalendarImportRunStatus = Literal["in_progress", "completed", "failed"]
CalendarImportItemStatus = Literal[
    "imported",
    "skipped_duplicate",
    "downgraded",
    "failed",
    "historical_skipped",
]
CalendarAuthorizationStatus = Literal["active", "stopped", "revoked", "expired"]


class CalendarImportError(RuntimeError):
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
class CalendarOccurrence:
    recurrence_instance_key: str
    start: datetime | date
    end: datetime | date | None = None
    all_day: bool = False
    source_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CalendarSourceEvent:
    provider_calendar_id: str
    source_event_id: str
    title: str
    description: str
    start: datetime | date
    end: datetime | date | None
    all_day: bool
    recurrence_rule: dict[str, Any] = field(default_factory=dict)
    recurrence_expressible: bool = False
    occurrences: list[CalendarOccurrence] = field(default_factory=list)
    source_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CalendarImportRun:
    id: str
    account_id: str
    provider_type: str
    provider_account_id: str | None
    auth_artifact_id: str | None
    status: CalendarImportRunStatus
    imported_count: int
    skipped_count: int
    downgraded_count: int
    failed_count: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CalendarImportItem:
    id: str
    run_id: str
    provider_calendar_id: str
    source_event_id: str
    recurrence_instance_key: str
    status: CalendarImportItemStatus
    reason: str | None
    source_metadata: dict[str, Any]
    reminder_id: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CalendarImportSummary:
    run_id: str
    imported_count: int
    skipped_count: int
    downgraded_count: int
    failed_count: int
    items: list[CalendarImportItem]
    downgraded_items: list[CalendarImportItem]
    failed_items: list[CalendarImportItem]


@dataclass(frozen=True, slots=True)
class CalendarAuthorizationState:
    account_id: str
    auth_handle: str
    state: CalendarAuthorizationStatus
    updated_at: datetime
