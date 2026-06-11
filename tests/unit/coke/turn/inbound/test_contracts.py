from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from coke.turn.inbound.contracts import (
    ActionOutcome,
    CompiledAction,
    CompiledPlan,
    MaterializationPlan,
    PendingClarification,
    ProposedAction,
    SettledOutcome,
    TurnPlan,
)


def test_proposed_action_holds_keyword_params() -> None:
    action = ProposedAction(
        domain="reminder",
        operation="delete",
        params={"match": "gym"},
    )

    assert action.params["match"] == "gym"


def test_action_outcome_requires_category_and_status() -> None:
    outcome = ActionOutcome(
        category="done",
        status="created",
        data={"id": "r1"},
    )

    assert outcome.category == "done"
    assert outcome.status == "created"
    assert outcome.data["id"] == "r1"
    assert outcome.staged_command_id is None


def test_turn_plan_defaults_reply_needed() -> None:
    plan = TurnPlan(actions=())

    assert plan.actions == ()
    assert plan.reply_necessity == "reply_needed"


def test_contracts_are_frozen() -> None:
    action = ProposedAction(domain="reminder", operation="delete")

    with pytest.raises(FrozenInstanceError):
        action.operation = "create"  # type: ignore[misc]


def test_phase_one_contracts_construct_with_defaults() -> None:
    action = ProposedAction(
        domain="reminder",
        operation="delete",
        params={"match": "gym"},
    )
    compiled = CompiledAction(action=action)
    compiled_plan = CompiledPlan(actions=(compiled,))
    outcome = ActionOutcome(category="done", status="cancelled")
    settled = SettledOutcome(outcomes=(outcome,))
    pending = PendingClarification(
        unresolved_action_fingerprint="reminder:delete:gym",
        candidates=({"id": "r1", "content": "gym"},),
        source_input_window=(10, 12),
        expires_at=datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
        status="open",
    )
    materialization = MaterializationPlan(staged_command_ids=("cmd-1",))

    assert compiled.action == action
    assert compiled.category is None
    assert compiled.status is None
    assert compiled_plan.actions == (compiled,)
    assert settled.outcomes == (outcome,)
    assert pending.candidates[0]["content"] == "gym"
    assert materialization.staged_command_ids == ("cmd-1",)
