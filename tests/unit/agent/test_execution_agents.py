from __future__ import annotations

import asyncio
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
    DomainError,
    DomainExecutionResult,
    DomainOperationResult,
    ReplyContract,
)
from agent.agno_agent.runtime.execution_agents import (
    _make_scheduling_tool_fn,
    run_reminder_domain,
    run_scheduling_domain,
)
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


def _reminder_domain_result() -> DomainExecutionResult:
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


class _FakePort:
    def __init__(self, result) -> None:
        self._result = result

    async def run(self, input_message, run_context, args):
        return self._result


class _SyncPort:
    """Sync port; tests that asyncio.to_thread() path is used."""

    def __init__(self, result: CapabilityResult) -> None:
        self._result = result

    def run(self, input_message, run_context, args):
        return self._result


@pytest.mark.asyncio
async def test_run_reminder_domain_appends_exactly_one_result_to_domain_results():
    fake_result = _reminder_domain_result()
    domain_results = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.ReminderIntentPort",
        return_value=_FakePort(fake_result),
    ):
        await run_reminder_domain(
            input_message="提醒我喝水",
            run_context=_run_context(),
            domain_results=domain_results,
        )

    assert len(domain_results) == 1
    assert domain_results[0] is fake_result


@pytest.mark.asyncio
async def test_run_reminder_domain_returns_domain_result_envelope():
    fake_result = _reminder_domain_result()
    domain_results = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.ReminderIntentPort",
        return_value=_FakePort(fake_result),
    ):
        envelope = await run_reminder_domain(
            input_message="提醒我喝水",
            run_context=_run_context(),
            domain_results=domain_results,
        )

    assert envelope["domain"] == "reminder"
    assert envelope["outcome"] == "executed"
    assert envelope["operations"][0]["facts"]["title"] == "drink water"
    assert envelope["error"] is None
    assert "visible_summary" not in envelope
    assert "synthesis_context" not in envelope


@pytest.mark.asyncio
async def test_run_reminder_domain_forwards_failed_port_result():
    fake_result = DomainExecutionResult(
        domain="reminder",
        outcome="failed",
        operations=(),
        missing_fields=(),
        safety_boundary=None,
        reply_contract=ReplyContract(
            intent="report_failure",
            required_facts=(),
            required_questions=(),
            prohibited_claims=("reminder_created",),
            allow_rephrase=True,
        ),
        error=DomainError(
            code="reminder_service_unavailable",
            message="Reminder service unavailable",
            retryable=True,
            detail={},
        ),
    )
    domain_results = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.ReminderIntentPort",
        return_value=_FakePort(fake_result),
    ):
        envelope = await run_reminder_domain(
            input_message="set a reminder",
            run_context=_run_context(),
            domain_results=domain_results,
        )

    assert envelope["outcome"] == "failed"
    assert envelope["error"]["code"] == "reminder_service_unavailable"
    assert len(domain_results) == 1


@pytest.mark.asyncio
async def test_make_scheduling_tool_fn_appends_domain_result():
    fake_result = CapabilityResult(
        name="get_user_link",
        ok=True,
        content={"visible_summary": "Your booking link: https://kap.example/u/xyz"},
    )
    domain_results: list[DomainExecutionResult] = []

    fn = _make_scheduling_tool_fn(
        "get_user_link",
        _SyncPort(fake_result),
        input_message="show my link",
        run_context=_run_context(),
        domain_results=domain_results,
    )
    envelope = await fn()

    assert len(domain_results) == 1
    assert domain_results[0].domain == "scheduling"
    assert envelope["domain"] == "scheduling"
    assert envelope["outcome"] == "executed"
    assert envelope["operations"][0]["action"] == "get_user_link"
    assert (
        envelope["operations"][0]["facts"]["visible_summary"]
        == "Your booking link: https://kap.example/u/xyz"
    )


@pytest.mark.asyncio
async def test_make_scheduling_tool_fn_passes_non_none_args_to_port():
    received_args: list[dict] = []

    class RecordingPort:
        def run(self, input_message, run_context, args):
            received_args.append(args)
            return CapabilityResult(name="accept_shared_reminder", ok=True, content={})

    fn = _make_scheduling_tool_fn(
        "accept_shared_reminder",
        RecordingPort(),
        input_message="confirm that",
        run_context=_run_context(),
        domain_results=[],
    )
    await fn(request_id="srr_123", timezone=None)

    assert received_args == [{"request_id": "srr_123"}]


