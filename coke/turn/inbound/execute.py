from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Protocol

from coke.turn.inbound.contracts import (
    ActionOutcome,
    CompiledAction,
    CompiledPlan,
    ProposedAction,
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

    def execute(
        self,
        compiled_plan: CompiledPlan,
        guard: Any,
        action_context: Mapping[str, Any] | None = None,
    ) -> SettledOutcome:
        builder = ExecutionOutcomeBuilder()
        for compiled_action in compiled_plan.actions:
            builder.add(self._execute_one(compiled_action, guard, action_context))
        return builder.build()

    def _execute_one(
        self,
        compiled_action: CompiledAction,
        guard: Any,
        action_context: Mapping[str, Any] | None = None,
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
        # Inject the authenticated trusted context (account ids, timezone) into
        # the action params. The planner never provides these — they come from the
        # turn's trusted facts. Trusted context WINS on any collision so a
        # hallucinated account id can never override the authenticated account.
        if action_context:
            enriched = ProposedAction(
                domain=action.domain,
                operation=action.operation,
                params={**dict(action.params), **dict(action_context)},
            )
            compiled_action = replace(compiled_action, action=enriched)
        return handler.resolve_and_stage(compiled_action, guard)
