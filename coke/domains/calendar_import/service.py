from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, date, datetime, time
from typing import Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from coke import schema
from coke.domains._pg import (
    db_id,
    insert_row,
    json_value,
    many,
    one_or_none,
    update_row,
)
from coke.domains.calendar_import.google import GoogleCalendarClientPort
from coke.domains.calendar_import.models import (
    CalendarAuthorizationState,
    CalendarImportError,
    CalendarImportItem,
    CalendarImportItemStatus,
    CalendarImportRun,
    CalendarImportSummary,
    CalendarOccurrence,
    CalendarSourceEvent,
)
from coke.domains.reminder.models import ReminderBatchItem


class AccessGatePort(Protocol):
    def check_access_for_action(self, account_id: str, action: str): ...


class CalendarImportRepository(Protocol):
    def add_run(self, run: CalendarImportRun) -> None: ...

    def save_run(self, run: CalendarImportRun) -> None: ...

    def get_run(self, run_id: str) -> CalendarImportRun | None: ...

    def add_item(self, item: CalendarImportItem) -> None: ...

    def get_item_by_source_occurrence(
        self,
        provider_calendar_id: str,
        source_event_id: str,
        recurrence_instance_key: str,
    ) -> CalendarImportItem | None: ...

    def list_items_for_run(self, run_id: str) -> list[CalendarImportItem]: ...

    def save_authorization_state(self, state: CalendarAuthorizationState) -> None: ...

    def get_authorization_state(
        self, account_id: str, auth_handle: str
    ) -> CalendarAuthorizationState | None: ...


class InMemoryCalendarImportRepository:
    def __init__(self) -> None:
        self.runs_by_id: dict[str, CalendarImportRun] = {}
        self.items_by_id: dict[str, CalendarImportItem] = {}
        self.items_by_source_occurrence: dict[
            tuple[str, str, str], CalendarImportItem
        ] = {}
        self.authorization_states: dict[tuple[str, str], CalendarAuthorizationState] = (
            {}
        )

    def add_run(self, run: CalendarImportRun) -> None:
        if run.id in self.runs_by_id:
            raise ValueError("duplicate_calendar_import_run_id")
        self.runs_by_id[run.id] = run

    def save_run(self, run: CalendarImportRun) -> None:
        if run.id not in self.runs_by_id:
            raise ValueError("calendar_import_run_not_found")
        self.runs_by_id[run.id] = run

    def get_run(self, run_id: str) -> CalendarImportRun | None:
        return self.runs_by_id.get(run_id)

    def add_item(self, item: CalendarImportItem) -> None:
        key = _source_occurrence_key(
            item.provider_calendar_id,
            item.source_event_id,
            item.recurrence_instance_key,
        )
        if item.id in self.items_by_id:
            raise ValueError("duplicate_calendar_import_item_id")
        if key in self.items_by_source_occurrence:
            raise ValueError("duplicate_calendar_import_source_occurrence")
        self.items_by_id[item.id] = item
        self.items_by_source_occurrence[key] = item

    def get_item_by_source_occurrence(
        self,
        provider_calendar_id: str,
        source_event_id: str,
        recurrence_instance_key: str,
    ) -> CalendarImportItem | None:
        return self.items_by_source_occurrence.get(
            _source_occurrence_key(
                provider_calendar_id,
                source_event_id,
                recurrence_instance_key,
            )
        )

    def list_items_for_run(self, run_id: str) -> list[CalendarImportItem]:
        return [item for item in self.items_by_id.values() if item.run_id == run_id]

    def list_source_occurrence_items(self) -> list[CalendarImportItem]:
        return list(self.items_by_source_occurrence.values())

    def save_authorization_state(self, state: CalendarAuthorizationState) -> None:
        self.authorization_states[(state.account_id, state.auth_handle)] = state

    def get_authorization_state(
        self, account_id: str, auth_handle: str
    ) -> CalendarAuthorizationState | None:
        return self.authorization_states.get((account_id, auth_handle))


class PostgresCalendarImportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_run(self, run: CalendarImportRun) -> None:
        insert_row(
            self.session,
            schema.calendar_import_run,
            _run_values(run),
            {"pk_calendar_import_run": "duplicate_calendar_import_run_id"},
            default_error="duplicate_calendar_import_run_id",
        )

    def save_run(self, run: CalendarImportRun) -> None:
        if (
            update_row(
                self.session,
                schema.calendar_import_run,
                _run_values(run),
                {},
                default_error="duplicate_calendar_import_run_id",
            )
            == 0
        ):
            raise ValueError("calendar_import_run_not_found")

    def get_run(self, run_id: str) -> CalendarImportRun | None:
        row = one_or_none(
            self.session,
            schema.calendar_import_run,
            schema.calendar_import_run.c.id == run_id,
        )
        return _run(row) if row else None

    def add_item(self, item: CalendarImportItem) -> None:
        insert_row(
            self.session,
            schema.calendar_import_item,
            _item_values(item),
            {
                "pk_calendar_import_item": "duplicate_calendar_import_item_id",
                "uq_calendar_import_item_source_occurrence": "duplicate_calendar_import_source_occurrence",
            },
            default_error="duplicate_calendar_import_source_occurrence",
        )

    def get_item_by_source_occurrence(
        self,
        provider_calendar_id: str,
        source_event_id: str,
        recurrence_instance_key: str,
    ) -> CalendarImportItem | None:
        row = one_or_none(
            self.session,
            schema.calendar_import_item,
            schema.calendar_import_item.c.provider_calendar_id == provider_calendar_id,
            schema.calendar_import_item.c.source_event_id == source_event_id,
            schema.calendar_import_item.c.recurrence_instance_key
            == recurrence_instance_key,
        )
        return _item(row) if row else None

    def list_items_for_run(self, run_id: str) -> list[CalendarImportItem]:
        return [
            _item(row)
            for row in many(
                self.session,
                schema.calendar_import_item,
                schema.calendar_import_item.c.run_id == run_id,
                order_by=(
                    schema.calendar_import_item.c.created_at,
                    schema.calendar_import_item.c.id,
                ),
            )
        ]

    def save_authorization_state(self, state: CalendarAuthorizationState) -> None:
        artifact_id = uuid5(
            NAMESPACE_URL,
            f"calendar_authorization:{state.account_id}:{state.auth_handle}",
        ).hex
        values = {
            "id": artifact_id,
            "account_id": state.account_id,
            "target_account_id": None,
            "type": "calendar_authorization",
            "purpose": "google_calendar",
            "delivery": "oauth",
            "token_hash": state.auth_handle,
            "browser_session": None,
            "continuation": {"account_id": state.account_id},
            "expires_at": state.updated_at,
            "consumed_at": None,
            "delivery_state": state.state,
            "resend_count": 0,
            "created_at": state.updated_at,
            "updated_at": state.updated_at,
        }
        existing = one_or_none(
            self.session,
            schema.auth_artifact,
            schema.auth_artifact.c.type == "calendar_authorization",
            schema.auth_artifact.c.purpose == "google_calendar",
            schema.auth_artifact.c.account_id == state.account_id,
            schema.auth_artifact.c.token_hash == state.auth_handle,
        )
        if existing is None:
            insert_row(
                self.session,
                schema.auth_artifact,
                values,
                {"uq_auth_artifact_token_hash": "duplicate_calendar_authorization"},
                default_error="duplicate_calendar_authorization",
            )
        else:
            values["id"] = existing["id"]
            values["created_at"] = existing["created_at"]
            update_row(
                self.session,
                schema.auth_artifact,
                values,
                {"uq_auth_artifact_token_hash": "duplicate_calendar_authorization"},
                default_error="duplicate_calendar_authorization",
            )

    def get_authorization_state(
        self, account_id: str, auth_handle: str
    ) -> CalendarAuthorizationState | None:
        row = one_or_none(
            self.session,
            schema.auth_artifact,
            schema.auth_artifact.c.type == "calendar_authorization",
            schema.auth_artifact.c.purpose == "google_calendar",
            schema.auth_artifact.c.account_id == account_id,
            schema.auth_artifact.c.token_hash == auth_handle,
        )
        if row is None:
            return None
        return CalendarAuthorizationState(
            account_id=db_id(row["account_id"]),
            auth_handle=row["token_hash"],
            state=row["delivery_state"],
            updated_at=row["updated_at"],
        )


