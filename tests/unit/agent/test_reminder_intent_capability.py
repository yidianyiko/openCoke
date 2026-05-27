import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

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


def _run_context() -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="UTC"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
    )


def _executed_result(summary: str = "ok") -> DomainExecutionResult:
    return DomainExecutionResult(
        domain="reminder",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="create",
                ok=True,
                effect="write",
                entity_type="reminder",
                entity_id="rem-1",
                facts={"summary": summary},
            ),
        ),
        reply_contract=ReplyContract(
            intent="confirm_execution",
            prohibited_claims=("not_created",),
        ),
    )


def _failed_result(code: str, summary: str = "") -> DomainExecutionResult:
    return DomainExecutionResult(
        domain="reminder",
        outcome="failed",
        operations=(),
        reply_contract=ReplyContract(
            intent="report_failure",
            prohibited_claims=("reminder_created",),
        ),
        error=DomainError(
            code=code,
            message=summary or code,
            retryable=False,
        ),
    )


def _assert_executed(result: DomainExecutionResult) -> None:
    assert isinstance(result, DomainExecutionResult)
    assert result.domain == "reminder"
    assert result.outcome == "executed"


def _assert_needs_clarification(
    result: DomainExecutionResult,
    *,
    safety_boundary: str | None = None,
    missing_fields: tuple[str, ...] | None = None,
    error_code: str | None = None,
) -> None:
    assert isinstance(result, DomainExecutionResult)
    assert result.domain == "reminder"
    assert result.outcome == "needs_clarification"
    assert result.reply_contract.intent == "ask_clarification"
    assert result.reply_contract.prohibited_claims == ("reminder_created",)
    if safety_boundary is not None:
        assert result.safety_boundary == safety_boundary
    if missing_fields is not None:
        if safety_boundary == "high_frequency_requires_end":
            assert "end_time" in result.missing_fields
        else:
            assert result.missing_fields == missing_fields
    if error_code is not None:
        assert result.error is not None
        assert result.error.code == error_code


def _assert_no_action(result: DomainExecutionResult) -> None:
    assert isinstance(result, DomainExecutionResult)
    assert result.domain == "reminder"
    assert result.outcome == "no_action"
    assert result.operations == ()
    assert result.reply_contract.intent == "direct_answer"


def _assert_failed(result: DomainExecutionResult, code: str) -> None:
    assert isinstance(result, DomainExecutionResult)
    assert result.domain == "reminder"
    assert result.outcome == "failed"
    assert result.error is not None
    assert result.error.code == code


def test_build_reminder_intent_input_carries_dynamic_context_only():
    """v2: input carries dynamic context (time, tz, conversation, history,
    few-shots, user message). It must NOT embed the legacy Workflow
    Boundary rule list — those rules belong in the system prompt and
    duplicating them inflates every per-turn prompt token count, the
    pattern ADR 0004 forbids.
    """
    from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input

    prompt = build_reminder_intent_input(
        "今天有两个事情提醒我，17:57喝水，每天17:58锻炼",
        _run_context(),
    )

    # Structural sections.
    assert "### 当前时间" in prompt
    assert "### 用户时区" in prompt
    assert "### conversation_id" in prompt
    assert "### 最近对话上下文（最近5条）" in prompt
    assert "### Reminder Few-Shot Decisions" in prompt
    assert "### 当前用户消息" in prompt
    # User message preserved verbatim.
    assert "每天17:58锻炼" in prompt
    # Few-shot decisions visible (schema patterns from the few-shot data).
    assert '"schedule_basis": "explicit_occurrences"' in prompt
    assert '"rrule": "FREQ=DAILY"' in prompt
    # Legacy inline Workflow Boundary rules must not return. Spot-check the
    # representative phrases — if a future change reintroduces any of these
    # at the input layer, the diet has been reversed.
    legacy_phrases = (
        "### Workflow Boundary",
        "One-shot deadline wording",
        "Need/intention statements",
        "Pomodoro/tomato timer starts are timed reminder requests",
        "Status-only or referential fragments",
        "Do not use RRULE or explicit_cadence unless the user supplies",
        "Weekly recurrence with listed weekdays must include every listed weekday",
        "manual correction or exception to occurrence times",
    )
    for phrase in legacy_phrases:
        assert phrase not in prompt, (
            f"legacy inline rule re-appeared in build_reminder_intent_input: "
            f"{phrase!r} — move to system prompt or few-shot data"
        )


def test_reminder_intent_input_uses_system_rules_not_weekday_special_case_few_shot():
    from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input

    prompt = build_reminder_intent_input(
        "每个星期一到星期五的晚上22∶12提醒我洗澡",
        _run_context(),
    )

    assert "每个星期一到星期五的晚上22∶12提醒我洗澡" in prompt
    assert "每天22∶12提醒我洗澡" not in prompt
    assert "BYDAY=MO,TU,WE,TH,FR" not in prompt


def test_reminder_intent_input_uses_system_rules_not_trailing_reminder_few_shot():
    from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input

    prompt = build_reminder_intent_input(
        "19点30分，我要开始背诵毛概，请提醒我",
        _run_context(),
    )

    assert "19点30分，我要开始背诵毛概，请提醒我" in prompt
    assert '"title": "背诵毛概"' not in prompt


def test_agent_runtime_reminder_detect_default_timeout_allows_agent_runtime_llm_budget(
    monkeypatch,
):
    from agent.agno_agent.capabilities import reminder_intent

    monkeypatch.delenv(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS", raising=False
    )

    assert reminder_intent._agent_runtime_reminder_detect_timeout_seconds() == 30.0


def test_agent_runtime_reminder_detect_primary_timeout_leaves_user_path_budget(
    monkeypatch,
):
    from agent.agno_agent.capabilities import reminder_intent

    monkeypatch.delenv(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS", raising=False
    )
    assert reminder_intent._agent_runtime_reminder_detect_timeout_seconds() <= 75.0


