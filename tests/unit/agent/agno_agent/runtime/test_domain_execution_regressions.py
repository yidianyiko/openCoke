from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort
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
from agent.agno_agent.runtime.execution_agents import run_scheduling_domain
from agent.agno_agent.runtime.result import CapabilityResult


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
    def __init__(self, result: DomainExecutionResult):
        self.result = result

    def execute(self, decision, run_context):
        return self.result


def _case_7_created_result() -> DomainExecutionResult:
    return DomainExecutionResult(
        domain="reminder",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="create",
                ok=True,
                effect="write",
                entity_type="reminder",
                entity_id="rem-case-7",
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


@pytest.mark.asyncio
async def test_case_7_english_relative_reminder_preserves_executed_facts():
    result = await ReminderIntentPort(
        detector_agent=_Detector(
            SimpleNamespace(
                intent_type="crud",
                action="create",
                title="drink water",
                trigger_at="2026-05-22T22:06:00+09:00",
                rrule=None,
                operations=None,
            )
        ),
        command_executor=_Executor(_case_7_created_result()),
    ).run("Remind me to drink water later tonight", _run_context())

    assert result.outcome == "executed"
    assert result.operations[0].entity_id == "rem-case-7"
    assert result.operations[0].facts["title"] == "drink water"
    assert result.operations[0].facts["local_time"] == "22:06:00"


@pytest.mark.asyncio
async def test_scheduling_no_tool_called_returns_typed_failed_domain_result():
    class _NoOpAgent:
        def __init__(self, **kwargs):
            pass

        async def arun(self, **kwargs):
            return None

    class _Port:
        def run(self, input_message, run_context, args):
            return CapabilityResult(name="get_user_link", ok=True, content={})

    domain_results: list[DomainExecutionResult] = []
    with patch("agent.agno_agent.runtime.execution_agents.Agent", _NoOpAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: _Port(),
        ):
            envelope = await run_scheduling_domain(
                input_message="set up a shared reminder",
                intent="create_shared_reminder",
                run_context=_run_context(),
                domain_results=domain_results,
            )

    assert envelope["outcome"] == "failed"
    assert envelope["error"]["code"] == "no_tool_called"
    assert domain_results[0].outcome == "failed"
