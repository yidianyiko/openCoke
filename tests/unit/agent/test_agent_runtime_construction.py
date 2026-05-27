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
from agent.agno_agent.runtime.domain_results import (
    DomainError,
    DomainExecutionResult,
    DomainOperationResult,
    ReplyContract,
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


class _IgnoredAgent:
    async def arun(self, **_kwargs):
        return SimpleNamespace(content="ignored", messages=[])


def test_resolve_domain_visible_text_joins_multiple_successful_operation_summaries():
    visible_text = agent_runtime._resolve_domain_visible_text(
        [
            DomainExecutionResult(
                domain="reminder",
                outcome="executed",
                operations=(
                    DomainOperationResult(
                        action="create",
                        effect="write",
                        ok=True,
                        entity_type="reminder",
                        entity_id="reminder-1",
                        facts={"visible_summary": "已创建提醒：喝水（17:57）"},
                    ),
                    DomainOperationResult(
                        action="create",
                        effect="write",
                        ok=True,
                        entity_type="reminder",
                        entity_id="reminder-2",
                        facts={"visible_summary": "已创建提醒：锻炼（17:58）"},
                    ),
                ),
            )
        ]
    )

    assert visible_text == "已创建提醒：喝水（17:57）\n已创建提醒：锻炼（17:58）"


def test_selected_tool_names_match_exposed_domain_tool_names():
    selected_tool_names = agent_runtime._selected_tool_names(
        [
            DomainExecutionResult(
                domain="reminder",
                outcome="executed",
                operations=(
                    DomainOperationResult(
                        action="create",
                        effect="write",
                        ok=True,
                        entity_type="reminder",
                        entity_id="reminder-1",
                    ),
                ),
            ),
            DomainExecutionResult(
                domain="scheduling",
                outcome="executed",
                operations=(
                    DomainOperationResult(
                        action="get",
                        effect="read",
                        ok=True,
                        entity_type="friend",
                        entity_id="friend-1",
                    ),
                ),
            ),
        ],
        [
            CapabilityResult(
                name="timezone",
                ok=True,
                content={"visible_summary": "timezone ok"},
            )
        ],
    )

    assert selected_tool_names == ("reminder_domain", "scheduling_domain", "timezone")


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

    def fake_create_interaction_agent(**kwargs):
        create_kwargs.update(kwargs)
        return FakeAgent()

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", fake_create_interaction_agent
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert isinstance(result, AgentRunResult)
    assert result.visible_messages[0].content == "fallback content"
    assert result.output_disposition.status == "ok"
    assert result.capability_results == ()
    assert result.post_analyze_input == {
        "input_message": "hi",
        "message_source": "user",
    }
    assert result.trace.schema_version == "agent_turn_trace.v1"
    assert result.trace.runtime.status == "ok"
    assert result.trace.routing.route == "direct_reply"
    assert result.trace.routing.reason == "no_tool_requested"
    assert create_kwargs["agent_input"] == _agent_input()
    assert create_kwargs["input_message"] == "hi"
    assert create_kwargs["capability_results"] == []
    assert create_kwargs["domain_results"] == []
    assert model_inputs == ["hi"]


@pytest.mark.asyncio
async def test_run_agent_runtime_emits_trace_from_runtime_metadata_without_env(
    monkeypatch,
):
    emitted = {}

    class FakeAgent:
        async def arun(self, **kwargs):
            return SimpleNamespace(
                content="ok",
                messages=[
                    SimpleNamespace(role="user", content="hi"),
                    SimpleNamespace(role="assistant", content="ok"),
                ],
            )

    def fake_emit_agent_turn_trace_jsonl(**kwargs):
        emitted.update(kwargs)
        return True

    monkeypatch.delenv("COKE_AGENT_TURN_TRACE_JSONL", raising=False)
    monkeypatch.delenv("COKE_AGENT_TURN_TRACE_RUN_ID", raising=False)
    monkeypatch.delenv("COKE_AGENT_TURN_TRACE_SUITE", raising=False)
    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", lambda **_: FakeAgent()
    )
    monkeypatch.setattr(
        agent_runtime,
        "emit_agent_turn_trace_jsonl",
        fake_emit_agent_turn_trace_jsonl,
    )

    run_context = AgentRunContext(
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
        runtime_metadata={
            "message_source": "user",
            "agent_turn_trace": {
                "suite": "reminder-normal",
                "run_id": "reminder-normal-first-loop",
            },
        },
    )

    await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=run_context,
    )

    assert emitted["path"].as_posix() == (
        "artifacts/evidence/agent-turn-traces/reminder-normal/"
        "reminder-normal-first-loop.jsonl"
    )
    assert emitted["suite"] == "reminder-normal"
    assert emitted["trace_run_id"] == "reminder-normal-first-loop"


@pytest.mark.asyncio
async def test_run_agent_runtime_uses_captured_capability_results(monkeypatch):
    class FakeAgent:
        async def arun(self, **kwargs):
            return SimpleNamespace(
                content="ignored",
                messages=[
                    SimpleNamespace(role="tool", content='{"ok": true}'),
                    SimpleNamespace(role="assistant", content=""),
                ],
                capability_results=[
                    CapabilityResult(
                        name="ignored_run_output_field",
                        ok=True,
                        content={"visible_summary": "wrong"},
                    )
                ],
            )

    def fake_create_interaction_agent(**kwargs):
        kwargs["capability_results"].append(
            CapabilityResult(
                name="reminder",
                ok=True,
                content={"visible_summary": "已为你设好提醒"},
                metadata={"durable_write": True},
            )
        )
        return FakeAgent()

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", fake_create_interaction_agent
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert result.visible_messages[0].content == "ignored"
    assert [tool.name for tool in result.capability_results] == ["reminder"]


@pytest.mark.asyncio
async def test_run_agent_runtime_routes_explicit_reminder_through_agent(monkeypatch):
    created = {}

    class FakeAgent:
        async def arun(self, **kwargs):
            created["model_input"] = kwargs["input"]
            return SimpleNamespace(
                content="",
                messages=[SimpleNamespace(role="assistant", content="")],
            )

    def fake_create_interaction_agent(**kwargs):
        created["called"] = True
        assert kwargs["input_message"] == "18:05提醒我出门"
        kwargs["capability_results"].append(
            CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：出门（2026-05-10 18:05）"},
                metadata={"durable_write": True},
            )
        )
        return FakeAgent()

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", fake_create_interaction_agent
    )

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
    assert [tool.name for tool in result.capability_results] == ["reminder"]
    assert result.trace.runtime.name == "agent_runtime"
    assert result.trace.routing.route == "utility_capability"
    assert created["called"] is True
    assert created["model_input"] == "18:05提醒我出门"


@pytest.mark.asyncio
async def test_run_agent_runtime_fails_closed_when_agent_raises(monkeypatch):
    class FailingAgent:
        async def arun(self, **kwargs):
            raise RuntimeError("model unavailable")

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", lambda **kwargs: FailingAgent()
    )

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
    assert result.trace.runtime.status == "exception"
    assert result.trace.error is not None
    assert result.trace.error.code == "agent_runtime_exception"


