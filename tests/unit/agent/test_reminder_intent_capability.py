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


def test_build_reminder_intent_input_includes_legacy_few_shot_decisions():
    from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input

    prompt = build_reminder_intent_input(
        "今天有两个事情提醒我，17:57喝水，每天17:58锻炼",
        _run_context(),
    )

    assert "### Reminder Few-Shot Decisions" in prompt
    assert '"schedule_basis": "explicit_occurrences"' in prompt
    assert '"schedule_evidence"' in prompt
    assert '"rrule": "FREQ=DAILY"' in prompt
    assert "### 当前用户消息" in prompt
    assert "### Active Pending Workflow" not in prompt
    assert "每天17:58锻炼" in prompt


def test_build_reminder_intent_input_includes_active_pending_workflow_from_metadata():
    from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input

    context = _run_context()
    context = type(context)(
        user=context.user,
        character=context.character,
        conversation=context.conversation,
        relation=context.relation,
        platform=context.platform,
        recent_chat_history=context.recent_chat_history,
        current_time=context.current_time,
        runtime_metadata={
            "pending_workflow": {
                "revision": 2,
                "document": {"id": "workflow_1", "status": "awaiting_user"},
            }
        },
    )

    prompt = build_reminder_intent_input("从现在到晚上七点", context)

    assert "### Active Pending Workflow" in prompt
    assert '"revision": 2' in prompt
    assert '"id": "workflow_1"' in prompt


def test_build_reminder_intent_input_serializes_datetime_workflow_metadata():
    from agent.agno_agent.prompts.reminder_intent import build_reminder_intent_input

    context = _run_context()
    context = type(context)(
        user=context.user,
        character=context.character,
        conversation=context.conversation,
        relation=context.relation,
        platform=context.platform,
        recent_chat_history=context.recent_chat_history,
        current_time=context.current_time,
        runtime_metadata={
            "pending_workflow": {
                "revision": 2,
                "loaded_at": datetime(2026, 5, 6, 1, 30, tzinfo=UTC),
                "document": {
                    "id": "workflow_1",
                    "origin": {
                        "created_at": datetime(2026, 5, 6, 1, 0, tzinfo=UTC)
                    },
                },
            }
        },
    )

    prompt = build_reminder_intent_input("从现在到晚上七点", context)

    assert '"loaded_at": "2026-05-06T01:30:00+00:00"' in prompt
    assert '"created_at": "2026-05-06T01:00:00+00:00"' in prompt


def test_agent_runtime_reminder_detect_default_timeout_allows_agent_runtime_llm_budget(
    monkeypatch,
):
    from agent.agno_agent.capabilities import reminder_intent

    monkeypatch.delenv(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS", raising=False
    )

    assert reminder_intent._agent_runtime_reminder_detect_timeout_seconds() == 45.0


def test_agent_runtime_reminder_detect_timeout_retry_has_short_default_budget(
    monkeypatch,
):
    from agent.agno_agent.capabilities import reminder_intent

    monkeypatch.delenv(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_RETRY_SECONDS",
        raising=False,
    )

    assert (
        reminder_intent._agent_runtime_reminder_detect_timeout_retry_seconds() == 20.0
    )


def test_agent_runtime_reminder_detect_retry_has_short_default_budget(monkeypatch):
    from agent.agno_agent.capabilities import reminder_intent

    monkeypatch.delenv(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS", raising=False
    )

    assert (
        reminder_intent._agent_runtime_reminder_detect_retry_timeout_seconds() == 20.0
    )


@pytest.mark.asyncio
async def test_reminder_intent_port_runs_detector_and_executor():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(intent_type="crud", action="create", title="drink water")

    class FakeAgent:
        async def arun(self, *, input, session_state):
            assert "drink water" in input
            assert session_state["user"]["id"] == "user-1"
            return SimpleNamespace(content=decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision is decision
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：drink water"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FakeExecutor(),
    ).run("18:00 remind me to drink water", _run_context())

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：drink water"


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
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=detector_content)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.intent_type == "crud"
            assert received_decision.action == "batch"
            assert [op.title for op in received_decision.operations] == ["喝水", "锻炼"]
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：喝水；已创建提醒：锻炼"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        command_executor=FakeExecutor(),
    ).run("今天17:57提醒我喝水，每天17:58提醒我锻炼", _run_context())

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：喝水；已创建提醒：锻炼"


