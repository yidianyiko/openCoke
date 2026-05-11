from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from agent.prompt.reminder_few_shot import format_reminder_few_shots_for_prompt

from agent.agno_agent.runtime.context import AgentRunContext


def _json_safe_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_safe_metadata(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_metadata(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def build_reminder_intent_input(
    input_message: str, run_context: AgentRunContext
) -> str:
    pending_workflow = run_context.runtime_metadata.get("pending_workflow")
    workflow_lines: list[str] = []
    if pending_workflow:
        workflow_lines = [
            "",
            "### Active Pending Workflow",
            json.dumps(
                _json_safe_metadata(pending_workflow),
                ensure_ascii=False,
                sort_keys=True,
            ),
        ]

    return "\n".join(
        [
            "### 当前时间",
            run_context.current_time.isoformat(),
            "",
            "### 用户时区",
            run_context.user.timezone or "UTC",
            "",
            "### conversation_id",
            run_context.conversation.id,
            "",
            "### 最近对话上下文（最近5条）",
            run_context.recent_chat_history or "(empty)",
            "",
            "### Reminder Few-Shot Decisions",
            format_reminder_few_shots_for_prompt(),
            *workflow_lines,
            "",
            "### Workflow Boundary",
            "workflow_update is only for pending clarification workflows.",
            "When no pending-workflow block is present, do not output workflow_update.",
            "Complete CRUD decisions must omit workflow_update.",
            "Never attach workflow_update to create, update, delete, complete, batch, or list decisions.",
            "One-shot deadline wording such as 'before/by 22:30' is not a concrete trigger_at; clarify for when to remind unless the user says to remind at that deadline.",
            "For recurring cadence wording with an end phrase such as '到/直到/until + clock/date', treat that end phrase as deadline_at. Use trigger_at for the first future occurrence in the cadence, not for the ending deadline unless it is also the first occurrence.",
            "Need/intention statements such as 'I need to do X at Y' are discussion, not clarify, unless the user asks for reminder supervision.",
            "Meta discussion or complaints about reminder/alarm behavior, acknowledgement, whether replies are required, or how reminders stay active are discussion unless the same message asks for a concrete reminder operation.",
            "Plans to test, improve, or discuss reminder functionality/capability are discussion unless the same message asks for a concrete reminder operation.",
            "Do not ask whether to set a reminder for ordinary plans or need/intention statements; return discussion.",
            "Pomodoro/tomato timer starts are timed reminder requests: if the user asks to start a new Pomodoro/tomato timer and asks to be reminded at the end/time without an explicit duration, use 25 minutes after Time as trigger_at.",
            "Relative delays such as after 1 min, 20min later, 过20min, or in 10 minutes are concrete; resolve them from Time to trigger_at.",
            "Completion-conditioned reminders such as after I finish/read/watch this are not schedulable without a clock or duration; clarify for when to remind.",
            "Status-only or referential fragments such as 'not done yet', '还没做', '这件事', or 'that' are not reminder content unless current-turn task text or recent context names the task; clarify for the task/content.",
            "Noisy filler before a concrete clock time is not recurrence evidence.",
            "Undesignated local clock times attached to a reminder task are concrete; if the clock has passed, resolve the next future local occurrence and do not ask for date or trigger_at.",
            "Day-of-month wording before the reminder verb and clock, such as '22号早上9点提醒我', is an explicit reminder date; preserve that day in trigger_at.",
            "Do not use RRULE or explicit_cadence unless the user supplies recurrence frequency or interval wording.",
            "Every batch create decision must include top-level schedule_basis and schedule_evidence; do not put them only inside operations.",
            "Clarify and discussion decisions must use empty action and empty operations.",
            "A bounded window with explicit start date, start clock, end clock, cadence, and reminder content is complete; use trigger_at for the first occurrence and deadline_at for the window end.",
            "Weekly recurrence with listed weekdays must include every listed weekday in BYDAY; do not keep only the first weekday.",
            "Weekday names used as a recurrence cadence are concrete; create the weekly recurrence and do not ask which calendar date.",
            "If an interval schedule includes a manual correction or exception to occurrence times, clarify for the exact occurrence list instead of approximating with RRULE.",
            "For a bounded cadence, wording that stops the cadence at or after the same deadline is the deadline boundary, not a manual correction or occurrence-time exception.",
            "Do not ask for frequency confirmation unless the user explicitly requests a cadence or recurrence.",
            "",
            "### 当前用户消息",
            input_message,
        ]
    )
