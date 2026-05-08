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
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload
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

    class FakeAgent:
        async def arun(self, **kwargs):
            assert kwargs["input"] == "hi"
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


@pytest.mark.asyncio
async def test_run_agent_runtime_captures_tool_result_into_run_result(monkeypatch):
    captured_envelopes: list[dict] = []

    class StubPort:
        async def run(self, input_message, run_context, args):
            return CapabilityResult(
                name="reminder",
                ok=True,
                content={"visible_summary": "ok"},
                metadata={"durable_write": True},
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
