from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.inputs import AgentInput, ReminderFirePayload, UserTurnPayload
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

_DELEGATION_BOUNDARY = """Delegation boundary:
- Use reminder_domain only when the user explicitly requests creating, updating, cancelling, completing, or listing a reminder or notification.
- Use scheduling_domain(intent=...) only for explicit user-link, friend-request, friendship/block, or shared-reminder actions.
- Ordinary one-person reminders must use the Reminder Runtime path, not scheduling_domain.
- A shared reminder requires one active friend. If the named person is not an active friend, explain that the user must add them as a friend first.
- If the friend name is ambiguous, ask the user to choose one friend and do not call scheduling_domain.
- Do not treat an iLink QR as a public friend-link QR. iLink is only for the current account's personal-channel binding.
- Ask for confirmation before reset/disable user link, accept/reject/cancel requests, remove friendship, block, or unblock unless the current turn explicitly confirms the exact action.
- Use timezone, calendar_import, or url_context directly - no delegation needed.
- For any other input, respond directly without calling a domain tool.
- Do not invent a reminder or scheduling action from casual mention of time, plans, or activities."""

_DOMAIN_EXECUTION_RESULT_CONTRACT = """Domain execution result contract:
- Reminder and scheduling domain tools return structured DomainExecutionResult JSON.
- Treat operations, facts, missing_fields, and safety_boundary as trusted execution facts.
- Follow reply_contract when wording the final answer.
- Do not claim a write occurred unless outcome == "executed" and an operation reports ok=True with effect="write".
- Do not omit required questions.
- Do not invent ids, dates, times, recurrence, appointment state, reminder state, or confirmation state.
- If unable to complete the requested action, explain the domain failure or ask the needed clarification using the structured domain facts.
- The final wording is yours, but it must be grounded in the structured domain result."""


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
    elif isinstance(agent_input.payload, UserTurnPayload):
        product_notification = agent_input.payload.metadata.get("product_notification")
        if isinstance(product_notification, Mapping):
            lines.append(
                "product_notification: "
                f"{json.dumps(dict(product_notification), ensure_ascii=False)}"
            )
    return "\n".join(lines)


def _agent_instance_profile_block(run_context: AgentRunContext) -> str:
    profile = run_context.agent_instance_profile
    if profile.is_empty():
        return ""

    fields = [
        ("display_name", profile.display_name),
        ("nickname", profile.nickname),
        ("user_address_name", profile.user_address_name),
        ("persona", profile.persona),
        ("background", profile.background),
        ("speaking_style", profile.speaking_style),
        ("extra_rules", profile.extra_rules),
        ("status_place", profile.status_place),
        ("status_action", profile.status_action),
        ("proactive_enabled", profile.proactive_enabled),
        ("memory_enabled", profile.memory_enabled),
    ]
    lines = ["User-configured agent profile:"]
    for key, value in fields:
        if value is None:
            continue
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    return "\n".join(lines)


def build_chat_response_instructions(
    run_context: AgentRunContext,
    agent_input: AgentInput,
) -> str:
    cleaned = _strip_legacy_artifacts(INSTRUCTIONS_CHAT_RESPONSE)
    timezone = run_context.user.timezone or "UTC"
    profile_block = _agent_instance_profile_block(run_context)
    parts = [
        cleaned,
        _runtime_context_block(run_context, agent_input),
    ]
    if profile_block:
        parts.append(profile_block)
    parts.extend(
        [
            _USER_VISIBLE_REPLY_BOUNDARY,
            _DELEGATION_BOUNDARY,
            _DOMAIN_EXECUTION_RESULT_CONTRACT,
            f"Default user timezone: {_instruction_value(timezone)}",
        ]
    )
    return "\n\n".join(parts)
