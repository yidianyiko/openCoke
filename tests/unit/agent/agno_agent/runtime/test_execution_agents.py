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
from agent.agno_agent.runtime.execution_agents import run_scheduling_domain
from agent.agno_agent.runtime.result import CapabilityResult


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


class _SyncSchedulingPort:
    def __init__(self, result: CapabilityResult) -> None:
        self.result = result

    def run(self, input_message, run_context, args):
        return self.result


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


@pytest.mark.asyncio
async def test_run_scheduling_domain_returns_typed_failed_result_when_no_tool_called():
    class _NoOpAgent:
        def __init__(self, **kwargs):
            pass

        async def arun(self, **kwargs):
            return None

    domain_results: list[DomainExecutionResult] = []

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _NoOpAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: _SyncSchedulingPort(
                CapabilityResult(name=tool_name, ok=True, content={})
            ),
        ):
            envelope = await run_scheduling_domain(
                input_message="book an appointment",
                intent="request_appointment",
                run_context=_run_context(),
                domain_results=domain_results,
            )

    assert envelope["domain"] == "scheduling"
    assert envelope["outcome"] == "failed"
    assert envelope["error"]["code"] == "no_tool_called"
    assert domain_results[0].error is not None
    assert domain_results[0].error.code == "no_tool_called"


@pytest.mark.asyncio
async def test_run_scheduling_domain_converts_called_tool_to_domain_result():
    fake_result = CapabilityResult(
        name="request_appointment",
        ok=True,
        content={
            "request_id": "req-1",
            "target_account_id": "acct-provider",
            "consumer_account_id": "acct-consumer",
            "instance_start": "2026-05-23T09:00:00+09:00",
            "instance_end": "2026-05-23T09:30:00+09:00",
            "timezone": "Asia/Tokyo",
        },
        metadata={"durable_write": True, "requires_response_synthesis": True},
    )

    class _CallingAgent:
        def __init__(self, **kwargs):
            self.tools = {item.name: item.entrypoint for item in kwargs["tools"]}

        async def arun(self, **kwargs):
            await self.tools["request_appointment"](
                target_account_id="acct-provider",
                consumer_account_id="acct-consumer",
            )

    domain_results: list[DomainExecutionResult] = []

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _CallingAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: _SyncSchedulingPort(fake_result),
        ):
            envelope = await run_scheduling_domain(
                input_message="book that",
                intent="request_appointment",
                run_context=_run_context(),
                domain_results=domain_results,
            )

    assert envelope["domain"] == "scheduling"
    assert envelope["outcome"] == "executed"
    assert envelope["operations"][0]["action"] == "request_appointment"
    assert envelope["operations"][0]["effect"] == "write"
    assert envelope["operations"][0]["entity_id"] == "req-1"
    assert domain_results[0].reply_contract.intent == "confirm_execution"


@pytest.mark.asyncio
async def test_run_scheduling_domain_returns_successful_write_when_later_duplicate_fails():
    successful_write = CapabilityResult(
        name="request_appointment",
        ok=True,
        content={
            "request_id": "req-1",
            "target_account_id": "acct-provider",
            "consumer_account_id": "acct-consumer",
            "instance_start": "2026-05-23T09:00:00+09:00",
            "instance_end": "2026-05-23T09:30:00+09:00",
            "timezone": "Asia/Tokyo",
        },
    )

    class _DuplicateCallingAgent:
        def __init__(self, **kwargs):
            self.tools = {item.name: item.entrypoint for item in kwargs["tools"]}

        async def arun(self, **kwargs):
            await self.tools["request_appointment"](
                target_account_id="acct-provider",
                consumer_account_id="acct-consumer",
            )
            await self.tools["cancel_appointment"](appointment_or_request_id="req-1")

    domain_results: list[DomainExecutionResult] = []

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _DuplicateCallingAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: _SyncSchedulingPort(successful_write),
        ):
            envelope = await run_scheduling_domain(
                input_message="book that, actually cancel it",
                intent="request_appointment",
                run_context=_run_context(),
                domain_results=domain_results,
            )

    assert envelope["domain"] == "scheduling"
    assert envelope["outcome"] == "executed"
    assert envelope["error"] is None
    assert envelope["operations"][0]["action"] == "request_appointment"
    assert envelope["operations"][0]["effect"] == "write"
    assert envelope["operations"][0]["entity_id"] == "req-1"
    assert envelope["operations"][0]["facts"]["request_id"] == "req-1"
    assert [item.error.code if item.error else None for item in domain_results] == [
        None,
        "duplicate_scheduling_tool_call",
    ]