@pytest.mark.asyncio
async def test_reminder_intent_port_runs_detector_and_executor():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="drink water",
        duration_minutes=60,
    )

    class FakeAgent:
        async def arun(self, *, input, session_state, session_id=None):
            assert "drink water" in input
            assert session_state["user"]["id"] == "user-1"
            return SimpleNamespace(content=decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.intent_type == decision.intent_type
            assert received_decision.action == decision.action
            assert received_decision.title == decision.title
            assert received_decision.duration_minutes == 60
            return _executed_result("已创建提醒：drink water")

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FakeExecutor(),
    ).run("18:00 remind me to drink water", _run_context())

    _assert_executed(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "帮我约一节羽毛球教练课",
        "周日下午 3 点帮我约彭教练",
        "帮我约下周六上午的网球课",
    ],
)
async def test_reminder_intent_port_rejects_unsupported_booking_requests(message):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class FakeAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content=SimpleNamespace(intent_type="discussion", action="")
            )

    class FailingExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("unsupported booking should not write reminders")

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FailingExecutor(),
    ).run(message, _run_context())

    _assert_no_action(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_allows_explicit_reminder_about_booking():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="约彭教练",
        trigger_at="2026-05-31T15:00:00+08:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.title == "约彭教练"
            return _executed_result("已创建提醒：约彭教练")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("周日下午3点提醒我约彭教练", _run_context())

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_duration_minutes_and_stripped_title():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="开会",
        trigger_at="2026-05-07T19:00:00+09:00",
        duration_minutes=60,
    )

    class FakeAgent:
        async def arun(self, *, input, session_state, session_id=None):
            del input, session_state, session_id
            return SimpleNamespace(content=decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            del run_context
            assert received_decision.title == "开会"
            assert received_decision.duration_minutes == 60
            return _executed_result("已创建提醒：开会")

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FakeExecutor(),
    ).run("提醒我明天 19:00 开会一小时", _run_context())

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_normalizes_zero_create_duration_to_point_reminder():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="做平板支撑",
        trigger_at="2026-05-07T08:00:00+09:00",
        duration_minutes=0,
    )

    class FakeAgent:
        async def arun(self, *, input, session_state, session_id=None):
            del input, session_state, session_id
            return SimpleNamespace(content=decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            del run_context
            assert received_decision.title == "做平板支撑"
            assert received_decision.duration_minutes is None
            return _executed_result("已创建提醒：做平板支撑")

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FakeExecutor(),
    ).run("提醒我明天早上 8 点做平板支撑。", _run_context())

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_normalizes_zero_batch_create_duration_to_point_reminder():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(
        intent_type="crud",
        action="batch",
        operations=[
            {"action": "create", "title": "拉伸", "duration_minutes": 0},
            {"action": "create", "title": "喝水", "duration_minutes": None},
        ],
    )

    class FakeAgent:
        async def arun(self, *, input, session_state, session_id=None):
            del input, session_state, session_id
            return SimpleNamespace(content=decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            del run_context
            assert [
                item["duration_minutes"] for item in received_decision.operations
            ] == [
                None,
                None,
            ]
            return _executed_result("已创建提醒")

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FakeExecutor(),
    ).run("提醒我明天早上 8 点拉伸，下午 3 点喝水。", _run_context())

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_command_executor_forwards_duration_minutes_to_tool_entrypoint():
    from agent.agno_agent.adapters.reminder_command_executor import (
        ReminderCommandExecutor,
    )

    captured_kwargs = {}

    def tool_entrypoint(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "ok": True,
            "action": "create",
            "reminder": {
                "id": "rem-1",
                "title": "开会",
                "schedule": {
                    "anchor_at": "2026-05-07T10:00:00+00:00",
                    "local_date": "2026-05-07",
                    "local_time": "19:00:00",
                    "timezone": "Asia/Tokyo",
                    "rrule": None,
                    "duration_minutes": 60,
                },
                "agent_output_target": {
                    "conversation_id": "conv-1",
                    "character_id": "char-1",
                    "route_key": None,
                },
                "created_by_system": "agent",
                "origin": "user",
                "visibility": "visible",
                "fire_mode": "notify",
                "prompt": None,
                "metadata": {},
                "lifecycle_state": "active",
                "next_fire_at": "2026-05-07T10:00:00+00:00",
                "last_fired_at": None,
                "last_event_ack_at": None,
                "last_error": None,
                "created_at": "2026-05-07T10:00:00+00:00",
                "updated_at": "2026-05-07T10:00:00+00:00",
                "completed_at": None,
                "cancelled_at": None,
                "failed_at": None,
            },
            "summary": "已创建提醒：开会（2026-05-07 19:00）",
        }

    executor = ReminderCommandExecutor(
        tool_entrypoint,
        session_state_setter=lambda session_state: None,
    )
    result = executor.execute(
        SimpleNamespace(
            intent_type="crud",
            action="create",
            title="开会",
            trigger_at="2026-05-07T19:00:00+09:00",
            duration_minutes=60,
        ),
        _run_context(),
    )

    assert captured_kwargs["duration_minutes"] == 60
    assert result.outcome == "executed"


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_explicit_list_query_from_detector():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(
        intent_type="query",
        action="list",
        list_from_local_date=None,
        list_to_local_date=None,
        list_title_query=None,
        list_states=["active"],
    )

    class FakeAgent:
        async def arun(self, **_kwargs):
            return SimpleNamespace(content=decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.intent_type == "query"
            assert received_decision.action == "list"
            return DomainExecutionResult(
                domain="reminder",
                outcome="executed",
                operations=(
                    DomainOperationResult(
                        action="list",
                        ok=True,
                        effect="read",
                        entity_type="reminder",
                        entity_id=None,
                        facts={"summary": "- 跑步 @ 2026-05-29T10:30:00"},
                    ),
                ),
                reply_contract=ReplyContract(intent="direct_answer"),
            )

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FakeExecutor(),
    ).run("看看我现在所有的提醒，特别是和 Alice 的那条。", _run_context())

    _assert_executed(result)
    assert result.operations[0].action == "list"


