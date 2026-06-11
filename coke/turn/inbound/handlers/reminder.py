from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.domains.reminder.models import (
    DetectedReminderFields,
    Reminder,
    ReminderBatchItem,
    ReminderDetectorPort,
    ReminderItemResult,
)
from coke.domains.reminder.service import ReminderService
from coke.turn.inbound.contracts import ActionOutcome, CompiledAction
from coke.turn.inbound.staging import json_safe


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

    def resolve_and_stage(
        self,
        compiled_action: CompiledAction,
        guard: Any,
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
            return self._create(params, owner, guard)
        if action.operation == "batch_create":
            return self._batch_create(params, owner, guard)
        if action.operation in {"update", "delete", "complete"}:
            return self._keyword_mutation(action.operation, params, owner, guard)
        return ActionOutcome(
            category="not_possible",
            status="unsupported_operation",
            data={"domain": "reminder", "operation": action.operation},
        )

    def _list(self, params: Mapping[str, Any], owner: str) -> ActionOutcome:
        reminders = self.reminder_service.filter_reminders(
            owner_account_id=owner,
            keyword=_optional_str(params.get("keyword")),
            lifecycle=_lifecycle_filter(params),
            kind=_kind_filter(params),
            trigger_after=_optional_datetime(params.get("trigger_after")),
            trigger_before=_optional_datetime(params.get("trigger_before")),
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
    ) -> ActionOutcome:
        detected = self._extract_create_fields(params)
        if detected.trigger_time is None:
            return ActionOutcome(
                category="needs_input",
                status="missing_trigger_time",
                data={"field": "trigger_time"},
            )
        _item, payload = self._create_item_from_detected(
            params,
            detected,
            item_index=1,
            guard=guard,
        )
        conflict = self._check_time_conflict(owner, _item, exclude_reminder_id=None)
        if conflict is not None:
            return _blocked_keyword_outcome(conflict)
        staged_id = _stage_execute_batch(guard, owner, [_staged_create_item(payload)])
        return ActionOutcome(
            category="done",
            status="created",
            data=_optimistic_batch_data(owner, [payload]),
            staged_command_id=staged_id,
        )

    def _batch_create(
        self,
        params: Mapping[str, Any],
        owner: str,
        guard: Any,
    ) -> ActionOutcome:
        raw_items = params.get("items")
        if not isinstance(raw_items, list):
            return ActionOutcome(
                category="needs_input",
                status="missing_items",
                data={"field": "items"},
            )

        items: list[ReminderBatchItem] = []
        payloads: list[dict[str, Any]] = []
        for index, raw_item in enumerate(raw_items, start=1):
            if not isinstance(raw_item, Mapping):
                return ActionOutcome(
                    category="needs_input",
                    status="invalid_item",
                    data={"item_index": index},
                )
            item, payload = self._batch_item_from_params(raw_item, index, guard)
            if item.trigger_time is None or item.time_state == "invalid":
                return ActionOutcome(
                    category="needs_input",
                    status="missing_trigger_time",
                    data={"field": "trigger_time", "item_index": index},
                )
            conflict = self._check_time_conflict(owner, item, exclude_reminder_id=None)
            if conflict is not None:
                return _blocked_keyword_outcome(conflict)
            items.append(item)
            payloads.append(payload)

        if not items:
            return ActionOutcome(
                category="not_possible",
                status="empty_batch",
                data={"owner_account_id": owner, "items": []},
            )

        staged_id = _stage_execute_batch(guard, owner, payloads)
        return ActionOutcome(
            category="done",
            status="created",
            data=_optimistic_batch_data(owner, payloads),
            staged_command_id=staged_id,
        )

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
            result = self.reminder_service.resolve_user_mutable_keyword(
                owner_account_id=owner,
                keyword=match,
            )
            if (
                result.state == "succeeded"
                and result.reminder_id is not None
                and (
                    trigger_time is not None
                    or params.get("duration_minutes") is not None
                )
            ):
                conflict = self._check_time_conflict(
                    owner,
                    ReminderBatchItem(
                        operation="create",
                        trigger_time=trigger_time,
                        captured_timezone=_timezone(params),
                        duration_minutes=params.get("duration_minutes"),
                    ),
                    exclude_reminder_id=result.reminder_id,
                )
                if conflict is not None:
                    return _blocked_keyword_outcome(
                        ReminderItemResult(
                            state=conflict.state,
                            reminder_id=result.reminder_id,
                            reason=conflict.reason,
                            time_state=conflict.time_state,
                            fact=conflict.fact,
                        )
                    )
            return self._keyword_mutation_outcome(
                result,
                guard,
                status="updated",
                staged_operation="update_reminder",
                command_payload={
                    "operation": "update_reminder",
                    "owner_account_id": owner,
                    "content": params.get("content"),
                    "trigger_time": trigger_time,
                    "captured_timezone": params.get("captured_timezone"),
                    "duration_minutes": params.get("duration_minutes"),
                },
            )

        if operation == "delete":
            result = self.reminder_service.resolve_user_mutable_keyword(
                owner_account_id=owner,
                keyword=match,
            )
            return self._keyword_mutation_outcome(
                result,
                guard,
                status="cancelled",
                staged_operation="delete_reminder",
                command_payload={
                    "operation": "delete_reminder",
                    "owner_account_id": owner,
                },
            )

        result = self.reminder_service.resolve_user_mutable_keyword(
            owner_account_id=owner,
            keyword=match,
        )
        return self._keyword_mutation_outcome(
            result,
            guard,
            status="completed",
            staged_operation="complete_reminder",
            command_payload={
                "operation": "complete_reminder",
                "owner_account_id": owner,
            },
        )

    def _check_time_conflict(
        self,
        owner: str,
        item: ReminderBatchItem,
        *,
        exclude_reminder_id: str | None,
    ) -> ReminderItemResult | None:
        check = getattr(self.reminder_service, "check_time_conflict", None)
        if not callable(check):
            return None
        duration_minutes = (
            item.duration_minutes if item.duration_minutes is not None else 15
        )
        return check(
            owner_account_id=owner,
            trigger_time=item.trigger_time,
            captured_timezone=item.captured_timezone,
            duration_minutes=duration_minutes,
            exclude_reminder_id=exclude_reminder_id,
        )

    def _keyword_mutation_outcome(
        self,
        result: ReminderItemResult,
        guard: Any,
        *,
        status: str,
        staged_operation: str,
        command_payload: Mapping[str, Any],
    ) -> ActionOutcome:
        if result.state == "succeeded":
            if result.reminder_id is None:
                return ActionOutcome(
                    category="not_possible",
                    status="missing_resolved_reminder_id",
                    data=_item_data(result),
                )
            payload = {
                key: value
                for key, value in {
                    **dict(command_payload),
                    "reminder_id": result.reminder_id,
                }.items()
                if value is not None
            }
            staged_id = _stage_command(
                guard,
                operation=staged_operation,
                command_payload=payload,
                preview_facts={
                    "status": "staged",
                    "operation": staged_operation,
                    "owner_account_id": payload.get("owner_account_id"),
                },
            )
            return ActionOutcome(
                category="done",
                status=status,
                data=_item_data(result),
                staged_command_id=staged_id,
            )
        return _blocked_keyword_outcome(result)

    def _extract_create_fields(
        self,
        params: Mapping[str, Any],
    ) -> DetectedReminderFields:
        timezone = _timezone(params)
        return self.detector.extract(_detector_text(params), timezone, self._now())

    def _create_item_from_detected(
        self,
        params: Mapping[str, Any],
        detected: DetectedReminderFields,
        *,
        item_index: int,
        guard: Any,
    ) -> tuple[ReminderBatchItem, dict[str, Any]]:
        timezone = _timezone(params)
        trigger_time = _trigger_time(detected.trigger_time, timezone)
        content = detected.content or _optional_str(params.get("content"))
        payload = {
            "content": content,
            "trigger_time": trigger_time,
            "captured_timezone": timezone,
            "recurrence_rule": dict(detected.recurrence_rule),
            "duration_minutes": detected.duration_minutes,
            "kind": detected.kind,
            "entry_point": "turn_pipeline",
        }
        item = ReminderBatchItem(
            operation="create",
            turn_id=_turn_id(guard),
            item_index=item_index,
            **payload,
        )
        return item, {key: value for key, value in payload.items() if value is not None}

    def _batch_item_from_params(
        self,
        params: Mapping[str, Any],
        item_index: int,
        guard: Any,
    ) -> tuple[ReminderBatchItem, dict[str, Any]]:
        timezone = _timezone(params)
        trigger_time = _optional_datetime(params.get("trigger_time"))
        if trigger_time is None and _has_time_phrase(params):
            detected = self._extract_create_fields(params)
            if detected.trigger_time is None:
                return (
                    ReminderBatchItem(
                        operation="create",
                        content=_optional_str(params.get("content")),
                        captured_timezone=timezone,
                        time_state="invalid",
                        turn_id=_turn_id(guard),
                        item_index=item_index,
                    ),
                    {
                        "operation": "create",
                        "content": _optional_str(params.get("content")),
                        "captured_timezone": timezone,
                        "time_state": "invalid",
                    },
                )
            trigger_time = _trigger_time(detected.trigger_time, timezone)
        payload = {
            "operation": "create",
            "content": _optional_str(params.get("content")),
            "trigger_time": trigger_time,
            "captured_timezone": timezone,
            "recurrence_rule": dict(params.get("recurrence_rule") or {}),
            "duration_minutes": params.get("duration_minutes"),
            "kind": params.get("kind"),
            "entry_point": "turn_pipeline",
        }
        item = ReminderBatchItem(
            turn_id=_turn_id(guard),
            item_index=item_index,
            **payload,
        )
        return item, {key: value for key, value in payload.items() if value is not None}


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
    if result.state == "needs-follow-up":
        return ActionOutcome(
            category="needs_input",
            status=result.reason or "needs_follow_up",
            data=_item_data(result),
        )
    return ActionOutcome(
        category="not_possible",
        status=result.reason or "reminder_action_failed",
        data=_item_data(result),
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


def _stage_execute_batch(
    guard: Any,
    owner: str,
    items: list[dict[str, Any]],
) -> str | None:
    # Duplicate detection is intentionally deferred to the close materializer;
    # execute-time handlers only build and stage the command.
    return _stage_command(
        guard,
        operation="execute_batch",
        command_payload={
            "operation": "execute_batch",
            "owner_account_id": owner,
            "items": items,
        },
        preview_facts={
            "status": "staged",
            "operation": "execute_batch",
            "owner_account_id": owner,
        },
    )


def _staged_create_item(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"operation": "create", **dict(payload)}


def _optimistic_batch_data(
    owner: str,
    payloads: list[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "owner_account_id": owner,
        "items": [
            {
                "state": "succeeded",
                "reminder_id": None,
                "reason": None,
                "time_state": None,
                "fact": json_safe(
                    {key: value for key, value in payload.items() if key != "operation"}
                ),
            }
            for payload in payloads
        ],
    }


def _stage_command(
    guard: Any,
    *,
    operation: str,
    command_payload: Mapping[str, Any],
    preview_facts: Mapping[str, Any],
    item_index: int = 1,
) -> str | None:
    stage_command = getattr(guard, "stage_command", None)
    if not callable(stage_command):
        return None
    staged = stage_command(
        domain="reminder",
        operation=operation,
        command_payload=json_safe(dict(command_payload)),
        preview_facts=json_safe(dict(preview_facts)),
        item_index=item_index,
    )
    return getattr(staged, "id", None)


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
            # Resolving natural date-range list filters (e.g. "周五") to real
            # ranges is a separate quality follow-up; this only avoids a crash.
            return None
    return None


def _detector_text(params: Mapping[str, Any]) -> str:
    raw_text = _optional_str(params.get("raw_text") or params.get("text"))
    if raw_text is not None:
        return raw_text
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


def _turn_id(guard: Any) -> str | None:
    value = getattr(guard, "turn_id", None)
    return value if isinstance(value, str) else None
