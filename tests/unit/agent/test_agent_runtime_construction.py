import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import agent.agno_agent.runtime.agent_runtime as agent_runtime
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import (
    AgentInput,
    ReminderFirePayload,
    UserTurnPayload,
)
from agent.agno_agent.runtime.result import AgentRunResult, CapabilityResult


def _agent_input() -> AgentInput:
    return AgentInput(
        input_type="user.turn",
        conversation_id="conv-1",
        text="hi",
        payload=UserTurnPayload(current_message_ids=["msg-1"]),
        occurred_at=datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
    )


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
        recent_chat_history="User: hi",
        current_time=datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
        runtime_metadata={"message_source": "user"},
    )


@pytest.mark.asyncio
async def test_run_agent_runtime_returns_agent_run_result_for_no_tool_run(monkeypatch):
    create_kwargs = {}
    model_inputs = []

    class FakeAgent:
        async def arun(self, **kwargs):
            model_inputs.append(kwargs["input"])
            assert kwargs["session_id"] == "conv-1"
            return SimpleNamespace(
                content="fallback content",
                messages=[
                    SimpleNamespace(role="user", content="hi"),
                    SimpleNamespace(role="assistant", content="hi back"),
                ],
            )

    def fake_create_agent(**kwargs):
        create_kwargs.update(kwargs)
        return FakeAgent()

    monkeypatch.setattr(agent_runtime, "_create_agent", fake_create_agent)

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert isinstance(result, AgentRunResult)
    assert result.visible_messages[0].content == "hi back"
    assert result.output_disposition.status == "ok"
    assert result.tool_results == ()
    assert result.post_analyze_input == {
        "input_message": "hi",
        "message_source": "user",
    }
    assert create_kwargs["input_message"] == "hi"
    assert create_kwargs["tool_results"] == []
    model_input = model_inputs[0]
    assert "input_type: user.turn" in model_input
    assert "message_source: user" in model_input
    assert "current_time: 2026-05-09T01:00:00+00:00" in model_input
    assert "user: User (user-1)" in model_input
    assert "character: Coke (char-1)" in model_input
    assert "recent_chat_history:\nUser: hi" in model_input
    assert "user_message:\nhi" in model_input


@pytest.mark.asyncio
async def test_run_agent_runtime_uses_captured_tool_results(monkeypatch):
    class FakeAgent:
        async def arun(self, **kwargs):
            return SimpleNamespace(
                content="ignored",
                messages=[
                    SimpleNamespace(role="tool", content='{"ok": true}'),
                    SimpleNamespace(role="assistant", content=""),
                ],
                tool_results=[
                    CapabilityResult(
                        name="ignored_run_output_field",
                        ok=True,
                        content={"visible_summary": "wrong"},
                    )
                ],
            )

    def fake_create_agent(**kwargs):
        kwargs["tool_results"].append(
            CapabilityResult(
                name="reminder",
                ok=True,
                content={"visible_summary": "已为你设好提醒"},
                metadata={"durable_write": True},
            )
        )
        return FakeAgent()

    monkeypatch.setattr(agent_runtime, "_create_agent", fake_create_agent)

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert result.visible_messages[0].content == "已为你设好提醒"
    assert [tool.name for tool in result.tool_results] == ["reminder"]