@pytest.mark.asyncio
async def test_run_agent_runtime_times_out_when_agent_hangs(monkeypatch):
    class HangingAgent:
        async def arun(self, **kwargs):
            await asyncio.sleep(1)

    monkeypatch.setenv("COKE_AGENT_RUNTIME_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", lambda **kwargs: HangingAgent()
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "agent_runtime_timeout"
    assert result.error_disposition.retryable is True
    assert result.trace.runtime.status == "timeout"
    assert result.trace.error is not None
    assert result.trace.error.code == "agent_runtime_timeout"


def test_agent_runtime_default_timeout_stays_inside_user_path_budget(monkeypatch):
    monkeypatch.delenv("COKE_AGENT_RUNTIME_TIMEOUT_SECONDS", raising=False)

    assert agent_runtime._agent_runtime_timeout_seconds() == 100.0


@pytest.mark.asyncio
async def test_run_agent_runtime_timeout_returns_captured_tool_summary(monkeypatch):
    class HangingAgent:
        async def arun(self, **kwargs):
            await asyncio.sleep(1)

    def fake_create_interaction_agent(**kwargs):
        kwargs["capability_results"].append(
            CapabilityResult(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：喝水（2026-05-09 17:57）"},
                metadata={"durable_write": True},
            )
        )
        return HangingAgent()

    monkeypatch.setenv("COKE_AGENT_RUNTIME_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", fake_create_interaction_agent
    )

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


@pytest.mark.asyncio
async def test_run_agent_runtime_visible_text_prefers_final_text_over_visible_summary(
    monkeypatch,
):
    class FakeAgent:
        async def arun(self, **kwargs):
            return SimpleNamespace(
                content="character voiced reply",
                messages=[
                    SimpleNamespace(role="assistant", content=""),
                ],
            )

    def fake_create_interaction_agent(**kwargs):
        kwargs["capability_results"].append(
            CapabilityResult(
                name="reminder",
                ok=True,
                content={"visible_summary": "raw port summary"},
                metadata={"durable_write": True},
            )
        )
        return FakeAgent()

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", fake_create_interaction_agent
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert len(result.capability_results) == 1
    assert result.visible_messages[0].content == "character voiced reply"


@pytest.mark.asyncio
async def test_run_agent_runtime_visible_text_falls_back_to_visible_summary_when_final_text_empty(
    monkeypatch,
):
    class FakeAgent:
        async def arun(self, **kwargs):
            return SimpleNamespace(
                content="",
                messages=[
                    SimpleNamespace(role="assistant", content=""),
                ],
            )

    def fake_create_interaction_agent(**kwargs):
        kwargs["capability_results"].append(
            CapabilityResult(
                name="reminder",
                ok=True,
                content={"visible_summary": "port summary used as fallback"},
                metadata={"durable_write": True},
            )
        )
        return FakeAgent()

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", fake_create_interaction_agent
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert result.visible_messages[0].content == "port summary used as fallback"


@pytest.mark.asyncio
async def test_run_agent_runtime_prefers_domain_visible_summary_for_explicit_scheduling_action(
    monkeypatch,
):
    preloaded_domain_result = DomainExecutionResult(
        domain="scheduling",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="accept_friend_request",
                ok=True,
                effect="write",
                entity_type="friend_request",
                entity_id="fr-1",
                facts={"visible_summary": "已通过好友请求。"},
            ),
        ),
        missing_fields=(),
        safety_boundary=None,
        reply_contract=ReplyContract(
            intent="confirm_execution",
            required_facts=(),
            required_questions=(),
            prohibited_claims=("not_accepted",),
            allow_rephrase=True,
        ),
    )

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
    ):
        del input_message, intent, run_context
        domain_results.append(preloaded_domain_result)
        return preloaded_domain_result.to_dict()

    class FakeAgent:
        async def arun(self, **kwargs):
            return SimpleNamespace(
                content="哎呀，系统刚才出了点状况，没能成功处理你的好友请求。",
                messages=[SimpleNamespace(role="assistant", content="")],
            )

    async def fake_interpret_semantic_intent(**_kwargs):
        return agent_runtime.SemanticIntentResult(
            intent="accept_friend_request",
            confidence="high",
        )

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )
    monkeypatch.setattr(
        agent_runtime,
        "interpret_semantic_intent",
        fake_interpret_semantic_intent,
    )
    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", lambda **kwargs: FakeAgent()
    )

    agent_input = _agent_input()
    agent_input = type(agent_input)(
        input_type=agent_input.input_type,
        conversation_id=agent_input.conversation_id,
        text="通过 Bob 的好友请求。",
        payload=agent_input.payload,
        occurred_at=agent_input.occurred_at,
        metadata=agent_input.metadata,
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=agent_input,
        run_context=_run_context(),
    )

    assert [message.content for message in result.visible_messages] == [
        "已通过好友请求。"
    ]
    assert result.domain_results == (preloaded_domain_result,)


@pytest.mark.asyncio
async def test_run_agent_runtime_prefers_explicit_past_reminder_failure_text(
    monkeypatch,
):
    past_result = DomainExecutionResult(
        domain="reminder",
        outcome="failed",
        operations=(
            DomainOperationResult(
                action="create",
                ok=False,
                effect="none",
                entity_type="reminder",
                entity_id=None,
                facts={
                    "visible_summary": "这个提醒时间已经过去了，请告诉我一个未来的时间。"
                },
            ),
        ),
        safety_boundary="explicit_past",
        reply_contract=ReplyContract(
            intent="report_failure",
            required_facts=(),
            required_questions=(),
            prohibited_claims=("reminder_created",),
        ),
        error=DomainError(
            code="InvalidSchedule",
            message="这个提醒时间已经过去了，请告诉我一个未来的时间。",
            retryable=False,
            detail={"reason": "past_one_shot"},
        ),
    )

    class FakeAgent:
        async def arun(self, **kwargs):
            return SimpleNamespace(
                content="我没接住你刚才的意思。你可以换个说法再说一次吗？",
                messages=[SimpleNamespace(role="assistant", content="")],
            )

    def fake_create_interaction_agent(**kwargs):
        kwargs["domain_results"].append(past_result)
        return FakeAgent()

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", fake_create_interaction_agent
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert [message.content for message in result.visible_messages] == [
        "这个提醒时间已经过去了，请告诉我一个未来的时间。"
    ]
    assert result.domain_results == (past_result,)


@pytest.mark.asyncio
async def test_run_agent_runtime_prefers_reminder_list_visible_summary(monkeypatch):
    list_result = DomainExecutionResult(
        domain="reminder",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="list",
                ok=True,
                effect="read",
                entity_type="reminder",
                entity_id=None,
                facts={
                    "count": 2,
                    "reminders": (
                        {"title": "买菜", "local_date": "2026-05-26"},
                        {"title": "喝水", "local_date": "2026-05-26"},
                    ),
                    "visible_summary": "你今天有 2 个提醒：\n- 买菜（2026-05-26 10:00）\n- 喝水（2026-05-26 12:00）",
                },
            ),
        ),
        reply_contract=ReplyContract(
            intent="direct_answer",
            required_facts=(),
            required_questions=(),
            prohibited_claims=("reminder_created",),
        ),
    )

    class FakeAgent:
        async def arun(self, **kwargs):
            return SimpleNamespace(
                content='{"MultiModalResponses":[{"type":"text","content":"你今天有2个提醒：\\n- 喝水"}]}',
                messages=[SimpleNamespace(role="assistant", content="")],
            )

    def fake_create_interaction_agent(**kwargs):
        kwargs["domain_results"].append(list_result)
        return FakeAgent()

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", fake_create_interaction_agent
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert [message.content for message in result.visible_messages] == [
        "你今天有 2 个提醒：\n- 买菜（2026-05-26 10:00）\n- 喝水（2026-05-26 12:00）"
    ]


