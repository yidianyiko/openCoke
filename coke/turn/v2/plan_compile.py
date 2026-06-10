from __future__ import annotations

from coke.turn.v2.contracts import (
    CompiledAction,
    CompiledPlan,
    ProposedAction,
    TurnPlan,
)
from coke.turn.v2.param_schema import (
    RequiredParams,
    required_params_by_operation,
)

REQUIRED_PARAMS: RequiredParams = required_params_by_operation()


def compile_plan(plan: TurnPlan) -> CompiledPlan:
    return CompiledPlan(
        actions=tuple(_compile_action(action) for action in plan.actions),
        reply_necessity=plan.reply_necessity,
    )


def _compile_action(action: ProposedAction) -> CompiledAction:
    if action.domain not in REQUIRED_PARAMS:
        return CompiledAction(
            action=action,
            category="not_possible",
            status="unsupported_domain",
            data={"domain": action.domain},
        )
    domain_schema = REQUIRED_PARAMS[action.domain]
    if action.operation not in domain_schema:
        return CompiledAction(
            action=action,
            category="not_possible",
            status="unsupported_operation",
            data={"domain": action.domain, "operation": action.operation},
        )
    missing = tuple(
        param
        for param in domain_schema[action.operation]
        if action.params.get(param) is None
    )
    if missing:
        return CompiledAction(
            action=action,
            category="needs_input",
            status="missing_required_param",
            data={"missing_params": missing},
        )
    return CompiledAction(action=action)
