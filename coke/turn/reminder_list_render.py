from __future__ import annotations

from typing import Any, Mapping


def render_reminder_list_reply(
    facts: Mapping[str, Any],
    *,
    user_text: str,
    account_id: str,
) -> str:
    del account_id
    count = facts.get("count", 0)
    chinese = looks_chinese(user_text)
    if chinese:
        lines = [f"你现在一共有 {count} 个提醒："]
    else:
        lines = [f"You currently have {count} reminders:"]

    reminders = facts.get("reminders")
    if isinstance(reminders, list):
        for index, reminder in enumerate(reminders, start=1):
            if isinstance(reminder, Mapping):
                lines.append(render_reminder_list_line(index, reminder, chinese))
    return "\n".join(lines)


def render_reminder_list_line(
    index: int,
    reminder: Mapping[str, Any],
    chinese: bool,
) -> str:
    content = str(reminder.get("content") or "").strip()
    time_value = reminder.get("display_time_label") or reminder.get("next_fire_at")
    time_label = (
        str(time_value) if time_value else ("未设定时间" if chinese else "unscheduled")
    )
    if chinese:
        return f"{index}. {content}（{time_label}）"
    return f"{index}. {content} ({time_label})"


def looks_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)
