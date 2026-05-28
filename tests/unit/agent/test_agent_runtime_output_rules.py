from datetime import UTC, datetime
import json

import pytest

from agent.agno_agent.runtime import agent_runtime
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
from agent.agno_agent.runtime.inputs import (
    AgentInput,
    ReminderFirePayload,
    UserTurnPayload,
)
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
    capability_results: list[CapabilityResult],
    monkeypatch: pytest.MonkeyPatch,
    input_text: str = "hi",
    content: str = "",
    domain_results: list[DomainExecutionResult] | None = None,
    input_type: str = "user.turn",
):
    class FakeOutput:
        def __init__(self, msgs, text):
            self.content = text
            self.messages = msgs

    class FakeAgent:
        async def arun(self, **_kwargs):
            return FakeOutput(messages, content)

    def patched_create(
        *,
        run_context,
        agent_input,
        input_message,
        capability_results,
        domain_results,
        preloaded_scheduling_domain_result=None,
    ):
        del run_context, agent_input, input_message
        del preloaded_scheduling_domain_result
        capability_results.extend(captured_results)
        domain_results.extend(captured_domain_results)
        return FakeAgent()

    captured_results = list(capability_results)
    captured_domain_results = list(domain_results or [])
    monkeypatch.setattr(agent_runtime, "_create_interaction_agent", patched_create)
    payload = (
        ReminderFirePayload(
            fire_id="reminder-1:2026-05-28T00:30:00+00:00",
            reminder_id="reminder-1",
            title="follow up",
            scheduled_for=datetime.now(UTC),
            metadata={"fire_mode": "followup", "kind": "internal_followup"},
        )
        if input_type == "reminder.fired"
        else UserTurnPayload(current_message_ids=["msg1"])
    )
    return await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type=input_type,
            conversation_id="conv1",
            text=input_text,
            payload=payload,
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
            {
                "role": "assistant",
                "content": _segments_payload(
                    {"type": "text", "content": "synthesized reply"}
                ),
            },
        ],
        capability_results=[url_result, timezone_result],
        monkeypatch=monkeypatch,
        content=_segments_payload({"type": "text", "content": "synthesized reply"}),
    )

    assert [message.content for message in result.visible_messages] == [
        "synthesized reply"
    ]


@pytest.mark.asyncio
async def test_capability_visible_summary_does_not_replace_empty_model_text(
    monkeypatch,
):
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
        capability_results=[url_result, reminder_result],
        monkeypatch=monkeypatch,
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"


@pytest.mark.asyncio
async def test_multiple_capability_visible_summaries_do_not_replace_empty_model_text(
    monkeypatch,
):
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
        capability_results=[reminder_result, timezone_result],
        monkeypatch=monkeypatch,
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"


@pytest.mark.asyncio
async def test_failed_tool_message_and_success_summary_do_not_replace_empty_model_text(
    monkeypatch,
):
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
        capability_results=[timezone_result, reminder_result],
        monkeypatch=monkeypatch,
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"


@pytest.mark.asyncio
async def test_reminder_write_metadata_does_not_replace_nonempty_agent_text(
    monkeypatch,
):
    emoji_title = "🍅 番茄钟 ⏰"
    reminder_result = DomainExecutionResult(
        domain="reminder",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="create",
                ok=True,
                effect="write",
                entity_type="reminder",
                entity_id="rem-emoji",
                facts={
                    "title": emoji_title,
                    "local_date": "2026-05-27",
                    "local_time": "09:00:00",
                    "rrule": None,
                    "visible_summary": f"已创建提醒：{emoji_title}（2026-05-27 周三 09:00）",
                },
            ),
        ),
        reply_contract=ReplyContract(
            intent="confirm_execution",
        ),
    )
    model_reply = _segments_payload(
        {
            "type": "text",
            "content": "好嘞，明天早上9点🍅番茄钟提醒已经设好了~",
        }
    )

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": model_reply}],
        capability_results=[],
        domain_results=[reminder_result],
        monkeypatch=monkeypatch,
        input_text="明天 9 点提醒我 🍅 番茄钟 ⏰",
        content=model_reply,
    )

    assert [message.content for message in result.visible_messages] == [
        "好嘞，明天早上9点🍅番茄钟提醒已经设好了~"
    ]


