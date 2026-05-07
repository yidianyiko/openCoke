from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.tools.reminder_protocol import set_reminder_session_state
from util.log_util import get_logger


logger = get_logger(__name__)


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


def _normalize_operation(operation: Any) -> Any:
    if isinstance(operation, Mapping):
        return dict(operation)

    model_dump = getattr(operation, "model_dump", None)
    if callable(model_dump):
        return model_dump()

    if is_dataclass(operation) and not isinstance(operation, type):
        return asdict(operation)

    try:
        values = vars(operation)
    except TypeError:
        return operation

    public_values = {
        key: value
        for key, value in values.items()
        if not key.startswith("_") and not callable(value)
    }
    return public_values or operation


def _normalize_operations(operations: Any) -> list[Any] | None:
    if not operations:
        return None
    if isinstance(operations, (str, bytes)):
        return [operations]
    try:
        return [_normalize_operation(operation) for operation in operations]
    except TypeError:
        return [_normalize_operation(operations)]


def _build_session_state(run_context: AgentRunContext) -> dict[str, Any]:
    session_state: dict[str, Any] = {
        "user": {
            "id": run_context.user.id,
            "timezone": run_context.user.timezone,
        },
        "character": {"id": run_context.character.id},
        "conversation": {
            "id": run_context.conversation.id,
            "route_key": run_context.conversation.route_key,
        },
        "platform": run_context.platform,
        "current_time": run_context.current_time.isoformat(),
    }

    if run_context.conversation.route_key:
        session_state["route_key"] = run_context.conversation.route_key
        session_state["delivery_route_key"] = run_context.conversation.route_key

    return session_state


class ReminderCommandExecutor:
    def __init__(
        self,
        tool_entrypoint: Callable[..., str],
        *,
        session_state_setter: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._tool_entrypoint = tool_entrypoint
        self._session_state_setter = session_state_setter or set_reminder_session_state

    def execute(
        self,
        decision: Any,
        run_context: AgentRunContext,
    ) -> CapabilityResult:
        try:
            self._session_state_setter(_build_session_state(run_context))
            kwargs = {
                field: _decision_value(decision, field)
                for field in _REMINDER_DECISION_FIELDS
            }
            kwargs["operations"] = _normalize_operations(kwargs["operations"])

            summary = self._tool_entrypoint(**kwargs)
        except Exception as exc:
            logger.exception("ReminderCommandExecutor adapter failed")
            return CapabilityResult(
                name="reminder",
                ok=False,
                content={},
                error="ReminderCommandExecutorError",
                metadata={
                    "error_type": type(exc).__name__,
                    "message": "adapter failed",
                },
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
