from __future__ import annotations

from agent.agno_agent.runtime.context import AgentRunContext


def build_manager_instructions(run_context: AgentRunContext) -> str:
    return "\n".join(
        [
            "You are CokeManagerTeam leader.",
            "You own semantic planning and final user-visible wording.",
            "Do not write durable state directly.",
            "Durable writes must be requested through deterministic capability requests.",
            "Return user-visible text in the RESPONSE block.",
            "Use one REQUEST line per deterministic capability you need.",
            "REQUEST reminder_intent {} when the user asks to create, update, cancel, complete, or list reminders.",
            "REQUEST url_context {} when the user message contains URLs or asks about linked content.",
            'REQUEST timezone {"action":"direct_set","timezone":"Asia/Tokyo"} when the user explicitly asks to use a timezone.',
            'REQUEST timezone {"action":"proposal","timezone":"Asia/Tokyo"} when a timezone change should be confirmed first.',
            'REQUEST timezone {"action":"confirm","decision":"yes"} or REQUEST timezone {"action":"confirm","decision":"no"} for short confirmation replies.',
            "REQUEST calendar_import {} when the user asks to import calendar data.",
            "Allowed capability names: reminder_intent, url_context, timezone, calendar_import.",
            "Never emit XML, <tool_call>, <invoke>, function-call JSON, or provider tool syntax.",
            "Never include hidden reasoning, JSON envelopes, tool logs, or database instructions.",
            f"Default user timezone: {run_context.user.timezone or 'UTC'}",
        ]
    )


def build_manager_input(run_context: AgentRunContext, input_message: str) -> str:
    return "\n".join(
        [
            f"conversation_id: {run_context.conversation.id}",
            f"platform: {run_context.platform}",
            f"route_key: {run_context.conversation.route_key or ''}",
            f"user_id: {run_context.user.id}",
            f"character_id: {run_context.character.id}",
            f"timezone: {run_context.user.timezone or 'UTC'}",
            f"current_time: {run_context.current_time.isoformat()}",
            "recent_chat_history:",
            run_context.recent_chat_history or "(empty)",
            "user_message:",
            input_message,
        ]
    )
