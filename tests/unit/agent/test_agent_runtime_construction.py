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
    assert create_kwargs["agent_input"] == _agent_input()
    assert create_kwargs["input_message"] == "hi"
    assert create_kwargs["capability_results"] == []
    assert create_kwargs["domain_results"] == []
    assert model_inputs == ["hi"]


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
    assert result.trace == {"runtime": "agent"}
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

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
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
async def test_run_agent_runtime_preloads_scheduling_action_from_product_notification_context(
    monkeypatch,
):
    captured = {}
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

    monkeypatch.setattr(
        "agent.agno_agent.runtime.execution_agents.run_scheduling_domain",
        fake_run_scheduling_domain,
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
    assert [message.content for message in result.visible_messages] == [
        "已通过好友请求。"
    ]


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
async def test_create_interaction_agent_reminder_domain_caches_parallel_calls(
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

    first, second = await asyncio.gather(reminder_domain(), reminder_domain())

    assert calls == 1
    assert first is envelope
    assert second is envelope


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

    result = await scheduling_domain(intent={"domain": "friend-request_pending", "params": {}})

    assert result is envelope
    assert captured == {
        "input_message": "通过 Bob 的好友请求",
        "intent": "accept_friend_request",
        "run_context": run_context,
        "domain_results": domain_results,
        "forced_args": None,
    }


def test_scheduling_intent_inference_treats_own_invite_link_as_get_user_link():
    assert (
        agent_runtime._infer_scheduling_intent_from_message(
            "把我自己的好友邀请链接给我，我要分享给一个朋友。"
        )
        == "get_user_link"
    )


def test_scheduling_intent_inference_treats_pending_shared_reminders_as_scheduling():
    assert (
        agent_runtime._infer_scheduling_intent_from_message(
            "我现在有没有待处理的共享提醒？只列待处理的，告诉我是谁发的、什么内容。"
        )
        == "list_pending_shared_reminders"
    )


def test_scheduling_intent_inference_treats_delete_friend_wording_as_remove_friendship():
    assert (
        agent_runtime._infer_scheduling_intent_from_message("把 Bob 从我的好友里删了。")
        == "remove_friendship"
    )


def test_product_notification_context_turns_short_confirmation_into_friend_request_accept():
    agent_input = AgentInput(
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
    )

    assert (
        agent_runtime._infer_scheduling_intent_from_agent_input("确认", agent_input)
        == "accept_friend_request"
    )


def test_product_notification_context_turns_short_confirmation_into_shared_reminder_accept():
    agent_input = AgentInput(
        input_type="user.turn",
        conversation_id="conv-1",
        text="同意",
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
    )

    assert (
        agent_runtime._infer_scheduling_intent_from_agent_input("同意", agent_input)
        == "accept_shared_reminder"
    )
    assert agent_runtime._infer_scheduling_intent_and_args_from_agent_input(
        "同意",
        agent_input,
    ) == ("accept_shared_reminder", {"request_id": "srr_1"})


def test_short_confirmation_without_product_notification_stays_non_scheduling():
    assert (
        agent_runtime._infer_scheduling_intent_from_agent_input("确认", _agent_input())
        is None
    )


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
async def test_create_interaction_agent_scheduling_domain_preserves_tool_key_args(
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
                "friend_name": "Bob",
                "reminder_title": "跑步",
                "reminder_time": "2026-05-29T19:30:00",
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
async def test_create_interaction_agent_scheduling_domain_normalizes_common_create_aliases(
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
        captured.update({"intent": intent, "forced_args": forced_args})
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

    await scheduling_domain(
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

    assert captured == {
        "intent": "create_shared_reminder",
        "forced_args": {
            "invitee_name": "Bob",
            "title": "小区操场跑步",
            "fire_at": "2026-05-29T19:30:00",
            "duration_minutes": 40,
        },
    }


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
async def test_create_interaction_agent_scheduling_domain_caches_parallel_calls(
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
    ):
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
        scheduling_domain(intent="accept_shared_reminder: request_id=srr_1"),
        scheduling_domain(intent="accept_shared_reminder: request_id=srr_2"),
    )

    assert calls == 1
    assert first is second
    assert first == envelope | {"intent": "accept_shared_reminder"}


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
