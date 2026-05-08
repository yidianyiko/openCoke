import sys
import types
import asyncio
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


def test_team_manager_default_timeouts_are_bounded_for_live_eval(monkeypatch):
    from agent.agno_agent.runtime import team_runtime

    monkeypatch.delenv("COKE_TEAM_MANAGER_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("COKE_TEAM_MANAGER_RETRY_TIMEOUT_SECONDS", raising=False)

    assert team_runtime._team_manager_timeout_seconds() == 30.0
    assert team_runtime._team_manager_retry_timeout_seconds() == 10.0


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

    assert result.visible_messages[0].content == "已创建提醒：drink water"
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
async def test_run_team_runtime_uses_reminder_detect_model_for_manager(monkeypatch):
    _install_fake_team(monkeypatch)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    captured = {}

    def fake_create_llm_model(*, max_tokens, role=None):
        captured["max_tokens"] = max_tokens
        captured["role"] = role
        return object()

    monkeypatch.setattr(team_runtime, "create_llm_model", fake_create_llm_model)

    class FakeReminderPort:
        async def run(self, input_message, run_context, args=None):
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
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": FakeReminderPort()},
    )

    assert result.output_disposition.status == "ok"
    assert captured == {"max_tokens": 2000, "role": "reminder_detect"}


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

    assert result.visible_messages[0].content == "已创建提醒"
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


@pytest.mark.asyncio
async def test_run_team_runtime_returns_empty_when_capability_has_no_visible_summary(
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

    class NoopReminderPort:
        async def run(self, input_message, run_context, args=None):
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"action": "none", "intent_type": "discussion"},
                metadata={"durable_write": False},
            )

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="嗯嗯计划写的4点半开始",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": NoopReminderPort()},
    )

    assert result.visible_messages == ()
    assert result.tool_results[0].content["action"] == "none"
    assert result.output_disposition.status == "empty"
    assert result.error_disposition.code == "team_runtime_empty_output"
    assert result.trace["capability_requests"] == ("reminder_intent",)


@pytest.mark.asyncio
async def test_run_team_runtime_surfaces_capability_message_when_summary_missing(
    monkeypatch,
):
    class TimezoneOnlyTeam(FakeTeam):
        async def arun(self, input, **kwargs):
            self.input = input
            self.run_kwargs = kwargs
            return types.SimpleNamespace(
                content='REQUEST timezone {"action":"direct_set","timezone":"Asia/Tokyo"}'
            )

    _install_fake_team(monkeypatch, TimezoneOnlyTeam)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeTimezonePort:
        def run(self, input_message, run_context, args=None):
            return CapabilityResult(
                name="timezone",
                ok=True,
                content={
                    "ok": True,
                    "message": "已将您的时区更新为东京时间（UTC+9）。",
                    "state": {"timezone": "Asia/Tokyo"},
                },
                metadata={"durable_write": True},
            )

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="把我的时区改成东京",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"timezone": FakeTimezonePort()},
    )

    assert result.visible_messages[0].content == "已将您的时区更新为东京时间（UTC+9）。"
    assert result.output_disposition.status == "ok"
    assert result.trace["capability_requests"] == ("timezone",)


@pytest.mark.asyncio
async def test_run_team_runtime_uses_capability_protocol_visible_summary(monkeypatch):
    class TimezoneOnlyTeam(FakeTeam):
        async def arun(self, input, **kwargs):
            self.input = input
            self.run_kwargs = kwargs
            return types.SimpleNamespace(
                content='REQUEST timezone {"action":"direct_set","timezone":"Asia/Tokyo"}'
            )

    _install_fake_team(monkeypatch, TimezoneOnlyTeam)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeTimezonePort:
        def run(self, input_message, run_context, args=None):
            return CapabilityResult(
                name="timezone",
                ok=True,
                content={
                    "visible_summary": "已按协议更新为东京时间。",
                    "state": {"timezone": "Asia/Tokyo"},
                },
                metadata={"durable_write": True},
            )

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="把我的时区改成东京",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"timezone": FakeTimezonePort()},
    )

    assert result.visible_messages[0].content == "已按协议更新为东京时间。"
    assert result.output_disposition.status == "ok"


