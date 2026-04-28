from __future__ import annotations

import contextvars
from datetime import datetime
from typing import Any

from agno.tools import tool
from dateutil.rrule import rrulestr

from agent.agno_agent.tools.tool_result import append_tool_result
from util.time_util import get_default_timezone

from .service import DeferredActionService


_context_session_state: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "deferred_action_session_state", default={}
)


def set_deferred_action_session_state(session_state: dict) -> None:
    _context_session_state.set(session_state or {})


def _get_session_state() -> dict:
    return _context_session_state.get()


def _resolve_runtime_timezone(session_state: dict) -> str:
    user = session_state.get("user", {})
    return str(
        user.get("effective_timezone")
        or user.get("timezone")
        or get_default_timezone().key
    )


def _parse_trigger_at(trigger_at: str) -> datetime:
    if not trigger_at:
        raise ValueError("trigger_at is required")
    try:
        parsed = datetime.fromisoformat(trigger_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("trigger_at must be an ISO 8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("trigger_at must include a timezone offset or Z")
    return parsed


def _validate_rrule(rrule: str | None, dtstart: datetime) -> str | None:
    if rrule is None:
        return None
    normalized = rrule.strip()
    if not normalized:
        return None
    if not normalized.startswith("FREQ="):
        raise ValueError("rrule must be an RFC 5545 RRULE string starting with FREQ=")
    try:
        rrulestr(normalized, dtstart=dtstart)
    except Exception as exc:
        raise ValueError(f"Invalid RRULE: {normalized}") from exc
    return normalized


def _target_id(
    service: DeferredActionService,
    *,
    user_id: str,
    reminder_id: str | None,
    keyword: str | None,
    action: str,
) -> str:
    if reminder_id:
        return reminder_id
    if not keyword:
        raise ValueError(f"reminder_id or keyword is required for {action}")
    return str(service.resolve_visible_reminder_by_keyword(user_id, keyword)["_id"])


def _execute_visible_reminder_operation(
    *,
    service: DeferredActionService,
    session_state: dict,
    action: str,
    title: str | None = None,
    trigger_at: str | None = None,
    reminder_id: str | None = None,
    keyword: str | None = None,
    new_title: str | None = None,
    new_trigger_at: str | None = None,
    rrule: str | None = None,
) -> str:
    user = session_state.get("user", {})
    character = session_state.get("character", {})
    conversation = session_state.get("conversation", {})
    user_id = str(user.get("id", ""))
    character_id = str(character.get("_id", ""))
    conversation_id = str(conversation.get("_id", ""))
    timezone = _resolve_runtime_timezone(session_state)

    if action == "create":
        if not title or not trigger_at:
            raise ValueError("title and trigger_at are required for create")
        dtstart = _parse_trigger_at(trigger_at)
        created = service.create_visible_reminder(
            user_id=user_id,
            character_id=character_id,
            conversation_id=conversation_id,
            title=title,
            dtstart=dtstart,
            timezone=timezone,
            rrule=_validate_rrule(rrule, dtstart),
            schedule_kind="floating_local",
            fixed_timezone=False,
        )
        session_state["reminder_created_with_time"] = True
        return f"已创建提醒：{created['title']}"

    if action == "list":
        reminders = service.list_visible_reminders(user_id)
        return "\n".join(
            f"- {item['title']} @ {item['next_run_at'].isoformat() if item.get('next_run_at') else 'none'}"
            for item in reminders
        ) or "暂无提醒"

    if action == "update":
        target_id = _target_id(
            service,
            user_id=user_id,
            reminder_id=reminder_id,
            keyword=keyword,
            action="update",
        )
        updates: dict[str, Any] = {}
        if new_title is not None or title is not None:
            updates["title"] = new_title or title
        if new_trigger_at is not None or trigger_at is not None:
            dtstart = _parse_trigger_at(new_trigger_at or trigger_at or "")
            updates.update(
                {
                    "dtstart": dtstart,
                    "timezone": timezone,
                    "schedule_kind": "floating_local",
                    "fixed_timezone": False,
                }
            )
            session_state["reminder_created_with_time"] = True
            if rrule is not None:
                updates["rrule"] = _validate_rrule(rrule, dtstart)
        elif rrule is not None:
            current = service._require_visible_reminder(target_id, user_id)
            updates["rrule"] = _validate_rrule(rrule, current["dtstart"])
        updated = service.update_visible_reminder(
            action_id=target_id,
            user_id=user_id,
            **updates,
        )
        return f"已更新提醒：{updated['title']}"

    if action == "delete":
        target_id = _target_id(
            service,
            user_id=user_id,
            reminder_id=reminder_id,
            keyword=keyword,
            action="delete",
        )
        deleted = service.delete_visible_reminder(target_id, user_id)
        return f"已删除提醒：{deleted['title']}"

    if action == "complete":
        target_id = _target_id(
            service,
            user_id=user_id,
            reminder_id=reminder_id,
            keyword=keyword,
            action="complete",
        )
        completed = service.complete_visible_reminder(target_id, user_id)
        return f"已完成提醒：{completed['title']}"

    raise ValueError(f"Unsupported action: {action}")


@tool(
    stop_after_tool_call=True,
    description=(
        "Visible reminder management for deferred actions. "
        "Supports create, list, update, delete, complete, and batch for user reminders. "
        "For create/update time changes, trigger_at/new_trigger_at must be ISO 8601 "
        "with an explicit timezone offset or Z, for example 2026-04-28T17:58:00+09:00. "
        "Use RFC 5545 RRULE strings for recurrence, for example FREQ=DAILY."
    ),
)
def visible_reminder_tool(
    action: str,
    title: str | None = None,
    trigger_at: str | None = None,
    reminder_id: str | None = None,
    keyword: str | None = None,
    new_title: str | None = None,
    new_trigger_at: str | None = None,
    rrule: str | None = None,
    operations: list[dict[str, Any]] | None = None,
) -> str:
    session_state = _get_session_state()
    service = DeferredActionService()

    if action == "batch":
        if not operations:
            raise ValueError("operations are required for batch")
        summaries = []
        for operation in operations:
            summary = _execute_visible_reminder_operation(
                service=service,
                session_state=session_state,
                action=str(operation.get("action") or ""),
                title=operation.get("title"),
                trigger_at=operation.get("trigger_at"),
                reminder_id=operation.get("reminder_id"),
                keyword=operation.get("keyword"),
                new_title=operation.get("new_title"),
                new_trigger_at=operation.get("new_trigger_at"),
                rrule=operation.get("rrule"),
            )
            summaries.append(summary)
            append_tool_result(
                session_state,
                tool_name="提醒操作",
                ok=True,
                result_summary=summary,
            )
        return "\n".join(summaries)

    summary = _execute_visible_reminder_operation(
        service=service,
        session_state=session_state,
        action=action,
        title=title,
        trigger_at=trigger_at,
        reminder_id=reminder_id,
        keyword=keyword,
        new_title=new_title,
        new_trigger_at=new_trigger_at,
        rrule=rrule,
    )
    append_tool_result(
        session_state,
        tool_name="提醒操作",
        ok=True,
        result_summary=summary,
    )
    return summary