class CalendarImportService:
    def __init__(
        self,
        repository: CalendarImportRepository,
        google_client: GoogleCalendarClientPort,
        reminder_service,
        access_gate: AccessGatePort | None = None,
        now: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self.repository = repository
        self.google_client = google_client
        self.reminder_service = reminder_service
        self.access_gate = access_gate
        self._now = now or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda prefix: uuid4().hex)

    def import_google_calendar(
        self,
        account_id: str,
        auth_handle: str,
        provider_account_id: str | None,
        visible_start: datetime,
        visible_end: datetime,
        captured_timezone: str,
        auth_artifact_id: str | None = None,
    ) -> CalendarImportSummary:
        self._require_aware_datetime(visible_start, "visible_start")
        self._require_aware_datetime(visible_end, "visible_end")
        self._require_timezone(captured_timezone)
        self._require_access_allowed(account_id)
        self._require_active_authorization(account_id, auth_handle)
        if visible_end < visible_start:
            raise CalendarImportError("invalid_visible_window")

        now = self._now()
        run = CalendarImportRun(
            id=self._id_factory("calendar_import_run"),
            account_id=account_id,
            provider_type="google_calendar",
            provider_account_id=provider_account_id,
            auth_artifact_id=auth_artifact_id,
            status="in_progress",
            imported_count=0,
            skipped_count=0,
            downgraded_count=0,
            failed_count=0,
            started_at=now,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        self.repository.add_run(run)

        summary_items: list[CalendarImportItem] = []
        events = self.google_client.list_events(auth_handle, visible_start, visible_end)
        for event in events:
            for occurrence in self._considered_occurrences(event):
                item = self._import_occurrence(
                    run=run,
                    account_id=account_id,
                    event=event,
                    occurrence=occurrence,
                    captured_timezone=captured_timezone,
                )
                summary_items.append(item)

        completed = self._complete_run(run, summary_items)
        return _summary(completed.id, summary_items)

    def stop_authorization(
        self, account_id: str, auth_handle: str
    ) -> CalendarAuthorizationState:
        return self._save_authorization_state(account_id, auth_handle, "stopped")

    def revoke_authorization(
        self, account_id: str, auth_handle: str
    ) -> CalendarAuthorizationState:
        self.google_client.revoke_authorization(auth_handle)
        return self._save_authorization_state(account_id, auth_handle, "revoked")

    def _import_occurrence(
        self,
        run: CalendarImportRun,
        account_id: str,
        event: CalendarSourceEvent,
        occurrence: CalendarOccurrence,
        captured_timezone: str,
    ) -> CalendarImportItem:
        existing = self.repository.get_item_by_source_occurrence(
            event.provider_calendar_id,
            event.source_event_id,
            occurrence.recurrence_instance_key,
        )
        if existing is not None:
            return self._build_item(
                run_id=run.id,
                event=event,
                occurrence=occurrence,
                status="skipped_duplicate",
                reason="already_imported",
                reminder_id=existing.reminder_id,
            )

        trigger_time = self._trigger_time(occurrence, captured_timezone)
        if trigger_time < self._now():
            return self._persist_item(
                run_id=run.id,
                event=event,
                occurrence=occurrence,
                status="historical_skipped",
                reason="historical_event",
                reminder_id=None,
            )

        status: CalendarImportItemStatus = "imported"
        reason = None
        recurrence_rule: dict = {}
        kind = "timed"
        if event.recurrence_rule:
            if event.recurrence_expressible:
                recurrence_rule = dict(event.recurrence_rule)
                kind = "recurring"
            else:
                status = "downgraded"
                reason = "recurrence_rule_not_expressible"

        result = self.reminder_service.execute_batch(
            owner_account_id=account_id,
            items=[
                ReminderBatchItem(
                    operation="create",
                    content=_content(event),
                    trigger_time=trigger_time,
                    captured_timezone=captured_timezone,
                    recurrence_rule=recurrence_rule,
                    duration_minutes=self._duration_minutes(
                        occurrence, captured_timezone
                    ),
                    kind=kind,
                    entry_point="calendar_import",
                    time_state="valid_future",
                )
            ],
        ).items[0]
        if result.state != "succeeded" or result.reminder_id is None:
            return self._persist_item(
                run_id=run.id,
                event=event,
                occurrence=occurrence,
                status="failed",
                reason=result.reason or "reminder_create_failed",
                reminder_id=None,
            )
        return self._persist_item(
            run_id=run.id,
            event=event,
            occurrence=occurrence,
            status=status,
            reason=reason,
            reminder_id=result.reminder_id,
        )

    def _persist_item(
        self,
        run_id: str,
        event: CalendarSourceEvent,
        occurrence: CalendarOccurrence,
        status: CalendarImportItemStatus,
        reason: str | None,
        reminder_id: str | None,
    ) -> CalendarImportItem:
        item = self._build_item(
            run_id=run_id,
            event=event,
            occurrence=occurrence,
            status=status,
            reason=reason,
            reminder_id=reminder_id,
        )
        self.repository.add_item(item)
        return item

    def _build_item(
        self,
        run_id: str,
        event: CalendarSourceEvent,
        occurrence: CalendarOccurrence,
        status: CalendarImportItemStatus,
        reason: str | None,
        reminder_id: str | None,
    ) -> CalendarImportItem:
        metadata = {
            **dict(event.source_metadata),
            **dict(occurrence.source_metadata),
            "title": event.title,
            "description": event.description,
            "start": _metadata_time(occurrence.start),
            "end": _metadata_time(occurrence.end),
            "all_day": occurrence.all_day,
            "recurrence_rule": dict(event.recurrence_rule),
        }
        return CalendarImportItem(
            id=self._id_factory("calendar_import_item"),
            run_id=run_id,
            provider_calendar_id=event.provider_calendar_id,
            source_event_id=event.source_event_id,
            recurrence_instance_key=occurrence.recurrence_instance_key,
            status=status,
            reason=reason,
            source_metadata=metadata,
            reminder_id=reminder_id,
            created_at=self._now(),
        )

    def _considered_occurrences(
        self, event: CalendarSourceEvent
    ) -> list[CalendarOccurrence]:
        if event.occurrences:
            return list(event.occurrences)
        key = _metadata_time(event.start)
        return [
            CalendarOccurrence(
                recurrence_instance_key=key,
                start=event.start,
                end=event.end,
                all_day=event.all_day,
            )
        ]

    def _trigger_time(
        self, occurrence: CalendarOccurrence, captured_timezone: str
    ) -> datetime:
        zone = ZoneInfo(captured_timezone)
        if occurrence.all_day:
            occurrence_date = (
                occurrence.start
                if isinstance(occurrence.start, date)
                else occurrence.start.date()
            )
            return datetime.combine(occurrence_date, time(0, 0), tzinfo=zone)
        if not isinstance(occurrence.start, datetime):
            return datetime.combine(occurrence.start, time(0, 0), tzinfo=zone)
        if occurrence.start.tzinfo is None:
            raise CalendarImportError(
                "invalid_calendar_event",
                fact={"type": "invalid_calendar_event", "field": "start"},
            )
        return occurrence.start

    def _duration_minutes(
        self, occurrence: CalendarOccurrence, captured_timezone: str
    ) -> int:
        if occurrence.end is None:
            return 15
        start = self._trigger_time(occurrence, captured_timezone)
        zone = ZoneInfo(captured_timezone)
        if isinstance(occurrence.end, datetime):
            if occurrence.end.tzinfo is None:
                return 15
            duration = occurrence.end - start
        else:
            duration = datetime.combine(occurrence.end, time(0, 0), tzinfo=zone) - start
        minutes = int(duration.total_seconds() // 60)
        return minutes if minutes > 0 else 15

    def _complete_run(
        self, run: CalendarImportRun, items: list[CalendarImportItem]
    ) -> CalendarImportRun:
        summary = _summary(run.id, items)
        completed = replace(
            run,
            status="completed",
            imported_count=summary.imported_count,
            skipped_count=summary.skipped_count,
            downgraded_count=summary.downgraded_count,
            failed_count=summary.failed_count,
            completed_at=self._now(),
            updated_at=self._now(),
        )
        self.repository.save_run(completed)
        return completed

    def _save_authorization_state(
        self, account_id: str, auth_handle: str, state: str
    ) -> CalendarAuthorizationState:
        authorization = CalendarAuthorizationState(
            account_id=account_id,
            auth_handle=auth_handle,
            state=state,
            updated_at=self._now(),
        )
        self.repository.save_authorization_state(authorization)
        return authorization

    def _require_active_authorization(self, account_id: str, auth_handle: str) -> None:
        state = self.repository.get_authorization_state(account_id, auth_handle)
        if state is not None and state.state in {"stopped", "revoked", "expired"}:
            raise CalendarImportError(
                "calendar_authorization_inactive",
                fact={
                    "type": "calendar_authorization_inactive",
                    "state": state.state,
                },
            )

    def _require_access_allowed(self, account_id: str) -> None:
        if self.access_gate is None:
            raise CalendarImportError(
                "access_gate_unavailable",
                fact={"type": "access_gate_unavailable"},
            )
        decision = self.access_gate.check_access_for_action(
            account_id,
            "calendar_import",
        )
        if not getattr(decision, "allowed", False):
            raise CalendarImportError(
                "access_denied",
                fact=getattr(decision, "fact", None)
                or {"type": "account_access_denied", "account_id": account_id},
            )

    def _require_timezone(self, value: str) -> None:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise CalendarImportError("invalid_timezone") from error

    def _require_aware_datetime(self, value: datetime, field: str) -> None:
        if value.tzinfo is None:
            raise CalendarImportError(
                "invalid_request",
                fact={"type": "invalid_request", "field": field},
            )


def _summary(run_id: str, items: list[CalendarImportItem]) -> CalendarImportSummary:
    imported_count = sum(1 for item in items if item.status == "imported")
    skipped_count = sum(
        1
        for item in items
        if item.status in {"skipped_duplicate", "historical_skipped"}
    )
    downgraded_items = [item for item in items if item.status == "downgraded"]
    failed_items = [item for item in items if item.status == "failed"]
    return CalendarImportSummary(
        run_id=run_id,
        imported_count=imported_count,
        skipped_count=skipped_count,
        downgraded_count=len(downgraded_items),
        failed_count=len(failed_items),
        items=list(items),
        downgraded_items=downgraded_items,
        failed_items=failed_items,
    )


def _content(event: CalendarSourceEvent) -> str:
    title = event.title.strip() or "Untitled calendar event"
    description = event.description.strip()
    if description:
        return f"{title}\n\n{description}"
    return title


def _metadata_time(value: datetime | date | None) -> str:
    if value is None:
        return ""
    return value.isoformat()


def _source_occurrence_key(
    provider_calendar_id: str,
    source_event_id: str,
    recurrence_instance_key: str,
) -> tuple[str, str, str]:
    return (provider_calendar_id, source_event_id, recurrence_instance_key)


def _run_values(run: CalendarImportRun) -> dict:
    return {
        "id": run.id,
        "account_id": run.account_id,
        "provider_type": run.provider_type,
        "provider_account_id": run.provider_account_id,
        "auth_artifact_id": run.auth_artifact_id,
        "status": run.status,
        "imported_count": run.imported_count,
        "skipped_count": run.skipped_count,
        "downgraded_count": run.downgraded_count,
        "failed_count": run.failed_count,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


def _run(row: Mapping) -> CalendarImportRun:
    return CalendarImportRun(
        db_id(row["id"]),
        db_id(row["account_id"]),
        row["provider_type"],
        row["provider_account_id"],
        db_id(row["auth_artifact_id"]) if row["auth_artifact_id"] is not None else None,
        row["status"],
        row["imported_count"],
        row["skipped_count"],
        row["downgraded_count"],
        row["failed_count"],
        row["started_at"],
        row["completed_at"],
        row["created_at"],
        row["updated_at"],
    )


def _item_values(item: CalendarImportItem) -> dict:
    return {
        "id": item.id,
        "run_id": item.run_id,
        "provider_calendar_id": item.provider_calendar_id,
        "source_event_id": item.source_event_id,
        "recurrence_instance_key": item.recurrence_instance_key,
        "status": item.status,
        "reason": item.reason,
        "source_metadata": json_value(item.source_metadata),
        "reminder_id": item.reminder_id,
        "created_at": item.created_at,
    }


def _item(row: Mapping) -> CalendarImportItem:
    return CalendarImportItem(
        db_id(row["id"]),
        db_id(row["run_id"]),
        row["provider_calendar_id"],
        row["source_event_id"],
        row["recurrence_instance_key"],
        row["status"],
        row["reason"],
        dict(row["source_metadata"]),
        db_id(row["reminder_id"]) if row["reminder_id"] is not None else None,
        row["created_at"],
    )
