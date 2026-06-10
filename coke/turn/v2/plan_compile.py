from __future__ import annotations

from typing import Mapping

from coke.turn.v2.contracts import (
    CompiledAction,
    CompiledPlan,
    ProposedAction,
    TurnPlan,
)

RequiredParams = Mapping[str, Mapping[str, tuple[str, ...]]]

REQUIRED_PARAMS: RequiredParams = {
    "calendar_import": {
        "import": ("source",),
    },
    "friendship": {
        "add_via_code": ("code",),
        "get_friend_link": (),
        "list_friends": (),
        "remove_friend": ("friend",),
    },
    "reminder": {
        "batch_create": ("items",),
        "complete": ("match",),
        "create": ("content",),
        "delete": ("match",),
        "list": (),
        "update": ("match",),
    },
    "settings": {
        "set_timezone": ("timezone_text",),
        "toggle_memory": ("enabled",),
        "toggle_proactive": ("enabled",),
        "update_settings": ("preference",),
    },
    "social_scheduling": {
        "availability_query": ("participant",),
        "cancel_shared_reminder": ("participant", "match"),
        "create_shared_reminder": ("participant", "content"),
        "list_shared": (),
    },
}


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
