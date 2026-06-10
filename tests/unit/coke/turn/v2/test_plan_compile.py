from __future__ import annotations

from coke.turn.v2.contracts import CompiledAction, ProposedAction, TurnPlan
from coke.turn.v2.plan_compile import compile_plan


def test_compile_plan_accepts_valid_action() -> None:
    action = ProposedAction(
        domain="reminder",
        operation="delete",
        params={"match": "gym"},
    )

    compiled = compile_plan(TurnPlan(actions=(action,)))

    assert compiled.actions == (CompiledAction(action=action),)
    assert compiled.reply_necessity == "reply_needed"


def test_missing_required_param_yields_needs_input_mark() -> None:
    action = ProposedAction(domain="reminder", operation="create", params={})

    compiled = compile_plan(TurnPlan(actions=(action,)))

    mark = compiled.actions[0]
    assert mark.action == action
    assert mark.category == "needs_input"
    assert mark.status == "missing_required_param"
    assert mark.data["missing_params"] == ("content",)


def test_unknown_domain_yields_not_possible_mark() -> None:
    action = ProposedAction(
        domain="unknown", operation="delete", params={"match": "gym"}
    )

    compiled = compile_plan(TurnPlan(actions=(action,)))

    mark = compiled.actions[0]
    assert mark.action == action
    assert mark.category == "not_possible"
    assert mark.status == "unsupported_domain"
    assert mark.data["domain"] == "unknown"


def test_unknown_operation_yields_not_possible_mark() -> None:
    action = ProposedAction(
        domain="reminder",
        operation="invent_id_lookup",
        params={"match": "gym"},
    )

    compiled = compile_plan(TurnPlan(actions=(action,)))

    mark = compiled.actions[0]
    assert mark.action == action
    assert mark.category == "not_possible"
    assert mark.status == "unsupported_operation"
    assert mark.data["operation"] == "invent_id_lookup"


def test_compile_plan_preserves_reply_necessity() -> None:
    compiled = compile_plan(
        TurnPlan(actions=(), reply_necessity="intentional_no_reply")
    )

    assert compiled.actions == ()
    assert compiled.reply_necessity == "intentional_no_reply"


def test_compile_plan_does_not_resolve_natural_references() -> None:
    action = ProposedAction(
        domain="reminder",
        operation="update",
        params={"match": "gym", "time_text": "tomorrow night"},
    )

    compiled = compile_plan(TurnPlan(actions=(action,)))

    assert compiled.actions[0].action == action
    assert compiled.actions[0].data == {}
    assert compiled.actions[0].action.params["match"] == "gym"
