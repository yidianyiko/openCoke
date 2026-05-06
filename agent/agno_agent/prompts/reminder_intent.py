from __future__ import annotations

from agent.agno_agent.runtime.context import AgentRunContext


def build_reminder_intent_input(
    input_message: str, run_context: AgentRunContext
) -> str:
    return "\n".join(
        [
            f"current_time: {run_context.current_time.isoformat()}",
            f"timezone: {run_context.user.timezone or 'UTC'}",
            f"conversation_id: {run_context.conversation.id}",
            "recent_chat_history:",
            run_context.recent_chat_history or "(empty)",
            "user_message:",
            input_message,
        ]
    )
