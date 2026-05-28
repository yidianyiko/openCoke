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
        capability_results=[url_result, reminder_result],
        monkeypatch=monkeypatch,
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"


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
        capability_results=[reminder_result, timezone_result],
        monkeypatch=monkeypatch,
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"


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
        capability_results=[timezone_result, reminder_result],
        monkeypatch=monkeypatch,
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"


@pytest.mark.asyncio
async def test_reminder_write_domain_summary_does_not_replace_nonempty_agent_text(
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
            prohibited_claims=("not_created", "needs_more_info"),
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
async def test_malformed_envelope_json_is_protocol_violation_not_lenient_recovery(
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
async def test_preselected_scheduling_failure_summary_becomes_visible_text(monkeypatch):
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
                required_questions=(),
                prohibited_claims=("appointment_confirmed",),
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


def test_unconfirmed_durable_write_direct_friendship_patterns():
    """Regression: "now you are friends" claims require a successful write."""
    from agent.agno_agent.runtime.agent_runtime import (
        _UNCONFIRMED_DURABLE_WRITE_PATTERNS,
    )

    must_match = [
        "now you are friends.",
        "你们现在是好朋友啦~",
    ]
    must_skip = [
        "需要先和对方建立好友关系才行",  # safe — no first-person write claim
        "建共享提醒需要先把对方加为好友。",  # decline
        "要通过还是拒绝？",  # asking user
    ]
    for text in must_match:
        assert any(p.search(text) for p in _UNCONFIRMED_DURABLE_WRITE_PATTERNS), text
    for text in must_skip:
        assert not any(
            p.search(text) for p in _UNCONFIRMED_DURABLE_WRITE_PATTERNS
        ), text


@pytest.mark.asyncio
async def test_fenced_multimodal_json_envelope_is_unwrapped(monkeypatch):
    """Model occasionally emits the MultiModalResponses envelope wrapped in
    a ```json markdown fence. The runtime must strip the fence before parsing
    so the user never sees the raw envelope."""
    envelope = _segments_payload(
        {"type": "text", "content": "Hii！我是 Coke"},
        {"type": "text", "content": "我可以帮你约课"},
    )
    fenced = f"```json\n{envelope}\n```"

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": fenced}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=fenced,
    )

    assert [message.content for message in result.visible_messages] == [
        "Hii！我是 Coke",
        "我可以帮你约课",
    ]


@pytest.mark.asyncio
async def test_fenced_envelope_in_assistant_message_is_used_when_content_empty(
    monkeypatch,
):
    envelope = _segments_payload(
        {"type": "text", "content": "Hii！我是 Coke"},
        {"type": "text", "content": "我可以帮你列待处理通知。"},
    )
    fenced = f"```json {envelope} ```"

    result = await _run_with_fake_agent(
        messages=[
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": fenced},
        ],
        capability_results=[],
        monkeypatch=monkeypatch,
        content="",
    )

    assert [message.content for message in result.visible_messages] == [
        "Hii！我是 Coke",
        "我可以帮你列待处理通知。",
    ]


@pytest.mark.asyncio
async def test_malformed_envelope_json_recovers_text_segments(monkeypatch):
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
async def test_malformed_multimodal_json_recovers_text_lenient(monkeypatch):
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
async def test_non_envelope_invalid_json_still_falls_back_to_raw(monkeypatch):
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
async def test_failed_reminder_domain_result_blocks_created_claim(monkeypatch):
    failed_result = DomainExecutionResult(
        domain="reminder",
        outcome="failed",
        operations=(
            DomainOperationResult(
                action="update",
                ok=False,
                effect="none",
                entity_type="reminder",
                entity_id=None,
                error=DomainError(
                    code="AmbiguousReminderKeyword",
                    message="更新提醒失败：没有找到要更新的提醒，请告诉我提醒名称。",
                    retryable=False,
                ),
            ),
        ),
        reply_contract=ReplyContract(
            intent="report_failure",
            prohibited_claims=("reminder_created",),
            allow_rephrase=True,
        ),
        error=DomainError(
            code="AmbiguousReminderKeyword",
            message="更新提醒失败：没有找到要更新的提醒，请告诉我提醒名称。",
            retryable=False,
        ),
    )
    text = "提醒已创建：喝水-fire-real-20260527T073551Z，今天下午3点39分提醒。"

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": _text_payload(text)}],
        capability_results=[],
        domain_results=[failed_result],
        monkeypatch=monkeypatch,
        input_text="2分钟后提醒我喝水-fire-real-20260527T073551Z。",
        content=_text_payload(text),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "domain_reply_contract_violation"
    assert result.error_disposition.metadata == {
        "domain": "reminder",
        "violations": ("prohibited claim reminder_created",),
    }


@pytest.mark.asyncio
async def test_shared_reminder_creation_claim_fails_closed_without_confirmed_write(
    monkeypatch,
):
    result = await _run_with_fake_agent(
        messages=[
            {
                "role": "assistant",
                "content": _text_payload("好啦，已经帮你和 Nora 建了共享提醒。"),
            }
        ],
        capability_results=[],
        monkeypatch=monkeypatch,
        input_text="我们聊一下共享提醒能力",
        content=_text_payload("好啦，已经帮你和 Nora 建了共享提醒。"),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "unconfirmed_durable_write_promise"


@pytest.mark.asyncio
async def test_stale_shared_reminder_invite_claim_fails_closed(
    monkeypatch,
):
    text = "搞定了！今天上午11点去奇迹创坛的邀请已经发给 eva 了，等他确认～"

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": _text_payload(text)}],
        capability_results=[],
        monkeypatch=monkeypatch,
        input_text="今天上午11点帮我预约一个活动是和eva一起去奇迹创坛",
        content=_text_payload(text),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "unconfirmed_durable_write_promise"


@pytest.mark.asyncio
async def test_stale_shared_reminder_invite_claim_rejected_after_other_write(
    monkeypatch,
):
    unrelated_write = DomainExecutionResult(
        domain="scheduling",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="reset_user_link",
                ok=True,
                effect="write",
                entity_type="user_link",
                entity_id="link_1",
                facts={"visible_summary": "已重置用户链接。"},
            ),
        ),
    )
    text = "邀请已经发给 eva 了，等他确认。"

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": _text_payload(text)}],
        capability_results=[],
        domain_results=[unrelated_write],
        monkeypatch=monkeypatch,
        input_text="今天上午11点帮我预约一个活动是和eva一起去奇迹创坛",
        content=_text_payload(text),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "unconfirmed_durable_write_promise"


@pytest.mark.asyncio
async def test_shared_reminder_creation_claim_allowed_after_create_write(
    monkeypatch,
):
    create_write = DomainExecutionResult(
        domain="scheduling",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="create_shared_reminder",
                ok=True,
                effect="write",
                entity_type="shared_reminder",
                entity_id="srr_1",
                facts={"visible_summary": "已创建共享提醒。"},
            ),
        ),
    )
    text = "已创建和 eva 的共享提醒。"

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": _text_payload(text)}],
        capability_results=[],
        domain_results=[create_write],
        monkeypatch=monkeypatch,
        input_text="今天上午11点帮我预约一个活动是和eva一起去奇迹创坛",
        content=_text_payload(text),
    )

    assert result.output_disposition.status == "ok"
    assert [message.content for message in result.visible_messages] == [text]


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
async def test_visible_identifier_leak_guardrail_trips_on_account_id_patterns(
    monkeypatch,
):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": ""}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=_text_payload(
            "你有 1 个待处理的共享提醒：ck_smoke_20260525t045815z_alice 发来的“打羽毛球”。"
        ),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "visible_identifier_leak"


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