@pytest.mark.asyncio
async def test_run_agent_runtime_preflights_explicit_reminder_intent(monkeypatch):
    class FakeReminderPort:
        async def run(self, input_message, run_context, args=None):
            assert input_message == "18:05提醒我出门"
            assert args == {}
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：出门（2026-05-10 18:05）"},
                metadata={"durable_write": True},
            )

    def fake_default_ports():
        return {"reminder_intent": FakeReminderPort()}

    def fail_create_agent(**kwargs):
        raise AssertionError("explicit reminders should route to ReminderDetect first")

    monkeypatch.setattr(agent_runtime, "_default_capability_ports", fake_default_ports)
    monkeypatch.setattr(agent_runtime, "_create_agent", fail_create_agent)

    agent_input = _agent_input()
    agent_input = type(agent_input)(
        input_type=agent_input.input_type,
        conversation_id=agent_input.conversation_id,
        text="18:05提醒我出门",
        payload=agent_input.payload,
        occurred_at=agent_input.occurred_at,
        metadata=agent_input.metadata,
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=agent_input,
        run_context=_run_context(),
    )

    assert result.visible_messages[0].content == "已创建提醒：出门（2026-05-10 18:05）"
    assert [tool.name for tool in result.tool_results] == ["reminder"]
    assert result.trace["status"] == "preflight_reminder_intent"


@pytest.mark.asyncio
async def test_run_agent_runtime_fails_closed_when_agent_raises(monkeypatch):
    class FailingAgent:
        async def arun(self, **kwargs):
            raise RuntimeError("model unavailable")

    monkeypatch.setattr(agent_runtime, "_create_agent", lambda **kwargs: FailingAgent())

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert result.visible_messages == ()
    assert result.post_analyze_input is None
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "agent_runtime_exception"
    assert result.error_disposition.retryable is True


@pytest.mark.asyncio
async def test_run_agent_runtime_times_out_when_agent_hangs(monkeypatch):
    class HangingAgent:
        async def arun(self, **kwargs):
            await asyncio.sleep(1)

    monkeypatch.setenv("COKE_AGENT_RUNTIME_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setattr(agent_runtime, "_create_agent", lambda **kwargs: HangingAgent())

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "agent_runtime_timeout"
    assert result.error_disposition.retryable is True


def test_agent_runtime_default_timeout_covers_reminder_tool_budget(monkeypatch):
    monkeypatch.delenv("COKE_AGENT_RUNTIME_TIMEOUT_SECONDS", raising=False)

    assert agent_runtime._agent_runtime_timeout_seconds() == 160.0


@pytest.mark.asyncio
async def test_run_agent_runtime_timeout_returns_captured_tool_summary(monkeypatch):
    class HangingAgent:
        async def arun(self, **kwargs):
            await asyncio.sleep(1)

    def fake_create_agent(**kwargs):
        kwargs["tool_results"].append(
            CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：喝水（2026-05-09 17:57）"},
                metadata={"durable_write": True},
            )
        )
        return HangingAgent()

    monkeypatch.setenv("COKE_AGENT_RUNTIME_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setattr(agent_runtime, "_create_agent", fake_create_agent)

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert result.output_disposition.status == "ok"
    assert [message.content for message in result.visible_messages] == [
        "已创建提醒：喝水（2026-05-09 17:57）"
    ]
    assert result.error_disposition is not None
    assert result.error_disposition.code == "agent_runtime_timeout"


def test_create_agent_registers_canonical_capability_tools():
    agent = agent_runtime._create_agent(
        run_context=_run_context(),
        input_message="hi",
        tool_results=[],
    )

    assert [tool.name for tool in agent.tools] == [
        "reminder_intent",
        "timezone",
        "calendar_import",
        "url_context",
    ]


def test_create_agent_uses_chat_response_model_role(monkeypatch):
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def fake_create_llm_model(*, role, max_tokens):
        captured.update({"role": role, "max_tokens": max_tokens})
        return object()

    monkeypatch.setattr("agno.agent.Agent", FakeAgent)
    monkeypatch.setattr(
        "agent.agno_agent.model_factory.create_llm_model",
        fake_create_llm_model,
    )

    agent_runtime._create_agent(
        run_context=_run_context(),
        input_message="hi",
        tool_results=[],
    )

    assert captured == {"role": "chat_response", "max_tokens": 2000}


def test_create_agent_sets_tool_call_limit(monkeypatch):
    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("agno.agent.Agent", FakeAgent)
    monkeypatch.setattr(
        "agent.agno_agent.model_factory.create_llm_model",
        lambda **kwargs: object(),
    )

    agent = agent_runtime._create_agent(
        run_context=_run_context(),
        input_message="hi",
        tool_results=[],
    )

    assert agent.kwargs["tool_call_limit"] == 4


def test_create_agent_stops_after_reminder_tool_call():
    agent = agent_runtime._create_agent(
        run_context=_run_context(),
        input_message="提醒我喝水",
        tool_results=[],
    )

    tool_flags = {tool.name: tool.stop_after_tool_call for tool in agent.tools}

    assert tool_flags["reminder_intent"] is True
    assert tool_flags["timezone"] is False
    assert tool_flags["calendar_import"] is False
    assert tool_flags["url_context"] is False


@pytest.mark.asyncio
async def test_run_agent_runtime_captures_tool_result_into_run_result(monkeypatch):
    captured_envelopes: list[dict] = []

    class StubPort:
        async def run(self, input_message, run_context, args):
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"visible_summary": "ok"},
                metadata={
                    "durable_write": True,
                    "requires_response_synthesis": True,
                },
            )

    monkeypatch.setattr(
        agent_runtime,
        "_default_capability_ports",
        lambda: {"reminder_intent": StubPort()},
    )

    class FakeAgent:
        def __init__(self, tools):
            self.tools = tools

        async def arun(self, **kwargs):
            envelope = await self.tools["reminder_intent"]()
            captured_envelopes.append(envelope)
            return SimpleNamespace(
                content="",
                messages=[
                    {"role": "user", "content": kwargs["input"]},
                    {"role": "tool", "content": str(envelope)},
                    {"role": "assistant", "content": ""},
                ],
            )

    def fake_create_agent(*, run_context, input_message, tool_results):
        from agent.agno_agent.runtime.tool_wrappers import (
            build_capability_tool_wrappers,
        )

        wrappers = build_capability_tool_wrappers(
            ports=agent_runtime._default_capability_ports(),
            run_context=run_context,
            input_message=input_message,
            tool_results=tool_results,
        )
        return FakeAgent(tools=wrappers)

    monkeypatch.setattr(agent_runtime, "_create_agent", fake_create_agent)

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert len(result.tool_results) == 1
    assert result.tool_results[0].name == "reminder"
    assert result.tool_results[0].durable_write is True
    assert [message.content for message in result.visible_messages] == ["ok"]
    assert captured_envelopes[0]["name"] == "reminder_intent"