@pytest.mark.asyncio
async def test_run_team_runtime_synthesizes_reply_after_url_context(monkeypatch):
    class UrlThenAnswerTeam(FakeTeam):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.calls = 0

        async def arun(self, input, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return types.SimpleNamespace(content="REQUEST url_context {}")
            assert "Capability results:" in input
            assert "Example article text" in input
            return types.SimpleNamespace(content="RESPONSE:\n这篇文章主要讲 example。")

    _install_fake_team(monkeypatch, UrlThenAnswerTeam)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeUrlPort:
        def run(self, input_message, run_context, args=None):
            return CapabilityResult(
                name="url_context",
                ok=True,
                content={
                    "items": [
                        {"url": "https://example.com", "text": "Example article text"}
                    ],
                    "context": "Example article text",
                },
                metadata={"durable_write": False, "requires_response_synthesis": True},
            )

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="帮我看下 https://example.com 讲了什么",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"url_context": FakeUrlPort()},
    )

    assert result.visible_messages[0].content == "这篇文章主要讲 example。"
    assert result.trace["response_synthesized_after_capabilities"] is True


@pytest.mark.asyncio
async def test_run_team_runtime_returns_retryable_empty_on_manager_timeout(
    monkeypatch,
):
    class HangingTeam(FakeTeam):
        async def arun(self, input, **kwargs):
            await asyncio.sleep(60)

    _install_fake_team(monkeypatch, HangingTeam)
    monkeypatch.setenv("COKE_TEAM_MANAGER_TIMEOUT_SECONDS", "0.01")

    from agent.agno_agent.runtime import team_runtime

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="17:57提醒我喝水",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={},
    )

    assert result.visible_messages == ()
    assert result.trace["manager_timeout"] is True
    assert result.trace["capability_requests"] == ()
    assert result.error_disposition.code == "team_runtime_empty_output"


@pytest.mark.asyncio
async def test_run_team_runtime_deduplicates_repeated_capability_requests(
    monkeypatch,
):
    class DuplicateRequestTeam(FakeTeam):
        async def arun(self, input, **kwargs):
            return types.SimpleNamespace(
                content=(
                    "RESPONSE:\n我来处理。\n"
                    "REQUEST reminder_intent {}\n"
                    "REQUEST reminder_intent {}\n"
                )
            )

    _install_fake_team(monkeypatch, DuplicateRequestTeam)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeReminderPort:
        def __init__(self):
            self.calls = 0

        async def run(self, input_message, run_context, args=None):
            self.calls += 1
            if self.calls > 1:
                raise TimeoutError("second reminder call should not run")
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：喝水"},
                metadata={"durable_write": True},
            )

    reminder_port = FakeReminderPort()

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="17:57提醒我喝水",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": reminder_port},
    )

    assert reminder_port.calls == 1
    assert result.visible_messages[0].content == "已创建提醒：喝水"
    assert result.trace["capability_requests"] == ("reminder_intent",)


@pytest.mark.asyncio
async def test_run_team_runtime_retries_empty_manager_output(monkeypatch):
    class EmptyThenRequestTeam(FakeTeam):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.calls = 0

        async def arun(self, input, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return types.SimpleNamespace(content="")
            assert "Previous manager output was empty" in input
            assert "REQUEST reminder_intent" in input
            return types.SimpleNamespace(content="REQUEST reminder_intent {}")

    _install_fake_team(monkeypatch, EmptyThenRequestTeam)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeReminderPort:
        async def run(self, input_message, run_context, args=None):
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：打卡"},
                metadata={"durable_write": True},
            )

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="每小时打卡，到晚上8点",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": FakeReminderPort()},
    )

    assert result.visible_messages[0].content == "已创建提醒：打卡"
    assert result.trace["manager_empty_retried"] is True
    assert result.trace["capability_requests"] == ("reminder_intent",)


@pytest.mark.asyncio
async def test_run_team_runtime_retries_manager_protocol_artifact(monkeypatch):
    class ArtifactThenRequestTeam(FakeTeam):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.calls = 0

        async def arun(self, input, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return types.SimpleNamespace(content="Operation cancelled by user")
            assert "Previous manager output violated" in input
            return types.SimpleNamespace(content="REQUEST reminder_intent {}")

    _install_fake_team(monkeypatch, ArtifactThenRequestTeam)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeReminderPort:
        async def run(self, input_message, run_context, args=None):
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：喝水"},
                metadata={"durable_write": True},
            )

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="17:57提醒我喝水",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": FakeReminderPort()},
    )

    assert result.visible_messages[0].content == "已创建提醒：喝水"
    assert result.trace["manager_protocol_retried"] is True
    assert result.trace["capability_requests"] == ("reminder_intent",)