@pytest.mark.asyncio
async def test_run_agent_runtime_short_circuits_explicit_past_reminder_before_model(
    monkeypatch,
):
    def fail_create_interaction_agent(**kwargs):
        raise AssertionError(
            "explicit past reminders should be handled deterministically"
        )

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", fail_create_interaction_agent
    )

    agent_input = _agent_input()
    agent_input = type(agent_input)(
        input_type=agent_input.input_type,
        conversation_id=agent_input.conversation_id,
        text="提醒我昨天 10 点开会。",
        payload=agent_input.payload,
        occurred_at=agent_input.occurred_at,
        metadata=agent_input.metadata,
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=agent_input,
        run_context=_run_context(),
    )

    assert [message.content for message in result.visible_messages] == [
        "这个提醒时间已经过去了，请告诉我一个未来的时间。"
    ]
    assert result.domain_results[0].safety_boundary == "explicit_past"
    assert result.output_disposition.status == "ok"


@pytest.mark.asyncio
async def test_run_agent_runtime_dispatches_semantic_focus_action_from_product_notification_context(
    monkeypatch,
):
    captured = {}
    interpreted = {}
    preloaded_domain_result = DomainExecutionResult(
        domain="scheduling",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="accept_friend_request",
                ok=True,
                effect="write",
                entity_type="friend_request",
                entity_id="fr-1",
                facts={"visible_summary": "已通过好友请求。"},
            ),
        ),
        missing_fields=(),
        safety_boundary=None,
        reply_contract=ReplyContract(
            intent="confirm_execution",
            required_facts=(),
            required_questions=(),
            prohibited_claims=("not_accepted",),
            allow_rephrase=True,
        ),
    )

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
        forced_args=None,
    ):
        captured.update(
            {
                "input_message": input_message,
                "intent": intent,
                "forced_args": forced_args,
            }
        )
        domain_results.append(preloaded_domain_result)
        return preloaded_domain_result.to_dict()

    class FakeAgent:
        async def arun(self, **kwargs):
            return SimpleNamespace(content="ignored", messages=[])

    semantic_client = object()

    async def fake_interpret_semantic_intent(*, focus, current_utterance, client=None):
        interpreted["focus"] = focus.model_dump(mode="json")
        interpreted["current_utterance"] = current_utterance
        interpreted["client"] = client
        return agent_runtime.SemanticIntentResult(
            intent="accept",
            confidence="high",
        )

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )
    monkeypatch.setattr(
        agent_runtime,
        "interpret_semantic_intent",
        fake_interpret_semantic_intent,
    )
    monkeypatch.setattr(
        agent_runtime,
        "_create_semantic_intent_client",
        lambda: semantic_client,
        raising=False,
    )
    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", lambda **kwargs: FakeAgent()
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="user.turn",
            conversation_id="conv-1",
            text="确认",
            payload=UserTurnPayload(
                current_message_ids=["msg-1"],
                metadata={
                    "product_notification": {
                        "request_id": "fr_1",
                        "request_type": "friend_request",
                        "allowed_actions": ["accept", "reject"],
                    }
                },
            ),
            occurred_at=datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
        ),
        run_context=_run_context(),
    )

    assert captured == {
        "input_message": "确认",
        "intent": "accept_friend_request",
        "forced_args": {"request_id": "fr_1"},
    }
    assert interpreted["focus"]["current"]["action_id"] == "fr_1"
    assert interpreted["current_utterance"] == "确认"
    assert interpreted["client"] is semantic_client
    assert [message.content for message in result.visible_messages] == [
        "已通过好友请求。"
    ]


@pytest.mark.asyncio
async def test_run_agent_runtime_fails_closed_when_focused_semantic_intent_is_ambiguous(
    monkeypatch,
):
    async def fake_interpret_semantic_intent(**_kwargs):
        return agent_runtime.SemanticIntentResult(
            intent="ambiguous",
            confidence="low",
            clarification_reason="semantic interpreter client unavailable",
        )

    class UnexpectedAgent:
        async def arun(self, **_kwargs):
            raise AssertionError(
                "interaction agent should not handle ambiguous focused action"
            )

    monkeypatch.setattr(
        agent_runtime, "interpret_semantic_intent", fake_interpret_semantic_intent
    )
    monkeypatch.setattr(
        agent_runtime,
        "_create_interaction_agent",
        lambda **kwargs: UnexpectedAgent(),
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="user.turn",
            conversation_id="conv-1",
            text="同意",
            payload=UserTurnPayload(
                current_message_ids=["msg-1"],
                metadata={
                    "product_notification": {
                        "request_id": "fr_1",
                        "request_type": "friend_request",
                        "allowed_actions": ["accept", "reject"],
                    }
                },
            ),
            occurred_at=datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
        ),
        run_context=_run_context(),
    )

    assert result.domain_results[0].safety_boundary == "semantic_focus_ambiguous"
    assert result.visible_messages[0].content == (
        "我没法可靠判断你要同意还是拒绝这条请求，请再明确回复同意或拒绝。"
    )


@pytest.mark.asyncio
async def test_run_agent_runtime_returns_stale_focus_when_fresh_friend_request_is_accepted(
    monkeypatch,
):
    port_calls = []

    class RecordingSchedulingPort:
        def __init__(self, *, tool_name: str):
            self.tool_name = tool_name

        async def run(self, input_message, run_context, args):
            del input_message, run_context, args
            port_calls.append(self.tool_name)
            if self.tool_name == "list_friend_requests":
                return CapabilityResult(
                    name=self.tool_name,
                    ok=True,
                    content={
                        "friend_requests": [
                            {
                                "id": "fr_1",
                                "status": "accepted",
                                "targetAccountId": "user-1",
                            }
                        ]
                    },
                )
            return CapabilityResult(
                name=self.tool_name,
                ok=True,
                content={"id": "fr_1", "status": "accepted"},
            )

    async def fake_interpret_semantic_intent(**_kwargs):
        return agent_runtime.SemanticIntentResult(intent="accept", confidence="high")

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
        RecordingSchedulingPort,
    )
    monkeypatch.setattr(
        agent_runtime, "interpret_semantic_intent", fake_interpret_semantic_intent
    )
    monkeypatch.setattr(
        agent_runtime,
        "_create_interaction_agent",
        lambda **kwargs: _IgnoredAgent(),
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="user.turn",
            conversation_id="conv-1",
            text="确认",
            payload=UserTurnPayload(
                current_message_ids=["msg-1"],
                metadata={
                    "product_notification": {
                        "request_id": "fr_1",
                        "request_type": "friend_request",
                        "allowed_actions": ["accept", "reject"],
                    }
                },
            ),
            occurred_at=datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
        ),
        run_context=_run_context(),
    )

    domain_result = result.domain_results[0]
    assert domain_result.outcome == "failed"
    assert domain_result.safety_boundary == "stale_focus"
    assert domain_result.operations[0].ok is False
    assert domain_result.reply_contract.intent == "report_failure"
    assert "accept_friend_request" not in port_calls


