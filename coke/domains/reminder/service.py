from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.domains.reminder.calendar_read_model import ReminderCalendarReadModel
from coke.domains.reminder.models import (
    CalendarQueryResult,
    DetectedReminderFields,
    Reminder,
    ReminderBatchItem,
    ReminderBatchResult,
    ReminderDeliveryPort,
    ReminderDetectorPort,
    ReminderError,
    ReminderFire,
    ReminderFireGroup,
    ReminderItemResult,
    ReminderKind,
    ReminderOutboxEvent,
    TimeValidationState,
    UndeliveredResendTurn,
)
from coke.domains.reminder.recurrence import next_occurrence_after
from coke.domains.reminder.repository import ReminderRepository
from coke.infra.tracing import generate_traceparent

CommitGuard = Callable[[], None] | None


class ReminderService:
    def __init__(
        self,
        repository: ReminderRepository,
        detector: ReminderDetectorPort | None = None,
        delivery: ReminderDeliveryPort | None = None,
        now: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
        friend_identifiers: Callable[[str, str], list[str]] | None = None,
    ) -> None:
        self.repository = repository
        self.detector = detector
        self.delivery = delivery
        self._now = now or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda prefix: uuid4().hex)
        self._friend_identifiers = friend_identifiers

    def execute_batch(
        self,
        owner_account_id: str,
        items: list[ReminderBatchItem],
        commit_guard: CommitGuard = None,
    ) -> ReminderBatchResult:
        results: list[ReminderItemResult] = []
        for item in items:
            try:
                results.append(self._execute_item(owner_account_id, item, commit_guard))
            except ReminderError as error:
                results.append(
                    ReminderItemResult(
                        state="failed",
                        reason=error.code,
                        fact=error.fact or {},
                    )
                )
            except ValueError as error:
                results.append(
                    ReminderItemResult(state="failed", reason=str(error), fact={})
                )
        return ReminderBatchResult(owner_account_id=owner_account_id, items=results)

    def schedule_unscheduled(
        self,
        owner_account_id: str,
        reminder_id: str,
        trigger_time: datetime,
        captured_timezone: str,
        commit_guard: CommitGuard = None,
    ) -> ReminderItemResult:
        reminder = self._require_owned_reminder(owner_account_id, reminder_id)
        if reminder.kind != "no_trigger_time" or reminder.next_fire_at is not None:
            raise ReminderError("reminder_not_unscheduled")
        time_state = self.validate_trigger_time(
            trigger_time=trigger_time,
            captured_timezone=captured_timezone,
            incomplete_date=False,
        )
        if time_state != "valid_future":
            return ReminderItemResult(
                state="needs-follow-up" if time_state != "invalid" else "failed",
                reminder_id=reminder.id,
                reason=time_state,
                time_state=time_state,
            )
        updated = replace(
            reminder,
            kind="timed",
            next_fire_at=trigger_time,
            captured_timezone=captured_timezone,
            updated_at=self._now(),
        )
        self._save_reminder_with_outbox(
            updated,
            "schedule_unscheduled",
            commit_guard=commit_guard,
        )
        return ReminderItemResult(
            state="succeeded",
            reminder_id=updated.id,
            time_state="valid_future",
            fact={"transition": "schedule_unscheduled"},
        )

    def reschedule_reminder(
        self,
        owner_account_id: str,
        reminder_id: str,
        trigger_time: datetime,
        captured_timezone: str,
        commit_guard: CommitGuard = None,
    ) -> ReminderItemResult:
        reminder = self._require_owned_reminder(owner_account_id, reminder_id)
        if reminder.kind == "no_trigger_time" or reminder.next_fire_at is None:
            return self.schedule_unscheduled(
                owner_account_id=owner_account_id,
                reminder_id=reminder_id,
                trigger_time=trigger_time,
                captured_timezone=captured_timezone,
                commit_guard=commit_guard,
            )
        if reminder.kind == "proactive":
            raise ReminderError("proactive_user_immutable")
        time_state = self.validate_trigger_time(
            trigger_time=trigger_time,
            captured_timezone=captured_timezone,
            incomplete_date=False,
        )
        if time_state != "valid_future":
            return ReminderItemResult(
                state="needs-follow-up" if time_state != "invalid" else "failed",
                reminder_id=reminder.id,
                reason=time_state,
                time_state=time_state,
            )
        updated = replace(
            reminder,
            next_fire_at=trigger_time,
            captured_timezone=captured_timezone,
            updated_at=self._now(),
        )
        self._save_reminder_with_outbox(
            updated,
            "reschedule",
            commit_guard=commit_guard,
        )
        return ReminderItemResult(
            state="succeeded",
            reminder_id=updated.id,
            time_state="valid_future",
            fact={"transition": "reschedule_reminder"},
        )

    def clear_trigger_time(
        self,
        owner_account_id: str,
        reminder_id: str,
        commit_guard: CommitGuard = None,
    ) -> ReminderItemResult:
        reminder = self._require_owned_reminder(owner_account_id, reminder_id)
        if reminder.kind == "recurring":
            return ReminderItemResult(
                state="needs-follow-up",
                reminder_id=reminder.id,
                fact={
                    "transition": "clear_recurring_trigger_time_requires_choice",
                    "choices": [
                        "convert_to_unscheduled",
                        "delete_recurring_series",
                    ],
                },
            )
        updated = replace(
            reminder,
            kind="no_trigger_time",
            next_fire_at=None,
            recurrence_rule={},
            updated_at=self._now(),
        )
        self._save_reminder_with_outbox(
            updated,
            "clear_trigger_time",
            commit_guard=commit_guard,
        )
        return ReminderItemResult(
            state="succeeded",
            reminder_id=updated.id,
            fact={"transition": "clear_trigger_time"},
        )

    def complete_reminder(
        self,
        owner_account_id: str,
        reminder_id: str,
        commit_guard: CommitGuard = None,
    ) -> ReminderItemResult:
        reminder = self._require_owned_reminder(owner_account_id, reminder_id)
        if reminder.kind == "proactive":
            raise ReminderError("proactive_user_immutable")
        if reminder.kind == "recurring":
            raise ReminderError("recurring_completion_requires_occurrence")
        updated = replace(reminder, lifecycle="completed", updated_at=self._now())
        self._save_reminder_with_outbox(
            updated,
            "complete",
            commit_guard=commit_guard,
        )
        return ReminderItemResult(state="succeeded", reminder_id=reminder.id)

    def delete_reminder(
        self,
        owner_account_id: str,
        reminder_id: str,
        user_initiated: bool = True,
        commit_guard: CommitGuard = None,
    ) -> ReminderItemResult:
        reminder = self._require_owned_reminder(owner_account_id, reminder_id)
        if user_initiated and reminder.kind == "proactive":
            raise ReminderError("proactive_user_immutable")
        updated = replace(reminder, lifecycle="deleted", updated_at=self._now())
        self._save_reminder_with_outbox(
            updated,
            "delete",
            commit_guard=commit_guard,
        )
        return ReminderItemResult(state="succeeded", reminder_id=reminder.id)

    def claim_due_fire(
        self,
        reminder_id: str,
        due_at: datetime,
        missed_catch_up: bool = False,
    ) -> ReminderFire:
        reminder = self._require_reminder(reminder_id)
        occurrence_key = due_at.isoformat()
        existing = self.repository.get_fire_by_occurrence(reminder_id, occurrence_key)
        if existing is not None:
            return existing
        now = self._now()
        fire = ReminderFire(
            id=self._id_factory("reminder_fire"),
            reminder_id=reminder.id,
            occurrence_key=occurrence_key,
            due_at=due_at,
            fire_state="claimed",
            delivery_result=None,
            handled_at=None,
            completed_at=None,
            missed_catch_up=missed_catch_up,
            created_at=now,
            updated_at=now,
        )
        self.repository.add_fire(fire)
        return fire

    def deliver_fire_group(
        self,
        owner_account_id: str,
        due_at: datetime,
        fire_ids: list[str],
    ) -> ReminderFireGroup:
        group = ReminderFireGroup(
            owner_account_id=owner_account_id,
            due_at=due_at,
            fire_ids=list(fire_ids),
            trigger_id=f"reminder_fire:{owner_account_id}:{due_at.isoformat()}",
        )
        outcome = "undelivered"
        if self.delivery is not None:
            raw_outcome = self.delivery.send_reminder_turn(
                owner_account_id,
                list(fire_ids),
                group.trigger_id,
            )
            outcome = "delivered" if raw_outcome == "delivered" else "undelivered"
        for fire_id in fire_ids:
            fire = self._require_fire(fire_id)
            reminder = self._require_reminder(fire.reminder_id)
            if reminder.kind == "proactive" and outcome != "delivered":
                updated_fire = replace(
                    fire,
                    fire_state="discarded",
                    updated_at=self._now(),
                )
            else:
                updated_fire = replace(
                    fire,
                    delivery_result=outcome,
                    updated_at=self._now(),
                )
            self.repository.save_fire(updated_fire)
        return group

    def mark_fire_undelivered(self, fire_id: str) -> ReminderFire:
        fire = self._require_fire(fire_id)
        updated = replace(
            fire,
            delivery_result="undelivered",
            updated_at=self._now(),
        )
        self.repository.save_fire(updated)
        return updated

    def record_fire_delivery(
        self,
        fire_ids: list[str],
        *,
        delivered: bool,
    ) -> list[ReminderFire]:
        updated_fires: list[ReminderFire] = []
        for fire_id in fire_ids:
            fire = self._require_fire(fire_id)
            reminder = self._require_reminder(fire.reminder_id)
            if reminder.kind == "proactive":
                updated_fires.append(
                    self.record_proactive_delivery(fire_id, delivered=delivered)
                )
                continue
            updated = replace(
                fire,
                delivery_result="delivered" if delivered else "undelivered",
                updated_at=self._now(),
            )
            self.repository.save_fire(updated)
            updated_fires.append(updated)
        return updated_fires

    def record_proactive_delivery(
        self,
        fire_id: str,
        *,
        delivered: bool,
    ) -> ReminderFire:
        fire = self._require_fire(fire_id)
        if delivered:
            updated = replace(
                fire,
                delivery_result="delivered",
                updated_at=self._now(),
            )
            self.repository.save_fire(updated)
            return updated
        return self.discard_proactive_fire(fire_id)

    def complete_fire(self, fire_id: str, completed_at: datetime) -> ReminderFire:
        fire = self._require_fire(fire_id)
        reminder = self._require_reminder(fire.reminder_id)
        updated_fire = replace(
            fire,
            fire_state="completed",
            handled_at=completed_at,
            completed_at=completed_at,
            updated_at=self._now(),
        )
        self.repository.save_fire(updated_fire)
        self._advance_or_complete_after_occurrence(reminder, fire.due_at)
        return updated_fire

    def mark_fire_handled(self, fire_id: str, handled_at: datetime) -> ReminderFire:
        fire = self._require_fire(fire_id)
        updated = replace(
            fire,
            handled_at=handled_at,
            updated_at=self._now(),
        )
        self.repository.save_fire(updated)
        return updated

    def discard_proactive_fire(
        self,
        fire_id: str,
        missed_catch_up: bool = False,
    ) -> ReminderFire:
        fire = self._require_fire(fire_id)
        updated = replace(
            fire,
            fire_state="discarded",
            missed_catch_up=missed_catch_up or fire.missed_catch_up,
            updated_at=self._now(),
        )
        self.repository.save_fire(updated)
        return updated

    def undelivered_resend_turn(self, owner_account_id: str) -> UndeliveredResendTurn:
        fire_ids: list[str] = []
        for fire in self.repository.list_fires_for_owner(owner_account_id):
            reminder = self._require_reminder(fire.reminder_id)
            if (
                reminder.lifecycle == "active"
                and reminder.kind != "proactive"
                and fire.delivery_result == "undelivered"
                and fire.handled_at is None
                and fire.completed_at is None
            ):
                fire_ids.append(fire.id)
        return UndeliveredResendTurn(
            owner_account_id=owner_account_id,
            fire_ids=fire_ids,
            trigger_id=f"reminder_undelivered:{owner_account_id}",
        )

    def calendar_entries(
        self,
        owner_account_id: str,
        visible_start: datetime,
        visible_end: datetime,
        display_timezone: str,
    ) -> CalendarQueryResult:
        return ReminderCalendarReadModel(
            self.repository,
            friend_identifiers=self._friend_identifiers,
        ).query(
            owner_account_id=owner_account_id,
            visible_start=visible_start,
            visible_end=visible_end,
            display_timezone=display_timezone,
        )

    def validate_trigger_time(
        self,
        trigger_time: datetime | None,
        captured_timezone: str,
        incomplete_date: bool = False,
    ) -> TimeValidationState:
        try:
            ZoneInfo(captured_timezone)
        except ZoneInfoNotFoundError:
            return "invalid"
        if trigger_time is None:
            return "valid_future"
        if trigger_time.tzinfo is None:
            return "invalid"
        if trigger_time < self._now():
            if incomplete_date:
                return "needs_incomplete_date_clarification"
            return "needs_past_time_confirmation"
        return "valid_future"

    def _execute_item(
        self,
        owner_account_id: str,
        item: ReminderBatchItem,
        commit_guard: CommitGuard,
    ) -> ReminderItemResult:
        if item.operation == "detect_and_create":
            item = self._detect_item(item)
        if item.operation != "create":
            raise ReminderError("unsupported_reminder_operation")
        return self._create(owner_account_id, item, commit_guard)

    def _detect_item(self, item: ReminderBatchItem) -> ReminderBatchItem:
        if self.detector is None or item.raw_text is None:
            raise ReminderError("detector_unavailable")
        try:
            detector_now = self._now().astimezone(ZoneInfo(item.captured_timezone))
            fields: DetectedReminderFields = self.detector.extract(
                item.raw_text,
                item.captured_timezone,
                detector_now,
            )
        except (RuntimeError, ZoneInfoNotFoundError) as error:
            raise ReminderError("invalid_detector_output") from error
        if not fields.content:
            raise ReminderError("invalid_detector_output")
        return ReminderBatchItem(
            operation="create",
            content=fields.content,
            trigger_time=self._detected_trigger_time(fields, item.captured_timezone),
            captured_timezone=item.captured_timezone,
            recurrence_rule=dict(fields.recurrence_rule),
            duration_minutes=fields.duration_minutes,
            kind=fields.kind,
            entry_point=item.entry_point,
            time_state=item.time_state,
            turn_id=item.turn_id,
            item_index=item.item_index,
        )

    def _detected_trigger_time(
        self,
        fields: DetectedReminderFields,
        captured_timezone: str,
    ) -> datetime | None:
        if fields.trigger_time is None:
            return None
        try:
            zone = ZoneInfo(captured_timezone)
        except ZoneInfoNotFoundError as error:
            raise ReminderError("invalid_detector_output") from error
        local_trigger = fields.trigger_time.replace(tzinfo=zone)
        return local_trigger.astimezone(UTC)

    def _create(
        self,
        owner_account_id: str,
        item: ReminderBatchItem,
        commit_guard: CommitGuard,
    ) -> ReminderItemResult:
        if not item.content:
            return ReminderItemResult(state="needs-follow-up", reason="needs_content")
        time_state = item.time_state or self.validate_trigger_time(
            trigger_time=item.trigger_time,
            captured_timezone=item.captured_timezone,
            incomplete_date=item.incomplete_date,
        )
        if time_state != "valid_future":
            return ReminderItemResult(
                state="needs-follow-up" if time_state != "invalid" else "failed",
                reason=time_state,
                time_state=time_state,
            )
        kind = self._derive_kind(item)
        now = self._now()
        reminder = Reminder(
            id=self._id_factory("reminder"),
            owner_account_id=owner_account_id,
            content=item.content,
            content_hash=_content_hash(item.content),
            kind=kind,
            next_fire_at=item.trigger_time,
            recurrence_rule=dict(item.recurrence_rule),
            captured_timezone=item.captured_timezone,
            duration_minutes=item.duration_minutes or 15,
            lifecycle="active",
            hidden_from_calendar=kind == "proactive",
            shared_reminder_id=item.shared_reminder_id,
            created_at=now,
            updated_at=now,
        )
        outbox = self._outbox_event("create", reminder, item=item)
        existing_event = self.repository.get_outbox_by_idempotency_key(
            outbox.idempotency_key
        )
        if existing_event is not None:
            reminder_id = existing_event.payload.get("reminder_id")
            return ReminderItemResult(
                state="succeeded",
                reminder_id=reminder_id if isinstance(reminder_id, str) else None,
                time_state=time_state,
                fact=dict(existing_event.payload),
            )
        try:
            self.repository.add_reminder_with_outbox(
                reminder,
                outbox,
                before_write=commit_guard,
            )
        except ValueError as error:
            if str(error) == "duplicate_reminder":
                return ReminderItemResult(
                    state="failed",
                    reason="duplicate_reminder",
                    time_state=time_state,
                )
            raise
        return ReminderItemResult(
            state="succeeded",
            reminder_id=reminder.id,
            time_state=time_state,
            fact={
                "kind": reminder.kind,
                "content": reminder.content,
                "trigger_time": (
                    reminder.next_fire_at.isoformat()
                    if reminder.next_fire_at is not None
                    else None
                ),
                "duration_minutes": reminder.duration_minutes,
            },
        )

    def _derive_kind(self, item: ReminderBatchItem) -> ReminderKind:
        if item.kind is not None:
            return item.kind
        if item.recurrence_rule:
            return "recurring"
        if item.trigger_time is None:
            return "no_trigger_time"
        return "timed"

    def _advance_or_complete_after_occurrence(
        self,
        reminder: Reminder,
        due_at: datetime,
    ) -> None:
        if reminder.kind == "recurring":
            next_fire = next_occurrence_after(
                reminder.recurrence_rule,
                due_at,
                reminder.captured_timezone,
            )
            self._save_reminder_with_outbox(
                replace(reminder, next_fire_at=next_fire, updated_at=self._now()),
                "advance_occurrence",
            )
        elif reminder.kind != "proactive":
            self._save_reminder_with_outbox(
                replace(reminder, lifecycle="completed", updated_at=self._now()),
                "complete_after_fire",
            )

    def _require_owned_reminder(
        self,
        owner_account_id: str,
        reminder_id: str,
    ) -> Reminder:
        reminder = self._require_reminder(reminder_id)
        if (
            reminder.owner_account_id != owner_account_id
            or reminder.lifecycle != "active"
        ):
            raise ReminderError("reminder_not_found")
        return reminder

    def _require_reminder(self, reminder_id: str) -> Reminder:
        reminder = self.repository.get_reminder(reminder_id)
        if reminder is None:
            raise ReminderError("reminder_not_found")
        return reminder

    def _require_fire(self, fire_id: str) -> ReminderFire:
        fire = self.repository.get_fire(fire_id)
        if fire is None:
            raise ReminderError("reminder_fire_not_found")
        return fire

    def _save_reminder_with_outbox(
        self,
        reminder: Reminder,
        operation: str,
        *,
        commit_guard: CommitGuard = None,
    ) -> None:
        outbox = self._outbox_event(operation, reminder)
        self.repository.save_reminder_with_outbox(
            reminder,
            outbox,
            before_write=commit_guard,
        )

    def _outbox_event(
        self,
        operation: str,
        reminder: Reminder,
        *,
        item: ReminderBatchItem | None = None,
    ) -> ReminderOutboxEvent:
        now = self._now()
        outbox_id = self._id_factory("outbox")
        if item is not None and item.turn_id and item.item_index is not None:
            idempotency_key = f"reminder:{operation}:{item.turn_id}:{item.item_index}"
        elif operation == "create":
            idempotency_key = f"reminder:create:{reminder.id}"
        else:
            idempotency_key = f"reminder:{operation}:{reminder.id}:{outbox_id}"
        next_fire_at = (
            reminder.next_fire_at.isoformat()
            if reminder.next_fire_at is not None
            else None
        )
        return ReminderOutboxEvent(
            id=outbox_id,
            topic="reminder.lifecycle",
            idempotency_key=idempotency_key,
            payload={
                "type": "reminder_lifecycle",
                "operation": operation,
                "reminder_id": reminder.id,
                "owner_account_id": reminder.owner_account_id,
                "turn_id": item.turn_id if item is not None else None,
                "item_index": item.item_index if item is not None else None,
                "kind": reminder.kind,
                "lifecycle": reminder.lifecycle,
                "next_fire_at": next_fire_at,
                "shared_reminder_id": reminder.shared_reminder_id,
            },
            traceparent=generate_traceparent(),
            status="pending",
            created_at=now,
            published_at=None,
            processed_at=None,
            acked_at=None,
            retry_count=0,
            last_error=None,
        )


def _content_hash(content: str) -> str:
    return sha256(content.strip().lower().encode("utf-8")).hexdigest()