@pytest.mark.asyncio
async def test_reminder_fired_input_marks_system_delivery_for_model(monkeypatch):
    model_inputs = []

    class FakeAgent:
        async def arun(self, **kwargs):
            model_inputs.append(kwargs["input"])
            return SimpleNamespace(
                content="",
                messages=[SimpleNamespace(role="assistant", content="该喝水了。")],
            )

    monkeypatch.setattr(agent_runtime, "_create_agent", lambda **kwargs: FakeAgent())

    ctx = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="UTC"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key="route-1",
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="User: 明天提醒我喝水\nCoke: 已设好提醒",
        current_time=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
        runtime_metadata={"message_source": "reminder"},
    )
    result = await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="reminder.fired",
            conversation_id="conv-1",
            text="提醒：喝水",
            payload=ReminderFirePayload(
                fire_id="fire-1",
                reminder_id="rem-1",
                title="喝水",
                scheduled_for=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
            ),
            occurred_at=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
        ),
        run_context=ctx,
    )

    assert result.output_disposition.status == "ok"
    model_input = model_inputs[0]
    assert "input_type: reminder.fired" in model_input
    assert "message_source: reminder" in model_input
    assert "system reminder delivery" in model_input
    assert "deliver the existing reminder" in model_input
    assert "do not create, update, cancel, or list reminders" in model_input
    assert "reminder_title: 喝水" in model_input
