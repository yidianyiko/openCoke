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
            "### 当前用户消息",
            input_message,
        ]
    )
