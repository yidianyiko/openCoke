from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from coke.turn.context import ToolProfile, TurnMode


@dataclass(frozen=True, slots=True)
class DomainExecutionResult:
    domain: str
    intent: str
    action: str
    effect: str
    intent_fulfilled: bool
    visible_summary: str
    reply_contract: str
    privacy_notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    ok: bool
    facts: Mapping[str, Any]
    reason_code: str | None = None
    domain_result: DomainExecutionResult | None = None


class StateChangingToolPort(Protocol):
    def execute(
        self, command: Mapping[str, Any], guard: Any
    ) -> ToolExecutionResult: ...


@dataclass(frozen=True, slots=True)
class AgentToolPorts:
    reminder_tool: StateChangingToolPort | None = None
    social_scheduling_tool: StateChangingToolPort | None = None
    calendar_import_tool: StateChangingToolPort | None = None
    identity_access_tool: StateChangingToolPort | None = None
    settings_tool: StateChangingToolPort | None = None


@dataclass(frozen=True, slots=True)
class AgentRequest:
    turn_id: str
    conversation_id: str
    account_id: str
    mode: TurnMode
    trigger_type: str
    payload: Mapping[str, Any]
    trusted_facts: Mapping[str, Any]
    tool_profile: ToolProfile
    freshness_guard: Any
    context: Any
    current_input_messages: tuple[Any, ...] = ()
    run_id: str | None = None


@dataclass(frozen=True, slots=True)
class AgentResult:
    output: Mapping[str, Any] | None = None
    timed_out: bool = False
    task_id: str | None = None
    blank_output: bool = False

    @classmethod
    def completed(
        cls, output: Mapping[str, Any] | None, *, blank_output: bool = False
    ) -> AgentResult:
        return cls(output=output, blank_output=blank_output)

    @classmethod
    def timeout(cls, task_id: str) -> AgentResult:
        return cls(timed_out=True, task_id=task_id)


class InteractionAgent(Protocol):
    def invoke(self, request: AgentRequest) -> AgentResult: ...

    async def ainvoke(self, request: AgentRequest) -> AgentResult: ...

    async def cancel(self, run_id: str) -> bool: ...

    def complete_async(self, task_id: str) -> AgentResult: ...
