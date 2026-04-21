from __future__ import annotations

import contextvars

from agno.tools import tool

from agent.agno_agent.tools.tool_result import append_tool_result

from .service import DeferredActionService
from .time_parser import parse_visible_reminder_time


_context_session_state: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "deferred_action_session_state", default={}
)


def set_deferred_action_session_state(session_state: dict) -> None:
    _context_session_state.set(session_state or {})


def _get_session_state() -> dict:
    return _context_session_state.get()


@tool(
    stop_after_tool_call=True,
    description=(
        "Visible reminder management for deferred actions. "
        "Supports create, list, update, delete, and complete for user reminders. "
        "trigger_time/new_trigger_time must use parser-supported formats only: "
        "ISO 8601 with explicit date/time, Chinese relative strings like 3分钟后 or 2小时后, "
        'or Chinese named relative dates like 明天/后天/下周. Never use English forms like "in 1 minute".'
    ),
)
def visible_reminder_tool(
    action: str,
    title: str | None = None,
    trigger_time: str | None = None,
    reminder_id: str | None = None,
    keyword: str | None = None,
    new_title: str | None = None,
    new_trigger_time: str | None = None,
    rrule: str | None = None,
) -> str:
    session_state = _get_session_state()
    user = session_state.get("user", {})
    character = session_state.get("character", {})
    conversation = session_state.get("conversation", {})
    user_id = str(user.get("id", ""))
    character_id = str(character.get("_id", ""))
    conversation_id = str(conversation.get("_id", ""))
    timezone = user.get("timezone") or "Asia/Shanghai"
    base_timestamp = session_state.get("input_timestamp")
    service = DeferredActionService()

    if action == "create":
        if not title or not trigger_time:
            raise ValueError("title and trigger_time are required for create")
        dtstart = parse_visible_reminder_time(
            trigger_time,
            timezone=timezone,
            base_timestamp=base_timestamp,
        )
        created = service.create_visible_reminder(
            user_id=user_id,
            character_id=character_id,
            conversation_id=conversation_id,
            title=title,
            dtstart=dtstart,
            timezone=timezone,
            rrule=rrule,
        )
        session_state["reminder_created_with_time"] = True
        summary = f"已创建提醒：{created['title']}"
    elif action == "list":
        reminders = service.list_visible_reminders(user_id)
        summary = "\n".join(
            f"- {item['title']} @ {item['next_run_at'].isoformat() if item.get('next_run_at') else 'none'}"
            for item in reminders
        ) or "暂无提醒"
    elif action == "update":
        target_id = reminder_id
        if not target_id:
            if not keyword:
                raise ValueError("reminder_id or keyword is required for update")
            target_id = str(
                service.resolve_visible_reminder_by_keyword(user_id, keyword)["_id"]
            )
        updates = {}
        if new_title is not None or title is not None:
            updates["title"] = new_title or title
        if new_trigger_time is not None or trigger_time is not None:
            updates["dtstart"] = parse_visible_reminder_time(
                new_trigger_time or trigger_time,
                timezone=timezone,
                base_timestamp=base_timestamp,
            )
            updates["timezone"] = timezone
        if rrule is not None:
            updates["rrule"] = rrule
        updated = service.update_visible_reminder(
            action_id=target_id,
            user_id=user_id,
            **updates,
        )
        if "dtstart" in updates:
            session_state["reminder_created_with_time"] = True
        summary = f"已更新提醒：{updated['title']}"
    elif action == "delete":
        target_id = reminder_id
        if not target_id:
            if not keyword:
                raise ValueError("reminder_id or keyword is required for delete")
            target_id = str(
                service.resolve_visible_reminder_by_keyword(user_id, keyword)["_id"]
            )
        deleted = service.delete_visible_reminder(target_id, user_id)
        summary = f"已删除提醒：{deleted['title']}"
    elif action == "complete":
        target_id = reminder_id
        if not target_id:
            if not keyword:
                raise ValueError("reminder_id or keyword is required for complete")
            target_id = str(
                service.resolve_visible_reminder_by_keyword(user_id, keyword)["_id"]
            )
        completed = service.complete_visible_reminder(target_id, user_id)
        summary = f"已完成提醒：{completed['title']}"
    else:
        raise ValueError(f"Unsupported action: {action}")

    append_tool_result(
        session_state,
        tool_name="提醒操作",
        ok=True,
        result_summary=summary,
    )
    return summary
