from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from agent.agno_agent.capabilities.reminder_intent import (
    ReminderIntentPort,
    _no_action_discussion_result,
)
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


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key="route-1",
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
    )


class _Detector:
    def __init__(self, decision):
        self.decision = decision

    async def arun(self, **kwargs):
        return SimpleNamespace(content=self.decision)


class _Executor:
    def execute(self, decision, run_context):
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
                    facts={
                        "title": "drink water",
                        "local_date": "2026-05-22",
                        "local_time": "22:06:00",
                        "timezone": "Asia/Tokyo",
                        "conversation_id": "conv-1",
                    },
                ),
            ),
            missing_fields=(),
            safety_boundary=None,
            reply_contract=ReplyContract(
                intent="confirm_execution",
                required_facts=(),
                allow_rephrase=True,
            ),
        )


def test_no_action_helper_returns_domain_execution_result():
    result = _no_action_discussion_result()

    assert result.outcome == "no_action"
    assert result.operations == ()
    assert result.reply_contract.intent == "direct_answer"


@pytest.mark.asyncio
async def test_run_returns_executor_domain_result_for_crud_decision():
    decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="drink water",
        trigger_at="2026-05-22T22:06:00+09:00",
        rrule=None,
        operations=None,
    )
    result = await ReminderIntentPort(
        detector_agent=_Detector(decision),
        command_executor=_Executor(),
    ).run("remind me to drink water at 10:06pm", _run_context())

    assert result.outcome == "executed"
    assert result.operations[0].facts["title"] == "drink water"