@pytest.mark.asyncio
async def test_rule3_no_tool_results_uses_final_text(monkeypatch):
    result = await _run_with_fake_agent(
        messages=[
            {
                "role": "assistant",
                "content": _segments_payload(
                    {"type": "text", "content": "ordinary chat"}
                ),
            }
        ],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=_segments_payload({"type": "text", "content": "ordinary chat"}),
    )

    assert [message.content for message in result.visible_messages] == ["ordinary chat"]


def _segments_payload(*segments: object) -> str:
    return json.dumps({"MultiModalResponses": list(segments)}, ensure_ascii=False)


def _text_payload(content: str) -> str:
    return _segments_payload({"type": "text", "content": content})


@pytest.mark.asyncio
async def test_valid_envelope_content_that_looks_like_tool_markup_is_visible(
    monkeypatch,
):
    model_text = _segments_payload(
        {
            "type": "text",
            "content": '<minimax:tool_call><invoke name="noop"></invoke></minimax:tool_call>',
        }
    )

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": model_text}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=model_text,
    )

    assert [message.content for message in result.visible_messages] == [
        '<minimax:tool_call><invoke name="noop"></invoke></minimax:tool_call>'
    ]
    assert result.error_disposition is None


@pytest.mark.asyncio
async def test_malformed_envelope_json_is_protocol_violation(
    monkeypatch,
):
    raw = '{"MultiModalResponses": [{"type": "text", "content": "缺了括号"}'
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": raw}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=raw,
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"


@pytest.mark.asyncio
async def test_preselected_scheduling_failure_summary_does_not_become_visible_text(
    monkeypatch,
):
    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
        forced_args=None,
    ):
        del input_message, intent, run_context, forced_args
        result = DomainExecutionResult(
            domain="scheduling",
            outcome="failed",
            operations=(
                DomainOperationResult(
                    action="create_shared_reminder",
                    ok=False,
                    effect="none",
                    entity_type="shared_reminder",
                    entity_id=None,
                    facts={"summary": "这个时间已经过去了，请给我一个未来的上课时间。"},
                    error=DomainError(
                        code="invalid_body",
                        message="invalid_body",
                        retryable=True,
                        detail={},
                    ),
                ),
            ),
            missing_fields=(),
            safety_boundary=None,
            reply_contract=ReplyContract(
                intent="report_failure",
                required_facts=(),
                allow_rephrase=True,
            ),
            error=DomainError(
                code="invalid_body",
                message="invalid_body",
                retryable=True,
                detail={},
            ),
        )
        domain_results.append(result)
        return result.to_dict()

    class FakeAgent:
        async def arun(self, **_kwargs):
            return type("FakeOutput", (), {"content": "", "messages": []})()

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )
    monkeypatch.setattr(
        agent_runtime,
        "_create_interaction_agent",
        lambda **_kwargs: FakeAgent(),
    )
    from agent.agno_agent.runtime.semantic_interpreter import SemanticIntentResult

    async def fake_interpret_semantic_intent(*, focus, current_utterance, **_kwargs):
        del focus, current_utterance
        return SemanticIntentResult(
            intent="create_shared_reminder",
            confidence="high",
        )

    monkeypatch.setattr(
        agent_runtime, "interpret_semantic_intent", fake_interpret_semantic_intent
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="user.turn",
            conversation_id="conv1",
            text="约教练 Alex 昨天 10 点。",
            payload=UserTurnPayload(current_message_ids=["msg1"]),
            occurred_at=datetime.now(UTC),
        ),
        run_context=_ctx(),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"