@pytest.mark.asyncio
async def test_run_agent_runtime_returns_stale_focus_when_shared_request_is_expired(
    monkeypatch,
):
    port_calls = []

    class RecordingSchedulingPort:
        def __init__(self, *, tool_name: str):
            self.tool_name = tool_name

        async def run(self, input_message, run_context, args):
            del input_message, args
            port_calls.append(self.tool_name)
            if self.tool_name == "list_shared_reminders":
                return CapabilityResult(
                    name=self.tool_name,
                    ok=True,
                    content={
                        "shared_reminders": [
                            {
                                "id": "srr_1",
                                "status": "pending_invitee_confirmation",
                                "inviteeAccountId": "user-1",
                                "expiresAt": "2026-05-09T00:59:59+00:00",
                            }
                        ]
                    },
                )
            return CapabilityResult(
                name=self.tool_name,
                ok=True,
                content={"id": "srr_1", "status": "accepted"},
            )

    async def fake_interpret_semantic_intent(**_kwargs):
        return agent_runtime.SemanticIntentResult(intent="accept", confidence="high")

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
        RecordingSchedulingPort,
    )
    monkeypatch.setattr(
        agent_runtime, "interpret_semantic_intent", fake_interpret_semantic_intent
    )
    monkeypatch.setattr(
        agent_runtime,
        "_create_interaction_agent",
        lambda **kwargs: _IgnoredAgent(),
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="user.turn",
            conversation_id="conv-1",
            text="确认",
            payload=UserTurnPayload(
                current_message_ids=["msg-1"],
                metadata={
                    "product_notification": {
                        "request_id": "srr_1",
                        "request_type": "shared_reminder_request",
                        "allowed_actions": ["accept", "reject"],
                    }
                },
            ),
            occurred_at=datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
        ),
        run_context=_run_context(),
    )

    domain_result = result.domain_results[0]
    assert domain_result.outcome == "failed"
    assert domain_result.safety_boundary == "stale_focus"
    assert domain_result.operations[0].ok is False
    assert "不再可处理" in domain_result.operations[0].facts["visible_summary"]
    assert "accept_shared_reminder" not in port_calls


@pytest.mark.asyncio
async def test_run_agent_runtime_returns_stale_focus_for_wrong_recipient(
    monkeypatch,
):
    port_calls = []

    class RecordingSchedulingPort:
        def __init__(self, *, tool_name: str):
            self.tool_name = tool_name

        async def run(self, input_message, run_context, args):
            del input_message, run_context, args
            port_calls.append(self.tool_name)
            if self.tool_name == "list_friend_requests":
                return CapabilityResult(
                    name=self.tool_name,
                    ok=True,
                    content={
                        "friend_requests": [
                            {
                                "id": "fr_1",
                                "status": "pending",
                                "targetAccountId": "someone-else",
                            }
                        ]
                    },
                )
            return CapabilityResult(
                name=self.tool_name,
                ok=True,
                content={"id": "fr_1", "status": "accepted"},
            )

    async def fake_interpret_semantic_intent(**_kwargs):
        return agent_runtime.SemanticIntentResult(intent="accept", confidence="high")

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.SchedulingCapabilityPort",
        RecordingSchedulingPort,
    )
    monkeypatch.setattr(
        agent_runtime, "interpret_semantic_intent", fake_interpret_semantic_intent
    )
    monkeypatch.setattr(
        agent_runtime,
        "_create_interaction_agent",
        lambda **kwargs: _IgnoredAgent(),
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="user.turn",
            conversation_id="conv-1",
            text="确认",
            payload=UserTurnPayload(
                current_message_ids=["msg-1"],
                metadata={
                    "product_notification": {
                        "request_id": "fr_1",
                        "request_type": "friend_request",
                        "allowed_actions": ["accept", "reject"],
                    }
                },
            ),
            occurred_at=datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
        ),
        run_context=_run_context(),
    )

    domain_result = result.domain_results[0]
    assert domain_result.outcome == "failed"
    assert domain_result.safety_boundary == "stale_focus"
    assert domain_result.operations[0].ok is False
    assert "accept_friend_request" not in port_calls


@pytest.mark.asyncio
async def test_run_agent_runtime_treats_domain_write_as_confirmed_reminder_promise(
    monkeypatch,
):
    class FakeAgent:
        async def arun(self, **kwargs):
            return SimpleNamespace(
                content="好的，18:00 我会提醒你喝水。",
                messages=[
                    SimpleNamespace(
                        role="assistant",
                        content="好的，18:00 我会提醒你喝水。",
                    )
                ],
            )

    def fake_create_interaction_agent(**kwargs):
        kwargs["domain_results"].append(
            DomainExecutionResult(
                domain="reminder",
                outcome="executed",
                operations=(
                    DomainOperationResult(
                        action="create",
                        ok=True,
                        effect="write",
                        entity_type="reminder",
                        entity_id="rem-1",
                        facts={"title": "drink water", "local_time": "18:00:00"},
                    ),
                ),
                missing_fields=(),
                safety_boundary=None,
                reply_contract=ReplyContract(
                    intent="confirm_execution",
                    required_facts=(),
                    required_questions=(),
                    prohibited_claims=("not_created",),
                    allow_rephrase=True,
                ),
            )
        )
        assert kwargs["capability_results"] == []
        return FakeAgent()

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", fake_create_interaction_agent
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=_agent_input(),
        run_context=_run_context(),
    )

    assert result.visible_messages[0].content == "好的，18:00 我会提醒你喝水。"
    assert result.capability_results == ()
    assert result.output_disposition.status == "ok"
    assert result.error_disposition is None


@pytest.mark.asyncio
async def test_run_agent_runtime_prefers_domain_summary_for_superseding_batched_write(
    monkeypatch,
):
    class FakeAgent:
        async def arun(self, **kwargs):
            return SimpleNamespace(
                content="已设置周一9点喝水提醒。再给你5个健康早餐推荐：燕麦。",
                messages=[
                    SimpleNamespace(
                        role="assistant",
                        content="已设置周一9点喝水提醒。再给你5个健康早餐推荐：燕麦。",
                    )
                ],
            )

    def fake_create_interaction_agent(**kwargs):
        kwargs["domain_results"].append(
            DomainExecutionResult(
                domain="reminder",
                outcome="executed",
                operations=(
                    DomainOperationResult(
                        action="create",
                        ok=True,
                        effect="write",
                        entity_type="reminder",
                        entity_id="rem-1",
                        facts={
                            "summary": "已创建提醒：喝水（2026-06-01 09:00）",
                            "title": "喝水",
                            "local_date": "2026-06-01",
                            "local_time": "09:00:00",
                        },
                    ),
                ),
                missing_fields=(),
                safety_boundary=None,
                reply_contract=ReplyContract(
                    intent="confirm_execution",
                    required_facts=(),
                    required_questions=(),
                    prohibited_claims=("not_created",),
                    allow_rephrase=True,
                ),
            )
        )
        return FakeAgent()

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", fake_create_interaction_agent
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="user.turn",
            conversation_id="conv-1",
            text=(
                "（2026年05月25日21时15分 Alice发来了文本消息）"
                "帮我把这周每天 9 点都设个喝水提醒，再给我推荐 5 个健康早餐\n"
                "（2026年05月25日21时15分 Alice发来了文本消息）"
                "等一下，先取消刚才说的，改成只设周一 9 点提醒"
            ),
            payload=UserTurnPayload(current_message_ids=["msg-1", "msg-2"]),
            occurred_at=datetime(2026, 5, 25, 13, 15, tzinfo=UTC),
        ),
        run_context=_run_context(),
    )

    assert [message.content for message in result.visible_messages] == [
        "已创建提醒：喝水（2026-06-01 09:00）"
    ]


