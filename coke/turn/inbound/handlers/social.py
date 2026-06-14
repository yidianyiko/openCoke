from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from coke.domains.social_scheduling.models import (
    FriendResolutionResult,
    SharedReminder,
    SocialSchedulingError,
)
from coke.domains.social_scheduling.service import SocialSchedulingService
from coke.turn.inbound.contracts import ActionOutcome, CompiledAction
from coke.turn.inbound.date_windows import resolve_date_phrase_window

CommitGuard = Callable[[], None] | None
_DEFAULT_AVAILABILITY_WINDOW_DAYS = 7


class SocialSchedulingActionHandler:
    def __init__(
        self,
        social_scheduling_service: SocialSchedulingService,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.social_scheduling_service = social_scheduling_service
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
        if action.operation == "create_shared_reminder":
            return self._create_shared_reminder(params, guard)
        if action.operation == "update_shared_reminder":
            return self._update_shared_reminder(params, guard)
        if action.operation == "cancel_shared_reminder":
            return self._cancel_shared_reminder(params, guard)
        if action.operation == "list_shared":
            return self._list_shared(params)
        if action.operation == "availability_query":
            return self._availability_query(params)
        return ActionOutcome(
            category="not_possible",
            status="unsupported_operation",
            data={"domain": "social_scheduling", "operation": action.operation},
        )

    def _create_shared_reminder(
        self,
        params: Mapping[str, Any],
        guard: Any,
    ) -> ActionOutcome:
        creator = _account_id(params, "creator_account_id")
        if creator is None:
            return _missing_input("creator_account_id")
        resolved = self._resolve_participants(creator, params)
        if isinstance(resolved, ActionOutcome):
            return resolved
        captured_timezone = _timezone(params)
        duration_minutes = _optional_int(params.get("duration_minutes"))
        local_trigger_at = _optional_datetime(
            params.get("local_trigger_at") or params.get("trigger_time")
        )
        try:
            if _should_detect_shared_reminder(params):
                result = (
                    self.social_scheduling_service.detect_and_create_shared_reminder(
                        creator_account_id=creator,
                        receiver_account_ids=resolved,
                        raw_text=_shared_reminder_detector_text(params),
                        title=_optional_str(
                            params.get("title") or params.get("content")
                        ),
                        captured_timezone=captured_timezone,
                        duration_minutes=duration_minutes,
                        commit_guard=_commit_guard(guard),
                    )
                )
                requested_interval = None
            else:
                result = self.social_scheduling_service.create_shared_reminder(
                    creator_account_id=creator,
                    receiver_account_ids=resolved,
                    title=_optional_str(params.get("title") or params.get("content")),
                    local_trigger_at=local_trigger_at,
                    captured_timezone=captured_timezone,
                    duration_minutes=duration_minutes,
                    commit_guard=_commit_guard(guard),
                )
                requested_interval = _requested_interval(
                    local_trigger_at,
                    captured_timezone=captured_timezone,
                    duration_minutes=duration_minutes,
                )
        except (SocialSchedulingError, ValueError) as error:
            return _social_error_outcome(error)

        return _shared_reminder_create_outcome(
            result,
            requested_interval=requested_interval,
        )

    def _cancel_shared_reminder(
        self,
        params: Mapping[str, Any],
        guard: Any,
    ) -> ActionOutcome:
        account_id = _account_id(params)
        if account_id is None:
            return _missing_input("account_id")
        resolved = self._resolve_participants(account_id, params)
        if isinstance(resolved, ActionOutcome):
            return resolved
        target = self._resolve_shared_reminder(account_id, resolved, params)
        if isinstance(target, ActionOutcome):
            return target
        shared_reminder_id = target.id
        try:
            result = self.social_scheduling_service.cancel_shared_reminder(
                account_id=account_id,
                shared_reminder_id=shared_reminder_id,
                commit_guard=_commit_guard(guard),
            )
        except (SocialSchedulingError, ValueError) as error:
            return _social_error_outcome(error)

        data = {
            "status": result.status,
            "shared_reminder_id": result.shared_reminder.id,
            "shared_reminder": _shared_reminder_fact(result.shared_reminder),
        }
        if result.status != "cancelled":
            return ActionOutcome(
                category="not_possible",
                status=result.status,
                data=data,
            )
        return ActionOutcome(
            category="done",
            status="cancelled",
            data=data,
        )

    def _update_shared_reminder(
        self,
        params: Mapping[str, Any],
        guard: Any,
    ) -> ActionOutcome:
        account_id = _account_id(params)
        if account_id is None:
            return _missing_input("account_id")
        shared_reminder_id = _optional_str(params.get("shared_reminder_id"))
        target: SharedReminder | None = None
        if shared_reminder_id is None:
            resolved = self._resolve_participants(account_id, params)
            if isinstance(resolved, ActionOutcome):
                return resolved
            target = self._resolve_shared_reminder(account_id, resolved, params)
            if isinstance(target, ActionOutcome):
                return target
            shared_reminder_id = target.id

        captured_timezone = _timezone(params)
        local_trigger_at = _optional_datetime(
            params.get("local_trigger_at") or params.get("trigger_time")
        )
        if local_trigger_at is None and _optional_str(params.get("time_phrase")):
            local_trigger_at = _detect_update_trigger_time(
                self.social_scheduling_service,
                params,
                captured_timezone=captured_timezone,
                now=self._now,
            )
            if local_trigger_at is None:
                return _missing_input("time")
        try:
            result = self.social_scheduling_service.update_shared_reminder(
                account_id=account_id,
                shared_reminder_id=shared_reminder_id,
                local_trigger_at=local_trigger_at,
                captured_timezone=captured_timezone,
                duration_minutes=_optional_int(params.get("duration_minutes")),
                commit_guard=_commit_guard(guard),
            )
        except (SocialSchedulingError, ValueError) as error:
            return _social_error_outcome(error)

        duration_minutes = _optional_int(params.get("duration_minutes"))
        if duration_minutes is None and target is not None:
            duration_minutes = target.duration_minutes
        outcome = _shared_reminder_update_outcome(
            result,
            requested_interval=_requested_interval(
                local_trigger_at,
                captured_timezone=captured_timezone,
                duration_minutes=duration_minutes,
            ),
        )
        return outcome

    def _list_shared(self, params: Mapping[str, Any]) -> ActionOutcome:
        account_id = _account_id(params)
        if account_id is None:
            return _missing_input("account_id")
        resolved: list[str] | None = None
        if _has_participant_reference(params):
            participant_result = self._resolve_participants(account_id, params)
            if isinstance(participant_result, ActionOutcome):
                return participant_result
            resolved = participant_result
        reminders = self.social_scheduling_service.list_shared_reminders(account_id)
        if resolved is not None:
            resolved_set = set(resolved)
            reminders = [
                reminder
                for reminder in reminders
                if resolved_set.intersection(reminder.participant_account_ids)
            ]
        facts = [_shared_reminder_fact(reminder) for reminder in reminders]
        return ActionOutcome(
            category="done",
            status="listed",
            data={"shared_reminders": facts, "count": len(facts)},
        )

    def _availability_query(self, params: Mapping[str, Any]) -> ActionOutcome:
        account_id = _account_id(params, "requester_account_id")
        if account_id is None:
            return _missing_input("account_id")
        resolved = self._resolve_participants(account_id, params)
        if isinstance(resolved, ActionOutcome):
            return resolved
        requester_timezone = str(params.get("requester_timezone") or _timezone(params))
        availability_window = _availability_window(
            params,
            requester_timezone=requester_timezone,
            now=self._now,
        )
        if availability_window is None:
            return _missing_input("local_start", field="time")
        local_start, local_end, defaulted = availability_window
        try:
            result = self.social_scheduling_service.query_availability(
                requester_account_id=account_id,
                friend_account_ids=resolved,
                local_start=local_start,
                local_end=local_end,
                requester_timezone=requester_timezone,
            )
        except (SocialSchedulingError, ValueError) as error:
            return _social_error_outcome(error)
        return ActionOutcome(
            category="done",
            status="availability",
            data={
                "availability": _availability_facts(result),
                "query_window": _availability_query_window_fact(
                    local_start,
                    local_end,
                    requester_timezone=requester_timezone,
                    defaulted=defaulted,
                ),
            },
        )

    def _resolve_participants(
        self,
        account_id: str,
        params: Mapping[str, Any],
    ) -> list[str] | ActionOutcome:
        references = _participant_references(params)
        if not references:
            return _missing_input("participant")
        resolved: list[str] = []
        for reference in references:
            result = self.social_scheduling_service.resolve_active_friend_reference(
                account_id,
                reference,
            )
            if result.status == "ambiguous":
                return _ambiguous_participant(reference, result)
            if result.status != "matched" or not result.matched_account_id:
                return ActionOutcome(
                    category="not_possible",
                    status="inactive_receiver",
                    data={"field": "participant", "reference": reference},
                )
            resolved.append(result.matched_account_id)
        return _dedupe(resolved)

    def _resolve_shared_reminder(
        self,
        account_id: str,
        participant_account_ids: list[str],
        params: Mapping[str, Any],
    ) -> SharedReminder | ActionOutcome:
        match = _optional_str(params.get("match"))
        participant_set = set(participant_account_ids)
        active_candidates = [
            reminder
            for reminder in self.social_scheduling_service.list_shared_reminders(
                account_id
            )
            if reminder.status == "active"
            and participant_set.intersection(reminder.participant_account_ids)
        ]
        if not active_candidates:
            return ActionOutcome(
                category="not_possible",
                status="not_found",
                data={
                    key: value
                    for key, value in {
                        "match": match,
                        "participant_account_ids": list(participant_account_ids),
                    }.items()
                    if value is not None
                },
            )
        if match is None:
            candidates = active_candidates
        else:
            match_value = match.casefold()
            candidates = [
                reminder
                for reminder in active_candidates
                if match_value in reminder.title.casefold()
            ]
            if not candidates:
                if len(active_candidates) > 1:
                    return _ambiguous_shared_reminder(match, active_candidates)
                return ActionOutcome(
                    category="not_possible",
                    status="not_found",
                    data={"match": match},
                )
        if len(candidates) > 1:
            return _ambiguous_shared_reminder(match, candidates)
        return candidates[0]


def _shared_reminder_create_outcome(
    result: Any,
    *,
    requested_interval: Mapping[str, Any] | None = None,
) -> ActionOutcome:
    status = str(getattr(result, "status", "invalid"))
    data = _create_result_data(result)
    if _partial_failed(result):
        return ActionOutcome(
            category="done",
            status="partial",
            data={
                **data,
                "succeeded": _breakdown_list(result, "succeeded"),
                "failed": _breakdown_list(result, "failed"),
            },
        )
    if status == "created":
        return ActionOutcome(category="done", status="created", data=data)
    if status == "duplicate":
        return ActionOutcome(
            category="not_possible",
            status="duplicate_active",
            data={
                **data,
                "blocker": _blocker_fact(
                    "duplicate_active",
                    data["breakdown"],
                    requested_interval=requested_interval,
                ),
            },
        )
    if status in {"needs_title", "needs_time", "needs_duration", "needs_participants"}:
        field = status.removeprefix("needs_")
        return ActionOutcome(
            category="needs_input",
            status=f"missing_{field}",
            data={"field": field, **_follow_up_data(result)},
        )
    if status == "needs_past_time_confirmation":
        return ActionOutcome(
            category="needs_confirmation",
            status=status,
            data=_follow_up_data(result),
        )
    if status == "needs_incomplete_date_clarification":
        return ActionOutcome(
            category="needs_input",
            status=status,
            data={"field": "time", **_follow_up_data(result)},
        )
    if status == "blocked":
        breakdown = getattr(result, "breakdown", {}) or {}
        if breakdown.get("conflicting_participants"):
            return ActionOutcome(
                category="not_possible",
                status="receiver_conflict",
                data={
                    **data,
                    "blocker": _blocker_fact(
                        "receiver_conflict",
                        breakdown,
                        requested_interval=requested_interval,
                    ),
                },
            )
        if breakdown.get("unreachable_participants"):
            return ActionOutcome(
                category="not_possible",
                status="unreachable",
                data={
                    **data,
                    "blocker": _blocker_fact(
                        "unreachable",
                        breakdown,
                        requested_interval=requested_interval,
                    ),
                },
            )
        return ActionOutcome(
            category="not_possible",
            status="blocked",
            data={
                **data,
                "blocker": _blocker_fact(
                    "blocked",
                    breakdown,
                    requested_interval=requested_interval,
                ),
            },
        )
    return ActionOutcome(
        category="not_possible",
        status=status,
        data=data,
    )


def _shared_reminder_update_outcome(
    result: Any,
    *,
    requested_interval: Mapping[str, Any] | None = None,
) -> ActionOutcome:
    status = str(getattr(result, "status", "invalid"))
    data = _create_result_data(result)
    if status == "rescheduled":
        return ActionOutcome(category="done", status="rescheduled", data=data)
    if status == "duplicate":
        return ActionOutcome(
            category="not_possible",
            status="duplicate_active",
            data={
                **data,
                "blocker": _blocker_fact(
                    "duplicate_active",
                    data["breakdown"],
                    requested_interval=requested_interval,
                ),
            },
        )
    if status == "needs_time":
        return ActionOutcome(
            category="needs_input",
            status="missing_time",
            data={"field": "time", **_follow_up_data(result)},
        )
    if status == "needs_update_fields":
        follow_up_facts = dict(getattr(result, "follow_up_facts", {}) or {})
        if follow_up_facts.get("reason") == "no_change":
            unchanged_data = {
                **data,
                "reason": "no_change",
            }
            if requested_interval is not None:
                unchanged_data["requested_interval"] = dict(requested_interval)
            return ActionOutcome(
                category="not_possible",
                status="unchanged",
                data=unchanged_data,
            )
        return ActionOutcome(
            category="needs_input",
            status=status,
            data={"field": "time_or_duration", **_follow_up_data(result)},
        )
    if status == "needs_past_time_confirmation":
        return ActionOutcome(
            category="needs_confirmation",
            status=status,
            data=_follow_up_data(result),
        )
    if status == "blocked":
        breakdown = getattr(result, "breakdown", {}) or {}
        if breakdown.get("conflicting_participants"):
            return ActionOutcome(
                category="not_possible",
                status="receiver_conflict",
                data={
                    **data,
                    "blocker": _blocker_fact(
                        "receiver_conflict",
                        breakdown,
                        requested_interval=requested_interval,
                    ),
                },
            )
        if breakdown.get("unreachable_participants"):
            return ActionOutcome(
                category="not_possible",
                status="unreachable",
                data={
                    **data,
                    "blocker": _blocker_fact(
                        "unreachable",
                        breakdown,
                        requested_interval=requested_interval,
                    ),
                },
            )
        return ActionOutcome(
            category="not_possible",
            status="blocked",
            data={
                **data,
                "blocker": _blocker_fact(
                    "blocked",
                    breakdown,
                    requested_interval=requested_interval,
                ),
            },
        )
    return ActionOutcome(category="not_possible", status=status, data=data)


def _create_result_data(result: Any) -> dict[str, Any]:
    shared_reminder = getattr(result, "shared_reminder", None)
    data: dict[str, Any] = {
        "status": str(getattr(result, "status", "invalid")),
        "shared_reminder": (
            _shared_reminder_fact(shared_reminder)
            if shared_reminder is not None
            else None
        ),
        "breakdown": dict(getattr(result, "breakdown", {}) or {}),
        "follow_up_facts": dict(getattr(result, "follow_up_facts", {}) or {}),
    }
    return data


def _blocker_fact(
    kind: str,
    breakdown: Mapping[str, Any],
    *,
    requested_interval: Mapping[str, Any] | None,
) -> dict[str, Any]:
    fact: dict[str, Any] = {
        "kind": kind,
        "conflicting_participants": _list_value(
            breakdown.get("conflicting_participants")
        ),
        "unreachable_participants": _list_value(
            breakdown.get("unreachable_participants")
        ),
        "available_participants": _list_value(breakdown.get("available_participants")),
    }
    if requested_interval is not None:
        fact["requested_interval"] = dict(requested_interval)
    return fact


def _requested_interval(
    local_trigger_at: datetime | None,
    *,
    captured_timezone: str,
    duration_minutes: int | None,
) -> dict[str, Any] | None:
    if local_trigger_at is None:
        return None
    fact: dict[str, Any] = {
        "local_start": local_trigger_at.isoformat(),
        "captured_timezone": captured_timezone,
    }
    if duration_minutes is not None:
        duration = int(duration_minutes)
        fact["local_end"] = (local_trigger_at + timedelta(minutes=duration)).isoformat()
        fact["duration_minutes"] = duration
    return fact


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _follow_up_data(result: Any) -> dict[str, Any]:
    return {"follow_up_facts": dict(getattr(result, "follow_up_facts", {}) or {})}


def _partial_failed(result: Any) -> bool:
    if str(getattr(result, "status", "")) == "partial":
        return True
    failed = _breakdown_list(result, "failed")
    return bool(failed)


def _breakdown_list(result: Any, key: str) -> list[Any]:
    value = getattr(result, key, None)
    if isinstance(value, list):
        return value
    breakdown = getattr(result, "breakdown", {}) or {}
    value = breakdown.get(key)
    return list(value) if isinstance(value, list) else []


def _shared_reminder_fact(reminder: SharedReminder) -> dict[str, Any]:
    return {
        "shared_reminder_id": reminder.id,
        "creator_account_id": reminder.creator_account_id,
        "participant_account_ids": list(reminder.participant_account_ids),
        "title": reminder.title,
        "local_trigger_at": reminder.local_trigger_at.isoformat(),
        "captured_timezone": reminder.captured_timezone,
        "duration_minutes": reminder.duration_minutes,
        "status": reminder.status,
    }


def _availability_facts(result: Any) -> list[dict[str, Any]]:
    items = result if isinstance(result, list) else [result]
    return [
        {
            "friend_account_id": item.friend_account_id,
            "friend_display_name": item.friend_display_name or item.friend_account_id,
            "windows": [window.to_public_dict() for window in item.windows],
        }
        for item in items
    ]


def _availability_query_window_fact(
    local_start: datetime,
    local_end: datetime,
    *,
    requester_timezone: str,
    defaulted: bool,
) -> dict[str, Any]:
    return {
        "local_start": local_start.isoformat(),
        "local_end": local_end.isoformat(),
        "requester_timezone": requester_timezone,
        "defaulted": defaulted,
    }


def _ambiguous_participant(
    reference: str,
    result: FriendResolutionResult,
) -> ActionOutcome:
    return ActionOutcome(
        category="needs_choice",
        status="ambiguous",
        data={
            "field": "participant",
            "reference": reference,
            "candidates": list(result.candidates),
        },
    )


def _ambiguous_shared_reminder(
    match: str | None,
    candidates: list[SharedReminder],
) -> ActionOutcome:
    data: dict[str, Any] = {
        "field": "shared_reminder",
        "candidates": [_shared_reminder_fact(item) for item in candidates],
    }
    if match is not None:
        data["match"] = match
    return ActionOutcome(
        category="needs_choice",
        status="ambiguous",
        data=data,
    )


def _social_error_outcome(error: BaseException) -> ActionOutcome:
    if isinstance(error, SocialSchedulingError):
        status = _social_error_status(error.code)
        return ActionOutcome(
            category="not_possible",
            status=status,
            data=error.fact or {"reason": error.code},
        )
    return ActionOutcome(
        category="not_possible",
        status=str(error) or "social_scheduling_failed",
    )


def _social_error_status(code: str) -> str:
    return {
        "friendship_not_found": "not_found",
        "shared_reminder_not_found": "not_found",
        "owner_channel_required": "unreachable",
        "joiner_channel_required": "unreachable",
    }.get(code, code)


def _commit_guard(guard: Any) -> CommitGuard:
    value = getattr(guard, "guard_state_change", None)
    return value if callable(value) else None


def _account_id(params: Mapping[str, Any], preferred: str = "account_id") -> str | None:
    for key in (preferred, "account_id", "owner_account_id", "creator_account_id"):
        value = _optional_str(params.get(key))
        if value is not None:
            return value
    return None


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _optional_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _detect_update_trigger_time(
    service: SocialSchedulingService,
    params: Mapping[str, Any],
    *,
    captured_timezone: str,
    now: Callable[[], datetime],
) -> datetime | None:
    detector = getattr(service, "detector", None)
    extract = getattr(detector, "extract", None)
    if not callable(extract):
        return None
    try:
        detector_text = _shared_reminder_detector_text(params)
    except ValueError:
        return None
    current = now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    try:
        zone = ZoneInfo(captured_timezone)
    except ZoneInfoNotFoundError:
        zone = UTC
    fields = extract(detector_text, captured_timezone, current.astimezone(zone))
    trigger_time = getattr(fields, "trigger_time", None)
    if not isinstance(trigger_time, datetime):
        return None
    if trigger_time.tzinfo is not None:
        return trigger_time.astimezone(zone).replace(tzinfo=None)
    return trigger_time


def _availability_window(
    params: Mapping[str, Any],
    *,
    requester_timezone: str,
    now: Callable[[], datetime],
) -> tuple[datetime, datetime, bool] | None:
    date_phrase = params.get("date_phrase")
    date_window = resolve_date_phrase_window(
        date_phrase,
        timezone_name=requester_timezone,
        now=now,
    )
    if date_window is not None:
        return date_window.local_start, date_window.local_end, False
    if date_phrase is not None:
        return None

    start_raw = params.get("local_start")
    end_raw = params.get("local_end")
    local_start = _optional_datetime(start_raw)
    local_end = _optional_datetime(end_raw)

    if local_start is not None:
        if local_end is not None:
            return local_start, local_end, False
        end_window = _date_phrase_window(end_raw, requester_timezone, now)
        if end_window is not None:
            return local_start, end_window.local_end, False
        return None

    start_window = _date_phrase_window(start_raw, requester_timezone, now)
    if start_window is not None:
        if local_end is not None:
            return start_window.local_start, local_end, False
        end_window = _date_phrase_window(end_raw, requester_timezone, now)
        if end_window is not None:
            return start_window.local_start, end_window.local_end, False
        return start_window.local_start, start_window.local_end, False

    if start_raw is not None or end_raw is not None:
        return None

    default_start = resolve_date_phrase_window(
        "today",
        timezone_name=requester_timezone,
        now=now,
    )
    if default_start is None:
        return None
    return (
        default_start.local_start,
        default_start.local_start + timedelta(days=_DEFAULT_AVAILABILITY_WINDOW_DAYS),
        True,
    )


def _date_phrase_window(
    value: Any,
    requester_timezone: str,
    now: Callable[[], datetime],
):
    return resolve_date_phrase_window(
        value,
        timezone_name=requester_timezone,
        now=now,
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _timezone(params: Mapping[str, Any]) -> str:
    return str(
        params.get("captured_timezone") or params.get("requester_timezone") or "UTC"
    )


def _has_participant_reference(params: Mapping[str, Any]) -> bool:
    return bool(_participant_references(params))


def _participant_references(params: Mapping[str, Any]) -> list[str]:
    value = params.get("participant")
    if isinstance(value, str):
        text = _optional_str(value)
        return [text] if text else []
    if isinstance(value, list | tuple):
        return [
            item.strip() for item in value if isinstance(item, str) and item.strip()
        ]
    return []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _missing_input(status_field: str, *, field: str | None = None) -> ActionOutcome:
    visible_field = field or status_field
    return ActionOutcome(
        category="needs_input",
        status=f"missing_{visible_field}",
        data={"field": visible_field},
    )


def _should_detect_shared_reminder(params: Mapping[str, Any]) -> bool:
    if (
        params.get("local_trigger_at") is not None
        or params.get("trigger_time") is not None
    ):
        return False
    return any(
        _optional_str(params.get(key)) for key in ("time_phrase", "raw_text", "text")
    )


def _shared_reminder_detector_text(params: Mapping[str, Any]) -> str:
    raw_text = _optional_str(params.get("raw_text") or params.get("text"))
    time_phrase = _optional_str(params.get("time_phrase"))
    if raw_text is not None:
        if time_phrase is not None and time_phrase not in raw_text:
            return f"{raw_text} {time_phrase}"
        return raw_text
    parts = [
        _optional_str(params.get("title") or params.get("content")),
        time_phrase,
    ]
    text = " ".join(part for part in parts if part)
    if text:
        return text
    raise ValueError("missing_raw_text")


def _asdict(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    return dict(vars(value))
