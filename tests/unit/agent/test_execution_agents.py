from __future__ import annotations

import asyncio
from dataclasses import replace
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
    _SCHEDULING_SYSTEM_PROMPT,
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
            return CapabilityResult(name="cancel_shared_reminder", ok=True, content={})

    fn = _make_scheduling_tool_fn(
        "cancel_shared_reminder",
        RecordingPort(),
        input_message="confirm that",
        run_context=_run_context(),
        domain_results=[],
    )
    await fn(shared_reminder_id="sr_123", timezone=None)

    assert received_args == [{"shared_reminder_id": "sr_123"}]


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

    assert captured["instructions"] == _SCHEDULING_SYSTEM_PROMPT
    assert "## Role" in captured["instructions"]
    assert "## Tool selection" in captured["instructions"]
    assert "## Boundaries" in captured["instructions"]
    assert (
        "create_friendship_by_user_link_code with user_link_code"
        in captured["instructions"]
    )
    assert "create_shared_reminder: pass receiver_name" in captured["instructions"]
    assert "send_friend_request_by_user_link_code" not in captured["instructions"]
    assert "invitee_name" not in captured["instructions"]
    assert "do not call list_friends" in captured["instructions"]
    assert "list_friend_calendar_facts: pass friend_name" in captured["instructions"]
    assert "plus timezone" in captured["instructions"]
    assert "Do not use Google Calendar" in captured["instructions"]
    assert "one active friend" in captured["instructions"]
    assert (
        "Ask for clarification when the name is ambiguous" in captured["instructions"]
    )
    assert (
        "use 60 minutes unless the user states another duration"
        in captured["instructions"]
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
                input_message="cancel that",
                intent="cancel_shared_reminder shared_reminder_id=sr_1",
                run_context=_run_context(),
                domain_results=[],
            )

    assert (
        "Resolved scheduling intent: cancel_shared_reminder shared_reminder_id=sr_1"
        in captured["input"]
    )
    assert "User message: cancel that" in captured["input"]


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
async def test_run_scheduling_domain_returns_friend_calendar_facts_as_read_only_result():
    captured_args: dict[str, dict] = {}

    class _CalendarFactsAgent:
        def __init__(self, **kwargs):
            self.tools = {item.name: item.entrypoint for item in kwargs["tools"]}

        async def arun(self, **kwargs):
            await self.tools["list_friend_calendar_facts"](
                target_account_id="acct_coach",
                from_date="2026-05-25",
                to_date="2026-05-31",
                timezone="Asia/Tokyo",
            )

    class RecordingSchedulingPort:
        def __init__(self, tool_name: str) -> None:
            self.tool_name = tool_name

        async def run(self, input_message, run_context, args):
            captured_args[self.tool_name] = args
            return CapabilityResult(
                name=self.tool_name,
                ok=True,
                content={
                    "target_account_id": "acct_coach",
                    "range": {
                        "from": "2026-05-25",
                        "to": "2026-05-31",
                        "timezone": "Asia/Tokyo",
                    },
                    "busy_intervals": [
                        {
                            "start_at": "2026-05-25T01:00:00+00:00",
                            "end_at": "2026-05-25T02:00:00+00:00",
                            "local_start": "2026-05-25 10:00",
                            "local_end": "2026-05-25 11:00",
                        }
                    ],
                    "privacy": {"event_details_included": False},
                },
            )

    domain_results: list[DomainExecutionResult] = []

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _CalendarFactsAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: RecordingSchedulingPort(tool_name),
        ):
            result = await run_scheduling_domain(
                input_message="A 这周有什么空余时间",
                intent="list_friend_calendar_facts for resolved friend acct_coach",
                run_context=_run_context(),
                domain_results=domain_results,
            )

    assert captured_args["list_friend_calendar_facts"] == {
        "target_account_id": "acct_coach",
        "from_date": "2026-05-25",
        "to_date": "2026-05-31",
        "timezone": "Asia/Tokyo",
    }
    operation = result["operations"][0]
    assert operation["action"] == "list_friend_calendar_facts"
    assert operation["effect"] == "read"
    assert operation["entity_type"] == "friend_calendar_facts"
    assert operation["facts"]["busy_intervals"] == [
        {
            "start_at": "2026-05-25T01:00:00+00:00",
            "end_at": "2026-05-25T02:00:00+00:00",
            "local_start": "2026-05-25 10:00",
            "local_end": "2026-05-25 11:00",
        }
    ]
    assert operation["facts"]["privacy"] == {"event_details_included": False}
    assert not {
        "reminder_id",
        "title",
        "prompt",
        "metadata",
        "agent_output_target",
    } & set(operation["facts"])


