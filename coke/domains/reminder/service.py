from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.domains.reminder.calendar_read_model import ReminderCalendarReadModel
from coke.domains.reminder.models import (
    BatchItemState,
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
    ReminderFireRenderFact,
    ReminderItemResult,
    ReminderKind,
    ReminderLifecycle,
    ReminderOutboxEvent,
    TimeValidationState,
    UndeliveredResendTurn,
)
from coke.domains.reminder.recurrence import next_occurrence_after
from coke.domains.reminder.repository import ReminderRepository
from coke.domains.reminder.temporal import (
    ReminderTemporalError,
    normalize_create_temporal,
    positive_duration_minutes,
    trigger_time_to_utc,
)
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
                results.extend(
                    self._execute_items(owner_account_id, item, commit_guard)
                )
            except ReminderError as error:
                results.append(
                    ReminderItemResult(
                        state="failed",
                        reason=error.code,
                        fact=error.fact or {},
                    )
                )
            except ValueError as error:
                reason = _safe_write_error_reason(error)
                results.append(
                    ReminderItemResult(
                        state="failed",
                        reason=reason,
                        fact={"type": reason},
                    )
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
        conflict = self.check_time_conflict(
            owner_account_id=owner_account_id,
            trigger_time=trigger_time,
            captured_timezone=captured_timezone,
            duration_minutes=reminder.duration_minutes,
            exclude_reminder_id=reminder.id,
        )
        if conflict is not None:
            return conflict
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
        conflict = self.check_time_conflict(
            owner_account_id=owner_account_id,
            trigger_time=trigger_time,
            captured_timezone=captured_timezone,
            duration_minutes=reminder.duration_minutes,
            exclude_reminder_id=reminder.id,
        )
        if conflict is not None:
            return conflict
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

    def update_reminder(
        self,
        owner_account_id: str,
        reminder_id: str,
        *,
        content: str | None = None,
        trigger_time: datetime | None = None,
        captured_timezone: str | None = None,
        duration_minutes: Any | None = None,
        commit_guard: CommitGuard = None,
    ) -> ReminderItemResult:
        reminder = self._require_owned_reminder(owner_account_id, reminder_id)
        if reminder.kind == "proactive":
            raise ReminderError("proactive_user_immutable")

        updates: dict[str, Any] = {"updated_at": self._now()}
        time_state: TimeValidationState | None = None
        if content is not None:
            content = content.strip()
            if not content:
                return ReminderItemResult(
                    state="needs-follow-up",
                    reminder_id=reminder.id,
                    reason="needs_content",
                )
            updates["content"] = content
            updates["content_hash"] = _content_hash(content)

        if trigger_time is not None:
            timezone = captured_timezone or reminder.captured_timezone
            time_state = self.validate_trigger_time(
                trigger_time=trigger_time,
                captured_timezone=timezone,
                incomplete_date=False,
            )
            if time_state != "valid_future":
                return ReminderItemResult(
                    state="needs-follow-up" if time_state != "invalid" else "failed",
                    reminder_id=reminder.id,
                    reason=time_state,
                    time_state=time_state,
                )
            updates["kind"] = (
                "timed" if reminder.kind == "no_trigger_time" else reminder.kind
            )
            updates["next_fire_at"] = trigger_time
            updates["captured_timezone"] = timezone

        if duration_minutes is not None:
            updates["duration_minutes"] = _duration_minutes(duration_minutes)

        if len(updates) == 1:
            return ReminderItemResult(
                state="needs-follow-up",
                reminder_id=reminder.id,
                reason="no_update_fields",
            )

        updated = replace(reminder, **updates)
        conflict = self.check_time_conflict(
            owner_account_id=owner_account_id,
            trigger_time=updated.next_fire_at,
            captured_timezone=updated.captured_timezone,
            duration_minutes=updated.duration_minutes,
            exclude_reminder_id=updated.id,
        )
        if conflict is not None:
            return replace(conflict, reminder_id=updated.id)
        self._save_reminder_with_outbox(
            updated,
            "update",
            commit_guard=commit_guard,
        )
        return ReminderItemResult(
            state="succeeded",
            reminder_id=updated.id,
            time_state=time_state,
            fact={
                "transition": "update_reminder",
                "kind": updated.kind,
                "content": updated.content,
                "trigger_time": (
                    updated.next_fire_at.isoformat()
                    if updated.next_fire_at is not None
                    else None
                ),
                "duration_minutes": updated.duration_minutes,
            },
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

    def filter_reminders(
        self,
        owner_account_id: str,
        keyword: str | None = None,
        lifecycle: ReminderLifecycle | None = "active",
        kind: ReminderKind | None = None,
        trigger_after: datetime | None = None,
        trigger_before: datetime | None = None,
    ) -> list[Reminder]:
        reminders = self.repository.list_reminders(owner_account_id)
        keyword_value = _normalized_keyword(keyword)
        matches: list[Reminder] = []
        for reminder in reminders:
            if lifecycle is not None and reminder.lifecycle != lifecycle:
                continue
            if kind is not None and reminder.kind != kind:
                continue
            if keyword_value and not _keyword_matches_content(
                keyword_value, reminder.content
            ):
                continue
            range_match = _reminder_in_trigger_range(
                reminder,
                trigger_after=trigger_after,
                trigger_before=trigger_before,
            )
            if range_match is None:
                continue
            matches.append(range_match)
        if trigger_after is not None or trigger_before is not None:
            matches.sort(key=_trigger_range_sort_key)
        return matches

    def complete_reminder_by_keyword(
        self,
        owner_account_id: str,
        keyword: str,
        commit_guard: CommitGuard = None,
    ) -> ReminderItemResult:
        matched = self.resolve_user_mutable_keyword(owner_account_id, keyword)
        if matched.state != "succeeded" or matched.reminder_id is None:
            return matched
        return self.complete_reminder(
            owner_account_id,
            matched.reminder_id,
            commit_guard=commit_guard,
        )

    def delete_reminder_by_keyword(
        self,
        owner_account_id: str,
        keyword: str,
        commit_guard: CommitGuard = None,
    ) -> ReminderItemResult:
        matched = self.resolve_user_mutable_keyword(owner_account_id, keyword)
        if matched.state != "succeeded" or matched.reminder_id is None:
            return matched
        return self.delete_reminder(
            owner_account_id,
            matched.reminder_id,
            commit_guard=commit_guard,
        )

    def delete_reminders_by_filter(
        self,
        *,
        owner_account_id: str,
        keyword: str | None = None,
        trigger_after: datetime | None = None,
        trigger_before: datetime | None = None,
        commit_guard: CommitGuard = None,
    ) -> ReminderBatchResult:
        return self._mutate_reminders_by_filter(
            operation="delete",
            owner_account_id=owner_account_id,
            keyword=keyword,
            trigger_after=trigger_after,
            trigger_before=trigger_before,
            commit_guard=commit_guard,
        )

    def complete_reminders_by_filter(
        self,
        *,
        owner_account_id: str,
        keyword: str | None = None,
        trigger_after: datetime | None = None,
        trigger_before: datetime | None = None,
        commit_guard: CommitGuard = None,
    ) -> ReminderBatchResult:
        return self._mutate_reminders_by_filter(
            operation="complete",
            owner_account_id=owner_account_id,
            keyword=keyword,
            trigger_after=trigger_after,
            trigger_before=trigger_before,
            commit_guard=commit_guard,
        )

    def update_reminder_by_keyword(
        self,
        owner_account_id: str,
        keyword: str,
        *,
        content: str | None = None,
        trigger_time: datetime | None = None,
        captured_timezone: str | None = None,
        duration_minutes: Any | None = None,
        commit_guard: CommitGuard = None,
    ) -> ReminderItemResult:
        matched = self.resolve_user_mutable_keyword(owner_account_id, keyword)
        if matched.state != "succeeded" or matched.reminder_id is None:
            return matched
        return self.update_reminder(
            owner_account_id,
            matched.reminder_id,
            content=content,
            trigger_time=trigger_time,
            captured_timezone=captured_timezone,
            duration_minutes=duration_minutes,
            commit_guard=commit_guard,
        )

    def resolve_user_mutable_keyword(
        self,
        owner_account_id: str,
        keyword: str,
    ) -> ReminderItemResult:
        return self._single_user_mutable_keyword_match(owner_account_id, keyword)

    def _mutate_reminders_by_filter(
        self,
        *,
        operation: str,
        owner_account_id: str,
        keyword: str | None,
        trigger_after: datetime | None,
        trigger_before: datetime | None,
        commit_guard: CommitGuard,
    ) -> ReminderBatchResult:
        matches = [
            reminder
            for reminder in self.filter_reminders(
                owner_account_id=owner_account_id,
                keyword=keyword,
                lifecycle="active",
                trigger_after=trigger_after,
                trigger_before=trigger_before,
            )
            if _user_mutable_reminder(reminder)
        ]
        results: list[ReminderItemResult] = []
        for reminder in matches:
            try:
                if operation == "delete":
                    results.append(
                        self.delete_reminder(
                            owner_account_id,
                            reminder.id,
                            commit_guard=commit_guard,
                        )
                    )
                elif operation == "complete":
                    results.append(
                        self.complete_reminder(
                            owner_account_id,
                            reminder.id,
                            commit_guard=commit_guard,
                        )
                    )
                else:
                    raise ReminderError("unsupported_reminder_operation")
            except ReminderError as error:
                results.append(
                    ReminderItemResult(
                        state="failed",
                        reminder_id=reminder.id,
                        reason=error.code,
                        fact=error.fact or {},
                    )
                )
        return ReminderBatchResult(owner_account_id=owner_account_id, items=results)

    def _single_user_mutable_keyword_match(
        self,
        owner_account_id: str,
        keyword: str,
    ) -> ReminderItemResult:
        if not _normalized_keyword(keyword):
            return ReminderItemResult(
                state="needs-follow-up",
                reason="keyword_required",
            )
        matches = [
            reminder
            for reminder in self.filter_reminders(
                owner_account_id=owner_account_id,
                keyword=keyword,
                lifecycle="active",
            )
            if _user_mutable_reminder(reminder)
        ]
        if len(matches) == 1:
            return ReminderItemResult(
                state="succeeded",
                reminder_id=matches[0].id,
                fact={
                    "match_count": 1,
                    "matched": _reminder_candidate_fact(matches[0]),
                },
            )
        if not matches:
            return ReminderItemResult(
                state="needs-follow-up",
                reason="no_matching_reminder",
                fact={"match_count": 0},
            )
        return ReminderItemResult(
            state="needs-follow-up",
            reason="ambiguous_reminder_reference",
            fact={
                "match_count": len(matches),
                "candidates": [
                    _reminder_candidate_fact(reminder) for reminder in matches
                ],
            },
        )

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
            if fire.fire_state == "completed":
                if delivered and fire.delivery_result != "delivered":
                    fire = replace(
                        fire,
                        delivery_result="delivered",
                        updated_at=self._now(),
                    )
                    self.repository.save_fire(fire)
                updated_fires.append(fire)
                continue
            updated = replace(
                fire,
                delivery_result="delivered" if delivered else "undelivered",
                updated_at=self._now(),
            )
            self.repository.save_fire(updated)
            if delivered:
                updated = self.complete_fire(fire_id, completed_at=self._now())
            updated_fires.append(updated)
        return updated_fires

    def reminder_fire_render_facts(
        self,
        *,
        owner_account_id: str,
        fire_ids: list[str],
        viewer_account_id: str | None = None,
    ) -> list[ReminderFireRenderFact]:
        if not fire_ids:
            raise ReminderError("reminder_fire_ids_required")
        viewer_id = viewer_account_id or owner_account_id
        facts: list[ReminderFireRenderFact] = []
        for fire_id in fire_ids:
            fire = self._require_fire(fire_id)
            reminder = self._require_reminder(fire.reminder_id)
            if reminder.owner_account_id != owner_account_id:
                raise ReminderError("reminder_fire_not_found")
            timezone_name, timezone = _zoneinfo_or_utc(reminder.captured_timezone)
            due_at = (
                fire.due_at
                if fire.due_at.tzinfo is not None
                else fire.due_at.replace(tzinfo=UTC)
            )
            participant_names: tuple[str, ...] = ()
            if reminder.shared_reminder_id and self._friend_identifiers is not None:
                participant_names = tuple(
                    self._friend_identifiers(reminder.shared_reminder_id, viewer_id)
                )
            facts.append(
                ReminderFireRenderFact(
                    fire_id=fire.id,
                    reminder_id=reminder.id,
                    title=reminder.content,
                    owner_account_id=reminder.owner_account_id,
                    viewer_account_id=viewer_id,
                    due_at=due_at.isoformat(),
                    local_due_at=due_at.astimezone(timezone).isoformat(),
                    timezone=timezone_name,
                    duration_minutes=reminder.duration_minutes,
                    kind=reminder.kind,
                    shared_reminder_id=reminder.shared_reminder_id,
                    participant_names=participant_names,
                )
            )
        return facts

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
        if fire.fire_state == "completed":
            return fire
        reminder = self._require_reminder(fire.reminder_id)
        updated_fire = replace(
            fire,
            fire_state="completed",
            handled_at=fire.handled_at or completed_at,
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

    def check_time_conflict(
        self,
        *,
        owner_account_id: str,
        trigger_time: datetime | None,
        captured_timezone: str,
        duration_minutes: Any | None,
        exclude_reminder_id: str | None = None,
        content_hash: str | None = None,
    ) -> ReminderItemResult | None:
        if trigger_time is None:
            return None
        if trigger_time.tzinfo is None:
            return None
        try:
            duration = _duration_minutes(duration_minutes)
        except ReminderError:
            return None
        proposed_start = trigger_time.astimezone(UTC)
        proposed_end = proposed_start + timedelta(minutes=duration)
        for reminder in self.repository.list_active_reminders(owner_account_id):
            if reminder.id == exclude_reminder_id:
                continue
            if not _calendar_visible_busy_reminder(reminder):
                continue
            existing_start = reminder.next_fire_at.astimezone(UTC)
            if (
                content_hash is not None
                and reminder.content_hash == content_hash
                and existing_start == proposed_start
            ):
                continue
            existing_end = existing_start + timedelta(minutes=reminder.duration_minutes)
            if _intervals_overlap(
                proposed_start, proposed_end, existing_start, existing_end
            ):
                return ReminderItemResult(
                    state="needs-follow-up",
                    reminder_id=exclude_reminder_id,
                    reason="time_conflict",
                    time_state="valid_future",
                    fact={
                        "type": "time_conflict",
                        "requested_interval": {
                            "start": proposed_start.isoformat(),
                            "end": proposed_end.isoformat(),
                            "captured_timezone": captured_timezone,
                            "duration_minutes": duration,
                        },
                        "conflict": {
                            "reminder_id": reminder.id,
                            "content": reminder.content,
                            "start": existing_start.isoformat(),
                            "end": existing_end.isoformat(),
                            "captured_timezone": reminder.captured_timezone,
                            "shared_reminder_id": reminder.shared_reminder_id,
                        },
                    },
                )
        return None

    def _execute_items(
        self,
        owner_account_id: str,
        item: ReminderBatchItem,
        commit_guard: CommitGuard,
    ) -> list[ReminderItemResult]:
        if item.operation == "detect_and_create":
            return [
                self._execute_item(owner_account_id, detected_item, commit_guard)
                for detected_item in self._detect_items(item)
            ]
        return [self._execute_item(owner_account_id, item, commit_guard)]

    def _execute_item(
        self,
        owner_account_id: str,
        item: ReminderBatchItem,
        commit_guard: CommitGuard,
    ) -> ReminderItemResult:
        if item.operation != "create":
            raise ReminderError("unsupported_reminder_operation")
        return self._create(owner_account_id, item, commit_guard)

    def _detect_items(self, item: ReminderBatchItem) -> list[ReminderBatchItem]:
        if self.detector is None or item.raw_text is None:
            raise ReminderError("detector_unavailable")
        try:
            detector_now = self._now().astimezone(ZoneInfo(item.captured_timezone))
            extract_many = getattr(self.detector, "extract_many", None)
            if callable(extract_many):
                detected_fields = extract_many(
                    item.raw_text,
                    item.captured_timezone,
                    detector_now,
                )
            else:
                detected_fields = [
                    self.detector.extract(
                        item.raw_text,
                        item.captured_timezone,
                        detector_now,
                    )
                ]
        except (RuntimeError, ZoneInfoNotFoundError) as error:
            raise ReminderError("invalid_detector_output") from error
        if not detected_fields:
            raise ReminderError("invalid_detector_output")
        detected_items: list[ReminderBatchItem] = []
        for offset, fields in enumerate(detected_fields):
            if not fields.content:
                raise ReminderError("invalid_detector_output")
            item_index = (
                item.item_index + offset if item.item_index is not None else None
            )
            detected_items.append(
                ReminderBatchItem(
                    operation="create",
                    content=fields.content,
                    trigger_time=self._detected_trigger_time(
                        fields,
                        item.captured_timezone,
                    ),
                    captured_timezone=item.captured_timezone,
                    recurrence_rule=dict(fields.recurrence_rule),
                    duration_minutes=fields.duration_minutes,
                    kind=fields.kind,
                    entry_point=item.entry_point,
                    time_state=item.time_state,
                    turn_id=item.turn_id,
                    item_index=item_index,
                )
            )
        return detected_items

    def _detected_trigger_time(
        self,
        fields: DetectedReminderFields,
        captured_timezone: str,
    ) -> datetime | None:
        if fields.trigger_time is None:
            return None
        try:
            return trigger_time_to_utc(fields.trigger_time, captured_timezone)
        except ReminderTemporalError as error:
            raise ReminderError("invalid_detector_output") from error

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
        try:
            temporal = normalize_create_temporal(
                trigger_time=item.trigger_time,
                recurrence_rule=item.recurrence_rule,
                duration_minutes=item.duration_minutes,
                kind=item.kind,
            )
        except ReminderTemporalError as error:
            return ReminderItemResult(
                state=_temporal_error_state(error.code),
                reason=error.code,
                time_state=time_state,
            )
        if _candidate_calendar_visible(temporal.kind, temporal.trigger_time):
            conflict = self.check_time_conflict(
                owner_account_id=owner_account_id,
                trigger_time=temporal.trigger_time,
                captured_timezone=item.captured_timezone,
                duration_minutes=temporal.duration_minutes,
                content_hash=_content_hash(item.content),
            )
            if conflict is not None:
                return conflict
        now = self._now()
        reminder = Reminder(
            id=self._id_factory("reminder"),
            owner_account_id=owner_account_id,
            content=item.content,
            content_hash=_content_hash(item.content),
            kind=temporal.kind,
            next_fire_at=temporal.trigger_time,
            recurrence_rule=temporal.recurrence_rule,
            captured_timezone=item.captured_timezone,
            duration_minutes=temporal.duration_minutes,
            lifecycle="active",
            hidden_from_calendar=temporal.kind == "proactive",
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
                "duration_minutes": reminder.duration_minutes,
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


def _normalized_keyword(keyword: str | None) -> str:
    if keyword is None:
        return ""
    return keyword.strip().casefold()


def _keyword_matches_content(keyword_value: str, content: str) -> bool:
    # Bidirectional containment: a natural-language reference matches a reminder
    # when one string contains the other. This handles both "user names part of
    # the reminder" (keyword in content, e.g. "跑步" -> "跑步去公园") and "user names
    # the reminder plus a generic word" (content in keyword, e.g. "跑步提醒" -> "跑步").
    # The single-match-for-mutation guard keeps over-matching safe (ambiguous ->
    # clarification, never a wrong mutation).
    content_value = content.casefold()
    return keyword_value in content_value or content_value in keyword_value


def _user_mutable_reminder(reminder: Reminder) -> bool:
    return reminder.kind not in {"proactive", "shared_projection"}


def _reminder_in_trigger_range(
    reminder: Reminder,
    *,
    trigger_after: datetime | None,
    trigger_before: datetime | None,
) -> Reminder | None:
    if trigger_after is None and trigger_before is None:
        return reminder
    next_fire_at = _aware_utc_datetime(reminder.next_fire_at)
    if next_fire_at is None:
        return None
    start = _aware_utc_datetime(trigger_after)
    end = _aware_utc_datetime(trigger_before)
    occurrence = next_fire_at
    if reminder.kind == "recurring" and reminder.recurrence_rule:
        occurrence = _first_recurring_occurrence_at_or_after(
            reminder,
            next_fire_at,
            start,
        )
        if occurrence is None:
            return None
    if start is not None and occurrence < start:
        return None
    if end is not None and occurrence >= end:
        return None
    if occurrence != reminder.next_fire_at:
        return replace(reminder, next_fire_at=occurrence)
    return reminder


def _first_recurring_occurrence_at_or_after(
    reminder: Reminder,
    next_fire_at: datetime,
    start: datetime | None,
) -> datetime | None:
    if start is None:
        return next_fire_at
    occurrence = next_fire_at
    for _ in range(4096):
        if occurrence >= start:
            return occurrence
        occurrence = next_occurrence_after(
            reminder.recurrence_rule,
            occurrence,
            reminder.captured_timezone,
        )
    return None


def _aware_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _trigger_range_sort_key(reminder: Reminder) -> tuple[datetime, str, str]:
    return (
        _aware_utc_datetime(reminder.next_fire_at) or datetime.max.replace(tzinfo=UTC),
        reminder.content,
        reminder.id,
    )


def _zoneinfo_or_utc(timezone_name: str) -> tuple[str, ZoneInfo]:
    try:
        return timezone_name, ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return "UTC", ZoneInfo("UTC")


def _reminder_candidate_fact(reminder: Reminder) -> dict[str, Any]:
    return {
        "reminder_id": reminder.id,
        "content": reminder.content,
        "kind": reminder.kind,
        "next_fire_at": (
            reminder.next_fire_at.isoformat()
            if reminder.next_fire_at is not None
            else None
        ),
    }


def _safe_write_error_reason(error: ValueError) -> str:
    reason = str(error)
    if reason in {
        "duplicate_reminder_outbox_id",
        "duplicate_reminder_outbox_idempotency",
    }:
        return reason
    return "reminder_write_failed"


def _calendar_visible_busy_reminder(reminder: Reminder) -> bool:
    return (
        reminder.lifecycle == "active"
        and not reminder.hidden_from_calendar
        and reminder.kind != "no_trigger_time"
        and reminder.next_fire_at is not None
    )


def _candidate_calendar_visible(
    kind: ReminderKind,
    trigger_time: datetime | None,
) -> bool:
    return kind not in {"no_trigger_time", "proactive"} and trigger_time is not None


def _intervals_overlap(
    left_start: datetime,
    left_end: datetime,
    right_start: datetime,
    right_end: datetime,
) -> bool:
    return left_start < right_end and right_start < left_end


def _duration_minutes(value: Any) -> int:
    try:
        return positive_duration_minutes(value)
    except ReminderTemporalError as error:
        raise ReminderError(error.code) from error


def _temporal_error_state(code: str) -> BatchItemState:
    if code in {"missing_recurring_trigger_time", "missing_trigger_time"}:
        return "needs-follow-up"
    return "failed"
