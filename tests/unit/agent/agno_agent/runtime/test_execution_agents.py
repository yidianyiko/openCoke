from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.domain_results import (
    DomainExecutionResult,
    DomainOperationResult,
    ReplyContract,
)
from agent.agno_agent.runtime.execution_agents import run_reminder_domain


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="UTC"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key=None,
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 22, 10, 0, tzinfo=UTC),
        runtime_metadata={},
    )


def _domain_result() -> DomainExecutionResult:
    return DomainExecutionResult(
        domain="reminder",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="create",
                ok=True,
                effect="write",
                entity_type="reminder",
                entity_id="rem-1",
                facts={"title": "drink water"},
            ),
        ),
        missing_fields=(),
        safety_boundary=None,
        reply_contract=ReplyContract(
            intent="confirm_execution",
            required_facts=(),
            required_questions=(),
            prohibited_claims=("not_created",),
            allow_rephrase=True,
        ),
    )


class _FakeReminderPort:
    async def run(self, input_message, run_context, args):
        return _domain_result()


@pytest.mark.asyncio
async def test_run_reminder_domain_appends_domain_result_and_returns_dict():
    domain_results: list[DomainExecutionResult] = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.ReminderIntentPort",
        return_value=_FakeReminderPort(),
    ):
        envelope = await run_reminder_domain(
            input_message="remind me to drink water",
            run_context=_run_context(),
            domain_results=domain_results,
        )

    assert domain_results == [_domain_result()]
    assert envelope["domain"] == "reminder"
    assert envelope["outcome"] == "executed"
    assert envelope["operations"][0]["facts"]["title"] == "drink water"
    assert "visible_summary" not in envelope
    assert "synthesis_context" not in envelope