@pytest.mark.asyncio
async def test_reminder_intent_port_extracts_today_scope_for_explicit_list_query():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(
        intent_type="query",
        action="list",
        list_from_local_date="2026-05-06",
        list_to_local_date="2026-05-06",
        list_title_query=None,
        list_states=["active"],
    )

    class FakeAgent:
        async def arun(self, **_kwargs):
            return SimpleNamespace(content=decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.intent_type == "query"
            assert received_decision.action == "list"
            assert received_decision.list_from_local_date == "2026-05-06"
            assert received_decision.list_to_local_date == "2026-05-06"
            assert received_decision.list_title_query is None
            assert received_decision.list_states == ["active"]
            return _executed_result("listed")

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FakeExecutor(),
    ).run("我今天有什么提醒？", _run_context())

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_keeps_general_list_query_unfiltered():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(
        intent_type="query",
        action="list",
        list_title_query=None,
        list_states=["active"],
    )

    class FakeAgent:
        async def arun(self, **_kwargs):
            return SimpleNamespace(content=decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.intent_type == "query"
            assert received_decision.action == "list"
            assert received_decision.list_title_query is None
            return _executed_result("listed")

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FakeExecutor(),
    ).run("列一下我的提醒。", _run_context())

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_extracts_title_query_for_explicit_list_query():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(
        intent_type="query",
        action="list",
        list_title_query="喝水",
        list_states=["active"],
    )

    class FakeAgent:
        async def arun(self, **_kwargs):
            return SimpleNamespace(content=decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.intent_type == "query"
            assert received_decision.action == "list"
            assert received_decision.list_title_query == "喝水"
            assert received_decision.list_states == ["active"]
            return _executed_result("listed")

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FakeExecutor(),
    ).run("我设过哪些喝水提醒？", _run_context())

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_creates_primary_detector_per_invocation(
    monkeypatch,
):
    from agent.agno_agent.capabilities import reminder_intent
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    created_agents = []

    class FakeAgent:
        def __init__(self):
            self.calls = 0

        async def arun(self, *, input, session_state, session_id=None):
            self.calls += 1
            assert "drink water" in input
            assert session_state["conversation"]["id"] == "conv-1"
            assert session_id == "conv-1"
            return SimpleNamespace(
                content=SimpleNamespace(
                    intent_type="crud",
                    action="create",
                    title="drink water",
                )
            )

    def fake_create_reminder_detector():
        agent = FakeAgent()
        created_agents.append(agent)
        return agent

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            return _executed_result(f"已创建提醒：{received_decision.title}")

    monkeypatch.setattr(
        reminder_intent,
        "_create_reminder_detector",
        fake_create_reminder_detector,
    )
    port = ReminderIntentPort(command_executor=FakeExecutor())

    first_result = await port.run("18:00 remind me to drink water", _run_context())
    second_result = await port.run("18:00 remind me to drink water", _run_context())

    _assert_executed(first_result)
    _assert_executed(second_result)
    assert len(created_agents) == 2
    assert [agent.calls for agent in created_agents] == [1, 1]