@pytest.mark.asyncio
async def test_run_agent_runtime_fails_closed_on_unconfirmed_reminder_promise(
    monkeypatch,
):
    reminder_calls = 0

    class FakeAgent:
        async def arun(self, **kwargs):
            return SimpleNamespace(
                content=("好的呀！17:57 我会提醒你喝水，" "还有什么需要我帮忙的吗？"),
                messages=[
                    SimpleNamespace(
                        role="assistant",
                        content=(
                            "好的呀！17:57 我会提醒你喝水，" "还有什么需要我帮忙的吗？"
                        ),
                    )
                ],
            )

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", lambda **kwargs: FakeAgent()
    )

    agent_input = _agent_input()
    agent_input = type(agent_input)(
        input_type=agent_input.input_type,
        conversation_id=agent_input.conversation_id,
        text="今天17:57提醒我喝水呀",
        payload=agent_input.payload,
        occurred_at=agent_input.occurred_at,
        metadata=agent_input.metadata,
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=agent_input,
        run_context=_run_context(),
    )

    assert reminder_calls == 0
    assert result.visible_messages == ()
    assert result.capability_results == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "unconfirmed_durable_write_promise"


@pytest.mark.asyncio
async def test_reminder_fired_input_passes_raw_input_to_model(monkeypatch):
    model_inputs = []

    class FakeAgent:
        async def arun(self, **kwargs):
            model_inputs.append(kwargs["input"])
            return SimpleNamespace(
                content="该喝水了。",
                messages=[SimpleNamespace(role="assistant", content="ignored")],
            )

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", lambda **kwargs: FakeAgent()
    )

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
    assert model_inputs == ["提醒：喝水"]


# --- New _create_interaction_agent() tests ---


def test_create_interaction_agent_user_turn_has_exactly_five_tools():
    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="hi",
        capability_results=[],
        domain_results=[],
    )

    assert [tool.name for tool in agent.tools] == [
        "reminder_domain",
        "scheduling_domain",
        "timezone",
        "calendar_import",
        "url_context",
    ]


def test_create_interaction_agent_reminder_fired_has_no_tools():
    reminder_input = AgentInput(
        input_type="reminder.fired",
        conversation_id="conv-1",
        text="提醒：喝水",
        payload=ReminderFirePayload(
            fire_id="fire-1",
            reminder_id="rem-1",
            title="喝水",
            scheduled_for=datetime(2026, 5, 22, 8, 0, tzinfo=UTC),
        ),
        occurred_at=datetime(2026, 5, 22, 8, 0, tzinfo=UTC),
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=reminder_input,
        input_message="提醒：喝水",
        capability_results=[],
        domain_results=[],
    )

    assert agent.tools == [] or agent.tools is None or len(agent.tools) == 0


def test_create_interaction_agent_uses_chat_response_model_role(monkeypatch):
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

    agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="hi",
        capability_results=[],
        domain_results=[],
    )

    assert captured == {"role": "chat_response", "max_tokens": 2000}


def test_create_interaction_agent_sets_tool_call_limit_four(monkeypatch):
    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("agno.agent.Agent", FakeAgent)
    monkeypatch.setattr(
        "agent.agno_agent.model_factory.create_llm_model",
        lambda **kwargs: object(),
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="hi",
        capability_results=[],
        domain_results=[],
    )

    assert agent.kwargs["tool_call_limit"] == 4


def test_create_interaction_agent_uses_injected_session_db(monkeypatch):
    injected_db = object()

    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("agno.agent.Agent", FakeAgent)
    monkeypatch.setattr(
        "agent.agno_agent.model_factory.create_llm_model",
        lambda **kwargs: object(),
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="hi",
        capability_results=[],
        domain_results=[],
        session_db=injected_db,
    )

    assert agent.kwargs["db"] is injected_db
    assert agent.kwargs["add_history_to_context"] is True
    assert agent.kwargs["num_history_messages"] == 20
    assert agent.kwargs["add_session_state_to_context"] is False


def test_create_interaction_agent_domain_tools_have_stop_after_tool_call_false():
    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="hi",
        capability_results=[],
        domain_results=[],
    )

    tool_flags = {tool.name: tool.stop_after_tool_call for tool in agent.tools}
    assert tool_flags["reminder_domain"] is False
    assert tool_flags["scheduling_domain"] is False


@pytest.mark.asyncio
async def test_create_interaction_agent_reminder_domain_delegates_with_domain_results(
    monkeypatch,
):
    captured = {}
    run_context = _run_context()
    capability_results = []
    domain_results = []
    envelope = {
        "domain": "reminder",
        "outcome": "executed",
        "operations": [
            {
                "action": "create",
                "ok": True,
                "effect": "write",
                "entity_type": "reminder",
                "entity_id": "rem-1",
                "facts": {"title": "drink water"},
                "error": None,
            }
        ],
        "missing_fields": [],
        "safety_boundary": None,
        "reply_contract": {
            "intent": "confirm_execution",
            "required_facts": [],
            "required_questions": [],
            "prohibited_claims": ["not_created"],
            "allow_rephrase": True,
        },
        "error": None,
    }

    async def fake_run_reminder_domain(
        *,
        input_message,
        run_context,
        domain_results,
    ):
        captured.update(
            {
                "input_message": input_message,
                "run_context": run_context,
                "domain_results": domain_results,
            }
        )
        return envelope

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_reminder_domain",
        fake_run_reminder_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=run_context,
        agent_input=_agent_input(),
        input_message="remind me to drink water",
        capability_results=capability_results,
        domain_results=domain_results,
    )
    reminder_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "reminder_domain"
    )

    result = await reminder_domain()

    assert result is envelope
    assert captured == {
        "input_message": "remind me to drink water",
        "run_context": run_context,
        "domain_results": domain_results,
    }


@pytest.mark.asyncio
async def test_create_interaction_agent_reminder_domain_rejects_duplicate_calls(
    monkeypatch,
):
    calls = 0
    envelope = {
        "domain": "reminder",
        "outcome": "executed",
        "operations": [],
        "missing_fields": [],
        "safety_boundary": None,
        "reply_contract": {
            "intent": "confirm_execution",
            "required_facts": [],
            "required_questions": [],
            "prohibited_claims": [],
            "allow_rephrase": True,
        },
        "error": None,
    }

    async def fake_run_reminder_domain(
        *,
        input_message,
        run_context,
        domain_results,
    ):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return envelope

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_reminder_domain",
        fake_run_reminder_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="hi",
        capability_results=[],
        domain_results=[],
    )
    reminder_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "reminder_domain"
    )

    first = await reminder_domain()
    second = await reminder_domain()

    assert calls == 1
    assert first is envelope
    assert second == {
        "domain": "reminder",
        "outcome": "failed",
        "operations": [],
        "missing_fields": [],
        "safety_boundary": "duplicate_call",
        "reply_contract": {
            "intent": "report_failure",
            "required_facts": [],
            "required_questions": [],
            "prohibited_claims": ["reminder_created"],
            "allow_rephrase": True,
        },
        "error": {
            "code": "duplicate_call",
            "message": "reminder_domain may only be called once per turn; answer from the first result",
            "retryable": False,
            "detail": {},
        },
    }


