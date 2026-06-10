from __future__ import annotations

from typing import Any

from coke.turn.v2.contracts import (
    ActionOutcome,
    CompiledAction,
    CompiledPlan,
    ProposedAction,
)
from coke.turn.v2.execute import ActionExecutor, ExecutionOutcomeBuilder


class RecordingHandler:
    def __init__(self) -> None:
        self.calls: list[tuple[CompiledAction, Any]] = []

    def resolve_and_stage(
        self, compiled_action: CompiledAction, guard: Any
    ) -> ActionOutcome:
        self.calls.append((compiled_action, guard))
        assert compiled_action.action is not None
        return ActionOutcome(
            category="done",
            status=f"{compiled_action.action.operation}_done",
            data={"operation": compiled_action.action.operation},
            staged_command_id=f"stage-{len(self.calls)}",
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
    )

    assert [item.status for item in outcome.outcomes] == [
        "create_done",
        "delete_done",
    ]
    assert [item.staged_command_id for item in outcome.outcomes] == [
        "stage-1",
        "stage-2",
    ]
    assert handler.calls == [(first, guard), (second, guard)]


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
