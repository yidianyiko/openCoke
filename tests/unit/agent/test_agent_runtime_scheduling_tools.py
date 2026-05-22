from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from agno.tools import tool

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
    tool_results = []
    domain_results = []
    context = _run_context()

    fn = _make_scheduling_tool_fn(
        "create_shared_reminder",
        port,
        input_message="Help me and A remember the meeting",
        run_context=context,
        tool_results=tool_results,
        domain_results=domain_results,
    )
    result = await fn(
        invitee_account_id="acct_a",
        title="meeting",
        fire_at="2026-05-22T07:00:00.000Z",
        timezone="Asia/Shanghai",
        idempotency_key="shared-1",
    )

    assert result["ok"] is True
    assert port.calls == [
        (
            "Help me and A remember the meeting",
            context,
            {
                "invitee_account_id": "acct_a",
                "title": "meeting",
                "fire_at": "2026-05-22T07:00:00.000Z",
                "timezone": "Asia/Shanghai",
                "idempotency_key": "shared-1",
            },
        )
    ]
    assert [item.name for item in tool_results] == ["create_shared_reminder"]
    assert [item.name for item in domain_results] == ["create_shared_reminder"]


def test_scheduling_tool_fn_schema_exposes_top_level_arguments():
    fn = _make_scheduling_tool_fn(
        "create_shared_reminder",
        RecordingPort(name="create_shared_reminder"),
        input_message="Help me and A remember the meeting",
        run_context=_run_context(),
        tool_results=[],
        domain_results=[],
    )
    function = tool(name="create_shared_reminder")(fn)

    assert "kwargs" not in function.parameters["properties"]
    assert "invitee_account_id" in function.parameters["properties"]
    assert "title" in function.parameters["properties"]
    assert "fire_at" in function.parameters["properties"]
    assert "idempotency_key" in function.parameters["properties"]


def test_scheduling_tool_fn_schema_exposes_friend_and_shared_reminder_arguments():
    fn = _make_scheduling_tool_fn(
        "block_account",
        RecordingPort(name="block_account"),
        input_message="block that account",
        run_context=_run_context(),
        tool_results=[],
        domain_results=[],
    )
    function = tool(name="block_account")(fn)

    assert "request_id" in function.parameters["properties"]
    assert "friendship_id" in function.parameters["properties"]
    assert "blocked_account_id" in function.parameters["properties"]


@pytest.mark.asyncio
async def test_scheduling_tool_fn_compacts_empty_shared_reminder_args():
    port = RecordingPort(name="create_shared_reminder")
    fn = _make_scheduling_tool_fn(
        "create_shared_reminder",
        port,
        input_message="Help me and A remember the meeting",
        run_context=_run_context(),
        tool_results=[],
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
