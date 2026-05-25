from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.domain_results import (
    DomainError,
    DomainExecutionResult,
    DomainOperationResult,
    ReplyContract,
    ReplyFactRequirement,
)
from agent.agno_agent.tools.reminder_protocol import set_reminder_session_state
from util.log_util import get_logger

logger = get_logger(__name__)


_REMINDER_DECISION_FIELDS = (
    "action",
    "title",
    "trigger_at",
    "duration_minutes",
    "reminder_id",
    "keyword",
    "target_title",
    "target_local_date",
    "target_local_time",
    "target_rrule",
    "target_scope",
    "new_title",
    "new_trigger_at",
    "rrule",
    "deadline_at",
    "list_from_local_date",
    "list_to_local_date",
    "list_title_query",
    "list_states",
    "operations",
)
_TOOL_DECISION_FIELDS = tuple(
    field for field in _REMINDER_DECISION_FIELDS if field != "deadline_at"
)
_LIST_SCOPE_FIELDS = (
    "list_from_local_date",
    "list_to_local_date",
    "list_title_query",
    "list_states",
)
_OPERATION_TOOL_DECISION_FIELDS = tuple(
    field for field in _TOOL_DECISION_FIELDS if field not in _LIST_SCOPE_FIELDS
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


def _empty_string_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _normalize_tool_operation(operation: Any) -> Any:
    operation = _normalize_operation(operation)
    if not isinstance(operation, Mapping):
        return operation
    return {
        field: (
            str(operation.get("action") or "")
            if field == "action"
            else _empty_string_to_none(operation.get(field))
        )
        for field in _OPERATION_TOOL_DECISION_FIELDS
        if field != "operations"
    }


def _normalize_operations(operations: Any) -> list[Any] | None:
    if not operations:
        return None
    if isinstance(operations, (str, bytes)):
        return [operations]
    try:
        return [_normalize_tool_operation(operation) for operation in operations]
    except TypeError:
        return [_normalize_tool_operation(operations)]


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
    ) -> DomainExecutionResult:
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
            kwargs = {
                field: (
                    kwargs.get(field)
                    if field in {"action", "operations"}
                    else _empty_string_to_none(kwargs.get(field))
                )
                for field in _TOOL_DECISION_FIELDS
            }
            if kwargs.get("action") != "list":
                for field in _LIST_SCOPE_FIELDS:
                    kwargs.pop(field, None)

            tool_result = self._tool_entrypoint(**kwargs)
        except Exception as exc:
            logger.exception("ReminderCommandExecutor adapter failed")
            return _failed_domain_result(
                action=str(_decision_value(decision, "action") or "unknown"),
                code="ReminderCommandExecutorError",
                message="adapter failed",
                detail={
                    "error_type": type(exc).__name__,
                },
            )

        if not isinstance(tool_result, Mapping):
            return _failed_domain_result(
                action=str(_decision_value(decision, "action") or "unknown"),
                code="ReminderToolInvalidResult",
                message="reminder tool returned a non-mapping result",
                detail={"result_type": type(tool_result).__name__},
            )

        if tool_result.get("ok") is not True:
            return _failed_domain_result(
                action=str(
                    tool_result.get("action")
                    or _decision_value(decision, "action")
                    or "unknown"
                ),
                code=str(tool_result.get("error_code") or "ReminderToolFailed"),
                message=str(tool_result.get("summary") or "Reminder tool failed"),
                detail={"summary": tool_result.get("summary")},
            )

        operations = _operations_from_tool_result(tool_result)
        return DomainExecutionResult(
            domain="reminder",
            outcome="executed",
            operations=operations,
            missing_fields=(),
            safety_boundary=None,
            reply_contract=_reply_contract_for_operations(operations),
        )


def _operations_from_tool_result(
    tool_result: Mapping[str, Any],
) -> Sequence[DomainOperationResult]:
    if tool_result.get("action") == "batch":
        return tuple(
            operation
            for item in tool_result.get("operations") or ()
            if isinstance(item, Mapping)
            for operation in _operations_from_tool_result(item)
        )

    action = str(tool_result.get("action") or "none")
    if tool_result.get("ok") is False:
        code = str(tool_result.get("error_code") or "ReminderToolFailed")
        error = DomainError(
            code=code,
            message=str(tool_result.get("summary") or "Reminder tool failed"),
            retryable=code in {"ReminderCommandExecutorError", "ReminderAdapterError"},
            detail={"summary": tool_result.get("summary")},
        )
        return (
            DomainOperationResult(
                action=action,
                ok=False,
                effect="none",
                entity_type="reminder",
                entity_id=None,
                facts={},
                error=error,
            ),
        )

    if action == "list":
        reminders = [
            item
            for item in tool_result.get("reminders") or ()
            if isinstance(item, Mapping)
        ]
        return (
            DomainOperationResult(
                action="list",
                ok=True,
                effect="read",
                entity_type="reminder",
                entity_id=None,
                facts={
                    "summary": tool_result.get("summary"),
                    "visible_summary": tool_result.get("summary"),
                    "count": len(reminders),
                    "reminder_ids": tuple(
                        str(item.get("id") or "") for item in reminders
                    ),
                    "reminders": tuple(_reminder_facts(item) for item in reminders),
                },
            ),
        )

    reminder = tool_result.get("reminder")
    if not isinstance(reminder, Mapping):
        return (
            DomainOperationResult(
                action=action,
                ok=True,
                effect=_effect_for_reminder_action(action),
                entity_type="reminder",
                entity_id=None,
                facts={},
            ),
        )

    return (
        DomainOperationResult(
            action=action,
            ok=True,
            effect=_effect_for_reminder_action(action),
            entity_type="reminder",
            entity_id=_optional_str(reminder.get("id")),
            facts={
                **_reminder_facts(reminder),
                "summary": tool_result.get("summary"),
                "visible_summary": _visible_reminder_summary(
                    action, tool_result, reminder
                ),
            },
        ),
    )


