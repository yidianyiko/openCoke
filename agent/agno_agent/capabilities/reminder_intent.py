from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent.agno_agent.adapters.reminder_command_executor import ReminderCommandExecutor
from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input
from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.tools.reminder_protocol import visible_reminder_tool


def _decision_from_response(response: Any) -> Any:
    return getattr(response, "content", response)


def _decision_value(decision: Any, field: str) -> Any:
    if isinstance(decision, Mapping):
        return decision.get(field)
    return getattr(decision, field, None)


def _visible_reminder_entrypoint() -> Any:
    entrypoint = getattr(visible_reminder_tool, "entrypoint", visible_reminder_tool)
    return getattr(entrypoint, "raw_function", entrypoint)


class ReminderIntentPort:
    def __init__(
        self,
        *,
        detector_agent: Any | None = None,
        command_executor: Any | None = None,
    ) -> None:
        if detector_agent is None:
            from agent.agno_agent.agents import reminder_detect_agent

            detector_agent = reminder_detect_agent
        self.detector_agent = detector_agent
        self.command_executor = command_executor or ReminderCommandExecutor(
            _visible_reminder_entrypoint()
        )

    async def run(
        self,
        input_message: str,
        run_context: AgentRunContext,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        response = await self.detector_agent.arun(
            input=build_reminder_intent_input(input_message, run_context),
            session_state={
                "user": {
                    "id": run_context.user.id,
                    "timezone": run_context.user.timezone,
                },
                "character": {"id": run_context.character.id},
                "conversation": {"id": run_context.conversation.id},
                "platform": run_context.platform,
            },
        )
        decision = _decision_from_response(response)
        intent_type = _decision_value(decision, "intent_type")
        action = _decision_value(decision, "action")

        if intent_type not in {"crud", "query"}:
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"action": "none", "intent_type": intent_type},
                metadata={"durable_write": False},
            )
        if intent_type == "query" and action != "list":
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"action": "none", "intent_type": intent_type},
                metadata={"durable_write": False},
            )

        result = self.command_executor.execute(decision, run_context)
        return CapabilityResult(
            name=result.name,
            ok=result.ok,
            content=dict(result.content or {}),
            error=result.error,
            metadata={**dict(result.metadata or {}), "durable_write": True},
        )
