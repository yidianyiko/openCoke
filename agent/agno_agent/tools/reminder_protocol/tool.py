from __future__ import annotations

import contextvars
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agno.tools import tool

from agent.agno_agent.tools.tool_result import append_tool_result
from agent.reminder.errors import InvalidArgument, ReminderError
from agent.reminder.models import (
    AgentOutputTarget,
    Reminder,
    ReminderCreateCommand,
    ReminderPatch,
    ReminderQuery,
)
from agent.reminder.schedule import build_schedule_from_anchor
from agent.reminder.service import ReminderService
from util.time_util import get_default_timezone


_context_session_state: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "reminder_session_state", default={}
)


@dataclass(frozen=True)
class _RuntimeContext:
    owner_user_id: str
    target: AgentOutputTarget
    timezone: str


class _KeywordResolutionError(Exception):
    def __init__(self, *, action: str, keyword: str, match_count: int) -> None:
        self.action = action
        self.keyword = keyword
        self.match_count = match_count
        super().__init__(f"keyword '{keyword}' matched {match_count} reminders")


def set_reminder_session_state(session_state: dict) -> None:
    _context_session_state.set(session_state or {})


def _get_session_state() -> dict:
    return _context_session_state.get()


def _execute_visible_reminder_tool_action(
    *,
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
    service = ReminderService()

    if action == "batch":
        if not operations:
            raise ValueError("operations are required for batch")
        summaries = []
        for operation in operations:
            if not isinstance(operation, dict):
                summary = "提醒操作失败：batch operation must be an object"
                append_tool_result(
                    session_state,
                    tool_name="提醒操作",
                    ok=False,
                    result_summary=summary,
                    extra_notes="action=batch; error_code=InvalidArgument",
                )
                summaries.append(summary)
                continue
            summaries.append(
                _run_operation(
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
            )
        return "\n".join(summaries)

    return _run_operation(
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


def _run_operation(
    *,
    service: ReminderService,
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
    canonical_action = _canonical_action(action)
    try:
        summary, timed_write = _execute_one(
            service=service,
            session_state=session_state,
            action=canonical_action,
            title=title,
            trigger_at=trigger_at,
            reminder_id=reminder_id,
            keyword=keyword,
            new_title=new_title,
            new_trigger_at=new_trigger_at,
            rrule=rrule,
        )
    except _KeywordResolutionError as exc:
        summary = f"{_action_failure_label(canonical_action)}失败：{exc}"
        append_tool_result(
            session_state,
            tool_name="提醒操作",
            ok=False,
            result_summary=summary,
            extra_notes=(
                f"action={canonical_action}; "
                "error_code=AmbiguousReminderKeyword"
            ),
        )
        return summary
    except ReminderError as exc:
        summary = f"{_action_failure_label(canonical_action)}失败：{exc.user_message}"
        append_tool_result(
            session_state,
            tool_name="提醒操作",
            ok=False,
            result_summary=summary,
            extra_notes=f"action={canonical_action}; error_code={exc.code}",
        )
        return summary
    except ValueError as exc:
        summary = f"{_action_failure_label(canonical_action)}失败：{exc}"
        append_tool_result(
            session_state,
            tool_name="提醒操作",
            ok=False,
            result_summary=summary,
            extra_notes=f"action={canonical_action}; error_code=InvalidArgument",
        )
        return summary

    if timed_write:
        session_state["reminder_created_with_time"] = True
    append_tool_result(
        session_state,
        tool_name="提醒操作",
        ok=True,
        result_summary=summary,
        extra_notes=f"action={canonical_action}",
    )
    return summary


def _execute_one(
    *,
    service: ReminderService,
    session_state: dict,
    action: str,
    title: str | None,
    trigger_at: str | None,
    reminder_id: str | None,
    keyword: str | None,
    new_title: str | None,
    new_trigger_at: str | None,
    rrule: str | None,
) -> tuple[str, bool]:
    context = _derive_runtime_context(session_state)

    if action == "create":
        if not title or not trigger_at:
            raise InvalidArgument(
                "Create reminder requires title and trigger_at",
                detail={"action": action},
            )
        command = ReminderCreateCommand(
            title=title,
            schedule=_schedule_from_iso(trigger_at, context.timezone, rrule),
            agent_output_target=context.target,
            created_by_system="agent",
        )
        created = service.create(
            owner_user_id=context.owner_user_id,
            command=command,
        )
        return f"已创建提醒：{created.title}", True

    if action == "list":
        reminders = service.list_for_user(
            owner_user_id=context.owner_user_id,
            query=ReminderQuery(lifecycle_states=["active"]),
        )
        return _format_list_summary(reminders), False

    if action == "update":
        target_id = _resolve_reminder_id(
            service=service,
            owner_user_id=context.owner_user_id,
            reminder_id=reminder_id,
            keyword=keyword,
            action=action,
        )
        patch = _build_patch(
            title=new_title if new_title is not None else title,
            trigger_at=new_trigger_at if new_trigger_at is not None else trigger_at,
            timezone=context.timezone,
            rrule=rrule,
        )
        updated = service.update(
            reminder_id=target_id,
            owner_user_id=context.owner_user_id,
            patch=patch,
        )
        return f"已更新提醒：{updated.title}", patch.schedule is not None

    if action == "cancel":
        target_id = _resolve_reminder_id(
            service=service,
            owner_user_id=context.owner_user_id,
            reminder_id=reminder_id,
            keyword=keyword,
            action=action,
        )
        cancelled = service.cancel(
            reminder_id=target_id,
            owner_user_id=context.owner_user_id,
        )
        return f"已取消提醒：{cancelled.title}", False

    if action == "complete":
        target_id = _resolve_reminder_id(
            service=service,
            owner_user_id=context.owner_user_id,
            reminder_id=reminder_id,
            keyword=keyword,
            action=action,
        )
        completed = service.complete(
            reminder_id=target_id,
            owner_user_id=context.owner_user_id,
        )
        return f"已完成提醒：{completed.title}", False

    raise InvalidArgument(
        "Unsupported reminder action",
        detail={"action": action},
    )


def _derive_runtime_context(session_state: dict) -> _RuntimeContext:
    user = session_state.get("user") or {}
    character = session_state.get("character") or {}
    conversation = session_state.get("conversation") or {}

    owner_user_id = _string_value(user.get("id") or user.get("_id"))
    character_id = _string_value(character.get("_id") or character.get("id"))
    conversation_id = _string_value(
        conversation.get("_id")
        or conversation.get("id")
        or session_state.get("conversation_id")
    )
    route_key = (
        session_state.get("route_key")
        or session_state.get("delivery_route_key")
        or conversation.get("route_key")
    )
    timezone = _string_value(
        user.get("effective_timezone")
        or user.get("timezone")
        or get_default_timezone().key
    )
    return _RuntimeContext(
        owner_user_id=owner_user_id,
        target=AgentOutputTarget(
            conversation_id=conversation_id,
            character_id=character_id,
            route_key=_string_value(route_key) if route_key else None,
        ),
        timezone=timezone,
    )


def _string_value(value: Any) -> str:
    return "" if value is None else str(value)


def _canonical_action(action: str) -> str:
    normalized = (action or "").strip().lower()
    if normalized == "delete":
        return "cancel"
    return normalized


def _schedule_from_iso(
    trigger_at: str,
    timezone: str,
    rrule: str | None,
):
    if not trigger_at:
        raise ValueError("trigger_at is required")
    try:
        anchor_at = datetime.fromisoformat(trigger_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("trigger_at must be an ISO 8601 datetime") from exc
    if anchor_at.tzinfo is None or anchor_at.utcoffset() is None:
        raise ValueError("trigger_at must include a timezone offset or Z")
    return build_schedule_from_anchor(anchor_at, timezone, _normalize_rrule(rrule))


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
) -> ReminderPatch:
    return ReminderPatch(
        title=title,
        schedule=(
            _schedule_from_iso(trigger_at, timezone, rrule)
            if trigger_at is not None
            else None
        ),
    )


def _resolve_reminder_id(
    *,
    service: ReminderService,
    owner_user_id: str,
    reminder_id: str | None,
    keyword: str | None,
    action: str,
) -> str:
    if reminder_id:
        return reminder_id
    if not keyword:
        raise InvalidArgument(
            "reminder_id or keyword is required",
            detail={"action": action},
        )

    reminders = service.list_for_user(
        owner_user_id=owner_user_id,
        query=ReminderQuery(lifecycle_states=["active"]),
    )
    exact_matches = [item for item in reminders if item.title == keyword]
    if exact_matches:
        matches = exact_matches
    else:
        matches = [item for item in reminders if keyword in item.title]
    if len(matches) != 1:
        raise _KeywordResolutionError(
            action=action,
            keyword=keyword,
            match_count=len(matches),
        )
    return matches[0].id


def _format_list_summary(reminders: list[Reminder]) -> str:
    if not reminders:
        return "暂无提醒"
    return "\n".join(
        f"- {item.title} @ "
        f"{item.next_fire_at.isoformat() if item.next_fire_at else 'none'}"
        for item in reminders
    )


def _action_failure_label(action: str) -> str:
    return {
        "create": "创建提醒",
        "update": "更新提醒",
        "cancel": "取消提醒",
        "complete": "完成提醒",
        "list": "列出提醒",
    }.get(action, "提醒操作")


@tool(
    stop_after_tool_call=True,
    description=(
        "Visible reminder management through the reminder command protocol. "
        "Supports create, list, update, cancel/delete, complete, and batch. "
        "For create/update time changes, trigger_at/new_trigger_at must be ISO "
        "8601 with an explicit timezone offset or Z, for example "
        "2026-04-28T17:58:00+09:00. Use RFC 5545 RRULE strings for recurrence, "
        "for example FREQ=DAILY."
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
    return _execute_visible_reminder_tool_action(
        action=action,
        title=title,
        trigger_at=trigger_at,
        reminder_id=reminder_id,
        keyword=keyword,
        new_title=new_title,
        new_trigger_at=new_trigger_at,
        rrule=rrule,
        operations=operations,
    )
