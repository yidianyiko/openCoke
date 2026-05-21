from __future__ import annotations

import json
import re
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.inputs import AgentInput, ReminderFirePayload
from agent.prompt.agent_instructions_prompt import INSTRUCTIONS_CHAT_RESPONSE

_FORBIDDEN_LINE_PATTERNS = (
    re.compile(r"^3\.\s*Output structured multi-modal messages.*$", re.MULTILINE),
    re.compile(r"^- Strictly output according to the JSON Schema.*$", re.MULTILINE),
    re.compile(r"^- Message types include:.*$", re.MULTILINE),
    re.compile(r"^Output the result as valid JSON,.*$", re.MULTILINE),
)

_LEGACY_BRACKET_REPLACEMENT = (
    "If there is a [reminder tool message] in context, use it to explain the actual state",
    "If a reminder tool result is available in the conversation, use its content to explain the actual state",
)

_USER_VISIBLE_REPLY_BOUNDARY = """User-visible reply boundary:
- Only output the final user-visible reply.
- Do not include analysis, reasoning, scratchpad notes, persona inspection, draft planning, or commentary about prompts, tools, logs, workflows, or system internals.
- If you need to reason internally, keep that reasoning out of the answer and send only the concise reply the user should see."""

_REMINDER_TOOL_BOUNDARY = """Reminder tool boundary:
- Use the reminder tool only when the current user message explicitly asks to create, update, cancel, complete, list, or clarify a reminder/notification/wake-up.
- A plain plan, schedule, intention, deadline, or activity statement is not by itself a reminder request. Reply normally without proposing or asking whether to set a reminder.
- If the user says they plan to do something before/after a time but does not ask to be reminded, do not turn it into a reminder clarification or reminder setup offer.
- Only speak as if a scheduled reminder is firing when the runtime context is a system reminder trigger; for ordinary user messages that mention a clock time, respond to the reported situation instead of delivering the activity cue."""


def _strip_legacy_artifacts(text: str) -> str:
    for pattern in _FORBIDDEN_LINE_PATTERNS:
        text = pattern.sub("", text)
    text = text.replace(*_LEGACY_BRACKET_REPLACEMENT)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _instruction_value(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _runtime_context_block(
    run_context: AgentRunContext,
    agent_input: AgentInput,
) -> str:
    lines = [
        "Trusted runtime context:",
        f"current_time: {_instruction_value(run_context.current_time.isoformat())}",
        f"user_id: {_instruction_value(run_context.user.id)}",
        f"user_nickname: {_instruction_value(run_context.user.nickname or 'User')}",
        f"character_id: {_instruction_value(run_context.character.id)}",
        (
            "character_nickname: "
            f"{_instruction_value(run_context.character.nickname or 'Coke')}"
        ),
        f"platform: {_instruction_value(run_context.platform)}",
        f"input_type: {_instruction_value(agent_input.input_type)}",
        f"conversation_id: {_instruction_value(run_context.conversation.id)}",
    ]
    if run_context.conversation.route_key:
        lines.append(
            f"route_key: {_instruction_value(run_context.conversation.route_key)}"
        )
    if isinstance(agent_input.payload, ReminderFirePayload):
        lines.extend(
            [
                (
                    "event_contract: system reminder delivery; deliver the existing "
                    "reminder to the user; do not create, update, cancel, or list "
                    "reminders for this event."
                ),
                f"reminder_id: {_instruction_value(agent_input.payload.reminder_id)}",
                f"reminder_title: {_instruction_value(agent_input.payload.title)}",
                (
                    "scheduled_for: "
                    f"{_instruction_value(agent_input.payload.scheduled_for.isoformat())}"
                ),
                f"fire_id: {_instruction_value(agent_input.payload.fire_id)}",
            ]
        )
    return "\n".join(lines)


def build_chat_response_instructions(
    run_context: AgentRunContext,
    agent_input: AgentInput,
) -> str:
    cleaned = _strip_legacy_artifacts(INSTRUCTIONS_CHAT_RESPONSE)
    timezone = run_context.user.timezone or "UTC"
    return "\n\n".join(
        [
            cleaned,
            _runtime_context_block(run_context, agent_input),
            _USER_VISIBLE_REPLY_BOUNDARY,
            _REMINDER_TOOL_BOUNDARY,
            f"Default user timezone: {_instruction_value(timezone)}",
        ]
    )