@pytest.mark.asyncio
async def test_reminder_intent_port_accepts_json_string_detector_content():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    detector_content = """
    {
      "intent_type": "crud",
      "action": "batch",
      "schedule_basis": "explicit_occurrences",
      "schedule_evidence": "17:57喝水，每天17:58锻炼",
      "operations": [
        {
          "action": "create",
          "title": "喝水",
          "trigger_at": "2026-05-07T17:57:00+09:00"
        },
        {
          "action": "create",
          "title": "锻炼",
          "trigger_at": "2026-05-07T17:58:00+09:00",
          "rrule": "FREQ=DAILY"
        }
      ]
    }
    """

    class FakeAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=detector_content)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.intent_type == "crud"
            assert received_decision.action == "batch"
            assert [op.title for op in received_decision.operations] == ["喝水", "锻炼"]
            return _executed_result("已创建提醒：喝水；已创建提醒：锻炼")

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FakeExecutor(),
    ).run("今天17:57提醒我喝水，每天17:58提醒我锻炼", _run_context())

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_fails_when_primary_has_no_executable_decision():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=None)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("primary no-decision path must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("17:57提醒我喝水", _run_context())

    _assert_needs_clarification(
        result,
        error_code="ReminderDetectInvalidDecision",
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_returns_primary_weekday_range_clarification():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_reason": "ambiguous_request",
                }
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("primary clarification must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("每个星期一到星期五的晚上22∶12提醒我洗澡", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="ambiguous_request",
        missing_fields=("target_reminder",),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_returns_primary_clocked_task_clarification():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_reason": "ambiguous_request",
                }
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("primary clarification must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("19点30分，我要开始背诵毛概，请提醒我", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="ambiguous_request",
        missing_fields=("target_reminder",),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_failcloses_single_create_title_before_reminder_verb():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "网球",
                    "trigger_at": "2026-05-18T11:30:00+09:00",
                    "schedule_evidence": "下周一中午12点，提前半小时",
                }
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("unsafe primary title must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("网球帮我设置到下周一中午12点，提前半小时提醒我出门", _run_context())

    _assert_needs_clarification(
        result,
        error_code="ReminderDetectInvalidDecision",
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_primary_timeout_fails_without_retry():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            raise asyncio.TimeoutError

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("timeout path must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("网球帮我设置到下周一中午12点，提前半小时提醒我出门", _run_context())

    _assert_needs_clarification(result, error_code="ReminderDetectTimeout")


@pytest.mark.asyncio
async def test_reminder_intent_port_returns_relative_delay_clarification():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_reason": "ambiguous_request",
                }
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("primary clarification must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("开始写作，请25分钟之后提醒我", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="ambiguous_request",
        missing_fields=("target_reminder",),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_referential_relative_delay_update_from_detector():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="User: 提醒我 30 分钟后喝水。\nCoke: 好嘞，30分钟后提醒你喝水",
        current_time=datetime(2026, 5, 25, 18, 46, tzinfo=UTC),
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content=SimpleNamespace(
                    intent_type="crud",
                    action="update",
                    target_scope="recent_active",
                    new_title="",
                    new_trigger_at="2026-05-25T18:56:00+00:00",
                )
            )

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.action == "update"
            assert received_decision.target_scope == "recent_active"
            assert received_decision.new_trigger_at == "2026-05-25T18:56:00+00:00"
            assert received_decision.new_title in {"", None}
            return _executed_result("已更新提醒：喝水")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("再过 10 分钟提醒我。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_bare_snooze_from_detector():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 18, 46, tzinfo=UTC),
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content=SimpleNamespace(
                    intent_type="crud",
                    action="update",
                    target_scope="recent_active",
                    new_trigger_at="2026-05-25T18:56:00+00:00",
                )
            )

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.action == "update"
            assert received_decision.target_scope == "recent_active"
            assert received_decision.new_trigger_at == "2026-05-25T18:56:00+00:00"
            return _executed_result("已更新提醒")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("再过 10 分钟提醒我。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_referential_delay_update():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="User: 提醒我 30 分钟后喝水。\nCoke: 好嘞。",
        current_time=datetime(2026, 5, 25, 18, 46, tzinfo=UTC),
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content=SimpleNamespace(
                    intent_type="crud",
                    action="update",
                    target_scope="recent_active",
                    new_trigger_at="2026-05-25T18:56:00+00:00",
                )
            )

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.action == "update"
            assert received_decision.target_scope == "recent_active"
            assert received_decision.new_trigger_at == "2026-05-25T18:56:00+00:00"
            return _executed_result("已更新提醒：喝水")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("再过 10 分钟提醒我。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_derives_title_time_selector_for_update():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 19, 37, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="update",
        target_title="喝水",
        target_scope="recent_active",
        new_trigger_at="2026-05-27T16:00:00+08:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.target_title == "喝水"
            assert getattr(received_decision, "target_local_time", None) is None
            assert received_decision.target_scope == "recent_active"
            assert received_decision.new_trigger_at == "2026-05-27T16:00:00+08:00"
            return _executed_result("已更新提醒：喝水")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("把那个喝水提醒改成下午 4 点。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_update_with_history_selector():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="User: 提醒我明天 8 点喝水。\nCoke: 好嘞。",
        current_time=datetime(2026, 5, 25, 19, 50, tzinfo=UTC),
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content=SimpleNamespace(
                    intent_type="crud",
                    action="update",
                    target_title="喝水",
                    target_local_time="08:00",
                    target_scope="recent_active",
                    new_title="吃药",
                )
            )

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.action == "update"
            assert received_decision.target_title == "喝水"
            assert received_decision.target_local_time == "08:00"
            assert received_decision.target_scope == "recent_active"
            assert received_decision.new_title == "吃药"
            return _executed_result("已更新提醒：吃药")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("把那个 8 点的提醒改成「吃药」。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_update_decision():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 19, 50, tzinfo=UTC),
    )
    detector_decision = SimpleNamespace(
        intent_type="crud",
        action="update",
        reminder_id="",
        target_local_time="08:00",
        target_scope="recent_active",
        new_title="吃药",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=detector_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.action == "update"
            assert received_decision.reminder_id == ""
            assert received_decision.target_local_time == "08:00"
            assert received_decision.target_scope == "recent_active"
            assert received_decision.new_title == "吃药"
            return _executed_result("已更新提醒：吃药")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run(
        "（2026年05月26日04时26分 Alice Personal Reminder 25202445发来了文本消息）把那个 8 点的提醒改成「吃药」。",
        run_context,
    )

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_daily_create_decision():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 20, 30, tzinfo=UTC),
    )
    detector_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="写日记",
        trigger_at="2026-05-26T08:00:00+08:00",
        rrule="FREQ=DAILY",
        schedule_basis="explicit_cadence",
        schedule_evidence="每天",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=detector_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.action == "create"
            assert received_decision.title == "写日记"
            assert received_decision.trigger_at == "2026-05-26T08:00:00+08:00"
            assert received_decision.rrule == "FREQ=DAILY"
            return _executed_result("已创建提醒：写日记")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run(
        "（2026年05月26日04时30分 Alice Personal Reminder 25202445发来了文本消息）每天 8 点提醒我写日记。",
        run_context,
    )

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_weekly_create_decision():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 20, 40, tzinfo=UTC),
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content=SimpleNamespace(
                    intent_type="crud",
                    action="create",
                    title="开会",
                    trigger_at="2026-05-27T14:00:00+08:00",
                    rrule="FREQ=WEEKLY;BYDAY=WE",
                    schedule_basis="explicit_cadence",
                    schedule_evidence="每周三",
                )
            )

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.action == "create"
            assert received_decision.title == "开会"
            assert received_decision.trigger_at == "2026-05-27T14:00:00+08:00"
            assert received_decision.rrule == "FREQ=WEEKLY;BYDAY=WE"
            return _executed_result("已创建提醒：开会")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("每周三 14:00 提醒我开会。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_biweekly_create_decision():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 20, 40, tzinfo=UTC),
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content=SimpleNamespace(
                    intent_type="crud",
                    action="create",
                    title="复盘",
                    trigger_at="2026-06-01T10:00:00+08:00",
                    rrule="FREQ=WEEKLY;INTERVAL=2;BYDAY=MO",
                    schedule_basis="explicit_cadence",
                    schedule_evidence="每隔一周周一",
                )
            )

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.action == "create"
            assert received_decision.title == "复盘"
            assert received_decision.trigger_at == "2026-06-01T10:00:00+08:00"
            assert received_decision.rrule == "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"
            return _executed_result("已创建提醒：复盘")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("每隔一周周一 10 点提醒我复盘。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_monthly_day_create_decision():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 20, 40, tzinfo=UTC),
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content=SimpleNamespace(
                    intent_type="crud",
                    action="create",
                    title="交房租",
                    trigger_at="2026-06-01T09:00:00+08:00",
                    rrule="FREQ=MONTHLY",
                    schedule_basis="explicit_cadence",
                    schedule_evidence="每月 1 号",
                )
            )

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.action == "create"
            assert received_decision.title == "交房租"
            assert received_decision.trigger_at == "2026-06-01T09:00:00+08:00"
            assert received_decision.rrule == "FREQ=MONTHLY"
            return _executed_result("已创建提醒：交房租")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("每月 1 号 09:00 提醒我交房租。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_preserves_long_create_title_from_user_text():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    long_title = "喝水" * 100
    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 20, 40, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title=long_title,
        trigger_at="2026-05-27T09:00:00+08:00",
        rrule="",
        schedule_basis="explicit_time",
        schedule_evidence="明天 9 点",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.action == "create"
            assert received_decision.title == long_title
            assert len(received_decision.title) == 200
            return _executed_result(f"已创建提醒：{long_title}")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run(f"明天 9 点提醒我 {long_title}。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_repairs_weekday_recurrence_update():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 20, 38, tzinfo=UTC),
    )
    detector_decision = SimpleNamespace(
        intent_type="crud",
        action="update",
        reminder_id="",
        target_local_time="08:00",
        target_rrule="FREQ=DAILY",
        rrule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=detector_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.action == "update"
            assert received_decision.reminder_id == ""
            assert received_decision.target_local_time == "08:00"
            assert received_decision.target_rrule == "FREQ=DAILY"
            assert received_decision.rrule == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
            return _executed_result("已更新提醒：喝水")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("把每天 8 点的提醒改成只有工作日。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_update_time_from_text():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 20, 37, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="update",
        target_title="喝水",
        new_trigger_at="2026-05-26T16:00:00+08:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.new_trigger_at == "2026-05-26T16:00:00+08:00"
            return _executed_result("已更新提醒：喝水")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("把那个喝水提醒改成下午 4 点。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_rejects_single_occurrence_skip_without_write():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_reason": "ambiguous_request",
                }
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=object(),
    ).run("这周的不用了。", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="ambiguous_request",
        missing_fields=("target_reminder",),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_clears_spurious_target_date_for_bare_time_update():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 19, 37, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="update",
        target_local_date=None,
        target_local_time="08:00",
        new_title="吃药",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.target_local_date is None
            assert received_decision.target_local_time == "08:00"
            assert received_decision.new_title == "吃药"
            return _executed_result("已更新提醒：吃药")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("把那个 8 点的提醒改成「吃药」。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_tomorrow_create_date():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 20, 17, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="吃药",
        trigger_at="2026-05-27T09:00:00+08:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.trigger_at == "2026-05-27T09:00:00+08:00"
            return _executed_result("已创建提醒：吃药")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("提醒我明天 9:00 吃药。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_derives_daily_rrule_update_selector():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="update",
        reminder_id="",
        target_rrule="FREQ=DAILY",
        target_local_time="08:00",
        rrule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            del run_context
            assert received_decision.reminder_id in {"", None}
            assert received_decision.target_rrule == "FREQ=DAILY"
            assert received_decision.target_local_time == "08:00"
            assert received_decision.rrule == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
            return _executed_result("已更新提醒：喝水")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("把每天 8 点的提醒改成只有工作日。", _run_context())

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_derives_complete_selector_from_today_title():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 19, 40, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="complete",
        reminder_id="",
        target_title="吃药",
        target_local_date="2026-05-26",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.reminder_id in {"", None}
            assert received_decision.target_title == "吃药"
            assert received_decision.target_local_date == "2026-05-26"
            return _executed_result("已完成提醒：吃药")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("完成今天的吃药提醒。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_explicit_workday_create():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 19, 40, tzinfo=UTC),
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content=SimpleNamespace(
                    intent_type="crud",
                    action="create",
                    title="喝水",
                    trigger_at="2026-05-26T08:00:00+08:00",
                    rrule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
                    schedule_basis="explicit_cadence",
                    schedule_evidence="工作日",
                )
            )

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.action == "create"
            assert received_decision.title == "喝水"
            assert received_decision.trigger_at == "2026-05-26T08:00:00+08:00"
            assert received_decision.rrule == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
            return _executed_result("已创建提醒：喝水")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("工作日早 8 点提醒我喝水。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_derives_daily_cancel_selector():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="cancel",
        target_rrule="FREQ=DAILY",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            del run_context
            assert received_decision.target_rrule == "FREQ=DAILY"
            return _executed_result("已取消提醒：写日记")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("把每天的提醒停掉。", _run_context())

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_derives_recent_history_title_for_daily_cancel():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="User: 每天 8 点提醒我写日记。\nCoke: 好嘞。",
        current_time=datetime(2026, 5, 25, 19, 54, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="cancel",
        target_title="写日记",
        target_rrule="FREQ=DAILY",
        target_scope="recent_active",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.target_title == "写日记"
            assert received_decision.target_rrule == "FREQ=DAILY"
            assert received_decision.target_scope == "recent_active"
            return _executed_result("已取消提醒：写日记")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("把每天的提醒停掉。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_clarifies_next_whole_hour_misread_as_cadence():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "画画",
                    "trigger_at": "2026-05-06T11:00:00+00:00",
                    "rrule": "FREQ=HOURLY",
                    "schedule_basis": "explicit_cadence",
                    "schedule_evidence": "下个整点",
                }
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("unsafe hourly cadence must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("画画，下个整点再叫我吧", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="high_frequency_requires_end",
        missing_fields=("end_time",),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_rejects_when_multiple_scheduled_clauses_are_dropped():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "询问当天规划",
                    "trigger_at": "2026-05-12T07:00:00+09:00",
                    "rrule": "FREQ=DAILY",
                    "schedule_basis": "explicit_cadence",
                    "schedule_evidence": "每天早上7点",
                }
            )

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            raise AssertionError("partial multiple-schedule write must not execute")

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run(
        "你能每天早上7点询问我当天的规划吗？最后在每天晚上23.00告诉我，我今天完成了哪些任务",
        _run_context(),
    )

    _assert_needs_clarification(result, error_code="ReminderDetectInvalidDecision")
    assert executor.received == []


@pytest.mark.asyncio
async def test_reminder_intent_port_rejects_back_reference_routine_time_drop():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "起床",
                    "trigger_at": "2026-05-12T07:15:00+09:00",
                    "schedule_basis": "explicit_occurrences",
                    "schedule_evidence": "7:15起床",
                }
            )

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            raise AssertionError("partial back-reference schedule must not execute")

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run(
        "我一般7:15起床，23:00睡觉。我需要你在上述这些时间提醒我",
        _run_context(),
    )

    _assert_needs_clarification(result, error_code="ReminderDetectInvalidDecision")
    assert executor.received == []


@pytest.mark.asyncio
async def test_reminder_intent_port_blocks_unbounded_high_frequency_batch():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "batch",
                    "schedule_basis": "explicit_cadence",
                    "schedule_evidence": "每小时",
                    "operations": [
                        {
                            "action": "create",
                            "title": "冥想",
                            "trigger_at": "2026-05-10T17:00:00+09:00",
                            "rrule": "FREQ=HOURLY",
                        },
                        {
                            "action": "create",
                            "title": "冥想",
                            "trigger_at": "2026-05-10T18:00:00+09:00",
                            "rrule": "FREQ=HOURLY",
                        },
                    ],
                }
            )

    class FailingExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("unbounded high-frequency cadence must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FailingExecutor(),
    ).run("每小时提醒我一次冥想，从下午五点开始", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="high_frequency_requires_end",
        missing_fields=("end_time",),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_blocks_detector_unbounded_high_frequency_batch():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "batch",
                    "schedule_basis": "explicit_cadence",
                    "schedule_evidence": "每小时",
                    "operations": [
                        {
                            "action": "create",
                            "title": "冥想",
                            "trigger_at": "2026-05-10T15:00:00+09:00",
                            "rrule": "FREQ=HOURLY",
                        },
                        {
                            "action": "create",
                            "title": "冥想",
                            "trigger_at": "2026-05-10T16:00:00+09:00",
                            "rrule": "FREQ=HOURLY",
                        },
                    ],
                }
            )

    class FailingExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("input-level high-frequency cadence must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FailingExecutor(),
    ).run("冥想可以每个小时提醒我做一次冥想吗", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="high_frequency_requires_end",
        missing_fields=("end_time",),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_blocks_detector_minutely_cadence_batch_without_end():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "batch",
                    "schedule_basis": "explicit_cadence",
                    "schedule_evidence": "每分钟",
                    "operations": [
                        {
                            "action": "create",
                            "title": "正念冥想",
                            "trigger_at": "2026-05-10T16:00:00+09:00",
                            "rrule": "FREQ=MINUTELY",
                        },
                        {
                            "action": "create",
                            "title": "正念冥想",
                            "trigger_at": "2026-05-10T17:00:00+09:00",
                            "rrule": "FREQ=MINUTELY",
                        },
                    ],
                }
            )

    class FailingExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("unbounded minutely cadence must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FailingExecutor(),
    ).run("每个小时一次提醒我正念冥想", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="high_frequency_requires_end",
        missing_fields=("end_time",),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_blocks_unbounded_hourly_rrule():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "冥想",
                    "trigger_at": "2026-05-10T17:00:00+09:00",
                    "rrule": "FREQ=HOURLY",
                    "schedule_basis": "explicit_cadence",
                    "schedule_evidence": "每小时",
                }
            )

    class FailingExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("unbounded hourly recurrence must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FailingExecutor(),
    ).run("每小时提醒我一次冥想，从下午五点开始", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="high_frequency_requires_end",
        missing_fields=("trigger_at", "end_time"),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_clarifies_bounded_cadence_with_deadline_loss():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "打卡",
                    "trigger_at": "2026-05-10T20:00:00+09:00",
                    "rrule": "FREQ=HOURLY",
                    "schedule_basis": "explicit_cadence",
                    "schedule_evidence": "每小时",
                }
            )

    class FakeExecutor:
        def __init__(self):
            self.decisions = []

        def execute(self, received_decision, run_context):
            self.decisions.append(received_decision)
            return _executed_result("ok")

    executor = FakeExecutor()

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run("每小时打卡，到晚上8点", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="high_frequency_requires_end",
        missing_fields=("end_time",),
    )
    assert executor.decisions == []


