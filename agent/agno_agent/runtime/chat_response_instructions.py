from __future__ import annotations

import re

from agent.agno_agent.runtime.context import AgentRunContext
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


def build_chat_response_instructions(run_context: AgentRunContext) -> str:
    cleaned = _strip_legacy_artifacts(INSTRUCTIONS_CHAT_RESPONSE)
    timezone = run_context.user.timezone or "UTC"
    return "\n\n".join(
        [
            cleaned,
            _USER_VISIBLE_REPLY_BOUNDARY,
            _REMINDER_TOOL_BOUNDARY,
            f"Default user timezone: {timezone}",
        ]
    )
