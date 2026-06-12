from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from coke.domains.calendar_import.models import (
    CalendarImportError,
    CalendarImportSummary,
)
from coke.turn.inbound.contracts import ActionOutcome, CompiledAction, ProposedAction
from coke.turn.inbound.handlers.calendar import CalendarImportActionHandler

VISIBLE_START = datetime(2026, 6, 10, 0, 0, tzinfo=UTC)
VISIBLE_END = datetime(2026, 6, 17, 0, 0, tzinfo=UTC)


class StubCalendarImportService:
    def __init__(self) -> None:
        self.summary = CalendarImportSummary(
            run_id="run-1",
            imported_count=2,
            skipped_count=1,
            downgraded_count=0,
            failed_count=0,
            items=[],
            downgraded_items=[],
            failed_items=[],
        )
        self.error: CalendarImportError | None = None
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def import_google_calendar(self, **kwargs: Any) -> CalendarImportSummary:
        self.calls.append(("import_google_calendar", kwargs))
        if self.error is not None:
            raise self.error
        return self.summary


class RecordingGuard:
    def __init__(self) -> None:
        self.staged: list[dict[str, Any]] = []
        self.state_change_calls = 0

    def guard_state_change(self) -> None:
        self.state_change_calls += 1

    def stage_command(self, **kwargs: Any) -> Any:
        self.staged.append(kwargs)
        raise AssertionError("calendar import handler must not stage commands")


def _compiled(params: dict[str, Any]) -> CompiledAction:
    return CompiledAction(
        action=ProposedAction(
            domain="calendar_import", operation="import", params=params
        )
    )


def _execute_handler(
    handler: CalendarImportActionHandler,
    compiled: CompiledAction,
    guard: RecordingGuard,
) -> ActionOutcome:
    return handler.execute(
        compiled,
        guard,
        action_index=0,
        turn_id="turn-1",
    )


def test_import_success_maps_counts_and_stages_google_import() -> None:
    service = StubCalendarImportService()
    guard = RecordingGuard()

    outcome = _execute_handler(
        CalendarImportActionHandler(service),
        _compiled(
            {
                "account_id": "acct-1",
                "source": "google_calendar",
                "auth_handle": "auth-1",
                "visible_start": VISIBLE_START,
                "visible_end": VISIBLE_END,
                "captured_timezone": "Asia/Tokyo",
            }
        ),
        guard,
    )

    assert outcome == ActionOutcome(
        category="done",
        status="imported",
        data={
            "run_id": "run-1",
            "imported": 2,
            "skipped": 1,
            "downgraded": 0,
            "failed": 0,
        },
    )
    assert service.calls == [
        (
            "import_google_calendar",
            {
                "account_id": "acct-1",
                "auth_handle": "auth-1",
                "provider_account_id": None,
                "visible_start": VISIBLE_START,
                "visible_end": VISIBLE_END,
                "captured_timezone": "Asia/Tokyo",
                "auth_artifact_id": None,
            },
        )
    ]


def test_import_with_failed_count_maps_partial_and_preserves_counts() -> None:
    service = StubCalendarImportService()
    service.summary = CalendarImportSummary(
        run_id="run-partial",
        imported_count=1,
        skipped_count=2,
        downgraded_count=1,
        failed_count=3,
        items=[],
        downgraded_items=[],
        failed_items=[],
    )
    guard = RecordingGuard()

    outcome = _execute_handler(
        CalendarImportActionHandler(service),
        _compiled(
            {
                "account_id": "acct-1",
                "source": "google_calendar",
                "auth_handle": "auth-1",
                "visible_start": VISIBLE_START,
                "visible_end": VISIBLE_END,
            }
        ),
        guard,
    )

    assert outcome.category == "done"
    assert outcome.status == "partial"
    assert outcome.data == {
        "run_id": "run-partial",
        "imported": 1,
        "skipped": 2,
        "downgraded": 1,
        "failed": 3,
    }


def test_import_missing_auth_handle_needs_input_without_service_or_stage() -> None:
    service = StubCalendarImportService()
    guard = RecordingGuard()

    outcome = _execute_handler(
        CalendarImportActionHandler(service),
        _compiled(
            {
                "account_id": "acct-1",
                "source": "google_calendar",
                "visible_start": VISIBLE_START,
                "visible_end": VISIBLE_END,
            }
        ),
        guard,
    )

    assert outcome == ActionOutcome(
        category="needs_input",
        status="missing_auth_handle",
        data={"field": "auth_handle"},
    )
    assert service.calls == []
    assert guard.staged == []


def test_import_access_denied_is_not_possible_without_stage() -> None:
    service = StubCalendarImportService()
    service.error = CalendarImportError(
        "access_denied",
        fact={"type": "account_access_denied", "account_id": "acct-1"},
    )
    guard = RecordingGuard()

    outcome = _execute_handler(
        CalendarImportActionHandler(service),
        _compiled(
            {
                "account_id": "acct-1",
                "source": "google_calendar",
                "auth_handle": "auth-1",
                "visible_start": VISIBLE_START,
                "visible_end": VISIBLE_END,
            }
        ),
        guard,
    )

    assert outcome == ActionOutcome(
        category="not_possible",
        status="access_denied",
        data={"type": "account_access_denied", "account_id": "acct-1"},
    )
    assert guard.staged == []


def test_import_unsupported_source_is_not_possible_without_service_or_stage() -> None:
    service = StubCalendarImportService()
    guard = RecordingGuard()

    outcome = _execute_handler(
        CalendarImportActionHandler(service),
        _compiled(
            {
                "account_id": "acct-1",
                "source": "ical_attachment",
                "auth_handle": "auth-1",
                "visible_start": VISIBLE_START,
                "visible_end": VISIBLE_END,
            }
        ),
        guard,
    )

    assert outcome == ActionOutcome(
        category="not_possible",
        status="unsupported_source",
        data={"source": "ical_attachment"},
    )
    assert service.calls == []
    assert guard.staged == []