@pytest.mark.asyncio
async def test_reminder_intent_port_returns_executor_failure_without_recurring_retry():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "打卡",
                    "trigger_at": "2026-05-10T20:00:00+09:00",
                    "rrule": "FREQ=HOURLY",
                    "deadline_at": "2026-05-10T20:00:00+09:00",
                    "schedule_basis": "explicit_cadence",
                    "schedule_evidence": "每小时",
                }
            )

    class FakeExecutor:
        def __init__(self):
            self.decisions = []

        def execute(self, received_decision, run_context):
            self.decisions.append(received_decision)
            if len(self.decisions) == 1:
                return _failed_result(
                    "InvalidSchedule",
                    "创建提醒失败：Recurring reminder schedule has no future fire time",
                )
            return _executed_result("ok")

    executor = FakeExecutor()

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run("每小时打卡，到晚上8点", _run_context())

    _assert_failed(result, "InvalidSchedule")
    assert len(executor.decisions) == 1


@pytest.mark.asyncio
async def test_reminder_intent_port_blocks_detector_unbounded_hourly_rrule_without_end():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "冥想",
                    "trigger_at": "2026-05-10T15:00:00+09:00",
                    "rrule": "FREQ=HOURLY",
                    "schedule_basis": "explicit_cadence",
                    "schedule_evidence": "每小时",
                }
            )

    class FailingExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("unbounded hourly rrule must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FailingExecutor(),
    ).run("冥想可以每个小时提醒我做一次冥想吗", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="high_frequency_requires_end",
        missing_fields=("end_time",),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_returns_primary_clarification_without_retrying():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_reason": "ambiguous_request",
                }
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.action == "create"
            assert received_decision.title == "学英语"
            return _executed_result("已创建提醒：学英语")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("你可以没太难18:00 提醒我学英语么", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="ambiguous_request",
        missing_fields=("target_reminder",),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_returns_primary_clarification_directly():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_reason": "ambiguous_request",
                }
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
    ).run("提醒我下周二去杭州", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="ambiguous_request",
        missing_fields=("target_reminder",),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_failcloses_when_title_drops_quoted_content():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "思考一个问题：工作应该去做",
                    "trigger_at": "2026-05-08T10:40:00+09:00",
                }
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.title == "思考：工作应该去做“非我不可”的事情"
            return _executed_result("已创建提醒：思考：工作应该去做“非我不可”的事情")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run(
        "另外10:40提醒思考一个问题：工作应该去做“非我不可”的事情",
        _run_context(),
    )

    _assert_needs_clarification(result, error_code="ReminderDetectInvalidDecision")


