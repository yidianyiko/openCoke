from __future__ import annotations

import contextvars
import re
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agno.tools import tool

from agent.agno_agent.tools.tool_result import append_tool_result
from agent.agno_agent.capabilities.reminder_target_resolver import (
    Clarify,
    ReminderTargetSelector,
    ResolvedOne,
    resolve_target,
)
from agent.reminder.errors import InvalidArgument, ReminderError
from agent.reminder.models import (
    Reminder,
    ReminderPatch,
    ReminderQuery,
)
from agent.reminder.runtime_contract import ReminderRuntimeContract
from agent.reminder import build_schedule_from_anchor
from util.log_util import get_logger

logger = get_logger(__name__)

_SUPPORTED_ACTIONS = {"create", "update", "cancel", "complete", "list", "batch"}


_context_session_state: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "reminder_session_state", default={}
)


class _KeywordResolutionError(Exception):
    def __init__(self, *, action: str, keyword: str, match_count: int) -> None:
        self.action = action
        self.keyword = keyword
        self.match_count = match_count
        super().__init__(_target_resolution_message(action, match_count))


def set_reminder_session_state(session_state: dict) -> None:
    _context_session_state.set(session_state or {})


def _get_session_state() -> dict:
    return _context_session_state.get()


def _execute_visible_reminder_tool_action(
    *,
    action: str,
    title: str | None = None,
    trigger_at: str | None = None,
    duration_minutes: int | None = None,
    reminder_id: str | None = None,
    keyword: str | None = None,
    target_title: str | None = None,
    target_local_date: str | None = None,
    target_local_time: str | None = None,
    target_rrule: str | None = None,
    target_scope: str | None = None,
    new_title: str | None = None,
    new_trigger_at: str | None = None,
    rrule: str | None = None,
    operations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    session_state = _get_session_state()
    canonical_action = _canonical_action(action)
    if canonical_action not in _SUPPORTED_ACTIONS:
        return _append_failure(
            session_state,
            action=canonical_action,
            summary="我还需要提醒内容和时间，才能帮你设置提醒。",
            error_code="MissingReminderDetails",
        )

    if canonical_action == "batch":
        if not operations:
            return _append_failure(
                session_state,
                action="batch",
                summary="批量提醒操作失败：operations are required for batch",
                error_code="InvalidArgument",
            )

    context_failure = _validate_runtime_context_for_action(
        session_state,
        action=canonical_action,
    )
    if context_failure is not None:
        return context_failure

    try:
        runtime = _build_reminder_runtime(session_state)
    except Exception:
        logger.exception("ReminderRuntimeContract adapter initialization failed")
        return _append_failure(
            session_state,
            action=canonical_action,
            summary="提醒操作失败：adapter failure",
            error_code="ReminderAdapterError",
        )

    try:
        if canonical_action == "batch":
            # The adapter batches operation-by-operation so keyword resolution and
            # ChatWorkflow-visible tool results are preserved for each item.
            return _execute_batch_operations(
                runtime=runtime,
                session_state=session_state,
                operations=operations or [],
            )

        return _run_operation(
            runtime=runtime,
            session_state=session_state,
            action=canonical_action,
            title=title,
            trigger_at=trigger_at,
            duration_minutes=duration_minutes,
            reminder_id=reminder_id,
            keyword=keyword,
            target_title=target_title,
            target_local_date=target_local_date,
            target_local_time=target_local_time,
            target_rrule=target_rrule,
            target_scope=target_scope,
            new_title=new_title,
            new_trigger_at=new_trigger_at,
            rrule=rrule,
        )
    except Exception:
        logger.exception("visible reminder tool adapter action failed")
        return _append_failure(
            session_state,
            action=canonical_action,
            summary=f"{_action_failure_label(canonical_action)}失败：adapter failure",
            error_code="ReminderAdapterError",
        )


def _validate_runtime_context_for_action(
    session_state: dict,
    *,
    action: str,
) -> dict[str, Any] | None:
    try:
        _derive_runtime_context(session_state)
    except ReminderError as exc:
        summary = f"{_action_failure_label(action)}失败：{exc.user_message}"
        return _append_failure(
            session_state,
            action=action,
            summary=summary,
            error_code=exc.code,
        )
    return None


def _execute_batch_operations(
    *,
    runtime: ReminderRuntimeContract,
    session_state: dict,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    context = _derive_runtime_context(session_state)
    results: list[dict[str, Any]] = []
    for operation in _dedupe_batch_create_operations(operations, context.timezone):
        if not isinstance(operation, dict):
            summary = "提醒操作失败：batch operation must be an object"
            results.append(
                _append_failure(
                    session_state,
                    action="batch",
                    summary=summary,
                    error_code="InvalidArgument",
                )
            )
            continue
        results.append(
            _run_operation(
                runtime=runtime,
                session_state=session_state,
                action=str(operation.get("action") or ""),
                title=operation.get("title"),
                trigger_at=operation.get("trigger_at"),
                duration_minutes=operation.get("duration_minutes"),
                reminder_id=operation.get("reminder_id"),
                keyword=operation.get("keyword"),
                target_title=operation.get("target_title"),
                target_local_date=operation.get("target_local_date"),
                target_local_time=operation.get("target_local_time"),
                target_rrule=operation.get("target_rrule"),
                target_scope=operation.get("target_scope"),
                new_title=operation.get("new_title"),
                new_trigger_at=operation.get("new_trigger_at"),
                rrule=operation.get("rrule"),
            )
        )
    return {
        "ok": any(result.get("ok") is True for result in results),
        "action": "batch",
        "operations": results,
        "summary": "\n".join(str(result.get("summary") or "") for result in results),
    }


def _dedupe_batch_create_operations(
    operations: list[dict[str, Any]],
    timezone: str,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    index_by_key: dict[tuple[str, str], int] = {}
    recurring_keys: set[tuple[str, str]] = set()

    for operation in operations:
        if not isinstance(operation, dict):
            selected.append(operation)
            continue

        key = _batch_create_dedupe_key(operation, timezone)
        if key is None:
            selected.append(operation)
            continue

        rrule_value = operation.get("rrule")
        has_rrule = (
            isinstance(rrule_value, str) and _normalize_rrule(rrule_value) is not None
        )
        existing_index = index_by_key.get(key)
        if existing_index is None:
            index_by_key[key] = len(selected)
            if has_rrule:
                recurring_keys.add(key)
            selected.append(operation)
            continue

        if has_rrule and key not in recurring_keys:
            selected[existing_index] = operation
            recurring_keys.add(key)

    return selected


def _batch_create_dedupe_key(
    operation: dict[str, Any],
    timezone: str,
) -> tuple[str, str] | None:
    if _canonical_action(str(operation.get("action") or "")) != "create":
        return None

    title = _normalize_batch_create_title(operation.get("title"))
    trigger_at = str(operation.get("trigger_at") or "").strip()
    if not title or not trigger_at:
        return None

    try:
        anchor_at = datetime.fromisoformat(trigger_at.replace("Z", "+00:00"))
        if anchor_at.tzinfo is None or anchor_at.utcoffset() is None:
            return None
        local_dt = anchor_at.astimezone(ZoneInfo(timezone))
    except (ValueError, TypeError, KeyError):
        return None

    local_time = local_dt.time().replace(microsecond=0).isoformat()
    return (title, local_time)


def _normalize_batch_create_title(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _run_operation(
    *,
    runtime: ReminderRuntimeContract,
    session_state: dict,
    action: str,
    title: str | None = None,
    trigger_at: str | None = None,
    duration_minutes: int | None = None,
    reminder_id: str | None = None,
    keyword: str | None = None,
    target_title: str | None = None,
    target_local_date: str | None = None,
    target_local_time: str | None = None,
    target_rrule: str | None = None,
    target_scope: str | None = None,
    new_title: str | None = None,
    new_trigger_at: str | None = None,
    rrule: str | None = None,
) -> dict[str, Any]:
    canonical_action = _canonical_action(action)
    try:
        result = _execute_one(
            runtime=runtime,
            session_state=session_state,
            action=canonical_action,
            title=title,
            trigger_at=trigger_at,
            duration_minutes=duration_minutes,
            reminder_id=reminder_id,
            keyword=keyword,
            target_title=target_title,
            target_local_date=target_local_date,
            target_local_time=target_local_time,
            target_rrule=target_rrule,
            target_scope=target_scope,
            new_title=new_title,
            new_trigger_at=new_trigger_at,
            rrule=rrule,
        )
    except _KeywordResolutionError as exc:
        summary = f"{_action_failure_label(canonical_action)}失败：{exc}"
        return _append_failure(
            session_state,
            action=canonical_action,
            summary=summary,
            error_code="AmbiguousReminderKeyword",
        )
    except ReminderError as exc:
        summary = (
            f"{_action_failure_label(canonical_action)}失败："
            f"{_user_safe_reminder_error_message(exc)}"
        )
        return _append_failure(
            session_state,
            action=canonical_action,
            summary=summary,
            error_code=exc.code,
        )
    except ValueError as exc:
        summary = f"{_action_failure_label(canonical_action)}失败：{exc}"
        return _append_failure(
            session_state,
            action=canonical_action,
            summary=summary,
            error_code="InvalidArgument",
        )
    except Exception:
        logger.exception("visible reminder operation failed")
        return _append_failure(
            session_state,
            action=canonical_action,
            summary=f"{_action_failure_label(canonical_action)}失败：adapter failure",
            error_code="ReminderAdapterError",
        )

    timed_write = bool(result.pop("timed_write", False))
    if timed_write:
        session_state["reminder_created_with_time"] = True
    append_tool_result(
        session_state,
        tool_name="提醒操作",
        ok=True,
        result_summary=str(result.get("summary") or ""),
        extra_notes=f"action={canonical_action}",
    )
    return result


def _user_safe_reminder_error_message(exc: ReminderError) -> str:
    if exc.code == "InvalidSchedule" and exc.detail.get("reason") == "past_one_shot":
        return "这个提醒时间已经过去了，请告诉我一个未来的时间。"
    if exc.code == "InvalidArgument" and exc.detail.get("reason") == "missing_target":
        return _target_resolution_message(str(exc.detail.get("action") or ""), None)
    return exc.user_message


def _execute_one(
    *,
    runtime: ReminderRuntimeContract,
    session_state: dict,
    action: str,
    title: str | None,
    trigger_at: str | None,
    duration_minutes: int | None,
    reminder_id: str | None,
    keyword: str | None,
    target_title: str | None,
    target_local_date: str | None,
    target_local_time: str | None,
    target_rrule: str | None,
    target_scope: str | None,
    new_title: str | None,
    new_trigger_at: str | None,
    rrule: str | None,
) -> dict[str, Any]:
    context = _derive_runtime_context(session_state)

    if action == "create":
        if not title:
            raise InvalidArgument(
                "Create reminder requires title",
                detail={"action": action},
            )
        created = runtime.create_visible_reminder(
            owner_user_id=context.owner_user_id,
            title=title,
            schedule=_schedule_from_iso(
                trigger_at or "",
                context.timezone,
                rrule,
                duration_minutes=duration_minutes,
            ),
            target=context.target,
        )
        return {
            "ok": True,
            "action": "create",
            "reminder": _reminder_to_dict(created),
            "summary": f"已创建提醒：{_format_reminder_with_schedule(created)}",
            "timed_write": True,
        }

    if action == "list":
        reminders = runtime.list_visible_reminders(
            owner_user_id=context.owner_user_id,
            query=ReminderQuery(lifecycle_states=["active"]),
        )
        return {
            "ok": True,
            "action": "list",
            "reminders": [_reminder_to_dict(reminder) for reminder in reminders],
            "summary": _format_list_summary(reminders),
            "timed_write": False,
        }

    if action == "update":
        resolved = _resolve_reminder_target(
            runtime=runtime,
            owner_user_id=context.owner_user_id,
            reminder_id=reminder_id,
            keyword=keyword,
            target_title=target_title,
            target_local_date=target_local_date,
            target_local_time=target_local_time,
            target_rrule=target_rrule,
            target_scope=target_scope,
            current_conversation_id=context.target.conversation_id,
            action=action,
            require_existing=True,
        )
        patch = _build_patch(
            title=new_title if new_title is not None else title,
            trigger_at=new_trigger_at if new_trigger_at is not None else trigger_at,
            timezone=context.timezone,
            rrule=rrule,
            duration_minutes=duration_minutes,
            existing_schedule=resolved.reminder.schedule if resolved.reminder else None,
        )
        updated = runtime.update_visible_reminder(
            reminder_id=resolved.reminder_id,
            owner_user_id=context.owner_user_id,
            patch=patch,
        )
        return {
            "ok": True,
            "action": "update",
            "reminder": _reminder_to_dict(updated),
            "summary": f"已更新提醒：{_format_reminder_with_schedule(updated)}",
            "timed_write": patch.schedule is not None,
        }

    if action == "cancel":
        resolved = _resolve_reminder_target(
            runtime=runtime,
            owner_user_id=context.owner_user_id,
            reminder_id=reminder_id,
            keyword=keyword,
            target_title=target_title,
            target_local_date=target_local_date,
            target_local_time=target_local_time,
            target_rrule=target_rrule,
            target_scope=target_scope,
            current_conversation_id=context.target.conversation_id,
            action=action,
            require_existing=False,
        )
        cancelled = runtime.cancel_visible_reminder(
            reminder_id=resolved.reminder_id,
            owner_user_id=context.owner_user_id,
        )
        return {
            "ok": True,
            "action": "cancel",
            "reminder": _reminder_to_dict(cancelled),
            "summary": f"已取消提醒：{cancelled.title}",
            "timed_write": False,
        }

    if action == "complete":
        resolved = _resolve_reminder_target(
            runtime=runtime,
            owner_user_id=context.owner_user_id,
            reminder_id=reminder_id,
            keyword=keyword,
            target_title=target_title,
            target_local_date=target_local_date,
            target_local_time=target_local_time,
            target_rrule=target_rrule,
            target_scope=target_scope,
            current_conversation_id=context.target.conversation_id,
            action=action,
            require_existing=False,
        )
        completed = runtime.complete_visible_reminder(
            reminder_id=resolved.reminder_id,
            owner_user_id=context.owner_user_id,
        )
        return {
            "ok": True,
            "action": "complete",
            "reminder": _reminder_to_dict(completed),
            "summary": f"已完成提醒：{completed.title}",
            "timed_write": False,
        }

    raise InvalidArgument(
        "Unsupported reminder action",
        detail={"action": action},
    )


def _derive_runtime_context(session_state: dict):
    from agent.agno_agent.adapters.coke_reminder_adapter import CokeReminderAdapter

    return CokeReminderAdapter().derive_context(session_state)


def _build_reminder_runtime(session_state: dict) -> ReminderRuntimeContract:
    from agent.agno_agent.adapters.coke_reminder_adapter import CokeReminderAdapter

    return CokeReminderAdapter().reminder_contract(session_state)


def _canonical_action(action: str) -> str:
    normalized = (action or "").strip().lower()
    if normalized == "delete":
        return "cancel"
    return normalized


def _schedule_from_iso(
    trigger_at: str,
    timezone: str,
    rrule: str | None,
    *,
    duration_minutes: int | None = None,
):
    if not trigger_at:
        raise ValueError("trigger_at is required")
    try:
        anchor_at = datetime.fromisoformat(trigger_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("trigger_at must be an ISO 8601 datetime") from exc
    if anchor_at.tzinfo is None or anchor_at.utcoffset() is None:
        raise ValueError("trigger_at must include a timezone offset or Z")
    return build_schedule_from_anchor(
        anchor_at,
        timezone,
        _normalize_rrule(rrule),
        duration_minutes=duration_minutes,
    )


def _normalize_rrule(rrule: str | None) -> str | None:
    if rrule is None:
        return None
    normalized = rrule.strip()
    return normalized or None


def _build_patch(
    *,
    title: str | None,
    trigger_at: str | None,
    timezone: str,
    rrule: str | None,
    duration_minutes: int | None = None,
    existing_schedule: Any | None = None,
) -> ReminderPatch:
    schedule = None
    if trigger_at is not None:
        schedule = _schedule_from_iso(
            trigger_at,
            timezone,
            rrule if rrule is not None else getattr(existing_schedule, "rrule", None),
            duration_minutes=(
                duration_minutes
                if duration_minutes is not None and duration_minutes > 0
                else getattr(existing_schedule, "duration_minutes", None)
            ),
        )
    elif rrule is not None and existing_schedule is not None:
        schedule = type(existing_schedule)(
            anchor_at=existing_schedule.anchor_at,
            local_date=existing_schedule.local_date,
            local_time=existing_schedule.local_time,
            timezone=existing_schedule.timezone,
            rrule=_normalize_rrule(rrule),
            duration_minutes=existing_schedule.duration_minutes,
        )

    return ReminderPatch(
        title=title,
        schedule=schedule,
    )


def _resolve_reminder_target(
    *,
    runtime: ReminderRuntimeContract,
    owner_user_id: str,
    reminder_id: str | None,
    keyword: str | None,
    target_title: str | None,
    target_local_date: str | None,
    target_local_time: str | None,
    target_rrule: str | None,
    target_scope: str | None,
    current_conversation_id: str | None,
    action: str,
    require_existing: bool,
) -> ResolvedOne:
    title_selector = target_title or keyword
    has_selector = any(
        [
            reminder_id,
            title_selector,
            target_local_date,
            target_local_time,
            target_rrule,
            target_scope,
        ]
    )
    if not has_selector:
        raise InvalidArgument(
            _target_resolution_message(action, None),
            detail={"action": action, "reason": "missing_target"},
        )
    if reminder_id and not require_existing:
        return ResolvedOne(reminder_id=reminder_id)

    selector = ReminderTargetSelector(
        reminder_id=reminder_id,
        target_title=title_selector,
        target_local_date=target_local_date,
        target_local_time=target_local_time,
        target_rrule=target_rrule,
        target_scope=target_scope,  # type: ignore[arg-type]
        current_conversation_id=current_conversation_id,
    )
    result = resolve_target(owner_user_id, selector, runtime)
    if (
        isinstance(result, Clarify)
        and not result.candidates
        and target_scope == "current_conversation"
        and not any(
            [reminder_id, title_selector, target_local_date, target_local_time, target_rrule]
        )
    ):
        result = resolve_target(
            owner_user_id,
            ReminderTargetSelector(
                target_scope="recent_active",
                current_conversation_id=current_conversation_id,
            ),
            runtime,
        )
    if isinstance(result, ResolvedOne):
        return result
    if isinstance(result, Clarify):
        raise _KeywordResolutionError(
            action=action,
            keyword=title_selector or "",
            match_count=len(result.candidates),
        )
    raise InvalidArgument(
        _target_resolution_message(action, None),
        detail={"action": action, "reason": "missing_target"},
    )


def _isoformat_or_none(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _reminder_to_dict(reminder: Reminder) -> dict[str, Any]:
    schedule = reminder.schedule
    target = reminder.agent_output_target
    return {
        "id": reminder.id,
        "owner_user_id": reminder.owner_user_id,
        "title": reminder.title,
        "schedule": {
            "anchor_at": _isoformat_or_none(schedule.anchor_at),
            "local_date": _isoformat_or_none(schedule.local_date),
            "local_time": _isoformat_or_none(schedule.local_time),
            "timezone": schedule.timezone,
            "rrule": schedule.rrule,
            "duration_minutes": schedule.duration_minutes,
        },
        "agent_output_target": {
            "conversation_id": target.conversation_id,
            "character_id": target.character_id,
            "route_key": target.route_key,
        },
        "created_by_system": reminder.created_by_system,
        "origin": reminder.origin,
        "visibility": reminder.visibility,
        "fire_mode": reminder.fire_mode,
        "prompt": reminder.prompt,
        "metadata": dict(reminder.metadata or {}),
        "lifecycle_state": reminder.lifecycle_state,
        "next_fire_at": _isoformat_or_none(reminder.next_fire_at),
        "last_fired_at": _isoformat_or_none(reminder.last_fired_at),
        "last_event_ack_at": _isoformat_or_none(reminder.last_event_ack_at),
        "last_error": reminder.last_error,
        "created_at": _isoformat_or_none(reminder.created_at),
        "updated_at": _isoformat_or_none(reminder.updated_at),
        "completed_at": _isoformat_or_none(reminder.completed_at),
        "cancelled_at": _isoformat_or_none(reminder.cancelled_at),
        "failed_at": _isoformat_or_none(reminder.failed_at),
    }


def _format_list_summary(reminders: list[Reminder]) -> str:
    if not reminders:
        return "暂无提醒"
    return "\n".join(
        f"- {item.title} @ "
        f"{item.next_fire_at.isoformat() if item.next_fire_at else 'none'}"
        for item in reminders
    )


def _format_reminder_with_schedule(reminder: Reminder) -> str:
    schedule = reminder.schedule
    time_text = _format_local_time(schedule.local_time)
    until_text = _format_rrule_until(schedule.rrule, schedule.timezone)
    weekly_text = _format_weekly_rrule(schedule.rrule)
    if schedule.rrule == "FREQ=DAILY" or (
        schedule.rrule and schedule.rrule.startswith("FREQ=DAILY;UNTIL=")
    ):
        schedule_text = f"每天 {time_text}"
        if until_text:
            schedule_text = f"{schedule_text}，截止 {until_text}"
    elif weekly_text:
        schedule_text = f"{weekly_text} {time_text}"
        if until_text:
            schedule_text = f"{schedule_text}，截止 {until_text}"
    elif schedule.rrule:
        schedule_text = (
            f"{schedule.local_date.isoformat()} {time_text}，循环规则 {schedule.rrule}"
        )
    else:
        schedule_text = f"{schedule.local_date.isoformat()} {time_text}"
    return f"{reminder.title}（{schedule_text}）"


def _format_local_time(value: Any) -> str:
    second = getattr(value, "second", 0)
    if second:
        return value.strftime("%H:%M:%S")
    return value.strftime("%H:%M")


def _format_weekly_rrule(rrule: str | None) -> str:
    if not rrule:
        return ""
    parts = _parse_rrule_parts(rrule)
    if parts.get("FREQ") != "WEEKLY":
        return ""
    interval_text = _format_weekly_interval(parts.get("INTERVAL"))
    byday = parts.get("BYDAY")
    if not byday:
        return interval_text
    labels = {
        "MO": "周一",
        "TU": "周二",
        "WE": "周三",
        "TH": "周四",
        "FR": "周五",
        "SA": "周六",
        "SU": "周日",
    }
    days = [labels.get(day.strip().upper(), "") for day in byday.split(",")]
    days = [day for day in days if day]
    if not days:
        return interval_text
    if interval_text == "每周":
        return f"每{'、'.join(days)}"
    return f"{interval_text}的{'、'.join(days)}"


def _format_weekly_interval(interval: str | None) -> str:
    if not interval:
        return "每周"
    try:
        weeks = int(interval)
    except (TypeError, ValueError):
        return "每周"
    if weeks <= 1:
        return "每周"
    if weeks == 2:
        return "每两周"
    return f"每{weeks}周"


def _parse_rrule_parts(rrule: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for raw_part in str(rrule or "").split(";"):
        if "=" not in raw_part:
            continue
        key, value = raw_part.split("=", 1)
        parts[key.strip().upper()] = value.strip().upper()
    return parts


def _format_rrule_until(rrule: str | None, timezone: str) -> str:
    if not rrule:
        return ""
    match = re.search(r"(?:^|;)UNTIL=(\d{8}T\d{6}Z)(?:;|$)", rrule)
    if not match:
        return ""
    try:
        until_at = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(
            tzinfo=UTC
        )
        return until_at.astimezone(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M")
    except (ValueError, ZoneInfoNotFoundError):
        return ""


def _action_failure_label(action: str) -> str:
    return {
        "create": "创建提醒",
        "update": "更新提醒",
        "cancel": "取消提醒",
        "complete": "完成提醒",
        "list": "列出提醒",
    }.get(action, "提醒操作")


def _target_resolution_action_text(action: str) -> str:
    return {
        "update": "更新",
        "cancel": "取消",
        "complete": "完成",
    }.get(action, "处理")


def _target_resolution_message(action: str, match_count: int | None) -> str:
    action_text = _target_resolution_action_text(action)
    if match_count is None:
        return f"要{action_text}哪条提醒？请告诉我提醒名称。"
    if match_count == 0:
        return f"没有找到要{action_text}的提醒，请告诉我提醒名称。"
    return "找到多条可能的提醒，请说得更具体一点。"


def _append_failure(
    session_state: dict,
    *,
    action: str,
    summary: str,
    error_code: str,
) -> dict[str, Any]:
    append_tool_result(
        session_state,
        tool_name="提醒操作",
        ok=False,
        result_summary=summary,
        extra_notes=f"action={action}; error_code={error_code}",
    )
    return {
        "ok": False,
        "action": action,
        "error_code": error_code,
        "summary": summary,
    }


@tool(
    stop_after_tool_call=True,
    description=(
        "Visible reminder management through the reminder command protocol. "
        "Supports create, list, update, cancel/delete, complete, and batch. "
        "For create/update time changes, trigger_at/new_trigger_at must be ISO "
        "8601 with an explicit timezone offset or Z, for example "
        "2026-04-28T17:58:00+09:00. Use RFC 5545 RRULE strings for recurrence, "
        "for example FREQ=DAILY. Do not call create/update with relative dates "
        "or ambiguous date-only requests; resolve safe absolute datetimes before "
        "calling this tool. Do not call create for a bare plan or schedule "
        "statement unless the user explicitly asks to be reminded, notified, "
        "alarmed, checked in on, nudged, or supervised. "
        "For habitual or general schedules, create recurring reminders only; "
        "do not also create one-shot reminders with the same title and local "
        "time in the same batch. "
        "Only call list for explicit user requests to view "
        "existing reminders; do not use list as fallback for ambiguous creation."
    ),
)
def visible_reminder_tool(
    action: str | None = None,
    title: str | None = None,
    trigger_at: str | None = None,
    duration_minutes: int | None = None,
    reminder_id: str | None = None,
    keyword: str | None = None,
    target_title: str | None = None,
    target_local_date: str | None = None,
    target_local_time: str | None = None,
    target_rrule: str | None = None,
    target_scope: str | None = None,
    new_title: str | None = None,
    new_trigger_at: str | None = None,
    rrule: str | None = None,
    operations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_action = action or ("batch" if operations is not None else "")
    return _execute_visible_reminder_tool_action(
        action=resolved_action,
        title=title,
        trigger_at=trigger_at,
        duration_minutes=duration_minutes,
        reminder_id=reminder_id,
        keyword=keyword,
        target_title=target_title,
        target_local_date=target_local_date,
        target_local_time=target_local_time,
        target_rrule=target_rrule,
        target_scope=target_scope,
        new_title=new_title,
        new_trigger_at=new_trigger_at,
        rrule=rrule,
        operations=operations,
    )