@pytest.mark.asyncio
async def test_reminder_intent_port_retries_when_primary_has_no_executable_decision():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=None)

    class RetryAgent:
        async def arun(self, *, input, session_state):
            assert "Return only a valid ReminderDetectDecision" in input
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "喝水",
                    "trigger_at": "2026-05-07T17:57:00+09:00",
                }
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.action == "create"
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：喝水"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=FakeExecutor(),
    ).run("17:57提醒我喝水", _run_context())

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：喝水"


@pytest.mark.asyncio
async def test_reminder_intent_port_blocks_unbounded_high_frequency_batch():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
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
                        },
                        {
                            "action": "create",
                            "title": "冥想",
                            "trigger_at": "2026-05-10T18:00:00+09:00",
                        },
                    ],
                }
            )

    class RetryAgent:
        async def arun(self, *, input, session_state):
            raise AssertionError("protocol guard should not need retry")

    class FailingExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("unbounded high-frequency cadence must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=FailingExecutor(),
    ).run("每小时提醒我一次冥想，从下午五点开始", _run_context())

    assert result.ok is True
    assert result.content["action"] == "clarify"
    assert result.content["summary"] == "冥想要持续到什么时候结束？请告诉我截止时间。"


@pytest.mark.asyncio
async def test_reminder_intent_port_blocks_input_high_frequency_batch_without_evidence():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "batch",
                    "schedule_basis": "explicit_occurrences",
                    "schedule_evidence": "15:00, 16:00",
                    "operations": [
                        {
                            "action": "create",
                            "title": "冥想",
                            "trigger_at": "2026-05-10T15:00:00+09:00",
                        },
                        {
                            "action": "create",
                            "title": "冥想",
                            "trigger_at": "2026-05-10T16:00:00+09:00",
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

    assert result.ok is True
    assert result.content["action"] == "clarify"
    assert result.content["summary"] == "冥想要持续到什么时候结束？请告诉我截止时间。"


@pytest.mark.asyncio
async def test_reminder_intent_port_blocks_unbounded_hourly_rrule():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
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

    assert result.ok is True
    assert result.content["action"] == "clarify"
    assert result.content["summary"] == "冥想要持续到什么时候结束？请告诉我截止时间。"


@pytest.mark.asyncio
async def test_reminder_intent_port_blocks_hourly_rrule_with_separate_deadline():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "冥想",
                    "trigger_at": "2026-05-10T15:00:00+09:00",
                    "rrule": "FREQ=HOURLY",
                    "deadline_at": "2026-05-10T23:00:00+09:00",
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

    assert result.ok is True
    assert result.content["action"] == "clarify"
    assert result.content["summary"] == "冥想要持续到什么时候结束？请告诉我截止时间。"


@pytest.mark.asyncio
async def test_reminder_intent_port_retries_primary_clarification_before_returning():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_question": "你是想每天提醒还是只提醒一次？",
                }
            )

    class RetryAgent:
        async def arun(self, *, input, session_state):
            assert "primary detector returned no executable decision" in input
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "学英语",
                    "trigger_at": "2026-05-07T18:00:00+09:00",
                }
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.action == "create"
            assert received_decision.title == "学英语"
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：学英语"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=FakeExecutor(),
    ).run("你可以没太难18:00 提醒我学英语么", _run_context())

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：学英语"


@pytest.mark.asyncio
async def test_reminder_intent_port_primary_clarification_survives_retry_timeout(
    monkeypatch,
):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    monkeypatch.setenv(
        "COKE_AGENT_RUNTIME_REMINDER_CLARIFICATION_RETRY_TIMEOUT_SECONDS", "0.01"
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_question": "下周二几点提醒你去杭州？",
                }
            )

    class SlowRetryAgent:
        async def arun(self, *, input, session_state):
            await asyncio.sleep(60)

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=SlowRetryAgent(),
    ).run("提醒我下周二去杭州", _run_context())

    assert result.ok is True
    assert result.content["action"] == "clarify"
    assert result.content["summary"] == "下周二几点提醒你去杭州？"


