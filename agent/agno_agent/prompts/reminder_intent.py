from __future__ import annotations

from agent.prompt.reminder_few_shot import format_reminder_few_shots_for_prompt

from agent.agno_agent.runtime.context import AgentRunContext


def build_reminder_intent_input(
    input_message: str, run_context: AgentRunContext
) -> str:
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
            "",
            "### 当前用户消息",
            input_message,
        ]
    )