@pytest.mark.asyncio
async def test_run_scheduling_domain_uses_friend_link_worker_prompt():
    captured: dict[str, str] = {}

    class _NoOpAgent:
        def __init__(self, **kwargs):
            captured["instructions"] = kwargs["instructions"]

        async def arun(self, **kwargs):
            pass

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _NoOpAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: _SyncPort(
                CapabilityResult(name=tool_name, ok=True, content={})
            ),
        ):
            await run_scheduling_domain(
                input_message="show my link",
                intent="get_user_link",
                run_context=_run_context(),
                domain_results=[],
            )

    assert captured["instructions"] == (
        "You are the friend-link and shared-reminder execution worker. "
        "Call exactly one scheduling tool that matches the intent. "
        "Do not create shared reminder state unless the named person resolves to "
        "one active friend. Ask for clarification when the name is ambiguous. "
        "Ordinary personal reminders are not scheduling-domain work. "
        "Do not treat an iLink QR as a public user-link QR."
    )


@pytest.mark.asyncio
async def test_run_scheduling_domain_passes_resolved_intent_to_worker_input():
    captured: dict[str, str] = {}

    class _NoOpAgent:
        def __init__(self, **kwargs):
            pass

        async def arun(self, **kwargs):
            captured["input"] = kwargs["input"]

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _NoOpAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: _SyncPort(
                CapabilityResult(name=tool_name, ok=True, content={})
            ),
        ):
            await run_scheduling_domain(
                input_message="accept that",
                intent="accept_shared_reminder request_id=srr_1",
                run_context=_run_context(),
                domain_results=[],
            )

    assert (
        "Resolved scheduling intent: accept_shared_reminder request_id=srr_1"
        in captured["input"]
    )
    assert "User message: accept that" in captured["input"]


@pytest.mark.asyncio
async def test_run_scheduling_domain_returns_no_tool_called_when_agent_calls_nothing():
    class _NoOpAgent:
        def __init__(self, **kwargs):
            pass

        async def arun(self, **kwargs):
            pass

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _NoOpAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: _SyncPort(
                CapabilityResult(name=tool_name, ok=True, content={})
            ),
        ):
            result = await run_scheduling_domain(
                input_message="show my link",
                intent="get_user_link",
                run_context=_run_context(),
                domain_results=[],
            )

    assert result["domain"] == "scheduling"
    assert result["outcome"] == "failed"
    assert result["error"]["code"] == "no_tool_called"


@pytest.mark.asyncio
async def test_run_scheduling_domain_returns_called_tool_result():
    fake_result = CapabilityResult(
        name="get_user_link",
        ok=True,
        content={"visible_summary": "Your booking link: https://kap.example/u/xyz"},
    )
    domain_results: list[DomainExecutionResult] = []

    class _CallingAgent:
        def __init__(self, **kwargs):
            self.tools = {item.name: item.entrypoint for item in kwargs["tools"]}

        async def arun(self, **kwargs):
            await self.tools["get_user_link"]()

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _CallingAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: _SyncPort(fake_result),
        ):
            result = await run_scheduling_domain(
                input_message="show my link",
                intent="get_user_link",
                run_context=_run_context(),
                domain_results=domain_results,
            )

    assert result["domain"] == "scheduling"
    assert result["outcome"] == "executed"
    assert result["operations"][0]["facts"]["visible_summary"] == (
        "Your booking link: https://kap.example/u/xyz"
    )
    assert len(domain_results) == 1
    assert domain_results[0].operations[0].action == "get_user_link"


@pytest.mark.asyncio
async def test_run_scheduling_domain_executes_only_first_concurrent_tool_call():
    calls: list[str] = []

    class RecordingPort:
        def __init__(self, tool_name: str) -> None:
            self.tool_name = tool_name

        async def run(self, input_message, run_context, args):
            calls.append(self.tool_name)
            return CapabilityResult(
                name=self.tool_name,
                ok=True,
                content={"visible_summary": f"called {self.tool_name}"},
            )

    class _DuplicateCallingAgent:
        def __init__(self, **kwargs):
            self.tools = {item.name: item.entrypoint for item in kwargs["tools"]}

        async def arun(self, **kwargs):
            await asyncio.gather(
                self.tools["get_user_link"](),
                self.tools["reset_user_link"](),
            )

    domain_results: list[DomainExecutionResult] = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.Agent", _DuplicateCallingAgent
    ):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: RecordingPort(tool_name),
        ):
            result = await run_scheduling_domain(
                input_message="show my link",
                intent="get_user_link",
                run_context=_run_context(),
                domain_results=domain_results,
            )

    assert calls == ["get_user_link"]
    assert [item.error.code if item.error else None for item in domain_results] == [
        None,
        "duplicate_scheduling_tool_call",
    ]
    assert result["domain"] == "scheduling"
    assert result["outcome"] == "executed"
    assert result["error"] is None
    assert result["operations"][0]["action"] == "get_user_link"
    assert (
        result["operations"][0]["facts"]["visible_summary"]
        == "called get_user_link"
    )