@pytest.mark.asyncio
async def test_create_interaction_agent_reminder_domain_ignores_model_supplied_args(
    monkeypatch,
):
    captured = {}
    envelope = {
        "domain": "reminder",
        "outcome": "executed",
        "operations": [],
        "missing_fields": [],
        "safety_boundary": None,
        "reply_contract": {
            "intent": "confirm_execution",
            "required_facts": [],
            "required_questions": [],
            "prohibited_claims": [],
            "allow_rephrase": True,
        },
        "error": None,
    }

    async def fake_run_reminder_domain(
        *,
        input_message,
        run_context,
        domain_results,
    ):
        captured["input_message"] = input_message
        captured["run_context"] = run_context
        captured["domain_results"] = domain_results
        return envelope

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_reminder_domain",
        fake_run_reminder_domain,
    )

    run_context = _run_context()
    capability_results = []
    domain_results = []
    agent = agent_runtime._create_interaction_agent(
        run_context=run_context,
        agent_input=_agent_input(),
        input_message="提醒我喝水",
        capability_results=capability_results,
        domain_results=domain_results,
    )
    reminder_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "reminder_domain"
    )

    result = await reminder_domain(
        action="create",
        reminder_params={"label": "喝水", "timezone": "Asia/Tokyo"},
    )

    assert result is envelope
    assert captured == {
        "input_message": "提醒我喝水",
        "run_context": run_context,
        "domain_results": domain_results,
    }


def test_create_interaction_agent_domain_tool_descriptions_route_friend_invites():
    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message=(
            "帮我约李梓豪，上海时间2029年1月1日10:00，"
            "标题是验收测试，持续5分钟。"
        ),
        capability_results=[],
        domain_results=[],
    )
    descriptions = {tool.name: tool.description for tool in agent.tools}

    assert "帮我约/邀请" in descriptions["scheduling_domain"]
    assert "create_shared_reminder" in descriptions["scheduling_domain"]
    assert "invitee_name" in descriptions["scheduling_domain"]
    assert "fire_at" in descriptions["scheduling_domain"]
    assert "duration_minutes" in descriptions["scheduling_domain"]
    assert "shared-reminder" not in descriptions["reminder_domain"]


@pytest.mark.asyncio
async def test_create_interaction_agent_scheduling_domain_delegates_with_intent(
    monkeypatch,
):
    captured = {}
    run_context = _run_context()
    capability_results = []
    domain_results = []
    envelope = {
        "ok": True,
        "domain": "scheduling",
        "visible_summary": "已确认预约",
        "synthesis_context": None,
        "content": {"visible_summary": "已确认预约"},
        "error": None,
    }

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
        forced_args=None,
    ):
        captured.update(
            {
                "input_message": input_message,
                "intent": intent,
                "run_context": run_context,
                "domain_results": domain_results,
                "forced_args": forced_args,
            }
        )
        return envelope

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=run_context,
        agent_input=_agent_input(),
        input_message="confirm it",
        capability_results=capability_results,
        domain_results=domain_results,
    )
    scheduling_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "scheduling_domain"
    )

    result = await scheduling_domain(intent="accept_shared_reminder: request_id=srr_1")

    assert result is envelope
    assert captured == {
        "input_message": "confirm it",
        "intent": "accept_shared_reminder",
        "run_context": run_context,
        "domain_results": domain_results,
        "forced_args": None,
    }


@pytest.mark.asyncio
async def test_create_interaction_agent_scheduling_domain_normalizes_dict_intent(
    monkeypatch,
):
    captured = {}
    run_context = _run_context()
    capability_results = []
    domain_results = []
    envelope = {
        "ok": True,
        "domain": "scheduling",
        "visible_summary": "已通过好友请求",
        "synthesis_context": None,
        "content": {"visible_summary": "已通过好友请求"},
        "error": None,
    }

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
        forced_args=None,
    ):
        captured.update(
            {
                "input_message": input_message,
                "intent": intent,
                "run_context": run_context,
                "domain_results": domain_results,
                "forced_args": forced_args,
            }
        )
        return envelope

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=run_context,
        agent_input=_agent_input(),
        input_message="通过 Bob 的好友请求",
        capability_results=capability_results,
        domain_results=domain_results,
    )
    scheduling_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "scheduling_domain"
    )

    result = await scheduling_domain(intent={"intent": "accept_friend_request"})

    assert result is envelope
    assert captured == {
        "input_message": "通过 Bob 的好友请求",
        "intent": "accept_friend_request",
        "run_context": run_context,
        "domain_results": domain_results,
        "forced_args": None,
    }


def test_scheduling_intent_normalization_does_not_reclassify_list_friend_requests():
    assert (
        agent_runtime._normalize_scheduling_intent(
            {"list_friend_requests": {"status": "pending", "from_friend_name": "Bob"}},
            "我有没有未处理的好友请求？通过 Bob 的。",
        )
        == 'list_friend_requests: {"status": "pending"}'
    )


@pytest.mark.asyncio
async def test_create_interaction_agent_scheduling_domain_normalizes_nested_current_intent(
    monkeypatch,
):
    captured = {}

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
        forced_args=None,
    ):
        del input_message, run_context, domain_results
        captured.update({"intent": intent, "forced_args": forced_args})
        return {"domain": "scheduling"}

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="帮我处理这次好友流程。",
        capability_results=[],
        domain_results=[],
    )
    scheduling_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "scheduling_domain"
    )

    await scheduling_domain(
        intent={
            "intent": {
                "intent_name": "send_friend_request_by_user_link_code",
                "user_link_code": "AbCdEfGhIjK_",
                "note": "FM01",
            }
        }
    )

    assert captured == {
        "intent": "send_friend_request_by_user_link_code",
        "forced_args": {
            "user_link_code": "AbCdEfGhIjK_",
            "message": "FM01",
        },
    }


@pytest.mark.asyncio
async def test_run_agent_runtime_refuses_retired_account_control_before_model(
    monkeypatch,
):
    def fail_create_interaction_agent(**kwargs):
        raise AssertionError("retired account-control turns should not reach model")

    monkeypatch.setattr(
        agent_runtime, "_create_interaction_agent", fail_create_interaction_agent
    )

    agent_input = _agent_input()
    agent_input = type(agent_input)(
        input_type=agent_input.input_type,
        conversation_id=agent_input.conversation_id,
        text="解除对 Bob 的屏蔽",
        payload=agent_input.payload,
        occurred_at=agent_input.occurred_at,
        metadata=agent_input.metadata,
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=agent_input,
        run_context=_run_context(),
    )

    assert result.visible_messages
    assert "屏蔽" in result.visible_messages[0].content
    assert result.domain_results[0].safety_boundary == "retired_account_control"
    assert result.domain_results[0].operations[0].action == "account_control"
    assert result.domain_results[0].operations[0].effect == "none"


@pytest.mark.asyncio
async def test_create_interaction_agent_scheduling_domain_honors_tool_key_intent(
    monkeypatch,
):
    captured = {}
    run_context = _run_context()
    capability_results = []
    domain_results = []
    envelope = {
        "ok": True,
        "domain": "scheduling",
        "visible_summary": "这是你的好友邀请链接",
        "synthesis_context": None,
        "content": {"visible_summary": "这是你的好友邀请链接"},
        "error": None,
    }

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
    ):
        captured.update(
            {
                "input_message": input_message,
                "intent": intent,
                "run_context": run_context,
                "domain_results": domain_results,
            }
        )
        return envelope

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=run_context,
        agent_input=_agent_input(),
        input_message="把我自己的好友邀请链接给我，我要分享给一个朋友。",
        capability_results=capability_results,
        domain_results=domain_results,
    )
    scheduling_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "scheduling_domain"
    )

    result = await scheduling_domain(intent={"get_user_link": {}})

    assert result is envelope
    assert captured == {
        "input_message": "把我自己的好友邀请链接给我，我要分享给一个朋友。",
        "intent": "get_user_link",
        "run_context": run_context,
        "domain_results": domain_results,
    }