@pytest.mark.asyncio
async def test_run_scheduling_domain_routes_friend_name_to_calendar_facts():
    captured_args: dict[str, dict] = {}

    class _CalendarFactsAgent:
        def __init__(self, **kwargs):
            self.tools = {item.name: item.entrypoint for item in kwargs["tools"]}

        async def arun(self, **kwargs):
            await self.tools["list_friend_calendar_facts"](
                friend_name="Coach A",
                from_date="2026-05-25",
                to_date="2026-05-31",
                timezone="Asia/Tokyo",
            )

    class RecordingSchedulingPort:
        def __init__(self, tool_name: str) -> None:
            self.tool_name = tool_name

        async def run(self, input_message, run_context, args):
            captured_args[self.tool_name] = args
            return CapabilityResult(
                name=self.tool_name,
                ok=True,
                content={
                    "target_account_id": "acct_coach",
                    "range": {
                        "from": "2026-05-25",
                        "to": "2026-05-31",
                        "timezone": "Asia/Tokyo",
                    },
                    "busy_intervals": [],
                    "privacy": {"event_details_included": False},
                },
            )

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _CalendarFactsAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: RecordingSchedulingPort(tool_name),
        ):
            await run_scheduling_domain(
                input_message="Coach A 这周有什么空余时间",
                intent="list_friend_calendar_facts for friend named coach a",
                run_context=_run_context(),
                domain_results=[],
            )

    assert captured_args["list_friend_calendar_facts"] == {
        "friend_name": "Coach A",
        "from_date": "2026-05-25",
        "to_date": "2026-05-31",
        "timezone": "Asia/Tokyo",
    }


@pytest.mark.asyncio
async def test_run_scheduling_domain_returns_shared_reminder_status_results():
    captured_args: dict[str, dict] = {}

    class _SharedReminderAgent:
        def __init__(self, **kwargs):
            self.tools = {item.name: item.entrypoint for item in kwargs["tools"]}

        async def arun(self, **kwargs):
            await self.tools["list_shared_reminders"](
                friend_name="Bob",
                status="active",
            )

    class RecordingSchedulingPort:
        def __init__(self, tool_name: str) -> None:
            self.tool_name = tool_name

        async def run(self, input_message, run_context, args):
            captured_args[self.tool_name] = args
            return CapabilityResult(
                name=self.tool_name,
                ok=True,
                content={
                    "friend_name": "Bob",
                    "shared_reminders": [
                        {
                            "id": "srr_1",
                            "title": "打羽毛球",
                            "status": "active",
                            "fireAt": "2026-05-25T08:00:00.000Z",
                            "timezone": "Asia/Tokyo",
                            "creator": {"displayName": "Alice Badminton"},
                            "receiver": {"displayName": "Bob Badminton"},
                        }
                    ],
                },
            )

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _SharedReminderAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: RecordingSchedulingPort(tool_name),
        ):
            result = await run_scheduling_domain(
                input_message="我跟 Bob 那个羽毛球的共享提醒现在是什么状态？",
                intent="list_shared_reminders for friend named Bob status active",
                run_context=_run_context(),
                domain_results=[],
            )

    assert captured_args["list_shared_reminders"] == {
        "friend_name": "Bob",
        "status": "active",
    }
    assert result["operations"][0]["action"] == "list_shared_reminders"
    assert result["operations"][0]["facts"]["shared_reminders"][0]["status"] == "active"


