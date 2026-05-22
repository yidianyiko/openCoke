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


class _FakePort:
    def __init__(self, result: CapabilityResult) -> None:
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
async def test_run_reminder_domain_appends_exactly_one_result_to_tool_results():
    fake_result = CapabilityResult(
        name="reminder",
        ok=True,
        content={"visible_summary": "已为你设好提醒"},
        metadata={"durable_write": True},
    )
    tool_results = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.ReminderIntentPort",
        return_value=_FakePort(fake_result),
    ):
        await run_reminder_domain(
            input_message="提醒我喝水",
            run_context=_run_context(),
            tool_results=tool_results,
        )

    assert len(tool_results) == 1
    assert tool_results[0] is fake_result


@pytest.mark.asyncio
async def test_run_reminder_domain_returns_full_capability_envelope():
    fake_result = CapabilityResult(
        name="reminder",
        ok=True,
        content={"visible_summary": "已为你设好提醒", "synthesis_context": "ctx"},
        metadata={"durable_write": True},
    )
    tool_results = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.ReminderIntentPort",
        return_value=_FakePort(fake_result),
    ):
        envelope = await run_reminder_domain(
            input_message="提醒我喝水",
            run_context=_run_context(),
            tool_results=tool_results,
        )

    assert envelope["ok"] is True
    assert envelope["visible_summary"] == "已为你设好提醒"
    assert envelope["synthesis_context"] == "ctx"
    assert "content" in envelope
    assert envelope["error"] is None


@pytest.mark.asyncio
async def test_run_reminder_domain_forwards_failed_port_result():
    fake_result = CapabilityResult(
        name="reminder",
        ok=False,
        content={},
        error="reminder_service_unavailable",
    )
    tool_results = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.ReminderIntentPort",
        return_value=_FakePort(fake_result),
    ):
        envelope = await run_reminder_domain(
            input_message="set a reminder",
            run_context=_run_context(),
            tool_results=tool_results,
        )

    assert envelope["ok"] is False
    assert envelope["error"] == "reminder_service_unavailable"
    assert len(tool_results) == 1


@pytest.mark.asyncio
async def test_make_scheduling_tool_fn_appends_to_both_lists():
    fake_result = CapabilityResult(
        name="get_user_link",
        ok=True,
        content={"visible_summary": "Your booking link: https://kap.example/u/xyz"},
    )
    tool_results: list[CapabilityResult] = []
    domain_results: list[CapabilityResult] = []

    fn = _make_scheduling_tool_fn(
        "get_user_link",
        _SyncPort(fake_result),
        input_message="show my link",
        run_context=_run_context(),
        tool_results=tool_results,
        domain_results=domain_results,
    )
    envelope = await fn()

    assert tool_results == [fake_result]
    assert domain_results == [fake_result]
    assert envelope["ok"] is True
    assert envelope["visible_summary"] == "Your booking link: https://kap.example/u/xyz"


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
        tool_results=[],
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
                tool_results=[],
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
                tool_results=[],
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
                tool_results=[],
            )

    assert result["ok"] is False
    assert result["error"] == "no_tool_called"
    assert result["domain"] == "scheduling"


@pytest.mark.asyncio
async def test_run_scheduling_domain_returns_called_tool_result():
    fake_result = CapabilityResult(
        name="get_user_link",
        ok=True,
        content={"visible_summary": "Your booking link: https://kap.example/u/xyz"},
    )
    tool_results: list[CapabilityResult] = []

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
                tool_results=tool_results,
            )

    assert result["ok"] is True
    assert result["domain"] == "scheduling"
    assert result["visible_summary"] == "Your booking link: https://kap.example/u/xyz"
    assert tool_results == [fake_result]


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

    tool_results: list[CapabilityResult] = []

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
                tool_results=tool_results,
            )

    assert calls == ["get_user_link"]
    assert [item.name for item in tool_results] == ["get_user_link"]
    assert result["ok"] is True
    assert result["visible_summary"] == "called get_user_link"
