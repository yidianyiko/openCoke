from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult


_REMINDER_DECISION_FIELDS = (
    "action",
    "title",
    "trigger_at",
    "reminder_id",
    "keyword",
    "new_title",
    "new_trigger_at",
    "rrule",
    "operations",
)


def _decision_value(decision: Any, field: str) -> Any:
    if isinstance(decision, Mapping):
        return decision.get(field)

    get_value = getattr(decision, "get", None)
    if callable(get_value):
        return get_value(field)

    return getattr(decision, field, None)


class ReminderCommandExecutor:
    def __init__(self, tool_entrypoint: Callable[..., str]) -> None:
        self._tool_entrypoint = tool_entrypoint

    def execute(
        self,
        decision: Any,
        run_context: AgentRunContext,
    ) -> CapabilityResult:
        try:
            kwargs = {
                field: _decision_value(decision, field)
                for field in _REMINDER_DECISION_FIELDS
            }
            if not kwargs["operations"]:
                kwargs["operations"] = None

            kwargs.update(
                {
                    "owner_user_id": run_context.user.id,
                    "character_id": run_context.character.id,
                    "conversation_id": run_context.conversation.id,
                    "timezone": run_context.user.timezone,
                    "platform": run_context.platform,
                }
            )

            summary = self._tool_entrypoint(**kwargs)
        except Exception as exc:
            return CapabilityResult(
                name="reminder",
                ok=False,
                content={},
                error="ReminderCommandExecutorError",
                metadata={"message": str(exc)},
            )

        return CapabilityResult(
            name="reminder",
            ok=True,
            content={
                "summary": summary,
                "owner_user_id": run_context.user.id,
                "conversation_id": run_context.conversation.id,
            },
        )