@pytest.mark.asyncio
async def test_run_scheduling_domain_allows_friend_lookup_then_calendar_facts():
    calls: list[str] = []

    class _LookupThenCalendarAgent:
        def __init__(self, **kwargs):
            self.tools = {item.name: item.entrypoint for item in kwargs["tools"]}

        async def arun(self, **kwargs):
            await self.tools["list_friends"]()
            await self.tools["list_friend_calendar_facts"](
                target_account_id="acct_eva",
                from_date="2026-05-25",
                to_date="2026-05-31",
                timezone="Asia/Tokyo",
            )

    class RecordingSchedulingPort:
        def __init__(self, tool_name: str) -> None:
            self.tool_name = tool_name

        async def run(self, input_message, run_context, args):
            calls.append(self.tool_name)
            if self.tool_name == "list_friends":
                return CapabilityResult(
                    name=self.tool_name,
                    ok=True,
                    content={
                        "friends": [{"account_id": "acct_eva", "display_name": "eva"}]
                    },
                )
            return CapabilityResult(
                name=self.tool_name,
                ok=True,
                content={
                    "target_account_id": args["target_account_id"],
                    "busy_intervals": [],
                    "privacy": {"event_details_included": False},
                },
            )

    domain_results: list[DomainExecutionResult] = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.Agent", _LookupThenCalendarAgent
    ):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: RecordingSchedulingPort(tool_name),
        ):
            result = await run_scheduling_domain(
                input_message="eva 有什么时间有空吗？",
                intent="list_friend_calendar_facts for friend named eva",
                run_context=_run_context(),
                domain_results=domain_results,
            )

    assert calls == ["list_friends", "list_friend_calendar_facts"]
    assert [item.error.code if item.error else None for item in domain_results] == [
        None,
        None,
    ]
    assert result["operations"][0]["action"] == "list_friend_calendar_facts"
    assert result["operations"][0]["facts"]["target_account_id"] == "acct_eva"


@pytest.mark.asyncio
async def test_run_scheduling_domain_clarifies_partial_friend_calendar_name_before_tools():
    class _UnexpectedAgent:
        def __init__(self, **kwargs):
            raise AssertionError(
                "ambiguous friend names should not spawn the worker agent"
            )

    class _UnexpectedSchedulingPort:
        def __init__(self, *, tool_name: str) -> None:
            raise AssertionError(
                f"ambiguous friend names should not create scheduling port {tool_name}"
            )

    domain_results: list[DomainExecutionResult] = []

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _UnexpectedAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            _UnexpectedSchedulingPort,
        ):
            result = await run_scheduling_domain(
                input_message="看 B 那个朋友这周的空闲时间。",
                intent='list_friend_calendar_facts: {"friend_name": "B"}',
                run_context=_run_context(),
                domain_results=domain_results,
            )

    assert result["domain"] == "scheduling"
    assert result["outcome"] == "needs_clarification"
    assert result["missing_fields"] == ["friend_name"]
    assert result["safety_boundary"] == "ambiguous_friend_name"
    assert result["reply_contract"]["intent"] == "ask_clarification"
    assert result["reply_contract"]["required_questions"] == ["which_friend"]
    assert result["operations"] == []
    assert result["error"] is None
    assert len(domain_results) == 1


@pytest.mark.asyncio
async def test_run_scheduling_domain_clarifies_partial_friend_calendar_preselected_intent():
    class _UnexpectedAgent:
        def __init__(self, **kwargs):
            raise AssertionError(
                "preselected ambiguous friend calendar intent should not spawn worker agent"
            )

    class _UnexpectedSchedulingPort:
        def __init__(self, *, tool_name: str) -> None:
            raise AssertionError(
                f"ambiguous friend names should not create scheduling port {tool_name}"
            )

    domain_results: list[DomainExecutionResult] = []

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _UnexpectedAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            _UnexpectedSchedulingPort,
        ):
            result = await run_scheduling_domain(
                input_message="看 B 那个朋友这周的空闲时间。",
                intent="list_friend_calendar_facts",
                run_context=_run_context(),
                domain_results=domain_results,
            )

    assert result["outcome"] == "needs_clarification"
    assert result["missing_fields"] == ["friend_name"]
    assert result["safety_boundary"] == "ambiguous_friend_name"
    assert result["operations"] == []
    assert len(domain_results) == 1


@pytest.mark.asyncio
async def test_run_scheduling_domain_clarifies_partial_friend_calendar_forced_args_before_port():
    class _UnexpectedSchedulingPort:
        def __init__(self, *, tool_name: str) -> None:
            raise AssertionError(
                f"ambiguous friend names should not create scheduling port {tool_name}"
            )

    domain_results: list[DomainExecutionResult] = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
        _UnexpectedSchedulingPort,
    ):
        result = await run_scheduling_domain(
            input_message="看 B 那个朋友这周的空闲时间。",
            intent="list_friend_calendar_facts",
            run_context=_run_context(),
            domain_results=domain_results,
            forced_args={"friend_name": "B"},
        )

    assert result["outcome"] == "needs_clarification"
    assert result["missing_fields"] == ["friend_name"]
    assert result["safety_boundary"] == "ambiguous_friend_name"
    assert result["reply_contract"]["intent"] == "ask_clarification"
    assert result["operations"] == []
    assert len(domain_results) == 1


