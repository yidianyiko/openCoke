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
    capability_results: list[CapabilityResult],
    monkeypatch: pytest.MonkeyPatch,
    input_text: str = "hi",
    content: str = "",
    domain_results: list[DomainExecutionResult] | None = None,
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
        capability_results=[url_result, timezone_result],
        monkeypatch=monkeypatch,
        content="synthesized reply",
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
        capability_results=[reminder_result, timezone_result],
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
        capability_results=[timezone_result, reminder_result],
        monkeypatch=monkeypatch,
    )

    assert [message.content for message in result.visible_messages] == [
        "已创建提醒：离开时手机（2026-05-10 11:00）"
    ]


@pytest.mark.asyncio
async def test_reminder_write_uses_domain_summary_to_preserve_exact_title(monkeypatch):
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
        "已创建提醒：🍅 番茄钟 ⏰（2026-05-27 周三 09:00）"
    ]


@pytest.mark.asyncio
async def test_rule3_no_tool_results_uses_final_text(monkeypatch):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": "ordinary chat"}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content="ordinary chat",
    )

    assert [message.content for message in result.visible_messages] == ["ordinary chat"]


def _segments_payload(*segments: object) -> str:
    return json.dumps({"MultiModalResponses": list(segments)}, ensure_ascii=False)


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
                    entity_type="shared_reminder_request",
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

    assert [message.content for message in result.visible_messages] == [
        "这个时间已经过去了，请给我一个未来的上课时间。"
    ]


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


def test_unconfirmed_durable_write_friend_accept_patterns():
    """Regression: when the assistant lies about accepting a friend request
    without a successful scheduling write, the unconfirmed-write detector
    must trip. The chat persona occasionally produces "已经通过 / 你们现在是
    好友啦" text even when accept_friend_request returned friend_request_not_found."""
    from agent.agno_agent.runtime.agent_runtime import (
        _UNCONFIRMED_DURABLE_WRITE_PATTERNS,
    )

    must_match = [
        "好嘞，Bob 的跑步搭子请求已经通过啦！",
        "已经通过 Bob 的好友请求。",
        "I've accepted the friend request.",
        "now you are friends.",
        "你们现在是好朋友啦~",
    ]
    must_skip = [
        "等对方通过你的好友请求就成啦",  # safe — describes the other side, no first-person claim
        "建共享提醒需要先把对方加为好友。",  # decline
        "要通过还是拒绝？",  # asking user
    ]
    for text in must_match:
        assert any(p.search(text) for p in _UNCONFIRMED_DURABLE_WRITE_PATTERNS), text
    for text in must_skip:
        assert not any(p.search(text) for p in _UNCONFIRMED_DURABLE_WRITE_PATTERNS), text


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
    """Model occasionally emits a MultiModalResponses envelope with broken
    braces / commas. Regression: lenient recovery should still extract the
    text contents so the user does not see raw JSON."""
    # Real example from smoke batch 143020Z T5: extra closing `}` before `]`.
    raw = (
        '{"MultiModalResponses": [{"type": "text", "content": '
        '"没有待处理的好友请求，目前都是清空的。"}}]}'
    )
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": raw}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=raw,
    )
    assert [m.content for m in result.visible_messages] == [
        "没有待处理的好友请求，目前都是清空的。",
    ]


@pytest.mark.asyncio
async def test_malformed_multimodal_json_recovers_text_lenient(monkeypatch):
    """When the envelope signature is present but the JSON is truncated /
    malformed, we still recover the user-visible content rather than leak
    the raw envelope. Updated from the previous fall-back-to-raw behavior
    after observing real malformed envelopes in production smoke runs."""
    raw = '{"MultiModalResponses": [{"type": "text", "content": "缺了括号"}'

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": raw}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=raw,
    )

    assert [message.content for message in result.visible_messages] == ["缺了括号"]


@pytest.mark.asyncio
async def test_non_envelope_invalid_json_still_falls_back_to_raw(monkeypatch):
    """Sanity: random invalid JSON without the MultiModalResponses signature
    must not trigger lenient recovery — it would silently swallow user-meant
    content. Pass it through unchanged."""
    raw = "just broken JSON {{ }}"
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": raw}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=raw,
    )
    assert [message.content for message in result.visible_messages] == [raw]


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

    assert [message.content for message in result.visible_messages] == ["一", "二", "三"]