def _reminder_facts(reminder: Mapping[str, Any]) -> dict[str, Any]:
    schedule = (
        reminder.get("schedule")
        if isinstance(reminder.get("schedule"), Mapping)
        else {}
    )
    target = (
        reminder.get("agent_output_target")
        if isinstance(reminder.get("agent_output_target"), Mapping)
        else {}
    )
    return {
        "title": reminder.get("title"),
        "local_date": schedule.get("local_date"),
        "local_time": schedule.get("local_time"),
        "timezone": schedule.get("timezone"),
        "rrule": schedule.get("rrule"),
        "duration_minutes": schedule.get("duration_minutes"),
        "conversation_id": target.get("conversation_id"),
        "character_id": target.get("character_id"),
        "route_key": target.get("route_key"),
        "lifecycle_state": reminder.get("lifecycle_state"),
        "owner_user_id": reminder.get("owner_user_id"),
        "metadata": dict(reminder.get("metadata") or {}),
    }


_WEEKDAY_LABELS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def _visible_reminder_summary(
    action: str,
    tool_result: Mapping[str, Any],
    reminder: Mapping[str, Any],
) -> str | None:
    if action not in {"create", "update"}:
        summary = tool_result.get("summary")
        return str(summary) if isinstance(summary, str) and summary.strip() else None
    schedule = (
        reminder.get("schedule")
        if isinstance(reminder.get("schedule"), Mapping)
        else {}
    )
    title = str(reminder.get("title") or "").strip()
    local_date = str(schedule.get("local_date") or "").strip()
    local_time = str(schedule.get("local_time") or "").strip()
    if not title or not local_date or not local_time:
        summary = tool_result.get("summary")
        return str(summary) if isinstance(summary, str) and summary.strip() else None
    try:
        weekday = _WEEKDAY_LABELS[datetime.fromisoformat(local_date).weekday()]
    except (ValueError, IndexError):
        weekday = ""
    time_label = _local_time_label(local_time)
    if weekday:
        return f"已创建提醒：{title}（{local_date} {weekday} {time_label}）"
    return f"已创建提醒：{title}（{local_date} {time_label}）"


def _local_time_label(local_time: str) -> str:
    parts = str(local_time or "").split(":")
    if len(parts) >= 3 and parts[2][:2] != "00":
        return ":".join((parts[0].zfill(2), parts[1].zfill(2), parts[2][:2].zfill(2)))
    if len(parts) >= 2:
        return ":".join((parts[0].zfill(2), parts[1].zfill(2)))
    return str(local_time or "")


def _effect_for_reminder_action(action: str) -> str:
    if action in {"create", "update", "cancel", "complete"}:
        return "write"
    if action == "list":
        return "read"
    return "none"


def _reply_contract_for_operations(
    operations: Sequence[DomainOperationResult],
) -> ReplyContract:
    write_index = next(
        (
            index
            for index, operation in enumerate(operations)
            if operation.effect == "write" and operation.ok
        ),
        None,
    )
    if write_index is not None:
        return ReplyContract(
            intent="confirm_execution",
            required_facts=(
                ReplyFactRequirement(path=f"operations[{write_index}].facts.title"),
                ReplyFactRequirement(
                    path=f"operations[{write_index}].facts.local_date"
                ),
                ReplyFactRequirement(
                    path=f"operations[{write_index}].facts.local_time"
                ),
                ReplyFactRequirement(path=f"operations[{write_index}].facts.rrule"),
            ),
            required_questions=(),
            prohibited_claims=("not_created", "needs_more_info"),
            allow_rephrase=True,
        )
    list_index = next(
        (
            index
            for index, operation in enumerate(operations)
            if operation.action == "list" and operation.ok
        ),
        None,
    )
    if list_index is not None:
        return ReplyContract(
            intent="direct_answer",
            required_facts=(
                ReplyFactRequirement(path=f"operations[{list_index}].facts.count"),
                ReplyFactRequirement(path=f"operations[{list_index}].facts.reminders"),
                ReplyFactRequirement(
                    path=f"operations[{list_index}].facts.visible_summary"
                ),
            ),
            required_questions=(),
            prohibited_claims=("reminder_created",),
            allow_rephrase=True,
        )
    return ReplyContract(
        intent="direct_answer",
        required_facts=(),
        required_questions=(),
        prohibited_claims=("reminder_created",),
        allow_rephrase=True,
    )


def _failed_domain_result(
    *,
    action: str,
    code: str,
    message: str,
    detail: Mapping[str, Any],
) -> DomainExecutionResult:
    error = DomainError(
        code=code,
        message=message,
        retryable=code in {"ReminderCommandExecutorError", "ReminderAdapterError"},
        detail=detail,
    )
    return DomainExecutionResult(
        domain="reminder",
        outcome="failed",
        operations=(
            DomainOperationResult(
                action=action,
                ok=False,
                effect="none",
                entity_type="reminder",
                entity_id=None,
                facts={},
                error=error,
            ),
        ),
        missing_fields=(),
        safety_boundary=None,
        reply_contract=ReplyContract(
            intent="report_failure",
            required_facts=(),
            required_questions=(),
            prohibited_claims=("reminder_created",),
            allow_rephrase=True,
        ),
        error=error,
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
