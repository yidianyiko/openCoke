from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Mapping, Protocol

from coke.turn.agent import ToolExecutionResult
from coke.turn.output_protocol import OutputProtocolValidator, ValidatedOutput
from coke.turn.reminder_list_render import render_reminder_list_reply


class ReminderListToolPort(Protocol):
    def execute_without_staging(
        self,
        command: Mapping[str, Any],
        guard: Any,
    ) -> ToolExecutionResult: ...


@dataclass(frozen=True, slots=True)
class ActionRunnerResult:
    handled: bool
    validated: ValidatedOutput | None
    tool_events: tuple[Mapping[str, Any], ...] = ()


class ActionRunner:
    def run_plain_reminder_list(
        self,
        *,
        account_id: str,
        display_timezone: str,
        user_text: str,
        reminder_tool: ReminderListToolPort,
        guard: Any,
    ) -> ActionRunnerResult:
        command = {
            "operation": "list_reminders",
            "owner_account_id": account_id,
            "display_timezone": display_timezone,
        }
        result = reminder_tool.execute_without_staging(command, guard)
        tool_events = (_tool_event(result),)
        if not result.ok or not _renders_reminder_list(result):
            return ActionRunnerResult(
                handled=False,
                validated=None,
                tool_events=tool_events,
            )

        segment = render_reminder_list_reply(
            result.facts,
            user_text=user_text,
            account_id=account_id,
        )
        validated = OutputProtocolValidator().validate_first_answer(
            {"type": "reply", "segments": [segment]}
        )
        return ActionRunnerResult(
            handled=validated.valid,
            validated=validated if validated.valid else None,
            tool_events=tool_events,
        )


def _renders_reminder_list(result: ToolExecutionResult) -> bool:
    domain_result = result.domain_result
    if domain_result is None:
        return False
    return getattr(domain_result, "reply_contract", None) == "render_reminder_list"


def _tool_event(result: ToolExecutionResult) -> Mapping[str, Any]:
    return {
        "ok": result.ok,
        "facts": dict(result.facts),
        "reason_code": result.reason_code,
        "domain_result": _domain_result_mapping(result.domain_result),
    }


def _domain_result_mapping(domain_result: Any) -> Mapping[str, Any] | None:
    if domain_result is None:
        return None
    if is_dataclass(domain_result):
        return asdict(domain_result)
    if isinstance(domain_result, Mapping):
        return dict(domain_result)
    return None
