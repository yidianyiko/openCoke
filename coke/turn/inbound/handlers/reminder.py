from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.domains.reminder.models import (
    DetectedReminderFields,
    Reminder,
    ReminderBatchItem,
    ReminderBatchResult,
    ReminderDetectorPort,
    ReminderItemResult,
)
from coke.domains.reminder.service import ReminderService
from coke.turn.inbound.contracts import ActionOutcome, CompiledAction
from coke.turn.inbound.date_windows import resolve_date_phrase_window


class ReminderActionHandler:
    def __init__(
        self,
        reminder_service: ReminderService,
        detector: ReminderDetectorPort,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.reminder_service = reminder_service
        self.detector = detector
        self._now = now or (lambda: datetime.now(UTC))

    def execute(
        self,
        compiled_action: CompiledAction,
        guard: Any,
        *,
        action_index: int,
        turn_id: str,
    ) -> ActionOutcome:
        action = compiled_action.action
        if action is None:
            return ActionOutcome(
                category="not_possible",
                status="invalid_compiled_action",
            )
        params = dict(action.params)
        owner = _owner_account_id(params)
        if owner is None:
            return ActionOutcome(
                category="needs_input",
                status="missing_owner_account_id",
                data={"field": "owner_account_id"},
            )

        if action.operation in {"list", "filter"}:
            return self._list(params, owner)
        if action.operation == "create":
            return self._create(params, owner, guard, action_index, turn_id)
        if action.operation == "batch_create":
            return self._batch_create(params, owner, guard, action_index, turn_id)
        if action.operation in {"update", "delete", "complete"}:
            return self._keyword_mutation(action.operation, params, owner, guard)
        return ActionOutcome(
            category="not_possible",
            status="unsupported_operation",
            data={"domain": "reminder", "operation": action.operation},
        )

    def _list(self, params: Mapping[str, Any], owner: str) -> ActionOutcome:
        trigger_after = _optional_datetime(params.get("trigger_after"))
        trigger_before = _optional_datetime(params.get("trigger_before"))
        date_window = resolve_date_phrase_window(
            params.get("date_phrase"),
            timezone_name=_timezone(params),
            now=self._now,
        )
        if date_window is not None:
            trigger_after = date_window.trigger_after
            trigger_before = date_window.trigger_before
        reminders = self.reminder_service.filter_reminders(
            owner_account_id=owner,
            keyword=_optional_str(params.get("keyword")),
            lifecycle=_lifecycle_filter(params),
            kind=_kind_filter(params),
            trigger_after=trigger_after,
            trigger_before=trigger_before,
        )
        facts = [_reminder_fact(reminder) for reminder in reminders]
        return ActionOutcome(
            category="done",
            status="listed",
            data={"reminders": facts, "count": len(facts)},
        )

    def _create(
        self,
        params: Mapping[str, Any],
        owner: str,
        guard: Any,
        action_index: int,
        turn_id: str,
    ) -> ActionOutcome:
        detected = self._extract_create_fields(
            params,
            source_text=_optional_str(params.get("_current_input_text")),
        )
        if detected.trigger_time is None:
            return ActionOutcome(
                category="needs_input",
                status="missing_trigger_time",
                data={"field": "trigger_time"},
            )
        item = self._create_item_from_detected(
            params,
            detected,
            item_index=action_index + 1,
            turn_id=turn_id,
        )
        if item.trigger_time is not None and item.duration_minutes is None:
            return _missing_duration_outcome()
        guard.guard_state_change()
        batch = self.reminder_service.execute_batch(
            owner_account_id=owner,
            items=[item],
            commit_guard=guard.guard_state_change,
        )
        return _batch_outcome_from_real_results(owner, batch)

    def _batch_create(
        self,
        params: Mapping[str, Any],
        owner: str,
        guard: Any,
        action_index: int,
        turn_id: str,
    ) -> ActionOutcome:
        raw_items = params.get("items")
        if not isinstance(raw_items, list):
            return ActionOutcome(
                category="needs_input",
                status="missing_items",
                data={"field": "items"},
            )

        items: list[ReminderBatchItem] = []
        source_text = _optional_str(params.get("_current_input_text"))
        single_item_source_text = source_text if len(raw_items) == 1 else None
        for index, raw_item in enumerate(raw_items, start=1):
            if not isinstance(raw_item, Mapping):
                return ActionOutcome(
                    category="needs_input",
                    status="invalid_item",
                    data={"item_index": index},
                )
            item = self._batch_item_from_params(
                raw_item,
                item_index=action_index + index,
                turn_id=turn_id,
                source_text=single_item_source_text,
            )
            if item.trigger_time is None or item.time_state == "invalid":
                return ActionOutcome(
                    category="needs_input",
                    status="missing_trigger_time",
                    data={"field": "trigger_time", "item_index": index},
                )
            if item.duration_minutes is None:
                return _missing_duration_outcome(item_index=index)
            items.append(item)

        if not items:
            return ActionOutcome(
                category="not_possible",
                status="empty_batch",
                data={"owner_account_id": owner, "items": []},
            )

        guard.guard_state_change()
        batch = self.reminder_service.execute_batch(
            owner_account_id=owner,
            items=items,
            commit_guard=guard.guard_state_change,
        )
        return _batch_outcome_from_real_results(owner, batch)

    def _keyword_mutation(
        self,
        operation: str,
        params: Mapping[str, Any],
        owner: str,
        guard: Any,
    ) -> ActionOutcome:
        match = _optional_str(params.get("match"))
        if operation == "update":
            trigger_time = None
            if _has_time_phrase(params):
                detected = self._extract_create_fields(params)
                if detected.trigger_time is None:
                    return ActionOutcome(
                        category="needs_input",
                        status="missing_trigger_time",
                        data={"field": "trigger_time"},
                    )
                trigger_time = _trigger_time(
                    detected.trigger_time,
                    _timezone(params),
                )
            guard.guard_state_change()
            result = self.reminder_service.update_reminder_by_keyword(
                owner_account_id=owner,
                keyword=match,
                content=_optional_str(params.get("content")),
                trigger_time=trigger_time,
                captured_timezone=params.get("captured_timezone"),
                duration_minutes=params.get("duration_minutes"),
                commit_guard=guard.guard_state_change,
            )
            return _keyword_mutation_outcome(result, status="updated")

        if operation == "delete":
            guard.guard_state_change()
            result = self.reminder_service.delete_reminder_by_keyword(
                owner_account_id=owner,
                keyword=match,
                commit_guard=guard.guard_state_change,
            )
            return _keyword_mutation_outcome(result, status="cancelled")

        guard.guard_state_change()
        result = self.reminder_service.complete_reminder_by_keyword(
            owner_account_id=owner,
            keyword=match,
            commit_guard=guard.guard_state_change,
        )
        return _keyword_mutation_outcome(result, status="completed")

    def _extract_create_fields(
        self,
        params: Mapping[str, Any],
        *,
        source_text: str | None = None,
    ) -> DetectedReminderFields:
        timezone = _timezone(params)
        return self.detector.extract(
            _detector_text(params, source_text=source_text),
            timezone,
            self._now(),
        )

    def _create_item_from_detected(
        self,
        params: Mapping[str, Any],
        detected: DetectedReminderFields,
        *,
        item_index: int,
        turn_id: str,
    ) -> ReminderBatchItem:
        timezone = _timezone(params)
        trigger_time = _trigger_time(detected.trigger_time, timezone)
        content = detected.content or _optional_str(params.get("content"))
        return ReminderBatchItem(
            operation="create",
            turn_id=turn_id,
            item_index=item_index,
            content=content,
            trigger_time=trigger_time,
            captured_timezone=timezone,
            recurrence_rule=dict(detected.recurrence_rule),
            duration_minutes=detected.duration_minutes,
            kind=detected.kind,
            entry_point="turn_pipeline",
        )

    def _batch_item_from_params(
        self,
        params: Mapping[str, Any],
        *,
        item_index: int,
        turn_id: str,
        source_text: str | None = None,
    ) -> ReminderBatchItem:
        timezone = _timezone(params)
        trigger_time = _optional_datetime(params.get("trigger_time"))
        content = _optional_str(params.get("content"))
        recurrence_rule = dict(params.get("recurrence_rule") or {})
        duration_minutes = params.get("duration_minutes")
        kind = params.get("kind")
        if _has_time_phrase(params):
            detected = self._extract_create_fields(params, source_text=source_text)
            if detected.trigger_time is None:
                return ReminderBatchItem(
                    operation="create",
                    content=content,
                    captured_timezone=timezone,
                    time_state="invalid",
                    turn_id=turn_id,
                    item_index=item_index,
                )
            trigger_time = _trigger_time(detected.trigger_time, timezone)
            content = detected.content or content
            recurrence_rule = dict(detected.recurrence_rule)
            duration_minutes = detected.duration_minutes
            kind = detected.kind
        return ReminderBatchItem(
            operation="create",
            content=content,
            trigger_time=trigger_time,
            captured_timezone=timezone,
            recurrence_rule=recurrence_rule,
            duration_minutes=duration_minutes,
            kind=kind,
            entry_point="turn_pipeline",
            turn_id=turn_id,
            item_index=item_index,
        )


def _batch_outcome_from_real_results(
    owner: str,
    batch: ReminderBatchResult,
) -> ActionOutcome:
    data = {
        "owner_account_id": owner,
        "items": [_item_data(item) for item in batch.items],
    }
    first_problem = next(
        (item for item in batch.items if item.state != "succeeded"),
        None,
    )
    if first_problem is None:
        return ActionOutcome(category="done", status="created", data=data)
    category, status = _category_status_for_item(first_problem)
    return ActionOutcome(category=category, status=status, data=data)


def _keyword_mutation_outcome(
    result: ReminderItemResult,
    *,
    status: str,
) -> ActionOutcome:
    if result.state == "succeeded":
        if result.reminder_id is None:
            return ActionOutcome(
                category="not_possible",
                status="missing_resolved_reminder_id",
                data=_item_data(result),
            )
        return ActionOutcome(category="done", status=status, data=_item_data(result))
    return _blocked_keyword_outcome(result)


def _blocked_keyword_outcome(result: ReminderItemResult) -> ActionOutcome:
    if result.reason == "ambiguous_reminder_reference":
        return ActionOutcome(
            category="needs_choice",
            status="ambiguous",
            data={
                "candidates": list(result.fact.get("candidates") or []),
                "reason": result.reason,
            },
        )
    if result.reason == "no_matching_reminder":
        return ActionOutcome(
            category="not_possible",
            status="not_found",
            data={"reason": result.reason, **dict(result.fact)},
        )
    if result.reason == "keyword_required":
        return ActionOutcome(
            category="needs_input",
            status="missing_match",
            data={"field": "match"},
        )
    category, status = _category_status_for_item(result)
    return ActionOutcome(category=category, status=status, data=_item_data(result))


def _category_status_for_item(result: ReminderItemResult) -> tuple[str, str]:
    if (
        result.reason == "needs_past_time_confirmation"
        or result.time_state == "needs_past_time_confirmation"
    ):
        return "needs_confirmation", "needs_past_time_confirmation"
    if result.state == "needs-follow-up":
        return "needs_input", result.reason or "needs_follow_up"
    return "not_possible", result.reason or "reminder_action_failed"


def _missing_duration_outcome(*, item_index: int | None = None) -> ActionOutcome:
    data: dict[str, Any] = {"field": "duration_minutes"}
    if item_index is not None:
        data["item_index"] = item_index
    return ActionOutcome(
        category="not_possible",
        status="missing_duration_minutes",
        data=data,
    )


def _item_data(item: ReminderItemResult) -> dict[str, Any]:
    return {
        "state": item.state,
        "reminder_id": item.reminder_id,
        "reason": item.reason,
        "time_state": item.time_state,
        "fact": item.fact,
    }


def _reminder_fact(reminder: Reminder) -> dict[str, Any]:
    return {
        "reminder_id": reminder.id,
        "content": reminder.content,
        "kind": reminder.kind,
        "next_fire_at": (
            reminder.next_fire_at.isoformat()
            if reminder.next_fire_at is not None
            else None
        ),
        "captured_timezone": reminder.captured_timezone,
        "duration_minutes": reminder.duration_minutes,
        "lifecycle": reminder.lifecycle,
        "hidden_from_calendar": reminder.hidden_from_calendar,
        "shared_reminder_id": reminder.shared_reminder_id,
    }


def _trigger_time(value: datetime | None, captured_timezone: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(UTC)
    try:
        return value.replace(tzinfo=ZoneInfo(captured_timezone)).astimezone(UTC)
    except ZoneInfoNotFoundError:
        return value.replace(tzinfo=UTC)


def _optional_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _detector_text(
    params: Mapping[str, Any],
    *,
    source_text: str | None = None,
) -> str:
    raw_text = _optional_str(params.get("raw_text") or params.get("text"))
    if raw_text is not None:
        return raw_text
    if source_text is not None:
        return source_text
    parts = [
        _optional_str(params.get("content")),
        _optional_str(params.get("time_phrase")),
    ]
    return " ".join(part for part in parts if part)


def _has_time_phrase(params: Mapping[str, Any]) -> bool:
    return bool(
        _optional_str(params.get("time_phrase"))
        or _optional_str(params.get("raw_text"))
        or _optional_str(params.get("text"))
    )


def _owner_account_id(params: Mapping[str, Any]) -> str | None:
    return _optional_str(params.get("owner_account_id") or params.get("account_id"))


def _timezone(params: Mapping[str, Any]) -> str:
    return str(
        params.get("captured_timezone") or params.get("display_timezone") or "UTC"
    )


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _lifecycle_filter(params: Mapping[str, Any]) -> str | None:
    value = params.get("lifecycle", params.get("status", "active"))
    if value is None or value == "all":
        return None
    return str(value)


def _kind_filter(params: Mapping[str, Any]) -> str | None:
    value = params.get("kind", params.get("reminder_type"))
    if value is None or value == "all":
        return None
    return str(value)