@pytest.mark.asyncio
async def test_reminder_intent_port_failcloses_when_day_of_month_is_dropped():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "给医院打电话预约手术",
                    "trigger_at": "2026-05-12T09:00:00+00:00",
                }
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.trigger_at == "2026-05-22T09:00:00+00:00"
            return _executed_result("已创建提醒：给医院打电话预约手术")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run(
        "然后再book一个22号早上9点提醒我给医院打电话预约手术",
        _run_context(),
    )

    _assert_needs_clarification(result, error_code="ReminderDetectInvalidDecision")


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_past_bare_clock_trigger():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="离开时手机",
        trigger_at="2026-05-06T11:00:00+00:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            assert received_decision.trigger_at == "2026-05-06T11:00:00+00:00"
            return _executed_result("已创建提醒：离开时手机")

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run(
        "（2026年05月10日14时44分 reminder-e2e-user-18发来了文本消息）十一点开始提醒我离开时手机",
        _run_context(),
    )

    assert len(executor.received) == 1
    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_weekday_bare_clock_date():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 13, 7, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="喝水",
        trigger_at="2026-06-01T09:00:00+08:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.trigger_at == "2026-06-01T09:00:00+08:00"
            return _executed_result("已创建提醒：喝水")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("等一下，先取消刚才说的，改成只设周一 9 点提醒", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_future_bare_clock_update_time():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="User: 提醒我明天早上 7 点跑步 30 分钟。",
        current_time=datetime(2026, 5, 25, 0, 36, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="update",
        keyword="跑步",
        new_trigger_at="2026-05-26T07:30:00+09:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, received_context):
            self.received.append(received_decision)
            assert received_context is run_context
            assert received_decision.new_trigger_at == "2026-05-26T07:30:00+09:00"
            return _executed_result("已更新提醒：跑步 30 分钟")

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run("把刚才那个跑步提醒改到早上 7 点半。", run_context)

    assert len(executor.received) == 1
    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_bare_numeric_clock_local_time():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 11, 10, 45, 17, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="回家开会",
        trigger_at="2026-05-12T09:20:00+09:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.trigger_at == "2026-05-12T09:20:00+09:00"
            return _executed_result("已创建提醒：回家开会")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("9:20 提醒我回家开会", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_same_hour_bare_colon_as_pm():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 11, 7, 35, 14, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="吃饭",
        trigger_at="2026-05-11T16:37:00+09:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.trigger_at == "2026-05-11T16:37:00+09:00"
            return _executed_result("已创建提醒：吃饭")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("4:37提醒我吃饭", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_explicit_clock_minutes():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 11, 3, 7, 20, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="起床",
        trigger_at="2026-05-11T13:50:00+09:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.trigger_at == "2026-05-11T13:50:00+09:00"
            return _executed_result("已创建提醒：起床")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("下午 1 点 50 分提醒我起床", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_minute_after_chinese_hour_marker():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 11, 22, 38, 56, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="内科横向刷题结束",
        trigger_at="2026-05-12T09:10:00+09:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.trigger_at == "2026-05-12T09:10:00+09:00"
            return _executed_result("已创建提醒：内科横向刷题结束")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("9点10提醒我内科横向刷题结束", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_zero_prefixed_chinese_minutes():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 11, 8, 0, 0, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="出门",
        trigger_at="2026-05-11T17:03:00+09:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.trigger_at == "2026-05-11T17:03:00+09:00"
            return _executed_result("已创建提醒：出门")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("下午五点零三分提醒我出门", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_guo_minute_phrase():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 11, 8, 3, 47, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="出门",
        trigger_at="2026-05-11T17:05:00+09:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.trigger_at == "2026-05-11T17:05:00+09:00"
            return _executed_result("已创建提醒：出门")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("五点过五分提醒我出门", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_minus_minute_phrase():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 11, 8, 5, 13, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="出门",
        trigger_at="2026-05-11T17:55:00+09:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.trigger_at == "2026-05-11T17:55:00+09:00"
            return _executed_result("已创建提醒：出门")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("六点差五分的时候提醒我一下出门", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_every_night_as_pm_clock():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 11, 14, 59, 21, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="洗漱",
        trigger_at="2026-05-12T22:30:00+09:00",
        rrule="FREQ=DAILY",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.trigger_at == "2026-05-12T22:30:00+09:00"
            return _executed_result("已创建提醒：洗漱")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("设置一个每晚10:30洗漱的提醒", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_relative_delay_trigger():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 11, 6, 31, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="起来休息，倒水喝",
        trigger_at="2026-05-11T06:56:00+00:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.trigger_at == "2026-05-11T06:56:00+00:00"
            return _executed_result("已创建提醒：起来休息，倒水喝")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("25分钟后提醒我起来休息，倒水喝", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_prefixed_min_relative_delay():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 11, 2, 20, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="check on 我的结论",
        trigger_at="2026-05-11T02:40:00+00:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.trigger_at == "2026-05-11T02:40:00+00:00"
            return _executed_result("已创建提醒：check on 我的结论")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("yes, 过20min提醒我，check on 我的结论", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_timer_phrase_relative_delay():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 11, 12, 37, 55, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="起来休息，喝水",
        trigger_at="2026-05-11T13:02:55+00:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.trigger_at == "2026-05-11T13:02:55+00:00"
            return _executed_result("已创建提醒：起来休息，喝水")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("开始25分钟计时，计时结束后提醒我起来休息，喝水", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_future_batch_operations():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="0点一次，0点半一次，2点一次",
        operations=[
            SimpleNamespace(
                action="create",
                title="完成学习任务打卡",
                trigger_at="2026-05-07T00:00:00+00:00",
            ),
            SimpleNamespace(
                action="create",
                title="完成学习任务打卡",
                trigger_at="2026-05-07T00:30:00+00:00",
            ),
            SimpleNamespace(
                action="create",
                title="完成学习任务打卡",
                trigger_at="2026-05-06T02:00:00+00:00",
            ),
        ],
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return _executed_result("已创建提醒：完成学习任务打卡")

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run("0点一次，0点半一次，2点一次，提醒我完成学习任务打卡", _run_context())

    _assert_executed(result)
    assert [op.trigger_at for op in executor.received[0].operations] == [
        "2026-05-07T00:00:00+00:00",
        "2026-05-07T00:30:00+00:00",
        "2026-05-06T02:00:00+00:00",
    ]


@pytest.mark.asyncio
async def test_reminder_intent_port_allows_vague_date_with_explicit_clock():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="喝水",
        trigger_at="2026-05-07T08:00:00+00:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return _executed_result("已创建提醒：喝水")

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run("明早 8 点提醒我喝水。", _run_context())

    assert len(executor.received) == 1
    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_explicit_seconds_from_user_text():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="喝水",
        trigger_at="2026-05-06T06:18:45+00:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_decision.trigger_at == "2026-05-06T06:18:45+00:00"
            return _executed_result("已创建提醒：喝水")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("6 点 18 分 45 秒提醒我喝水。", _run_context())

    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_does_not_reject_next_year_date_as_past():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    run_context = AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="User", timezone="Asia/Shanghai"),
        character=TrustedCharacterContext(id="char-1", nickname="Coke"),
        conversation=TrustedConversationContext(
            id="conv-1", platform="business", route_key=None
        ),
        relation=TrustedRelationContext(uid="user-1", cid="char-1"),
        platform="business",
        recent_chat_history="",
        current_time=datetime(2026, 5, 25, 22, 30, tzinfo=UTC),
    )
    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="写年度计划",
        trigger_at="2027-01-01T00:00:00+08:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_context is run_context
            assert received_decision.trigger_at == "2027-01-01T00:00:00+08:00"
            return _executed_result("已创建提醒：写年度计划")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("明年 1 月 1 日 0:00 提醒我写年度计划。", run_context)

    _assert_executed(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason,expected_boundary,expected_missing",
    [
        ("date_only_missing_time", "date_only_missing_time", ("trigger_at",)),
        ("ambiguous_time_range", "ambiguous_time_range", ("trigger_at",)),
        (
            "completion_condition_missing_time",
            "completion_condition_missing_time",
            ("trigger_at",),
        ),
        ("status_only_content", "missing_reminder_content", ("title",)),
        ("deadline_without_trigger", "deadline_without_trigger", ("trigger_at",)),
        ("advance_offset_missing", "advance_offset_missing", ("advance_offset",)),
        (
            "high_frequency_requires_end",
            "high_frequency_requires_end",
            ("trigger_at", "end_time"),
        ),
        ("missing_reminder_content", "missing_reminder_content", ("title",)),
        ("ambiguous_request", "ambiguous_request", ("target_reminder",)),
    ],
)
async def test_reminder_intent_port_routes_clarification_reason_to_template(
    reason,
    expected_boundary,
    expected_missing,
):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content=SimpleNamespace(
                    intent_type="clarify",
                    action="",
                    clarification_reason=reason,
                )
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("clarify must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("ignored — routing test", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary=expected_boundary,
        missing_fields=expected_missing,
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_batch_operations_after_reminder_verb():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="明天6点半叫我起床",
        operations=[
            SimpleNamespace(
                action="create",
                title="起床",
                trigger_at="2026-05-11T06:30:00+09:00",
            ),
        ],
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return _executed_result("已创建提醒：起床")

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run("1点睡觉，明天6点半叫我起床", _run_context())

    _assert_executed(result)
    assert len(executor.received) == 1
    assert [op.title for op in executor.received[0].operations] == ["起床"]


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_batch_operation_with_local_schedule_evidence():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="明天；晚上9:00",
        operations=[
            SimpleNamespace(
                action="create",
                title="收起全天学习的作业",
                trigger_at="2026-05-12T21:00:00+09:00",
            ),
        ],
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return _executed_result("已创建提醒：收起全天学习的作业")

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run("明天除了提醒任务之后，到晚上9:00要收起我全天学习的作业哦", _run_context())

    _assert_executed(result)
    assert len(executor.received) == 1
    assert [op.title for op in executor.received[0].operations] == [
        "收起全天学习的作业"
    ]


@pytest.mark.asyncio
async def test_reminder_intent_port_returns_clarification_for_mixed_clocked_clause():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_reason": "ambiguous_request",
                }
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.title == "收起全天学习的作业"
            return _executed_result("已创建提醒：收起全天学习的作业")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("明天除了提醒任务之后，到晚上9:00要收起我全天学习的作业哦", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="ambiguous_request",
        missing_fields=("target_reminder",),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_governed_cadence_batch():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_cadence",
        schedule_evidence="每小时打卡持续到20点",
        operations=[
            SimpleNamespace(
                action="create",
                title="打卡",
                trigger_at="2026-05-11T15:00:00+09:00",
                rrule="FREQ=HOURLY;UNTIL=20260511T110000Z",
            ),
        ],
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return _executed_result("已创建提醒：打卡")

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run(
        "帮我记住今天任务，15点起床，开始帮我每小时打卡持续到20点，跑步，20点睡觉",
        _run_context(),
    )

    _assert_executed(result)
    assert len(executor.received) == 1
    assert [op.title for op in executor.received[0].operations] == ["打卡"]


@pytest.mark.asyncio
async def test_reminder_intent_port_routes_detector_cadence_batch_without_inventory():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_cadence",
        schedule_evidence="开始帮我每小时打卡，打卡持续到20点",
        operations=[
            SimpleNamespace(
                action="create",
                title="打卡",
                trigger_at="2026-05-11T15:00:00+09:00",
                rrule="FREQ=HOURLY;UNTIL=20260511T110000Z",
            ),
        ],
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return _executed_result("已创建提醒：打卡")

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run(
        (
            "帮我记住今天任务，以这个版本为准\n\n"
            "15点-16点\n起床，开始帮我每小时打卡，打卡持续到20点\n跑步3公里"
        ),
        _run_context(),
    )

    _assert_executed(result)
    assert len(executor.received) == 1
    assert [op.title for op in executor.received[0].operations] == ["打卡"]


@pytest.mark.asyncio
async def test_reminder_intent_port_fails_invalid_structured_output_without_second_detector():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content="ReminderDetectInvalidStructuredOutput")

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return _executed_result("已创建提醒：打卡")

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run(
        "15点开始帮我每小时打卡，打卡持续到20点",
        _run_context(),
    )

    _assert_needs_clarification(result, error_code="ReminderDetectInvalidDecision")
    assert executor.received == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "input_text",
    [
        "All good, no reminders pls",
        "谢谢闹钟",
        "我以为把你纯当闹钟就行了……没想到还得回复你你才会保持提醒……",
        "可以呀，明天测试多线程能力，和提醒功能增强",
        "今天晚上8点我要看电影",
    ],
)
async def test_reminder_intent_port_routes_intent_discussion_to_no_action(input_text):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(
                content=SimpleNamespace(
                    intent_type="discussion",
                    action="",
                )
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("discussion intent must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run(input_text, _run_context())

    _assert_no_action(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_does_not_retry_feature_work_discussion():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content={"intent_type": "discussion", "action": ""})

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
    ).run(
        "可以呀，明天测试多线程能力，和提醒功能增强",
        _run_context(),
    )

    _assert_no_action(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_clarifies_bounded_cadence_deadline_loss_without_retry():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="跑步",
        trigger_at="2026-05-10T20:00:00+09:00",
        rrule="FREQ=DAILY",
        schedule_basis="explicit_cadence",
        schedule_evidence="每天晚上八点",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return _executed_result("已创建提醒：跑步")

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run("12月7号前，每天晚上八点提醒我跑步", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="high_frequency_requires_end",
        missing_fields=("end_time",),
    )
    assert executor.received == []


@pytest.mark.asyncio
async def test_reminder_intent_port_does_not_treat_sleep_before_as_deadline_loss():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="吃药",
        trigger_at="2026-05-06T22:00:00+00:00",
        duration_minutes=60,
        rrule="FREQ=DAILY",
        schedule_basis="explicit_cadence",
        schedule_evidence="每天睡前",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return _executed_result("已创建提醒：吃药")

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=executor,
    ).run("每天睡前提醒我吃药", _run_context())

    assert len(executor.received) == 1
    assert executor.received[0].title == primary_decision.title
    assert executor.received[0].duration_minutes == 60
    _assert_executed(result)


@pytest.mark.asyncio
async def test_reminder_intent_port_failcloses_bounded_cadence_deadline_loss():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="跑步",
        trigger_at="2026-05-10T20:00:00+09:00",
        rrule="FREQ=DAILY",
        schedule_basis="explicit_cadence",
        schedule_evidence="每天晚上八点",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("unsafe unbounded recurrence must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("12月7号前，每天晚上八点提醒我跑步", _run_context())

    _assert_needs_clarification(
        result,
        safety_boundary="high_frequency_requires_end",
        missing_fields=("end_time",),
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_failcloses_when_primary_output_is_invalid():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            return SimpleNamespace(content="Operation cancelled by user")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
    ).run("帮我设置一个本周六订蛋糕的提醒，预定链接是：#小程序://x", _run_context())

    _assert_needs_clarification(result, error_code="ReminderDetectInvalidDecision")


@pytest.mark.asyncio
async def test_reminder_intent_port_fails_when_primary_detector_times_out(
    monkeypatch,
):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    monkeypatch.setenv("COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS", "0.01")

    class PrimaryAgent:
        async def arun(self, *, input, session_state, session_id=None):
            await asyncio.sleep(60)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.action == "create"
            return _executed_result("已创建提醒：喝水")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FakeExecutor(),
    ).run("17:57提醒我喝水", _run_context())

    _assert_needs_clarification(result, error_code="ReminderDetectTimeout")