@pytest.mark.asyncio
async def test_segmented_reminder_promise_guardrail_uses_joined_visible_text(
    monkeypatch,
):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": ""}],
        capability_results=[],
        monkeypatch=monkeypatch,
        input_text="明天九点提醒我喝水",
        content=_segments_payload(
            {"type": "text", "content": "没问题"},
            {"type": "text", "content": "明天早上九点我会提醒你喝水"},
        ),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "unconfirmed_durable_write_promise"


@pytest.mark.asyncio
async def test_segmented_promise_guardrail_does_not_depend_on_input_request_shape(
    monkeypatch,
):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": ""}],
        capability_results=[],
        monkeypatch=monkeypatch,
        input_text="hi",
        content=_segments_payload(
            {"type": "text", "content": "没问题"},
            {"type": "text", "content": "我会提醒你。"},
        ),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "unconfirmed_durable_write_promise"


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
async def test_direct_reminder_promise_fails_closed_without_confirmed_write(
    monkeypatch, model_text
):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": model_text}],
        capability_results=[],
        monkeypatch=monkeypatch,
        input_text="明天九点提醒我喝水",
        content=model_text,
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "unconfirmed_durable_write_promise"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_text",
    [
        (
            "看了你的消息，我需要先说明一下：我是没有办法直接帮你预约教练的，"
            "只能帮你设置提醒。\n\n"
            "如果你是想周日下午3点去健身，需要我提前提醒你准备出发吗？"
            "或者提醒你那个时间去 App 上约课？"
        ),
        (
            "喂，我没办法帮你直接约教练课哦，这个需要你自行去 App 或者线下跟教练约。\n\n"
            "不过我可以帮你设个提醒——比如提前一天提醒你记得去约课？要不要我帮你设一个？"
        ),
        (
            "我没法帮你直接约彭教练的课程哦，预约得上你自己去App或线下处理。\n\n"
            "不过可以帮你设个提醒：周日下午3点前提醒你记得预约，这样到时候不会忘。可以帮你设吗？"
        ),
        (
            "我没法帮你直接约教练哦，预约得你自己去 App 或找教练那边确认。"
            "我能做的呢是——到点提醒你该去约课了，或者提醒你准时去上课。"
        ),
        (
            "抱歉呀，我暂时没有帮你直接预约网球课的能力哦。"
            "网球课需要通过对应的 App 或直接联系教练来约。"
            "不过，我可以帮你设置一个提醒——比如这周六上午几点提醒你记得去约课？"
            "到点我提醒你，你就可以顺手把课程约上~"
        ),
        (
            "哎，约教练这些线下预约我还帮你做不了哈。"
            "不过你可以告诉我具体想几点去、打算练多久，我到点提醒你，"
            "自己去 App 或找教练约就行。"
        ),
    ],
)
async def test_booking_refusal_can_offer_reminder_help_without_write_claim(
    monkeypatch, model_text
):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": model_text}],
        capability_results=[],
        monkeypatch=monkeypatch,
        input_text="周日下午 3 点帮我约彭教练",
        content=model_text,
    )

    assert [message.content for message in result.visible_messages] == [model_text]
    assert result.output_disposition.status == "ok"


@pytest.mark.asyncio
async def test_booking_refusal_still_blocks_completed_reminder_claim(monkeypatch):
    model_text = "我不能帮你预约教练，但已经帮你设置好了周日下午3点约课提醒。"

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": model_text}],
        capability_results=[],
        monkeypatch=monkeypatch,
        input_text="周日下午 3 点帮我约彭教练",
        content=model_text,
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "unconfirmed_durable_write_promise"


@pytest.mark.asyncio
async def test_direct_reminder_promise_does_not_invoke_recovery_port(monkeypatch):
    calls = 0

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": "我会在明天早上九点提醒你。"}],
        capability_results=[],
        monkeypatch=monkeypatch,
        input_text="明天九点提醒我喝水",
        content="我会在明天早上九点提醒你。",
    )

    assert calls == 0
    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "unconfirmed_durable_write_promise"


@pytest.mark.asyncio
async def test_shared_reminder_creation_claim_fails_closed_without_confirmed_write(monkeypatch):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": "好啦，已经帮你和 Nora 建了共享提醒。"}],
        capability_results=[],
        monkeypatch=monkeypatch,
        input_text="帮我和 Nora 建一个共享提醒",
        content="好啦，已经帮你和 Nora 建了共享提醒。",
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "unconfirmed_durable_write_promise"


@pytest.mark.asyncio
async def test_visible_identifier_leak_guardrail_trips_on_account_id_patterns(monkeypatch):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": ""}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content="你有 1 个待处理的共享提醒：ck_smoke_20260525t045815z_alice 发来的“打羽毛球”。",
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
