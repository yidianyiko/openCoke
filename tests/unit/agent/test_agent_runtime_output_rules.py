from datetime import UTC, datetime

import pytest

from agent.agno_agent.runtime import agent_runtime
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.inputs import AgentInput, UserTurnPayload
from agent.agno_agent.runtime.result import CapabilityResult


def _ctx() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="u1", nickname="Alice", timezone="UTC"),
        character=TrustedCharacterContext(id="c1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="u1", cid="c1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime.now(UTC),
    )


async def _run_with_fake_agent(
    *,
    messages,
    tool_results: list[CapabilityResult],
    monkeypatch: pytest.MonkeyPatch,
    input_text: str = "hi",
):
    class FakeOutput:
        def __init__(self, msgs):
            self.content = ""
            self.messages = msgs

    class FakeAgent:
        async def arun(self, **_kwargs):
            return FakeOutput(messages)

    def patched_create(*, run_context, input_message, tool_results):
        del run_context, input_message
        tool_results.extend(captured_results)
        return FakeAgent()

    captured_results = list(tool_results)
    monkeypatch.setattr(agent_runtime, "_create_agent", patched_create)
    return await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="user.turn",
            conversation_id="conv1",
            text=input_text,
            payload=UserTurnPayload(current_message_ids=["msg1"]),
            occurred_at=datetime.now(UTC),
        ),
        run_context=_ctx(),
    )


@pytest.mark.asyncio
async def test_rule1_synthesis_with_nonempty_final_text_wins(monkeypatch):
    url_result = CapabilityResult(
        name="url_context",
        ok=True,
        content={"items": [], "context": "..."},
        metadata={"requires_response_synthesis": True},
    )
    timezone_result = CapabilityResult(
        name="timezone",
        ok=True,
        content={"visible_summary": "已切换时区"},
        metadata={"durable_write": True},
    )

    result = await _run_with_fake_agent(
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "..."},
            {"role": "assistant", "content": "synthesized reply"},
        ],
        tool_results=[url_result, timezone_result],
        monkeypatch=monkeypatch,
    )

    assert [message.content for message in result.visible_messages] == [
        "synthesized reply"
    ]


@pytest.mark.asyncio
async def test_rule2_visible_summary_when_synthesis_text_empty(monkeypatch):
    url_result = CapabilityResult(
        name="url_context",
        ok=True,
        content={"items": [], "context": "..."},
        metadata={"requires_response_synthesis": True},
    )
    reminder_result = CapabilityResult(
        name="reminder",
        ok=True,
        content={"visible_summary": "已设好提醒"},
        metadata={"durable_write": True},
    )

    result = await _run_with_fake_agent(
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "..."},
            {"role": "assistant", "content": ""},
        ],
        tool_results=[url_result, reminder_result],
        monkeypatch=monkeypatch,
    )

    assert [message.content for message in result.visible_messages] == ["已设好提醒"]


@pytest.mark.asyncio
async def test_rule2_joins_multiple_visible_summaries(monkeypatch):
    reminder_result = CapabilityResult(
        name="reminder",
        ok=True,
        content={"visible_summary": "一"},
        metadata={"durable_write": True},
    )
    timezone_result = CapabilityResult(
        name="timezone",
        ok=True,
        content={"visible_summary": "二"},
        metadata={"durable_write": True},
    )

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": ""}],
        tool_results=[reminder_result, timezone_result],
        monkeypatch=monkeypatch,
    )

    assert [message.content for message in result.visible_messages] == ["一\n二"]


@pytest.mark.asyncio
async def test_failed_tool_message_is_not_joined_with_success_summary(monkeypatch):
    timezone_result = CapabilityResult(
        name="timezone",
        ok=False,
        content={"message": "unsupported timezone action: get"},
    )
    reminder_result = CapabilityResult(
        name="reminder",
        ok=True,
        content={"summary": "已创建提醒：离开时手机（2026-05-10 11:00）"},
        metadata={"durable_write": True},
    )

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": ""}],
        tool_results=[timezone_result, reminder_result],
        monkeypatch=monkeypatch,
    )

    assert [message.content for message in result.visible_messages] == [
        "已创建提醒：离开时手机（2026-05-10 11:00）"
    ]


@pytest.mark.asyncio
async def test_rule3_no_tool_results_uses_final_text(monkeypatch):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": "ordinary chat"}],
        tool_results=[],
        monkeypatch=monkeypatch,
    )

    assert [message.content for message in result.visible_messages] == [
        "ordinary chat"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_text",
    [
        "我会在明天早上九点提醒你。",
        "好的，明天早上九点提醒你。",
        "没问题，明天早上九点提醒你。",
        "明天早上九点我来叫你。",
    ],
)
async def test_direct_reminder_promise_without_tool_result_fails_closed(
    monkeypatch, model_text
):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": model_text}],
        tool_results=[],
        monkeypatch=monkeypatch,
        input_text="明天九点提醒我喝水",
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "unconfirmed_durable_write_promise"


@pytest.mark.asyncio
async def test_rule4_empty_disposition_when_nothing_resolves(monkeypatch):
    no_summary = CapabilityResult(
        name="reminder",
        ok=True,
        content={"action": "none"},
        metadata={"durable_write": False},
    )

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": ""}],
        tool_results=[no_summary],
        monkeypatch=monkeypatch,
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.post_analyze_input is None