@pytest.mark.asyncio
async def test_run_scheduling_domain_forced_create_rejects_date_time_alias():
    captured_args: dict[str, dict] = {}

    class _UnexpectedAgent:
        def __init__(self, **kwargs):
            raise AssertionError(
                "invalid forced scheduling args should not spawn the worker agent"
            )

    class RecordingSchedulingPort:
        def __init__(self, tool_name: str) -> None:
            self.tool_name = tool_name

        async def run(self, input_message, run_context, args):
            captured_args[self.tool_name] = args
            return CapabilityResult(
                name=self.tool_name,
                ok=True,
                content={"id": "srr_1", "status": "active"},
            )

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _UnexpectedAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: RecordingSchedulingPort(tool_name),
        ):
            result = await run_scheduling_domain(
                input_message="约 Alex 明天下午 3 点上课",
                intent="create_shared_reminder",
                run_context=_run_context(),
                domain_results=[],
                forced_args={
                    "receiver_name": "Alex",
                    "title": "上课",
                    "date_time": "2026-05-27T15:00:00+08:00",
                    "timezone": "Asia/Shanghai",
                },
            )

    assert captured_args == {}
    assert result["outcome"] == "failed"
    assert result["error"]["code"] == "invalid_scheduling_args"


@pytest.mark.asyncio
async def test_run_scheduling_domain_rejects_incomplete_forced_create_args():
    captured_tools: set[str] = set()

    class _SharedReminderAgent:
        def __init__(self, **kwargs):
            captured_tools.update(item.name for item in kwargs["tools"])
            raise AssertionError(
                "incomplete forced scheduling args should not spawn the worker agent"
            )

    class RecordingSchedulingPort:
        def __init__(self, tool_name: str) -> None:
            self.tool_name = tool_name

        async def run(self, input_message, run_context, args):
            return CapabilityResult(
                name=self.tool_name,
                ok=True,
                content={"id": "srr_1", "status": "active"},
            )

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _SharedReminderAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: RecordingSchedulingPort(tool_name),
        ):
            result = await run_scheduling_domain(
                input_message="约 Alex 明天下午 3 点上课",
                intent="create_shared_reminder",
                run_context=_run_context(),
                domain_results=[],
                forced_args={"date_time": "2026-05-27T15:00:00+08:00"},
            )

    assert captured_tools == set()
    assert result["outcome"] == "failed"
    assert result["error"]["code"] == "invalid_scheduling_args"


@pytest.mark.asyncio
async def test_run_scheduling_domain_forwards_lesson_duration_to_shared_reminder():
    captured_args: dict[str, dict] = {}

    class _SharedReminderAgent:
        def __init__(self, **kwargs):
            self.tools = {item.name: item.entrypoint for item in kwargs["tools"]}

        async def arun(self, **kwargs):
            await self.tools["create_shared_reminder"](
                receiver_account_id="acct_coach",
                title="lesson",
                fire_at="2026-05-26T01:00:00+00:00",
                duration_minutes=60,
                timezone="Asia/Tokyo",
                idempotency_key="lesson:acct_coach:2026-05-26T01:00:00Z",
            )

    class RecordingSchedulingPort:
        def __init__(self, tool_name: str) -> None:
            self.tool_name = tool_name

        async def run(self, input_message, run_context, args):
            captured_args[self.tool_name] = args
            return CapabilityResult(
                name=self.tool_name,
                ok=True,
                content={
                    "id": "srr_1",
                    "status": "active",
                },
            )

    domain_results: list[DomainExecutionResult] = []

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _SharedReminderAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: RecordingSchedulingPort(tool_name),
        ):
            result = await run_scheduling_domain(
                input_message="那周二 10 点上课",
                intent="create_shared_reminder for resolved friend acct_coach",
                run_context=_run_context(),
                domain_results=domain_results,
            )

    assert captured_args["create_shared_reminder"] == {
        "receiver_account_id": "acct_coach",
        "title": "lesson",
        "fire_at": "2026-05-26T01:00:00+00:00",
        "duration_minutes": 60,
        "timezone": "Asia/Tokyo",
        "idempotency_key": "lesson:acct_coach:2026-05-26T01:00:00Z",
    }
    operation = result["operations"][0]
    assert operation["action"] == "create_shared_reminder"
    assert operation["effect"] == "write"
    assert operation["entity_type"] == "shared_reminder"
    assert operation["entity_id"] == "srr_1"
    assert operation["facts"]["status"] == "active"