@pytest.mark.asyncio
async def test_create_interaction_agent_scheduling_domain_forces_complete_shared_reminder_create_args(
    monkeypatch,
):
    captured = {}

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
        forced_args=None,
    ):
        captured.update(
            {
                "input_message": input_message,
                "intent": intent,
                "forced_args": forced_args,
            }
        )
        del run_context, domain_results
        return {"domain": "scheduling"}

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="今天上午十点半，帮我和 EVA 约一个一个小时的时间去做测试",
        capability_results=[],
        domain_results=[],
    )
    scheduling_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "scheduling_domain"
    )

    await scheduling_domain(
        intent={
            "create_shared_reminder": {
                "invitee_name": "EVA",
                "title": "一起运动",
                "fire_at": "2026-05-26T10:30:00+08:00",
                "duration_minutes": 60,
            }
        }
    )

    assert captured == {
        "input_message": "今天上午十点半，帮我和 EVA 约一个一个小时的时间去做测试",
        "intent": "create_shared_reminder",
        "forced_args": {
            "invitee_name": "EVA",
            "title": "一起运动",
            "fire_at": "2026-05-26T10:30:00+08:00",
            "duration_minutes": 60,
        },
    }


@pytest.mark.asyncio
async def test_create_interaction_agent_scheduling_domain_delegates_tool_key_create_args_to_worker(
    monkeypatch,
):
    captured = {}
    run_context = _run_context()
    capability_results = []
    domain_results = []
    envelope = {
        "ok": True,
        "domain": "scheduling",
        "visible_summary": "已提交共享提醒请求。",
        "synthesis_context": None,
        "content": {"visible_summary": "已提交共享提醒请求。"},
        "error": None,
    }

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
        forced_args=None,
    ):
        captured.update(
            {
                "input_message": input_message,
                "intent": intent,
                "run_context": run_context,
                "domain_results": domain_results,
                "forced_args": forced_args,
            }
        )
        return envelope

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=run_context,
        agent_input=_agent_input(),
        input_message="我想约 Bob 这周五晚上 19:30 一起跑步 40 分钟，帮我们建共享提醒。",
        capability_results=capability_results,
        domain_results=domain_results,
    )
    scheduling_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "scheduling_domain"
    )

    result = await scheduling_domain(
        intent={
            "create_shared_reminder": {
                "invitee_name": "Bob",
                "title": "跑步",
                "fire_at": "2026-05-29T19:30:00",
                "duration_minutes": 40,
            }
        }
    )

    assert result is envelope
    assert captured["intent"] == "create_shared_reminder"
    assert captured["forced_args"] == {
        "invitee_name": "Bob",
        "title": "跑步",
        "fire_at": "2026-05-29T19:30:00",
        "duration_minutes": 40,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "error_code"),
    [
        (
            {
                "create_shared_reminder_request": {
                    "invitee_name": "Eva",
                    "title": "奇迹创坛",
                    "fire_at": "2026-05-27T11:00:00+09:00",
                }
            },
            "invalid_scheduling_intent",
        ),
        (
            {
                "create_shared_reminder": {
                    "invitee_name": "Eva",
                    "title": "奇迹创坛",
                    "start_time": "2026-05-27T11:00:00+09:00",
                }
            },
            "invalid_scheduling_args",
        ),
        (
            {
                "create_shared_reminder": {
                    "friend_id": "ck_CsFu-A91jbCSBwtizPx1K",
                    "title": "打篮球",
                    "fire_at": "2026-05-27T23:00:00+08:00",
                    "duration_minutes": 60,
                }
            },
            "invalid_scheduling_args",
        ),
        (
            {
                "create_shared_reminder": {
                    "invitee_name": "Eva",
                    "title": "奇迹创坛",
                    "start_datetime": "2026-05-27T11:00:00+09:00",
                }
            },
            "invalid_scheduling_args",
        ),
        (
            {
                "create_shared_reminder": {
                    "invitee_name": "Eva",
                    "title": "奇迹创坛",
                    "date_time": "2026-05-27T11:00:00+09:00",
                }
            },
            "invalid_scheduling_args",
        ),
    ],
)
async def test_create_interaction_agent_scheduling_domain_rejects_noncanonical_create_payloads(
    monkeypatch,
    payload,
    error_code,
):
    calls = 0
    domain_results = []

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
        forced_args=None,
    ):
        del input_message, intent, run_context, domain_results, forced_args
        nonlocal calls
        calls += 1
        return {"domain": "scheduling"}

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="帮我约好友打篮球",
        capability_results=[],
        domain_results=domain_results,
    )
    scheduling_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "scheduling_domain"
    )

    result = await scheduling_domain(intent=payload)

    assert calls == 0
    assert result["domain"] == "scheduling"
    assert result["outcome"] == "failed"
    assert result["error"]["code"] == error_code
    assert domain_results[-1].error is not None
    assert domain_results[-1].error.code == error_code


@pytest.mark.asyncio
async def test_create_interaction_agent_scheduling_domain_allows_read_then_write(
    monkeypatch,
):
    captured = []

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
        forced_args=None,
    ):
        del input_message, run_context, domain_results
        captured.append({"intent": intent, "forced_args": forced_args})
        return {"domain": "scheduling"}

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="先看一下好友，然后帮我约 Eva 去奇迹创坛",
        capability_results=[],
        domain_results=[],
    )
    scheduling_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "scheduling_domain"
    )

    await scheduling_domain(intent={"list_friends": {}})
    await scheduling_domain(
        intent={
            "create_shared_reminder": {
                "invitee_name": "Eva",
                "title": "奇迹创坛",
                "fire_at": "2026-05-27T11:00:00+09:00",
                "duration_minutes": 60,
            }
        }
    )

    assert captured == [
        {
            "intent": "list_friends",
            "forced_args": None,
        },
        {
            "intent": "create_shared_reminder",
            "forced_args": {
                "invitee_name": "Eva",
                "title": "奇迹创坛",
                "fire_at": "2026-05-27T11:00:00+09:00",
                "duration_minutes": 60,
            },
        },
    ]


@pytest.mark.asyncio
async def test_create_interaction_agent_scheduling_domain_fails_incomplete_forced_create_args(
    monkeypatch,
):
    calls = 0
    domain_results = []

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
        forced_args=None,
    ):
        del input_message, intent, run_context, domain_results, forced_args
        nonlocal calls
        calls += 1
        return {"domain": "scheduling"}

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="今晚九点，给我们约一个60分钟的共同提醒",
        capability_results=[],
        domain_results=domain_results,
    )
    scheduling_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "scheduling_domain"
    )

    result = await scheduling_domain(
        intent={
            "create_shared_reminder": {
                "invitee_name": "eva",
                "title": "共同提醒",
                "timezone": "Asia/Shanghai",
                "duration_minutes": 60,
            }
        }
    )

    assert calls == 0
    assert result["outcome"] == "failed"
    assert result["error"]["code"] == "invalid_scheduling_args"
    assert domain_results[-1].error is not None
    assert domain_results[-1].error.code == "invalid_scheduling_args"