@pytest.mark.asyncio
async def test_reminder_intent_port_retries_when_title_drops_quoted_content():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "思考一个问题：工作应该去做",
                    "trigger_at": "2026-05-08T10:40:00+09:00",
                }
            )

    class RetryAgent:
        async def arun(self, *, input, session_state):
            assert "dropped quoted reminder title content" in input
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "思考：工作应该去做“非我不可”的事情",
                    "trigger_at": "2026-05-08T10:40:00+09:00",
                }
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.title == "思考：工作应该去做“非我不可”的事情"
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：思考：工作应该去做“非我不可”的事情"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=FakeExecutor(),
    ).run(
        "另外10:40提醒思考一个问题：工作应该去做“非我不可”的事情",
        _run_context(),
    )

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：思考：工作应该去做“非我不可”的事情"


@pytest.mark.asyncio
async def test_reminder_intent_port_failcloses_when_retry_is_invalid():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content="Operation cancelled by user")

    class RetryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content="intentaction create")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
    ).run("帮我设置一个本周六订蛋糕的提醒，预定链接是：#小程序://x", _run_context())

    assert result.ok is False
    assert result.error == "ReminderDetectInvalidDecision"
    assert result.content["action"] == "clarify"
    assert "提醒设置还没完成" in result.content["summary"]
    assert result.metadata["durable_write"] is False


@pytest.mark.asyncio
async def test_reminder_intent_port_retries_when_primary_detector_times_out(
    monkeypatch,
):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    monkeypatch.setenv("COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS", "0.01")

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            await asyncio.sleep(60)

    class RetryAgent:
        async def arun(self, *, input, session_state):
            assert "Retry reason: primary detector timed out" in input
            assert "Return only a valid ReminderDetectDecision" in input
            assert "bounded cadence requests with a deadline" in input
            assert 'schedule_basis="explicit_cadence"' in input
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "喝水",
                    "trigger_at": "2026-05-07T17:57:00+09:00",
                }
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.action == "create"
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：喝水"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=FakeExecutor(),
    ).run("17:57提醒我喝水", _run_context())

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：喝水"


@pytest.mark.asyncio
async def test_reminder_intent_port_timeout_falls_back_to_visible_clarification(
    monkeypatch,
):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    monkeypatch.setenv("COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setenv(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS", "0.01"
    )

    class SlowAgent:
        async def arun(self, *, input, session_state):
            await asyncio.sleep(60)

    result = await ReminderIntentPort(
        detector_agent=SlowAgent(),
        retry_agent=SlowAgent(),
    ).run("明天提醒我", _run_context())

    assert result.ok is False
    assert result.error == "ReminderDetectTimeout"
    assert result.metadata["durable_write"] is False
    assert result.content["action"] == "clarify"
    assert "提醒设置还没完成" in result.content["summary"]


@pytest.mark.asyncio
async def test_reminder_intent_port_primary_timeout_uses_short_retry_budget(
    monkeypatch,
):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    monkeypatch.setenv("COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setenv(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_RETRY_SECONDS", "0.01"
    )
    monkeypatch.delenv(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS", raising=False
    )

    class SlowAgent:
        async def arun(self, *, input, session_state):
            await asyncio.sleep(60)

    result = await asyncio.wait_for(
        ReminderIntentPort(
            detector_agent=SlowAgent(),
            retry_agent=SlowAgent(),
        ).run("【bad case】今天有哪些提醒？", _run_context()),
        timeout=0.5,
    )

    assert result.ok is False
    assert result.error == "ReminderDetectTimeout"
    assert result.metadata["durable_write"] is False
    assert "提醒设置还没完成" in result.content["summary"]


@pytest.mark.asyncio
async def test_reminder_intent_port_returns_noop_for_non_reminder():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(intent_type="none", action=None)

    class FakeAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=decision)

    result = await ReminderIntentPort(detector_agent=FakeAgent()).run(
        "hello", _run_context()
    )

    assert result.ok is True
    assert result.content["action"] == "none"


@pytest.mark.asyncio
async def test_reminder_intent_port_surfaces_clarification_question():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    decision = SimpleNamespace(
        intent_type="clarify",
        action="",
        clarification_question="你想让我提醒你做什么？",
    )

    class FakeAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=decision)

    result = await ReminderIntentPort(detector_agent=FakeAgent()).run(
        "晚上10:00提醒我", _run_context()
    )

    assert result.ok is True
    assert result.content["action"] == "clarify"
    assert result.content["summary"] == "你想让我提醒你做什么？"
    assert result.metadata["durable_write"] is False
