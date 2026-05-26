from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from agno.tools import tool

from agent.agno_agent.runtime.domain_results import DomainExecutionResult
from agent.agno_agent.runtime.execution_agents import _make_scheduling_tool_fn
from agent.agno_agent.runtime.result import CapabilityResult


def _run_context():
    return SimpleNamespace(
        user=SimpleNamespace(id="ck_a", nickname="Coach A", timezone="Asia/Shanghai"),
        character=SimpleNamespace(id="char_1", nickname="Coke"),
        conversation=SimpleNamespace(id="conv_1", route_key="wechat_personal:primary"),
        relation=SimpleNamespace(uid="ck_a", cid="char_1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 6, 1, tzinfo=UTC),
    )


class RecordingPort:
    def __init__(self, name="get_user_link"):
        self.name = name
        self.calls = []

    def run(self, input_message, run_context, args):
        self.calls.append((input_message, run_context, args))
        return CapabilityResult(
            name=self.name,
            ok=True,
            content={"url": "https://kap.example/u/AbCdEfGhIjK_"},
        )


@pytest.mark.asyncio
async def test_scheduling_tool_fn_dispatches_model_args():
    port = RecordingPort(name="create_shared_reminder")
    domain_results: list[DomainExecutionResult] = []
    context = _run_context()

    fn = _make_scheduling_tool_fn(
        "create_shared_reminder",
        port,
        input_message="Help me and A remember the meeting",
        run_context=context,
        domain_results=domain_results,
    )
    result = await fn(
        invitee_account_id="acct_a",
        invitee_name="Coach A",
        title="meeting",
        fire_at="2026-05-22T07:00:00.000Z",
        timezone="Asia/Shanghai",
        idempotency_key="shared-1",
    )

    assert result["domain"] == "scheduling"
    assert result["outcome"] == "executed"
    assert result["operations"][0]["action"] == "create_shared_reminder"
    assert port.calls == [
        (
            "Help me and A remember the meeting",
            context,
            {
                "invitee_account_id": "acct_a",
                "invitee_name": "Coach A",
                "title": "meeting",
                "fire_at": "2026-05-22T07:00:00.000Z",
                "timezone": "Asia/Shanghai",
                "idempotency_key": "shared-1",
            },
        )
    ]
    assert [item.operations[0].action for item in domain_results] == [
        "create_shared_reminder"
    ]


def test_scheduling_tool_fn_schema_exposes_top_level_arguments():
    fn = _make_scheduling_tool_fn(
        "create_shared_reminder",
        RecordingPort(name="create_shared_reminder"),
        input_message="Help me and A remember the meeting",
        run_context=_run_context(),
        domain_results=[],
    )
    function = tool(name="create_shared_reminder")(fn)

    assert "kwargs" not in function.parameters["properties"]
    assert "invitee_account_id" in function.parameters["properties"]
    assert "invitee_name" in function.parameters["properties"]
    assert "friend_account_id" in function.parameters["properties"]
    assert "title" in function.parameters["properties"]
    assert "fire_at" in function.parameters["properties"]
    assert "idempotency_key" in function.parameters["properties"]
    assert "duration_minutes" in function.parameters["properties"]
    assert "status" in function.parameters["properties"]


@pytest.mark.asyncio
async def test_scheduling_tool_fn_maps_friend_account_id_to_invitee_account_id():
    port = RecordingPort(name="create_shared_reminder")
    fn = _make_scheduling_tool_fn(
        "create_shared_reminder",
        port,
        input_message="Help me and Nora remember the meeting",
        run_context=_run_context(),
        domain_results=[],
    )

    await fn(
        friend_account_id="acct_nora",
        title="meeting",
        fire_at="2026-05-22T07:00:00.000Z",
        timezone="Asia/Shanghai",
    )

    assert port.calls[0][2] == {
        "invitee_account_id": "acct_nora",
        "title": "meeting",
        "fire_at": "2026-05-22T07:00:00.000Z",
        "timezone": "Asia/Shanghai",
    }


@pytest.mark.asyncio
async def test_scheduling_tool_fn_exposes_calendar_fact_args():
    port = RecordingPort(name="list_friend_calendar_facts")
    fn = _make_scheduling_tool_fn(
        "list_friend_calendar_facts",
        port,
        input_message="What free time does Coach A have this week?",
        run_context=_run_context(),
        domain_results=[],
    )
    result = await fn(
        target_account_id="acct_a",
        from_date="2026-05-25",
        to_date="2026-05-31",
        timezone="Asia/Tokyo",
    )

    assert result["domain"] == "scheduling"
    assert port.calls[0][2] == {
        "target_account_id": "acct_a",
        "from_date": "2026-05-25",
        "to_date": "2026-05-31",
        "timezone": "Asia/Tokyo",
    }


@pytest.mark.asyncio
async def test_scheduling_tool_fn_exposes_shared_reminder_status_args():
    port = RecordingPort(name="list_shared_reminders")
    fn = _make_scheduling_tool_fn(
        "list_shared_reminders",
        port,
        input_message="What status is the shared reminder with Bob?",
        run_context=_run_context(),
        domain_results=[],
    )
    result = await fn(
        friend_name="Bob",
        status="accepted",
    )

    assert result["domain"] == "scheduling"
    assert port.calls[0][2] == {
        "friend_name": "Bob",
        "status": "accepted",
    }


def test_scheduling_tool_fn_schema_exposes_friend_and_shared_reminder_arguments():
    fn = _make_scheduling_tool_fn(
        "create_shared_reminder",
        RecordingPort(name="create_shared_reminder"),
        input_message="create a shared reminder with Bob",
        run_context=_run_context(),
        domain_results=[],
    )
    function = tool(name="create_shared_reminder")(fn)

    assert "request_id" in function.parameters["properties"]
    assert "friendship_id" in function.parameters["properties"]
    assert "friend_name" in function.parameters["properties"]


@pytest.mark.asyncio
async def test_scheduling_tool_fn_dispatches_user_link_code_friend_request_args():
    port = RecordingPort(name="send_friend_request_by_user_link_code")
    fn = _make_scheduling_tool_fn(
        "send_friend_request_by_user_link_code",
        port,
        input_message="我要加 Ming 为好友，链接码 AbCdEfGhIjK_，备注：一起测试提醒。",
        run_context=_run_context(),
        domain_results=[],
    )

    await fn(
        user_link_code="AbCdEfGhIjK_",
        message="一起测试提醒",
        idempotency_key="friend:req:code",
    )

    assert port.calls[0][2] == {
        "user_link_code": "AbCdEfGhIjK_",
        "message": "一起测试提醒",
        "idempotency_key": "friend:req:code",
    }


@pytest.mark.asyncio
async def test_scheduling_tool_fn_dispatches_friend_name_for_friend_request_actions():
    port = RecordingPort(name="accept_friend_request")
    fn = _make_scheduling_tool_fn(
        "accept_friend_request",
        port,
        input_message="通过 Bob 的好友请求",
        run_context=_run_context(),
        domain_results=[],
    )

    await fn(
        friend_name="Bob",
        requester_name="Bob",
        request_id="",
        idempotency_key="friend:req:accept",
    )

    assert port.calls[0][2] == {
        "friend_name": "Bob",
        "requester_name": "Bob",
        "idempotency_key": "friend:req:accept",
    }


def test_scheduling_execution_prompt_owns_defaults_and_backend_boundaries():
    from agent.agno_agent.runtime import execution_agents

    prompt = execution_agents._SCHEDULING_SYSTEM_PROMPT

    # Gateway now resolves the friend by friend_name; the legacy "call
    # list_friends first" instruction was removed once the resolver landed.
    assert "always pass from_date + to_date" in prompt
    assert "Do not ask the backend for recommended slots" in prompt
    assert "Do not use Google Calendar for friend availability" in prompt
    assert "use 60 minutes unless the user states another duration" in prompt
    assert "Otherwise pass duration_minutes only after" in prompt


@pytest.mark.asyncio
async def test_scheduling_tool_fn_compacts_empty_shared_reminder_args():
    port = RecordingPort(name="create_shared_reminder")
    fn = _make_scheduling_tool_fn(
        "create_shared_reminder",
        port,
        input_message="Help me and A remember the meeting",
        run_context=_run_context(),
        domain_results=[],
    )

    await fn(
        invitee_account_id="acct_a",
        title="meeting",
        fire_at="2026-05-22T07:00:00.000Z",
        timezone="Asia/Shanghai",
        idempotency_key="",
    )

    assert port.calls[0][2] == {
        "invitee_account_id": "acct_a",
        "title": "meeting",
        "fire_at": "2026-05-22T07:00:00.000Z",
        "timezone": "Asia/Shanghai",
    }