@pytest.mark.asyncio
async def test_create_interaction_agent_scheduling_domain_rejects_common_create_alias_payload(
    monkeypatch,
):
    calls = 0

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
        forced_args=None,
    ):
        del input_message, intent, run_context, domain_results, forced_args
        nonlocal calls
        calls += 1
        return {"domain": "scheduling"}

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="我想约 Bob 这周五晚上 19:30 一起在小区操场跑步 40 分钟，帮我们两个建一个共享提醒。",
        capability_results=[],
        domain_results=[],
    )
    scheduling_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "scheduling_domain"
    )

    result = await scheduling_domain(
        intent={
            "create_shared_reminder": {
                "invitee_name": "Bob",
                "scheduled_time": "2026-05-29T19:30:00",
                "duration": 40,
                "activity": "跑步",
                "location": "小区操场",
            }
        }
    )

    assert calls == 0
    assert result["outcome"] == "failed"
    assert result["error"]["code"] == "invalid_scheduling_args"


def test_create_interaction_agent_preselected_scheduling_intent_hides_reminder_domain():
    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="我现在有没有待处理的共享提醒？",
        capability_results=[],
        domain_results=[],
        preloaded_scheduling_domain_result={"domain": "scheduling"},
        preselected_scheduling_intent="list_pending_shared_reminders",
    )

    tool_names = {tool.name for tool in agent.tools}

    assert "scheduling_domain" in tool_names
    assert "reminder_domain" not in tool_names


@pytest.mark.asyncio
async def test_create_interaction_agent_scheduling_domain_reuses_exact_duplicate_call(
    monkeypatch,
):
    calls = 0
    envelope = {
        "ok": True,
        "domain": "scheduling",
        "visible_summary": "已接受共享提醒",
        "synthesis_context": None,
        "content": {"visible_summary": "已接受共享提醒"},
        "error": None,
    }

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
        forced_args=None,
    ):
        del input_message, run_context, domain_results, forced_args
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return envelope | {"intent": intent}

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="confirm it",
        capability_results=[],
        domain_results=[],
    )
    scheduling_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "scheduling_domain"
    )

    first, second = await asyncio.gather(
        scheduling_domain(intent={"accept_shared_reminder": {"request_id": "srr_1"}}),
        scheduling_domain(intent={"accept_shared_reminder": {"request_id": "srr_1"}}),
    )

    assert calls == 1
    assert first is second
    assert first == envelope | {"intent": "accept_shared_reminder"}


@pytest.mark.asyncio
async def test_create_interaction_agent_scheduling_domain_fails_different_write_after_write(
    monkeypatch,
):
    calls = 0
    envelope = {
        "ok": True,
        "domain": "scheduling",
        "outcome": "executed",
        "operations": [
            {
                "action": "accept_shared_reminder",
                "ok": True,
                "effect": "write",
                "entity_type": "shared_reminder_request",
                "entity_id": "srr_1",
                "facts": {"visible_summary": "已接受共享提醒。"},
                "error": None,
            }
        ],
        "visible_summary": "已接受共享提醒",
        "synthesis_context": None,
        "content": {"visible_summary": "已接受共享提醒"},
        "error": None,
    }

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
        forced_args=None,
    ):
        del input_message, run_context, domain_results, forced_args
        nonlocal calls
        calls += 1
        return envelope | {"intent": intent}

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="confirm it",
        capability_results=[],
        domain_results=[],
    )
    scheduling_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "scheduling_domain"
    )

    first = await scheduling_domain(
        intent={"accept_shared_reminder": {"request_id": "srr_1"}}
    )
    second = await scheduling_domain(
        intent={"accept_shared_reminder": {"request_id": "srr_2"}}
    )

    assert calls == 1
    assert first["intent"] == "accept_shared_reminder"
    assert second["domain"] == "scheduling"
    assert second["outcome"] == "failed"
    assert second["safety_boundary"] == "multiple_scheduling_calls_after_write"
    assert second["error"]["code"] == "multiple_scheduling_calls_after_write"


@pytest.mark.asyncio
async def test_create_interaction_agent_scheduling_domain_fails_read_after_write(
    monkeypatch,
):
    calls = 0
    envelope = {
        "ok": True,
        "domain": "scheduling",
        "outcome": "executed",
        "operations": [
            {
                "action": "create_shared_reminder",
                "ok": True,
                "effect": "write",
                "entity_type": "shared_reminder_request",
                "entity_id": "srr_1",
                "facts": {"visible_summary": "已提交共享提醒请求。"},
                "error": None,
            }
        ],
        "content": {"visible_summary": "已提交共享提醒请求。"},
        "error": None,
    }

    async def fake_run_scheduling_domain(
        *,
        input_message,
        intent,
        run_context,
        domain_results,
        forced_args=None,
    ):
        del input_message, run_context, domain_results, forced_args
        nonlocal calls
        calls += 1
        return envelope | {"intent": intent}

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="create then list",
        capability_results=[],
        domain_results=[],
    )
    scheduling_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "scheduling_domain"
    )

    await scheduling_domain(
        intent={
            "create_shared_reminder": {
                "invitee_name": "Eva",
                "title": "奇迹创坛",
                "fire_at": "2026-05-27T11:00:00+09:00",
            }
        }
    )
    second = await scheduling_domain(intent={"list_friends": {}})

    assert calls == 1
    assert second["outcome"] == "failed"
    assert second["error"]["code"] == "multiple_scheduling_calls_after_write"


@pytest.mark.asyncio
async def test_create_interaction_agent_preloaded_scheduling_result_not_reused_for_different_intent():
    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="同意这个请求",
        capability_results=[],
        domain_results=[],
        preloaded_scheduling_domain_result={
            "domain": "scheduling",
            "outcome": "executed",
            "operations": [
                {
                    "action": "accept_shared_reminder",
                    "ok": True,
                    "effect": "write",
                    "entity_type": "shared_reminder_request",
                    "entity_id": "srr_1",
                    "facts": {"visible_summary": "已接受共享提醒。"},
                    "error": None,
                }
            ],
            "error": None,
        },
        preselected_scheduling_intent="accept_shared_reminder",
    )
    scheduling_domain = next(
        tool.entrypoint for tool in agent.tools if tool.name == "scheduling_domain"
    )

    result = await scheduling_domain(intent={"list_friends": {}})

    assert result["domain"] == "scheduling"
    assert result["outcome"] == "failed"
    assert result["safety_boundary"] == "preselected_scheduling_result"
    assert result["error"]["code"] == "preselected_scheduling_result"


def test_create_interaction_agent_resolves_default_session_db(monkeypatch):
    resolved_db = object()

    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("agno.agent.Agent", FakeAgent)
    monkeypatch.setattr(
        "agent.agno_agent.model_factory.create_llm_model",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        agent_runtime,
        "get_agent_session_db",
        lambda: resolved_db,
        raising=False,
    )

    agent = agent_runtime._create_interaction_agent(
        run_context=_run_context(),
        agent_input=_agent_input(),
        input_message="hi",
        capability_results=[],
        domain_results=[],
    )

    assert agent.kwargs["db"] is resolved_db
    assert agent.kwargs["markdown"] is False
