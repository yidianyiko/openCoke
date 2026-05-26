from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.inputs import AgentInput, ReminderFirePayload, UserTurnPayload
from agent.prompt.agent_instructions_prompt import INSTRUCTIONS_CHAT_RESPONSE
from agent.prompt.onboarding_prompt import get_onboarding_context

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
- Output exactly one parseable JSON object.
- The JSON object must have this shape: {"MultiModalResponses": [{"type": "text", "content": "message text"}]}.
- Use 1 to 3 text messages. Prefer one message for concise confirmations, tool result summaries, URLs, dense instructions, or replies where splitting would reduce clarity.
- Segment only when it feels natural for chat. Segments should not be mechanically equal-sized.
- Do not output voice or photo items in this version.
- Do not output analysis, reasoning, scratchpad notes, persona inspection, draft planning, prompt commentary, tool logs, workflow internals, or any non-user-visible fields.
- For greetings, capability questions, and first-chat onboarding, reply directly with a concise non-empty introduction. Do not call tools and do not return blank content.
- Do not output any text outside the JSON object."""

_DELEGATION_BOUNDARY = """Delegation boundary:
- Use reminder_domain only when the user explicitly requests creating, updating, cancelling, completing, or listing a reminder or notification.
- "我有什么提醒", "我设过哪些 X 提醒", "列一下我的提醒", and "what reminders do I have" are explicit reminder listing requests; call reminder_domain instead of asking the user to restate the query.
- "完成今天的 X 提醒", "完成 X 提醒", and "mark the X reminder done" are explicit reminder completion requests; call reminder_domain instead of answering directly.
- Use scheduling_domain(intent=...) only for explicit user-link, friend-request, friendship, or shared-reminder actions.
- scheduling_domain accepts only one argument: intent. Never pass request_id, friend_request_id, id, _model_supplied_args, or other parameters; the inner worker resolves names and IDs from the user's message.
- When the user explicitly directs a scheduling action with a clear target — send a friend request by link code, accept / reject / cancel a friend request, remove a friendship, create / accept / reject / cancel a shared reminder, get / reset / disable the user link, list friends / friend requests / shared reminders — you MUST call scheduling_domain with the matching intent in this same turn. Avoid intention-only phrasing like "我帮你看一下", "let me check", or "I'll go look" in place of the call. An explicit user directive IS the confirmation; re-prompt only if target or verb is ambiguous.
- "加好友" / "加上 X" / "add friend" plus a user link code is a send_friend_request_by_user_link_code directive.
- Ordinary one-person reminders must use the Reminder Runtime path, not scheduling_domain.
- A shared reminder requires one active friend. If the named person is not an active friend, explain that the user must add them as a friend first.
- For create_shared_reminder, derive the title from the concrete shared item the user is asking to schedule in the current turn. Do not substitute a product-domain default or an older conversation topic for the current requested item.
- If the friend name is ambiguous, ask the user to choose one friend and do not call scheduling_domain.
- Coke reminders are the calendar source for friend availability. Do not use Google Calendar for friend availability in this feature.
- For friend availability ("X 这周哪些时间空", "看看 X 的空闲时间", "约 X 一起 Y" before a time is settled, or "is X free at T?"), call scheduling_domain(intent="list_friend_calendar_facts") in this same turn. Do not call list_friends first, ask whether they are friends, or block on friendship confirmation; the resolver fails closed on ambiguity.
- For shared-reminder status, history, or own course overview queries, call list_shared_reminders. Pass friend_name when the user names a friend, pass status when the user asks about a specific state like pending, accepted, rejected, cancelled, expired, or invalidated, and omit friend_name with from_date / to_date / timezone for current-account queries such as "我今天有几节课".
- When no date range is provided, supply the next 7 local calendar days using the target friend's timezone when available, otherwise the current conversation timezone.
- list_friend_calendar_facts returns privacy-preserving busy intervals only. The tool returns busy intervals only; you calculate how to describe free time and you show only free intervals to the user.
- Do not reveal reminder titles, prompts, metadata, ids, or output targets from a friend's calendar facts.
- For a reminder about attending a fitness class, lesson, or session, use 60 minutes unless the user states another duration. This duration choice is LLM policy; the backend must only persist the chosen interval.
- Do not treat an iLink QR as a public friend-link QR. iLink is only for the current account's personal-channel binding.
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
- When confirming or listing reminders, preserve the exact title text from reminder facts, including emoji, symbols, and Chinese text.
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


def _character_prompt_block(run_context: AgentRunContext) -> str:
    metadata = getattr(run_context.character, "metadata", {})
    description = metadata.get("description") if isinstance(metadata, Mapping) else None
    if not isinstance(description, str) or not description.strip():
        return ""
    return "Default character prompt:\n" + description.strip()


def _onboarding_prompt_block(run_context: AgentRunContext) -> str:
    onboarding_context = get_onboarding_context(
        bool(getattr(run_context, "is_new_user", False))
    ).strip()
    if not onboarding_context:
        return ""
    return "First-chat onboarding prompt:\n" + onboarding_context


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
    character_prompt_block = _character_prompt_block(run_context)
    onboarding_prompt_block = _onboarding_prompt_block(run_context)
    profile_block = _agent_instance_profile_block(run_context)
    parts = [cleaned]
    if character_prompt_block:
        parts.append(character_prompt_block)
    if onboarding_prompt_block:
        parts.append(onboarding_prompt_block)
    parts.append(_runtime_context_block(run_context, agent_input))
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
