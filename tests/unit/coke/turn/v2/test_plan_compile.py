from __future__ import annotations

from coke.turn.v2.contracts import CompiledAction, ProposedAction, TurnPlan
from coke.turn.v2.param_schema import PARAM_KEY_SCHEMA, required_params_by_operation
from coke.turn.v2.plan_compile import REQUIRED_PARAMS, compile_plan


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
    assert mark.data["missing_params"] == ("content", "time_phrase")


def test_live_probe_alias_param_names_do_not_satisfy_required_schema() -> None:
    actions = (
        ProposedAction(
            domain="reminder",
            operation="delete",
            params={"reminder_query": "gym"},
        ),
        ProposedAction(
            domain="reminder",
            operation="create",
            params={"task": "call mom", "time": "tomorrow"},
        ),
        ProposedAction(
            domain="reminder",
            operation="update",
            params={"reminder_name": "gym", "time": "tomorrow night"},
        ),
        ProposedAction(
            domain="social_scheduling",
            operation="create_shared_reminder",
            params={"person": "Amy", "time": "tomorrow", "event": "send deck"},
        ),
    )

    compiled = compile_plan(TurnPlan(actions=actions))

    assert [mark.data["missing_params"] for mark in compiled.actions] == [
        ("match",),
        ("content", "time_phrase"),
        ("match",),
        ("participant", "content", "time_phrase"),
    ]


def test_shared_cancel_can_omit_match_for_handler_disambiguation() -> None:
    action = ProposedAction(
        domain="social_scheduling",
        operation="cancel_shared_reminder",
        params={"participant": "张三"},
    )

    compiled = compile_plan(TurnPlan(actions=(action,)))

    assert compiled.actions == (CompiledAction(action=action),)


def test_shared_cancel_schema_uses_natural_refs_not_ids() -> None:
    shared_cancel = PARAM_KEY_SCHEMA["social_scheduling"]["cancel_shared_reminder"]

    assert shared_cancel.required == ("participant",)
    assert "match" in shared_cancel.optional
    assert "shared_reminder_id" not in shared_cancel.optional


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
        params={"match": "gym", "time_phrase": "tomorrow night"},
    )

    compiled = compile_plan(TurnPlan(actions=(action,)))

    assert compiled.actions[0].action == action
    assert compiled.actions[0].data == {}
    assert compiled.actions[0].action.params["match"] == "gym"


def test_compile_required_params_match_shared_param_key_schema() -> None:
    assert REQUIRED_PARAMS == required_params_by_operation(PARAM_KEY_SCHEMA)
