from __future__ import annotations

from typing import Any, Mapping, Protocol

from coke.turn.v2.contracts import (
    ActionOutcome,
    CompiledAction,
    CompiledPlan,
    SettledOutcome,
)


class ActionHandler(Protocol):
    def resolve_and_stage(
        self,
        compiled_action: CompiledAction,
        guard: Any,
    ) -> ActionOutcome: ...


class ExecutionOutcomeBuilder:
    def __init__(self) -> None:
        self._outcomes: list[ActionOutcome] = []

    def add(self, outcome: ActionOutcome) -> None:
        self._outcomes.append(outcome)

    def build(self) -> SettledOutcome:
        return SettledOutcome(outcomes=tuple(self._outcomes))


class ActionExecutor:
    def __init__(self, handlers: Mapping[str, ActionHandler]) -> None:
        self._handlers = dict(handlers)

    def execute(self, compiled_plan: CompiledPlan, guard: Any) -> SettledOutcome:
        builder = ExecutionOutcomeBuilder()
        for compiled_action in compiled_plan.actions:
            builder.add(self._execute_one(compiled_action, guard))
        return builder.build()

    def _execute_one(
        self,
        compiled_action: CompiledAction,
        guard: Any,
    ) -> ActionOutcome:
        if compiled_action.category is not None:
            return ActionOutcome(
                category=compiled_action.category,
                status=compiled_action.status or "compiled_action_blocked",
                data=compiled_action.data,
            )
        action = compiled_action.action
        if action is None:
            return ActionOutcome(
                category="not_possible",
                status="invalid_compiled_action",
            )
        handler = self._handlers.get(action.domain)
        if handler is None:
            return ActionOutcome(
                category="not_possible",
                status="unsupported_domain_handler",
                data={"domain": action.domain, "operation": action.operation},
            )
        return handler.resolve_and_stage(compiled_action, guard)
