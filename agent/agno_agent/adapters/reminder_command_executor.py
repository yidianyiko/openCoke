from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult
from agent.agno_agent.tools.reminder_protocol import set_reminder_session_state
from conf.config import CONF
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
    "deadline_at",
    "operations",
)
_TOOL_DECISION_FIELDS = tuple(
    field for field in _REMINDER_DECISION_FIELDS if field != "deadline_at"
)


def _last_failed_tool_result(session_state: dict[str, Any]) -> Mapping[str, Any] | None:
    tool_results = session_state.get("tool_results")
    if not isinstance(tool_results, list):
        return None

    for item in reversed(tool_results):
        if isinstance(item, Mapping) and item.get("ok") is False:
            return item
    return None


def _has_successful_tool_result(session_state: dict[str, Any]) -> bool:
    tool_results = session_state.get("tool_results")
    if not isinstance(tool_results, list):
        return False
    return any(
        isinstance(item, Mapping) and item.get("ok") is True for item in tool_results
    )


def _error_code_from_tool_result(tool_result: Mapping[str, Any]) -> str:
    notes = tool_result.get("extra_notes")
    if isinstance(notes, str):
        for part in notes.split(";"):
            key, separator, value = part.strip().partition("=")
            if separator and key == "error_code" and value:
                return value
    return "ReminderToolFailed"


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


def _rrule_with_deadline(rrule: Any, deadline_at: Any) -> Any:
    if not isinstance(rrule, str) or not rrule.strip():
        return rrule
    if not isinstance(deadline_at, str) or not deadline_at.strip():
        return rrule

    normalized = rrule.strip()
    upper_parts = {part.split("=", 1)[0].upper() for part in normalized.split(";")}
    if "UNTIL" in upper_parts or "COUNT" in upper_parts:
        return normalized

    try:
        deadline = datetime.fromisoformat(deadline_at.strip().replace("Z", "+00:00"))
    except ValueError:
        return normalized
    if deadline.tzinfo is None or deadline.utcoffset() is None:
        return normalized
    until = deadline.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{normalized};UNTIL={until}"


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
        tool_entrypoint: Callable[..., Any],
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
            session_state = _build_session_state(run_context)
            self._session_state_setter(session_state)
            kwargs = {
                field: _decision_value(decision, field)
                for field in _REMINDER_DECISION_FIELDS
            }
            kwargs["operations"] = _normalize_operations(kwargs["operations"])
            kwargs["rrule"] = _rrule_with_deadline(
                kwargs.get("rrule"),
                kwargs.get("deadline_at"),
            )
            kwargs = {field: kwargs.get(field) for field in _TOOL_DECISION_FIELDS}

            tool_result = self._tool_entrypoint(**kwargs)
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

        failed_tool_result = _last_failed_tool_result(session_state)
        if failed_tool_result is not None and not _has_successful_tool_result(
            session_state
        ):
            result_summary = failed_tool_result.get("result_summary")
            content = {}
            if isinstance(result_summary, str) and result_summary.strip():
                content["summary"] = result_summary.strip()
            return CapabilityResult(
                name="reminder",
                ok=False,
                content=content,
                error=_error_code_from_tool_result(failed_tool_result),
                metadata={
                    key: value
                    for key, value in {
                        "tool_name": failed_tool_result.get("tool_name"),
                        "extra_notes": failed_tool_result.get("extra_notes"),
                    }.items()
                    if value is not None
                },
            )

        if isinstance(tool_result, Mapping):
            summary = str(tool_result.get("summary") or "")
        else:
            summary = str(tool_result)

        content: dict[str, Any] = {
            "summary": summary,
            "owner_user_id": run_context.user.id,
            "conversation_id": run_context.conversation.id,
        }
        if isinstance(tool_result, Mapping):
            content["tool_result"] = tool_result

        return CapabilityResult(
            name="reminder",
            ok=True,
            content=content,
        )