@pytest.mark.asyncio
async def test_run_scheduling_domain_exposes_only_create_tool_for_shared_reminder_intent():
    captured_tools: set[str] = set()

    class _SharedReminderAgent:
        def __init__(self, **kwargs):
            captured_tools.update(item.name for item in kwargs["tools"])
            self.tools = {item.name: item.entrypoint for item in kwargs["tools"]}

        async def arun(self, **kwargs):
            await self.tools["create_shared_reminder"](
                receiver_name="Nora",
                title="meeting",
                fire_at="2026-05-25T06:00:00+00:00",
                timezone="Asia/Tokyo",
                idempotency_key="shared:nora:2026-05-25T06:00:00Z",
            )

    class RecordingSchedulingPort:
        def __init__(self, tool_name: str) -> None:
            self.tool_name = tool_name

        async def run(self, input_message, run_context, args):
            return CapabilityResult(
                name=self.tool_name,
                ok=True,
                content={"id": "srr_1", "status": "active"},
            )

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _SharedReminderAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: RecordingSchedulingPort(tool_name),
        ):
            await run_scheduling_domain(
                input_message="帮我和 Nora 建一个共享提醒",
                intent="create_shared_reminder for Nora",
                run_context=_run_context(),
                domain_results=[],
            )

    assert captured_tools == {"create_shared_reminder"}


@pytest.mark.asyncio
async def test_run_scheduling_domain_exposes_only_user_link_code_tool_for_link_friend_intent():
    captured_tools: set[str] = set()
    captured_args: dict[str, dict] = {}

    class _UserLinkFriendAgent:
        def __init__(self, **kwargs):
            captured_tools.update(item.name for item in kwargs["tools"])
            self.tools = {item.name: item.entrypoint for item in kwargs["tools"]}

        async def arun(self, **kwargs):
            await self.tools["create_friendship_by_user_link_code"](
                user_link_code="AbCdEfGhIjK_",
                message="跑步搭子",
                idempotency_key="friend-link:1",
            )

    class RecordingSchedulingPort:
        def __init__(self, tool_name: str) -> None:
            self.tool_name = tool_name

        async def run(self, input_message, run_context, args):
            captured_args[self.tool_name] = args
            return CapabilityResult(
                name=self.tool_name,
                ok=True,
                content={"friendship_id": "fs_1", "status": "active"},
            )

    with patch("agent.agno_agent.runtime.execution_agents.Agent", _UserLinkFriendAgent):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: RecordingSchedulingPort(tool_name),
        ):
            await run_scheduling_domain(
                input_message="我想加好友。这是对方的邀请链接码：AbCdEfGhIjK_。备注：跑步搭子。",
                intent="通过邀请链接码加好友",
                run_context=_run_context(),
                domain_results=[],
            )

    assert captured_tools == {"create_friendship_by_user_link_code"}
    assert captured_args["create_friendship_by_user_link_code"] == {
        "user_link_code": "AbCdEfGhIjK_",
        "message": "跑步搭子",
        "idempotency_key": "friend-link:1",
    }


@pytest.mark.asyncio
async def test_run_scheduling_domain_preserves_success_when_later_tool_call_duplicates():
    successful_write = CapabilityResult(
        name="reset_user_link",
        ok=True,
        content={
            "user_link_id": "link-1",
            "visible_summary": "Your booking link was reset.",
        },
    )

    class _DuplicateCallingAgent:
        def __init__(self, **kwargs):
            self.tools = {item.name: item.entrypoint for item in kwargs["tools"]}

        async def arun(self, **kwargs):
            await self.tools["reset_user_link"]()
            await self.tools["disable_user_link"]()

    domain_results: list[DomainExecutionResult] = []

    with patch(
        "agent.agno_agent.runtime.execution_agents.Agent", _DuplicateCallingAgent
    ):
        with patch(
            "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
            side_effect=lambda *, tool_name: _SyncPort(successful_write),
        ):
            result = await run_scheduling_domain(
                input_message="reset my link and then disable it",
                intent="reset_user_link",
                run_context=_run_context(),
                domain_results=domain_results,
            )

    assert result["domain"] == "scheduling"
    assert result["outcome"] == "executed"
    assert result["error"] is None
    assert result["operations"][0]["action"] == "reset_user_link"
    assert result["operations"][0]["effect"] == "write"
    assert result["operations"][0]["entity_id"] == "link-1"
    assert result["operations"][0]["facts"]["user_link_id"] == "link-1"
    assert [item.error.code if item.error else None for item in domain_results] == [
        None,
        "duplicate_scheduling_tool_call",
    ]


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
    assert result["operations"][0]["facts"]["visible_summary"] == "called get_user_link"