@pytest.mark.asyncio
async def test_run_team_runtime_bounds_protocol_retry_timeout(monkeypatch):
    class ArtifactThenHangingRetryTeam(FakeTeam):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.calls = 0

        async def arun(self, input, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return types.SimpleNamespace(content="Operation cancelled by user")
            await asyncio.sleep(60)

    _install_fake_team(monkeypatch, ArtifactThenHangingRetryTeam)
    monkeypatch.setenv("COKE_TEAM_MANAGER_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("COKE_TEAM_MANAGER_RETRY_TIMEOUT_SECONDS", "0.01")

    from agent.agno_agent.runtime import team_runtime

    result = await asyncio.wait_for(
        team_runtime.run_team_runtime(
            context=_legacy_context(),
            input_message_str="明晚 8pm 提醒我做timesheet",
            message_source="user",
            metadata={},
            current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
            capability_ports={},
        ),
        timeout=0.5,
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.trace["manager_timeout"] is True
    assert result.trace["manager_protocol_retried"] is True


@pytest.mark.asyncio
async def test_run_team_runtime_retries_provider_tool_artifact(monkeypatch):
    class ArtifactThenClarifyTeam(FakeTeam):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.calls = 0

        async def arun(self, input, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return types.SimpleNamespace(
                    content=(
                        "明天帮你设置提醒。\n"
                        "<minimax:tool_call>\n"
                        '<invoke name="reminder_intent">\n'
                        '<parameter name="action">create</parameter>\n'
                        "</invoke>\n"
                        "</minimax:tool_call>"
                    )
                )
            assert "Previous manager output violated" in input
            return types.SimpleNamespace(content="REQUEST reminder_intent {}")

    _install_fake_team(monkeypatch, ArtifactThenClarifyTeam)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeReminderPort:
        async def run(self, input_message, run_context, args=None):
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "明天几点提醒你看文章？"},
                metadata={"durable_write": False},
            )

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="明天继续提醒我看文章，要看完",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": FakeReminderPort()},
    )

    assert result.visible_messages[0].content == "明天几点提醒你看文章？"
    assert result.trace["manager_protocol_retried"] is True
    assert result.trace["capability_requests"] == ("reminder_intent",)


@pytest.mark.asyncio
async def test_run_team_runtime_retries_bracket_tool_artifact(monkeypatch):
    class BracketArtifactThenRequestTeam(FakeTeam):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.calls = 0

        async def arun(self, input, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return types.SimpleNamespace(
                    content=(
                        "我已为您设置了每天的提醒。\n"
                        "[TOOL_CALL]\n"
                        '{tool => "reminder_intent", args => {\n'
                        '  --action "create"\n'
                        "}}\n"
                        "[/TOOL_CALL]"
                    )
                )
            assert "Previous manager output violated" in input
            return types.SimpleNamespace(content="REQUEST reminder_intent {}")

    _install_fake_team(monkeypatch, BracketArtifactThenRequestTeam)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeReminderPort:
        async def run(self, input_message, run_context, args=None):
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：起床"},
                metadata={"durable_write": True},
            )

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="7:15起床，我需要你在上述这些时间提醒我",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": FakeReminderPort()},
    )

    assert result.visible_messages[0].content == "已创建提醒：起床"
    assert result.trace["manager_protocol_retried"] is True
    assert result.trace["capability_requests"] == ("reminder_intent",)


@pytest.mark.asyncio
async def test_run_team_runtime_delegates_reminder_after_failed_protocol_retries(
    monkeypatch,
):
    class RepeatedArtifactTeam(FakeTeam):
        async def arun(self, input, **kwargs):
            return types.SimpleNamespace(content="Operation cancelled by user")

    _install_fake_team(monkeypatch, RepeatedArtifactTeam)
    from agent.agno_agent.runtime import team_runtime
    from agent.agno_agent.runtime.result import CapabilityResult

    class FakeReminderPort:
        async def run(self, input_message, run_context, args=None):
            assert input_message == "大概你在晚上10:00提醒我"
            assert args == {}
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "晚上10:00提醒你什么？"},
                metadata={"durable_write": False},
            )

    result = await team_runtime.run_team_runtime(
        context=_legacy_context(),
        input_message_str="大概你在晚上10:00提醒我",
        message_source="user",
        metadata={},
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
        capability_ports={"reminder_intent": FakeReminderPort()},
    )

    assert result.visible_messages[0].content == "晚上10:00提醒你什么？"
    assert result.output_disposition.status == "ok"
    assert result.trace["manager_protocol_retried"] is True
    assert result.trace["manager_empty_retried"] is True
    assert result.trace["capability_requests"] == ("reminder_intent",)
