from __future__ import annotations

from typing import Any

from coke.turn.inbound.contracts import (
    ActionOutcome,
    CompiledAction,
    CompiledPlan,
    ProposedAction,
)
from coke.turn.inbound.execute import ActionExecutor, ExecutionOutcomeBuilder


class RecordingHandler:
    def __init__(self) -> None:
        self.calls: list[tuple[CompiledAction, Any, int, str]] = []

    def execute(
        self,
        compiled_action: CompiledAction,
        guard: Any,
        *,
        action_index: int,
        turn_id: str,
    ) -> ActionOutcome:
        self.calls.append((compiled_action, guard, action_index, turn_id))
        assert compiled_action.action is not None
        return ActionOutcome(
            category="done",
            status=f"{compiled_action.action.operation}_done",
            data={"operation": compiled_action.action.operation},
        )


def test_action_executor_runs_compiled_actions_in_order() -> None:
    first = CompiledAction(action=ProposedAction(domain="reminder", operation="create"))
    second = CompiledAction(
        action=ProposedAction(domain="reminder", operation="delete")
    )
    handler = RecordingHandler()
    guard = object()

    outcome = ActionExecutor({"reminder": handler}).execute(
        CompiledPlan(actions=(first, second)),
        guard,
        turn_id="turn-1",
    )

    assert [item.status for item in outcome.outcomes] == [
        "create_done",
        "delete_done",
    ]
    assert all(not hasattr(item, "staged_command_id") for item in outcome.outcomes)
    assert handler.calls == [
        (first, guard, 0, "turn-1"),
        (second, guard, 1, "turn-1"),
    ]


def test_action_executor_passes_compile_marks_through_as_outcomes() -> None:
    action = ProposedAction(domain="reminder", operation="create")
    mark = CompiledAction(
        action=action,
        category="needs_input",
        status="missing_required_param",
        data={"missing_params": ("content",)},
    )
    handler = RecordingHandler()

    outcome = ActionExecutor({"reminder": handler}).execute(
        CompiledPlan(actions=(mark,)),
        object(),
        turn_id="turn-1",
    )

    assert outcome.outcomes == (
        ActionOutcome(
            category="needs_input",
            status="missing_required_param",
            data={"missing_params": ("content",)},
        ),
    )
    assert handler.calls == []


def test_execution_outcome_builder_assembles_settled_outcome() -> None:
    builder = ExecutionOutcomeBuilder()
    first = ActionOutcome(category="done", status="listed", data={"count": 0})
    second = ActionOutcome(category="not_possible", status="not_found")

    builder.add(first)
    builder.add(second)

    assert builder.build().outcomes == (first, second)


def test_execute_injects_action_context_into_params() -> None:
    handler = RecordingHandler()
    executor = ActionExecutor({"reminder": handler})
    plan = CompiledPlan(
        actions=(
            CompiledAction(
                action=ProposedAction(
                    domain="reminder", operation="list", params={"keyword": "gym"}
                )
            ),
        )
    )
    executor.execute(
        plan,
        guard=None,
        turn_id="turn-1",
        action_context={
            "owner_account_id": "acct-1",
            "captured_timezone": "Asia/Tokyo",
        },
    )
    received = handler.calls[0][0].action.params
    assert received["owner_account_id"] == "acct-1"
    assert received["captured_timezone"] == "Asia/Tokyo"
    # planner-provided functional params are preserved
    assert received["keyword"] == "gym"


def test_trusted_context_wins_over_planner_account_id() -> None:
    # Security: a hallucinated account id from the planner must never override the
    # authenticated trusted account.
    handler = RecordingHandler()
    executor = ActionExecutor({"reminder": handler})
    plan = CompiledPlan(
        actions=(
            CompiledAction(
                action=ProposedAction(
                    domain="reminder",
                    operation="list",
                    params={"owner_account_id": "planner"},
                )
            ),
        )
    )
    executor.execute(
        plan,
        guard=None,
        turn_id="turn-1",
        action_context={"owner_account_id": "trusted"},
    )
    assert handler.calls[0][0].action.params["owner_account_id"] == "trusted"