@pytest.mark.asyncio
async def test_multimodal_json_becomes_ordered_visible_text_segments(monkeypatch):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": ""}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=_segments_payload(
            {"type": "text", "content": "先这样"},
            {"type": "text", "content": "我晚点再整理下一步"},
        ),
    )

    assert [message.message_type for message in result.visible_messages] == [
        "text",
        "text",
    ]
    assert [message.content for message in result.visible_messages] == [
        "先这样",
        "我晚点再整理下一步",
    ]
    assert result.output_disposition.status == "ok"


@pytest.mark.asyncio
async def test_multimodal_text_content_newlines_become_visible_segments(monkeypatch):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": ""}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=_segments_payload(
            {
                "type": "text",
                "content": "目前你还没有加好友哦~ List是空的。\n要想一起用共享提醒啥的功能，可以先加个好友，你想加谁呀？",
            },
        ),
    )

    assert [message.content for message in result.visible_messages] == [
        "目前你还没有加好友哦~ List是空的。",
        "要想一起用共享提醒啥的功能，可以先加个好友，你想加谁呀？",
    ]


@pytest.mark.asyncio
async def test_malformed_envelope_json_fails_closed(monkeypatch):
    """Malformed MultiModalResponses JSON fails closed instead of recovering."""
    # Real example from smoke batch 143020Z T5: extra closing `}` before `]`.
    raw = (
        '{"MultiModalResponses": [{"type": "text", "content": '
        '"没有共享提醒，目前都是清空的。"}}]}'
    )
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": raw}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=raw,
    )
    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"


@pytest.mark.asyncio
async def test_truncated_multimodal_json_fails_closed(monkeypatch):
    """Truncated envelopes are protocol violations, not visible text."""
    raw = '{"MultiModalResponses": [{"type": "text", "content": "缺了括号"}'

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": raw}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=raw,
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"


@pytest.mark.asyncio
async def test_non_envelope_invalid_json_fails_closed(monkeypatch):
    """Non-envelope text is a protocol violation under the strict contract."""
    raw = "just broken JSON {{ }}"
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": raw}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=raw,
    )
    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"


@pytest.mark.asyncio
async def test_multimodal_parser_ignores_non_text_and_caps_at_three(monkeypatch):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": ""}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=_segments_payload(
            {"type": "voice", "content": "不要发语音"},
            {"type": "text", "content": "一"},
            {"type": "photo", "content": "不要发图片"},
            {"type": "text", "content": "二"},
            {"type": "text", "content": "三"},
            {"type": "text", "content": "四"},
        ),
    )

    assert [message.content for message in result.visible_messages] == [
        "一",
        "二",
        "三",
    ]


@pytest.mark.asyncio
async def test_reminder_fire_raw_serialized_tool_call_protocol_violation(monkeypatch):
    model_text = (
        "<minimax:tool_call>\n"
        '<invoke name="scheduling_domain">\n'
        '<parameter name="_model_supplied_args">'
        '{"intent":"list_shared_reminders"}'
        "</parameter>\n"
        "</invoke>\n"
        "</minimax:tool_call>"
    )

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": model_text}],
        capability_results=[],
        monkeypatch=monkeypatch,
        input_text="提醒用户确认具体的数学课邀请",
        content=model_text,
        input_type="reminder.fired",
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"


@pytest.mark.asyncio
async def test_scheduling_write_without_visible_summary_fails_closed(monkeypatch):
    scheduling_write = DomainExecutionResult(
        domain="scheduling",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="create_shared_reminder",
                ok=True,
                effect="write",
                entity_type="shared_reminder",
                entity_id="srr_1",
                facts={},
            ),
        ),
    )

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": _text_payload("完成了。")}],
        capability_results=[],
        domain_results=[scheduling_write],
        monkeypatch=monkeypatch,
        input_text="约 eva 明天 11 点",
        content=_text_payload("完成了。"),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "durable_write_missing_visible_summary"


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
        capability_results=[no_summary],
        monkeypatch=monkeypatch,
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.post_analyze_input is None
