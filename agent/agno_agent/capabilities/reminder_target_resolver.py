from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from agent.reminder.models import ReminderQuery


TargetScope = Literal["current_conversation", "recent_active", "all_active"]


@dataclass(frozen=True)
class ReminderTargetSelector:
    reminder_id: str | None = None
    target_title: str | None = None
    target_local_date: str | None = None
    target_local_time: str | None = None
    target_rrule: str | None = None
    target_scope: TargetScope | None = None
    current_conversation_id: str | None = None


@dataclass(frozen=True)
class ReminderTargetFact:
    reminder_id: str
    title: str | None
    local_date: str | None
    local_time: str | None
    rrule: str | None
    conversation_id: str | None


@dataclass(frozen=True)
class ResolvedOne:
    reminder_id: str
    reminder: Any | None = None


@dataclass(frozen=True)
class Clarify:
    candidates: list[ReminderTargetFact]


ResolveResult = ResolvedOne | Clarify


def resolve_target(
    owner_id: str,
    selector: ReminderTargetSelector,
    mongo: Any,
) -> ResolveResult:
    reminders = _list_active_visible_reminders(owner_id, mongo)
    matches = list(reminders)

    reminder_id = _clean_reminder_id(selector.reminder_id)
    if reminder_id:
        matches = [item for item in matches if _reminder_id(item) == reminder_id]
        return _single_or_clarify(matches)

    target_title = _normalize_title_selector(selector.target_title)
    if target_title:
        exact = [
            item for item in matches if _normalize_title_selector(_title(item)) == target_title
        ]
        matches = exact or [
            item
            for item in matches
            if target_title in (_normalize_title_selector(_title(item)) or "")
        ]

    target_local_date = _clean(selector.target_local_date)
    if target_local_date:
        matches = [
            item for item in matches if _local_date(item) == target_local_date
        ]

    target_local_time = _clean(selector.target_local_time)
    if target_local_time:
        matches = [
            item
            for item in matches
            if (_local_time(item) or "")[:5] == target_local_time
        ]

    target_rrule = _clean(selector.target_rrule)
    if target_rrule:
        matches = [item for item in matches if _rrule(item) == target_rrule]

    if selector.target_scope == "current_conversation":
        conversation_id = _clean(selector.current_conversation_id)
        if conversation_id:
            matches = [
                item
                for item in matches
                if _conversation_id(item) == conversation_id
            ]
    elif selector.target_scope == "recent_active":
        conversation_id = _clean(selector.current_conversation_id)
        if conversation_id:
            scoped = [
                item
                for item in matches
                if _conversation_id(item) == conversation_id
            ]
            if scoped:
                matches = scoped
        matches = _unique_latest(matches)

    return _single_or_clarify(matches)


def _list_active_visible_reminders(owner_id: str, source: Any) -> list[Any]:
    list_visible = getattr(source, "list_visible_reminders", None)
    if callable(list_visible):
        return list(
            list_visible(
                owner_user_id=owner_id,
                query=ReminderQuery(lifecycle_states=["active"]),
            )
        )

    collection = getattr(source, "reminders", None) or getattr(source, "collection", None)
    find = getattr(collection, "find", None)
    if callable(find):
        return list(
            find(
                {
                    "owner_user_id": owner_id,
                    "visibility": "visible",
                    "lifecycle_state": "active",
                }
            )
        )

    raise TypeError("resolver source must list active visible reminders")


def _single_or_clarify(matches: list[Any]) -> ResolveResult:
    if len(matches) == 1:
        return ResolvedOne(reminder_id=_reminder_id(matches[0]) or "", reminder=matches[0])
    return Clarify(candidates=[_candidate_fact(item) for item in matches])


def _unique_latest(matches: list[Any]) -> list[Any]:
    if len(matches) <= 1:
        return matches
    keyed = [
        (item, _timestamp_value(_value(item, "updated_at") or _value(item, "created_at")))
        for item in matches
    ]
    latest = max((timestamp for _, timestamp in keyed), default=None)
    if latest is None:
        return matches
    latest_matches = [item for item, timestamp in keyed if timestamp == latest]
    return latest_matches if len(latest_matches) == 1 else matches


def _timestamp_value(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "timestamp"):
        try:
            return float(value.timestamp())
        except (OverflowError, OSError, ValueError):
            return None
    try:
        parsed = __import__("datetime").datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except Exception:
        return None
    try:
        return float(parsed.timestamp())
    except (OverflowError, OSError, ValueError):
        return None


def _candidate_fact(reminder: Any) -> ReminderTargetFact:
    return ReminderTargetFact(
        reminder_id=_reminder_id(reminder) or "",
        title=_title(reminder),
        local_date=_local_date(reminder),
        local_time=_local_time(reminder),
        rrule=_rrule(reminder),
        conversation_id=_conversation_id(reminder),
    )


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_reminder_id(value: Any) -> str | None:
    text = _clean(value)
    if text is None:
        return None
    if text.isdigit() and 6 <= len(text) <= 12:
        return None
    return text


def _normalize_title_selector(value: Any) -> str | None:
    text = _clean(value)
    if text is None:
        return None
    text = " ".join(text.split())
    for suffix in ("提醒事项", "提醒"):
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)].strip()
            break
    return text or None


def _value(obj: Any, name: str) -> Any:
    if isinstance(obj, Mapping):
        if name == "id":
            return obj.get("id") or obj.get("_id")
        return obj.get(name)
    return getattr(obj, name, None)


def _schedule(reminder: Any) -> Any:
    return _value(reminder, "schedule") or {}


def _target(reminder: Any) -> Any:
    return _value(reminder, "agent_output_target") or {}


def _reminder_id(reminder: Any) -> str | None:
    value = _value(reminder, "id")
    return str(value) if value is not None else None


def _title(reminder: Any) -> str | None:
    return _clean(_value(reminder, "title"))


def _local_date(reminder: Any) -> str | None:
    value = _value(_schedule(reminder), "local_date")
    return value.isoformat() if hasattr(value, "isoformat") else _clean(value)


def _local_time(reminder: Any) -> str | None:
    value = _value(_schedule(reminder), "local_time")
    return value.isoformat() if hasattr(value, "isoformat") else _clean(value)


def _rrule(reminder: Any) -> str | None:
    return _clean(_value(_schedule(reminder), "rrule"))


def _conversation_id(reminder: Any) -> str | None:
    return _clean(_value(_target(reminder), "conversation_id"))
