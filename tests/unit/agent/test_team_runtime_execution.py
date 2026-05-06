import sys
import types
from datetime import UTC, datetime

import pytest


class FakeTeam:
    last_instance = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakeTeam.last_instance = self

    async def arun(self, input, **kwargs):
        self.input = input
        self.run_kwargs = kwargs
        yield types.SimpleNamespace(
            event="TeamRunContent",
            content="RESPONSE:\n我来处理。\nREQUEST reminder_intent {}",
        )


def _install_fake_team(monkeypatch, team_cls=FakeTeam):
    team_mod = types.ModuleType("agno.team")
    team_mod.Team = team_cls
    monkeypatch.setitem(sys.modules, "agno.team", team_mod)


def _legacy_context():
    return {
        "user": {"id": "user-1", "nickname": "User", "timezone": "UTC"},
        "character": {"id": "char-1", "nickname": "Coke"},
        "conversation": {
            "id": "conv-1",
            "platform": "business",
            "conversation_info": {"chat_history_str": "User: hi"},
        },
        "relation": {"uid": "user-1", "cid": "char-1"},
        "platform": "business",
    }


@pytest.mark.asyncio
async def test_run_team_runtime_invokes_team_and_executes_requested_capability(
    monkeypatch,
):
    _install_fake_team(monkeypatch)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeReminderPort:
        async def run(self, input_message, run_context, args=None):
            assert input_message == "18:00 remind me to drink water"
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：drink water"},
                metadata={"durable_write": True},
            )

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="18:00 remind me to drink water",
        message_source="user",
        metadata={"request_id": "req-1"},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": FakeReminderPort()},
    )

    assert result.visible_messages[0].content == "我来处理。"
    assert result.tool_results[0].name == "reminder"
    assert result.output_disposition.status == "ok"
    assert result.post_analyze_input == {
        "input_message": "18:00 remind me to drink water",
        "message_source": "user",
    }
    assert result.trace["runtime"] == "team"
    assert result.trace["capability_requests"] == ("reminder_intent",)
    assert FakeTeam.last_instance.kwargs["name"] == "CokeManagerTeam"
    assert "conversation_id: conv-1" in FakeTeam.last_instance.input


@pytest.mark.asyncio
async def test_run_team_runtime_builds_default_capability_ports(monkeypatch):
    _install_fake_team(monkeypatch)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeReminderPort:
        async def run(self, input_message, run_context, args=None):
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "default reminder port used"},
            )

    monkeypatch.setattr(team_runtime, "ReminderIntentPort", FakeReminderPort)

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="18:00 remind me to drink water",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
    )

    assert result.tool_results[0].content["summary"] == "default reminder port used"


@pytest.mark.asyncio
async def test_run_team_runtime_empty_output_returns_empty_disposition(monkeypatch):
    class EmptyTeam(FakeTeam):
        async def arun(self, input, **kwargs):
            yield types.SimpleNamespace(event="TeamRunCompleted", content=None)

    _install_fake_team(monkeypatch, EmptyTeam)
    from agent.agno_agent.runtime import team_runtime

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="hello",
        message_source="user",
        metadata=None,
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition.code == "team_runtime_empty_output"


@pytest.mark.asyncio
async def test_run_team_runtime_accepts_coroutine_run_response(monkeypatch):
    class CoroutineTeam(FakeTeam):
        async def arun(self, input, **kwargs):
            self.input = input
            self.run_kwargs = kwargs
            return types.SimpleNamespace(
                content="RESPONSE:\n我来处理。\nREQUEST reminder_intent {}"
            )

    _install_fake_team(monkeypatch, CoroutineTeam)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeReminderPort:
        async def run(self, input_message, run_context, args=None):
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒"},
            )

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="18:00 remind me",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": FakeReminderPort()},
    )

    assert result.visible_messages[0].content == "我来处理。"
    assert result.tool_results[0].content["summary"] == "已创建提醒"


@pytest.mark.asyncio
async def test_run_team_runtime_sends_capability_summary_when_manager_only_requests(
    monkeypatch,
):
    class RequestOnlyTeam(FakeTeam):
        async def arun(self, input, **kwargs):
            self.input = input
            self.run_kwargs = kwargs
            return types.SimpleNamespace(content="REQUEST reminder_intent {}")

    _install_fake_team(monkeypatch, RequestOnlyTeam)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeReminderPort:
        async def run(self, input_message, run_context, args=None):
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：喝水；已创建提醒：锻炼"},
                metadata={"durable_write": True},
            )

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="今天17:57提醒我喝水，每天17:58提醒我锻炼",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": FakeReminderPort()},
    )

    assert result.visible_messages[0].content == "已创建提醒：喝水；已创建提醒：锻炼"
    assert result.output_disposition.status == "ok"
    assert result.post_analyze_input == {
        "input_message": "今天17:57提醒我喝水，每天17:58提醒我锻炼",
        "message_source": "user",
    }
