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


def _pending_workflow_document(**overrides):
    document = {
        "id": "workflow_1",
        "kind": "reminder_create",
        "status": "awaiting_user",
        "origin": {
            "conversation_id": "conv-1",
            "message_ids": ["msg-1"],
            "created_at": "2026-05-06T01:00:00+00:00",
            "updated_at": "2026-05-06T01:00:00+00:00",
            "expires_at": "2026-05-07T01:00:00+00:00",
        },
        "goal": "Set up whole-hour check-in reminders",
        "slots": {
            "title": {"value": "打卡", "status": "filled"},
            "start_at": {"value": None, "status": "missing"},
        },
        "missing_fields": ["start_at"],
        "assumptions": [],
        "constraints": [],
        "next_steps": ["ask_user"],
        "payload": {"reminder": {"draft_operations": []}},
    }
    document.update(overrides)
    return document


def _active_pending_workflow(*, revision=4, document=None):
    run_context = _run_context()
    workflow_document = document or _pending_workflow_document()
    return {
        "id": workflow_document["id"],
        "owner_user_id": "user-1",
        "conversation_id": "conv-1",
        "kind": workflow_document["kind"],
        "status": workflow_document["status"],
        "revision": revision,
        "created_at": run_context.current_time,
        "updated_at": run_context.current_time,
        "expires_at": run_context.current_time,
        "document": workflow_document,
    }


def _ready_pending_workflow_document(**overrides):
    document = _pending_workflow_document(
        status="ready_to_execute",
        slots={
            "title": {"value": "打卡", "status": "filled"},
            "start_at": {"value": "now", "status": "filled"},
        },
        missing_fields=[],
        next_steps=["execute_now"],
    )
    document.update(overrides)
    return document


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
    assert "Complete CRUD decisions must omit workflow_update" in prompt
    assert "One-shot deadline wording" in prompt
    assert "Need/intention statements" in prompt
    assert "Meta discussion or complaints about reminder/alarm behavior" in prompt
    assert "Plans to test, improve, or discuss reminder functionality" in prompt
    assert "Pomodoro/tomato timer starts are timed reminder requests" in prompt
    assert "20min later, 过20min" in prompt
    assert "Completion-conditioned reminders" in prompt
    assert "return discussion" in prompt
    assert "Day-of-month wording before the reminder verb" in prompt
    assert (
        "Noisy filler before a concrete clock time is not recurrence evidence" in prompt
    )
    assert (
        "Undesignated local clock times attached to a reminder task are concrete"
        in prompt
    )
    assert "Status-only or referential fragments" in prompt
    assert (
        "Do not use RRULE or explicit_cadence unless the user supplies recurrence"
        in prompt
    )
    assert "batch create decision must include top-level schedule_basis" in prompt
    assert "Clarify and discussion decisions must use empty action" in prompt
    assert (
        "Weekly recurrence with listed weekdays must include every listed weekday"
        in prompt
    )
    assert "Weekday names used as a recurrence cadence are concrete" in prompt
    assert "manual correction or exception to occurrence times" in prompt
    assert "stops the cadence at or after the same deadline" in prompt
    assert "到/直到/until + clock/date" in prompt
    assert "bounded window with explicit start date" in prompt


def test_retry_prompt_preserves_bare_call_me_clock_contract():
    from agent.agno_agent.capabilities.reminder_intent import (
        _build_reminder_retry_input,
    )

    prompt = _build_reminder_retry_input(
        "3点叫我",
        _run_context(),
        reason="primary detector timed out",
    )

    assert "Bare call/wake/alarm-me with a concrete clock time is complete" in prompt
    assert "do not ask for reminder content or date" in prompt
    assert "batch create decisions require top-level schedule_basis" in prompt
    assert "Clarify and discussion retries must return empty action" in prompt


def test_retry_prompt_preserves_status_only_missing_content_contract():
    from agent.agno_agent.capabilities.reminder_intent import (
        _build_reminder_retry_input,
    )

    prompt = _build_reminder_retry_input(
        "十一点提醒我吧 都还没做",
        _run_context(),
        reason="primary detector timed out",
    )

    assert "Status-only or referential fragments" in prompt
    assert "clarify for the task/content" in prompt


def test_retry_prompt_preserves_undesignated_task_clock_contract():
    from agent.agno_agent.capabilities.reminder_intent import (
        _build_reminder_retry_input,
    )

    prompt = _build_reminder_retry_input(
        "6点30开始学习提醒我下",
        _run_context(),
        reason="primary detector timed out",
    )

    assert (
        "Undesignated local clock times attached to a reminder task are concrete"
        in prompt
    )
    assert "do not ask for date or trigger_at" in prompt


def test_retry_prompt_preserves_weekday_recurrence_contract():
    from agent.agno_agent.capabilities.reminder_intent import (
        _build_reminder_retry_input,
    )

    prompt = _build_reminder_retry_input(
        "周六周天下午三点提醒小吴完成学习任务",
        _run_context(),
        reason="primary detector timed out",
    )

    assert "Weekday names used as a recurrence cadence are concrete" in prompt
    assert "do not ask which calendar date" in prompt


def test_retry_prompt_preserves_corrected_interval_sequence_contract():
    from agent.agno_agent.capabilities.reminder_intent import (
        _build_reminder_retry_input,
    )

    prompt = _build_reminder_retry_input(
        "在6点前，每50分钟通知我一次，4点40之后的提醒应该是5点半",
        _run_context(),
        reason="primary detector returned a past trigger",
    )

    assert "manual correction or exception to occurrence times" in prompt
    assert "clarify for the exact occurrence list" in prompt


def test_retry_prompt_preserves_bounded_cadence_end_phrase_contract():
    from agent.agno_agent.capabilities.reminder_intent import (
        _build_reminder_retry_input,
    )

    prompt = _build_reminder_retry_input(
        "每小时打卡，到晚上8点",
        _run_context(),
        reason="reminder tool rejected a bounded recurrence",
    )

    assert "到/直到/until + clock/date" in prompt
    assert "first future occurrence" in prompt


def test_retry_prompt_preserves_bounded_window_completion_contract():
    from agent.agno_agent.capabilities.reminder_intent import (
        _build_reminder_retry_input,
    )

    prompt = _build_reminder_retry_input(
        "从明天开始从早上7点到晚上11点，每小时提醒一次及时完成任务",
        _run_context(),
        reason="primary detector returned invalid structured output",
    )

    assert "bounded window with explicit start date" in prompt
    assert "trigger_at for the first occurrence" in prompt
    assert "deadline_at for the window end" in prompt


def test_retry_prompt_preserves_bounded_cadence_stop_boundary_contract():
    from agent.agno_agent.capabilities.reminder_intent import (
        _build_reminder_retry_input,
    )

    prompt = _build_reminder_retry_input(
        "开始帮我每小时打卡持续到20点，20点之后不要打卡",
        _run_context(),
        reason="primary detector returned no executable decision",
    )

    assert "stops the cadence at or after the same deadline" in prompt
    assert "not a manual correction" in prompt


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
                    "origin": {"created_at": datetime(2026, 5, 6, 1, 0, tzinfo=UTC)},
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

    assert reminder_intent._agent_runtime_reminder_detect_timeout_seconds() == 30.0


def test_agent_runtime_reminder_detect_timeout_retry_default_budget_covers_live_retry_latency(
    monkeypatch,
):
    from agent.agno_agent.capabilities import reminder_intent

    monkeypatch.delenv(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_RETRY_SECONDS",
        raising=False,
    )

    assert (
        reminder_intent._agent_runtime_reminder_detect_timeout_retry_seconds() == 80.0
    )


def test_agent_runtime_reminder_detect_retry_default_budget_covers_live_retry_latency(
    monkeypatch,
):
    from agent.agno_agent.capabilities import reminder_intent

    monkeypatch.delenv(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS", raising=False
    )

    assert (
        reminder_intent._agent_runtime_reminder_detect_retry_timeout_seconds() == 80.0
    )


def test_agent_runtime_reminder_detect_primary_timeout_leaves_user_path_budget(
    monkeypatch,
):
    from agent.agno_agent.capabilities import reminder_intent

    monkeypatch.delenv(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS", raising=False
    )
    monkeypatch.delenv(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_RETRY_SECONDS",
        raising=False,
    )

    total_timeout_budget = (
        reminder_intent._agent_runtime_reminder_detect_timeout_seconds()
        + reminder_intent._agent_runtime_reminder_detect_timeout_retry_seconds()
    )

    assert total_timeout_budget <= 110.0


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
async def test_reminder_intent_port_salvages_json_string_with_invalid_workflow_update():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    detector_content = """
    {
      "intent_type": "crud",
      "action": "create",
      "title": "更新登记表，15号的人也要更新",
      "trigger_at": "2026-05-12T10:00:00+09:00",
      "schedule_basis": "one_shot",
      "schedule_evidence": "明天上午10点",
      "workflow_update": {
        "assumptions": ["明天上午10点提醒"],
        "constraints": [],
        "missing_fields": [],
        "next_steps": [],
        "payload": {},
        "status": "draft"
      }
    }
    """

    class FakeAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=detector_content)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.intent_type == "crud"
            assert received_decision.action == "create"
            assert received_decision.title == "更新登记表，15号的人也要更新"
            assert received_decision.trigger_at == "2026-05-12T10:00:00+09:00"
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：更新登记表，15号的人也要更新"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=FakeAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run("明天上午10点提醒我更新登记表，15号的人也要更新", _run_context())

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：更新登记表，15号的人也要更新"


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
async def test_reminder_intent_port_blocks_model_inferred_deadline_for_high_frequency_batch():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "batch",
                    "schedule_basis": "explicit_occurrences",
                    "schedule_evidence": "16:00, 17:00",
                    "deadline_at": "2026-05-10T23:00:00+09:00",
                    "operations": [
                        {
                            "action": "create",
                            "title": "正念冥想",
                            "trigger_at": "2026-05-10T16:00:00+09:00",
                        },
                        {
                            "action": "create",
                            "title": "正念冥想",
                            "trigger_at": "2026-05-10T17:00:00+09:00",
                        },
                    ],
                }
            )

    class FailingExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("model-inferred deadline must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        command_executor=FailingExecutor(),
    ).run("每个小时一次提醒我正念冥想", _run_context())

    assert result.ok is True
    assert result.content["action"] == "clarify"
    assert (
        result.content["summary"] == "正念冥想要持续到什么时候结束？请告诉我截止时间。"
    )


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
async def test_reminder_intent_port_retries_bounded_cadence_with_dao_deadline_phrase():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
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

    class RetryAgent:
        async def arun(self, *, input, session_state):
            assert "keep the deadline as deadline_at" in input
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "打卡",
                    "trigger_at": "2026-05-10T17:00:00+09:00",
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
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "ok"},
                error=None,
                metadata={},
            )

    executor = FakeExecutor()

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=executor,
    ).run("每小时打卡，到晚上8点", _run_context())

    assert result.ok is True
    assert len(executor.decisions) == 1
    assert executor.decisions[0].deadline_at == "2026-05-10T20:00:00+09:00"


@pytest.mark.asyncio
async def test_reminder_intent_port_retries_bounded_recurring_no_future_schedule():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
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

    class RetryAgent:
        async def arun(self, *, input, session_state):
            assert "no future fire time" in input
            assert "first future occurrence" in input
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "打卡",
                    "trigger_at": "2026-05-10T17:00:00+09:00",
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
                return SimpleNamespace(
                    name="reminder",
                    ok=False,
                    content={
                        "summary": "创建提醒失败：Recurring reminder schedule has no future fire time"
                    },
                    error="InvalidSchedule",
                )
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "ok"},
                error=None,
                metadata={},
            )

    executor = FakeExecutor()

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=executor,
    ).run("每小时打卡，到晚上8点", _run_context())

    assert result.ok is True
    assert len(executor.decisions) == 2
    assert executor.decisions[1].trigger_at == "2026-05-10T17:00:00+09:00"


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
async def test_reminder_intent_port_retries_when_day_of_month_is_dropped():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "给医院打电话预约手术",
                    "trigger_at": "2026-05-12T09:00:00+00:00",
                }
            )

    class RetryAgent:
        async def arun(self, *, input, session_state):
            assert "dropped an explicit day-of-month date" in input
            assert "22号 before the reminder clock" in input
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "给医院打电话预约手术",
                    "trigger_at": "2026-05-22T09:00:00+00:00",
                }
            )

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            assert received_decision.trigger_at == "2026-05-22T09:00:00+00:00"
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：给医院打电话预约手术"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=FakeExecutor(),
    ).run(
        "然后再book一个22号早上9点提醒我给医院打电话预约手术",
        _run_context(),
    )

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：给医院打电话预约手术"


@pytest.mark.asyncio
async def test_reminder_intent_port_normalizes_past_bare_clock_to_next_occurrence():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="离开时手机",
        trigger_at="2026-05-06T00:00:00+00:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class RetryAgent:
        async def arun(self, *, input, session_state):
            raise AssertionError("bare clock normalization should not need retry")

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            assert received_decision.trigger_at == "2026-05-06T11:00:00+00:00"
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：离开时手机"},
                error=None,
                metadata={},
            )

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=executor,
    ).run(
        "（2026年05月10日14时44分 reminder-e2e-user-18发来了文本消息）十一点开始提醒我离开时手机",
        _run_context(),
    )

    assert len(executor.received) == 1
    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：离开时手机"


@pytest.mark.asyncio
async def test_reminder_intent_port_corrects_bare_numeric_clock_to_user_local_time():
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
        trigger_at="2026-05-12T10:20:00+00:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_decision.trigger_at == "2026-05-12T09:20:00+09:00"
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：回家开会"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run("9:20 提醒我回家开会", run_context)

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：回家开会"


@pytest.mark.asyncio
async def test_reminder_intent_port_preserves_explicit_clock_minutes():
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
        trigger_at="2026-05-11T04:00:00+00:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_decision.trigger_at == "2026-05-11T13:50:00+09:00"
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：起床"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run("下午 1 点 50 分提醒我起床", run_context)

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：起床"


@pytest.mark.asyncio
async def test_reminder_intent_port_treats_every_night_as_pm_clock():
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
        trigger_at="2026-05-12T01:30:00+00:00",
        rrule="FREQ=DAILY",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_decision.trigger_at == "2026-05-12T22:30:00+09:00"
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：洗漱"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run("设置一个每晚10:30洗漱的提醒", run_context)

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：洗漱"


@pytest.mark.asyncio
async def test_reminder_intent_port_corrects_relative_delay_trigger_to_runtime_time():
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
        trigger_at="2026-05-11T07:00:00+00:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_decision.trigger_at == "2026-05-11T06:56:00+00:00"
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：起来休息，倒水喝"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run("25分钟后提醒我起来休息，倒水喝", run_context)

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：起来休息，倒水喝"


@pytest.mark.asyncio
async def test_reminder_intent_port_corrects_prefixed_min_relative_delay():
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
        trigger_at="2026-05-11T03:00:00+00:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, received_context):
            assert received_decision.trigger_at == "2026-05-11T02:40:00+00:00"
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：check on 我的结论"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run("yes, 过20min提醒我，check on 我的结论", run_context)

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：check on 我的结论"


@pytest.mark.asyncio
async def test_reminder_intent_port_normalizes_past_bare_clock_batch_operations():
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
                trigger_at="2026-05-06T00:00:00+00:00",
            ),
            SimpleNamespace(
                action="create",
                title="完成学习任务打卡",
                trigger_at="2026-05-06T00:30:00+00:00",
            ),
            SimpleNamespace(
                action="create",
                title="完成学习任务打卡",
                trigger_at="2026-05-06T02:00:00+00:00",
            ),
        ],
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：完成学习任务打卡"},
                error=None,
                metadata={},
            )

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=executor,
    ).run("0点一次，0点半一次，2点一次，提醒我完成学习任务打卡", _run_context())

    assert result.ok is True
    assert [op.trigger_at for op in executor.received[0].operations] == [
        "2026-05-07T00:00:00+00:00",
        "2026-05-07T00:30:00+00:00",
        "2026-05-06T02:00:00+00:00",
    ]


@pytest.mark.asyncio
async def test_reminder_intent_port_retries_when_explicit_today_past_clock_fails():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="离开时手机",
        trigger_at="2026-05-06T00:00:00+00:00",
    )
    retry_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="离开时手机",
        trigger_at="2026-05-07T00:00:00+00:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class RetryAgent:
        async def arun(self, *, input, session_state):
            assert "tool rejected past trigger_at" in input
            assert "bare local clock time has already passed" in input
            assert "Pomodoro/tomato timer" in input
            assert "do not output workflow_update" in input
            assert "workflow_update is not an allowed output field" in input
            return SimpleNamespace(content=retry_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            if received_decision is primary_decision:
                return SimpleNamespace(
                    name="reminder",
                    ok=False,
                    content={
                        "summary": "这个提醒时间已经过去了，请告诉我一个未来的时间。"
                    },
                    error="InvalidSchedule",
                    metadata={},
                )
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：离开时手机"},
                error=None,
                metadata={},
            )

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=executor,
    ).run("今天十一点开始提醒我离开时手机", _run_context())

    assert executor.received == [primary_decision, retry_decision]
    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：离开时手机"


@pytest.mark.asyncio
async def test_reminder_intent_port_clarifies_date_only_create():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="预定礼盒",
        trigger_at="2026-05-10T09:00:00+00:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("date-only midnight create must clarify before tool")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run("10号提醒我预定饼干、甜品礼盒", _run_context())

    assert result.ok is True
    assert result.content["intent_type"] == "clarify"
    assert "几点" in result.content["summary"]


@pytest.mark.asyncio
async def test_reminder_intent_port_clarifies_completion_condition_without_time():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="进入论文研究",
        trigger_at="2026-05-11T06:00:00+00:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("unschedulable completion condition should clarify")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run("我现在要先看两篇文章，看完继续提醒我进入论文研究", _run_context())

    assert result.ok is True
    assert result.content == {
        "action": "clarify",
        "intent_type": "clarify",
        "summary": "我不能自动知道你什么时候完成。请告诉我具体什么时候提醒你。",
    }


@pytest.mark.asyncio
async def test_reminder_intent_port_clarifies_date_only_batch_create():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="10号",
        operations=[
            SimpleNamespace(
                action="create",
                title="预定礼盒",
                trigger_at="2026-05-10T09:00:00+00:00",
            )
        ],
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("date-only batch create must clarify before tool")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run("10号提醒我预定饼干、甜品礼盒", _run_context())

    assert result.ok is True
    assert result.content["intent_type"] == "clarify"
    assert "几点" in result.content["summary"]


@pytest.mark.asyncio
async def test_reminder_intent_port_clarifies_ambiguous_adjacent_hour_range():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="周四下午四五点",
        operations=[
            SimpleNamespace(
                action="create",
                title="准备 resume",
                trigger_at="2026-05-14T16:00:00+09:00",
            ),
            SimpleNamespace(
                action="create",
                title="准备 resume",
                trigger_at="2026-05-14T17:00:00+09:00",
            ),
        ],
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("ambiguous adjacent hour range must clarify")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run("提醒我周四下午四五点，准备下resume", _run_context())

    assert result.ok is True
    assert result.content["intent_type"] == "clarify"
    assert "具体几点" in result.content["summary"]


@pytest.mark.asyncio
async def test_reminder_intent_port_clarifies_status_only_reminder_content():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="还没弄完",
        trigger_at="2026-05-11T11:00:00+09:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("status-only reminder content must clarify")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run("十一点提醒我吧 还没弄完", _run_context())

    assert result.ok is True
    assert result.content["intent_type"] == "clarify"
    assert "提醒你做什么" in result.content["summary"]


@pytest.mark.asyncio
async def test_reminder_intent_port_drops_batch_operations_before_reminder_verb():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="1点睡觉，明天6点半叫我起床",
        operations=[
            SimpleNamespace(
                action="create",
                title="睡觉",
                trigger_at="2026-05-11T01:00:00+09:00",
            ),
            SimpleNamespace(
                action="create",
                title="起床",
                trigger_at="2026-05-11T06:30:00+09:00",
            ),
        ],
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：起床"},
                error=None,
                metadata={},
            )

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=executor,
    ).run("1点睡觉，明天6点半叫我起床", _run_context())

    assert result.ok is True
    assert len(executor.received) == 1
    assert [op.title for op in executor.received[0].operations] == ["起床"]


@pytest.mark.asyncio
async def test_reminder_intent_port_drops_ungoverned_task_inventory_from_cadence_batch():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_cadence",
        schedule_evidence="每小时打卡持续到20点",
        operations=[
            SimpleNamespace(
                action="create",
                title="起床",
                trigger_at="2026-05-11T15:00:00+09:00",
            ),
            SimpleNamespace(
                action="create",
                title="打卡",
                trigger_at="2026-05-11T15:00:00+09:00",
                rrule="FREQ=HOURLY;UNTIL=20260511T110000Z",
            ),
            SimpleNamespace(
                action="create",
                title="跑步",
                trigger_at="2026-05-11T15:00:00+09:00",
            ),
            SimpleNamespace(
                action="create",
                title="睡觉",
                trigger_at="2026-05-11T20:00:00+09:00",
            ),
        ],
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：打卡"},
                error=None,
                metadata={},
            )

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=executor,
    ).run(
        "帮我记住今天任务，15点起床，开始帮我每小时打卡持续到20点，跑步，20点睡觉",
        _run_context(),
    )

    assert result.ok is True
    assert len(executor.received) == 1
    assert [op.title for op in executor.received[0].operations] == ["打卡"]


@pytest.mark.asyncio
async def test_reminder_intent_port_drops_inventory_with_misapplied_cadence_rrule():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_cadence",
        schedule_evidence="开始帮我每小时打卡，打卡持续到20点",
        operations=[
            SimpleNamespace(
                action="create",
                title="起床",
                trigger_at="2026-05-11T15:00:00+09:00",
                rrule="FREQ=HOURLY;UNTIL=20260511T110000Z",
            ),
            SimpleNamespace(
                action="create",
                title="打卡",
                trigger_at="2026-05-11T15:00:00+09:00",
                rrule="FREQ=HOURLY;UNTIL=20260511T110000Z",
            ),
        ],
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：打卡"},
                error=None,
                metadata={},
            )

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=executor,
    ).run(
        (
            "帮我记住今天任务，以这个版本为准\n\n"
            "15点-16点\n起床，开始帮我每小时打卡，打卡持续到20点\n跑步3公里"
        ),
        _run_context(),
    )

    assert result.ok is True
    assert len(executor.received) == 1
    assert [op.title for op in executor.received[0].operations] == ["打卡"]


@pytest.mark.asyncio
async def test_reminder_intent_port_retries_today_time_range_recurring_compression():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="看法考网课和做题",
        trigger_at="2026-05-11T11:30:00+09:00",
        rrule="FREQ=DAILY",
        schedule_basis="explicit_cadence",
        schedule_evidence="今天的任务时间点",
    )
    retry_decision = SimpleNamespace(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="这些时间点",
        operations=[
            SimpleNamespace(
                action="create",
                title="看法考网课",
                trigger_at="2026-05-11T11:30:00+09:00",
            ),
            SimpleNamespace(
                action="create",
                title="健身",
                trigger_at="2026-05-11T13:30:00+09:00",
            ),
        ],
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class RetryAgent:
        async def arun(self, *, input, session_state):
            assert "today's task-range reminder" in input
            assert "action=batch" in input
            return SimpleNamespace(content=retry_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：看法考网课；已创建提醒：健身"},
                error=None,
                metadata={},
            )

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=executor,
    ).run(
        "这是我今天的任务 11：30-13：30 看法考网课；13：30-15：30 健身 请在这些时间点提醒我学习",
        _run_context(),
    )

    assert result.ok is True
    assert executor.received == [retry_decision]


@pytest.mark.asyncio
async def test_reminder_intent_port_clarifies_large_today_time_range_plan():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="这些时间点",
        operations=[
            SimpleNamespace(
                action="create",
                title="学习",
                trigger_at=f"2026-05-11T{hour:02d}:00:00+09:00",
            )
            for hour in range(11, 15)
        ],
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("large ambiguous day plan must clarify before tool")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run(
        "这是我今天的任务 11-12 吃饭；12-13 学习；13-14 健身；14-15 洗澡 请在这些时间点提醒我学习",
        _run_context(),
    )

    assert result.content["action"] == "clarify"
    assert "具体几点" in result.content["summary"]


@pytest.mark.asyncio
async def test_reminder_intent_port_retries_invalid_structured_output_with_schema_boundary():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    retry_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="打卡",
        trigger_at="2026-05-11T15:00:00+09:00",
        rrule="FREQ=HOURLY;UNTIL=20260511T110000Z",
        deadline_at="2026-05-11T20:00:00+09:00",
        schedule_basis="explicit_cadence",
        schedule_evidence="每小时打卡，打卡持续到20点",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content="ReminderDetectInvalidStructuredOutput")

    class RetryAgent:
        async def arun(self, *, input, session_state):
            assert "primary detector returned invalid structured output" in input
            assert "batch create decisions require top-level schedule_basis" in input
            assert "Clarify and discussion retries must return empty action" in input
            return SimpleNamespace(content=retry_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：打卡"},
                error=None,
                metadata={},
            )

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=executor,
    ).run(
        "15点开始帮我每小时打卡，打卡持续到20点",
        _run_context(),
    )

    assert result.ok is True
    assert len(executor.received) == 1
    assert executor.received[0].title == "打卡"


@pytest.mark.asyncio
async def test_reminder_intent_port_treats_standalone_english_opt_out_as_no_action():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="clarify",
        action="",
        clarification_question="Which reminder should I cancel?",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class RetryAgent:
        async def arun(self, *, input, session_state):
            raise AssertionError("standalone reminder opt-out should not retry")

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("standalone reminder opt-out should not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=FakeExecutor(),
    ).run("All good, no reminders pls", _run_context())

    assert result.ok is True
    assert result.content == {"action": "none", "intent_type": "discussion"}


@pytest.mark.asyncio
async def test_reminder_intent_port_suppresses_delete_for_standalone_english_opt_out():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="cancel",
        keyword="",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("standalone reminder opt-out should not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run("All good, no reminders pls", _run_context())

    assert result.ok is True
    assert result.content == {"action": "none", "intent_type": "discussion"}


@pytest.mark.asyncio
async def test_reminder_intent_port_suppresses_management_for_alarm_acknowledgement():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="complete",
        keyword="闹钟",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("standalone alarm acknowledgement should not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run("谢谢闹钟", _run_context())

    assert result.ok is True
    assert result.content == {"action": "none", "intent_type": "discussion"}


@pytest.mark.asyncio
async def test_reminder_intent_port_treats_behavior_meta_discussion_as_no_action():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="clarify",
        action="",
        clarification_question="请问你需要我给你创建什么样的提醒？",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("reminder behavior discussion should not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run(
        "我以为把你纯当闹钟就行了……没想到还得回复你你才会保持提醒……",
        _run_context(),
    )

    assert result.ok is True
    assert result.content == {"action": "none", "intent_type": "discussion"}


@pytest.mark.asyncio
async def test_reminder_intent_port_treats_feature_work_topic_as_no_action():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="clarify",
        action="",
        clarification_question="提醒设置还没完成。请确认具体提醒时间和提醒内容。",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class RetryAgent:
        async def arun(self, *, input, session_state):
            raise AssertionError("feature work topic should not retry as reminder")

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("feature work topic should not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=FakeExecutor(),
    ).run(
        "可以呀，明天测试多线程能力，和提醒功能增强",
        _run_context(),
    )

    assert result.ok is True
    assert result.content == {"action": "none", "intent_type": "discussion"}


@pytest.mark.asyncio
async def test_reminder_intent_port_does_not_retry_feature_work_discussion():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content={"intent_type": "discussion", "action": ""})

    class RetryAgent:
        async def arun(self, *, input, session_state):
            raise AssertionError("feature work discussion should not retry")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
    ).run(
        "可以呀，明天测试多线程能力，和提醒功能增强",
        _run_context(),
    )

    assert result.ok is True
    assert result.content == {"action": "none", "intent_type": "discussion"}


@pytest.mark.asyncio
async def test_reminder_intent_port_suppresses_invalid_structured_for_english_opt_out():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content="ReminderDetectInvalidStructuredOutput")

    class RetryAgent:
        async def arun(self, *, input, session_state):
            raise AssertionError("standalone reminder opt-out should not retry")

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("standalone reminder opt-out should not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=FakeExecutor(),
    ).run("All good, no reminders pls", _run_context())

    assert result.ok is True
    assert result.content == {"action": "none", "intent_type": "discussion"}


@pytest.mark.asyncio
async def test_reminder_intent_port_retries_bounded_cadence_deadline_loss():
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
    retry_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="跑步",
        trigger_at="2026-05-10T20:00:00+09:00",
        rrule="FREQ=DAILY",
        schedule_basis="explicit_cadence",
        schedule_evidence="每天晚上八点，12月7号前",
        deadline_at="2026-12-07T00:00:00+09:00",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class RetryAgent:
        async def arun(self, *, input, session_state):
            assert "cadence and a deadline" in input
            assert "deadline_at" in input
            return SimpleNamespace(content=retry_decision)

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：跑步"},
                error=None,
                metadata={},
            )

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=executor,
    ).run("12月7号前，每天晚上八点提醒我跑步", _run_context())

    assert executor.received == [retry_decision]
    assert result.ok is True


@pytest.mark.asyncio
async def test_reminder_intent_port_does_not_treat_sleep_before_as_deadline_loss():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    primary_decision = SimpleNamespace(
        intent_type="crud",
        action="create",
        title="吃药",
        trigger_at="2026-05-06T22:00:00+00:00",
        rrule="FREQ=DAILY",
        schedule_basis="explicit_cadence",
        schedule_evidence="每天睡前",
    )

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class RetryAgent:
        async def arun(self, *, input, session_state):
            raise AssertionError("睡前 is not a bounded deadline")

    class FakeExecutor:
        def __init__(self):
            self.received = []

        def execute(self, received_decision, run_context):
            self.received.append(received_decision)
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：吃药"},
                error=None,
                metadata={},
            )

    executor = FakeExecutor()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        command_executor=executor,
    ).run("每天睡前提醒我吃药", _run_context())

    assert executor.received == [primary_decision]
    assert result.ok is True


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
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content=primary_decision)

    class FakeExecutor:
        def execute(self, received_decision, run_context):
            raise AssertionError("unsafe unbounded recurrence must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
    ).run("12月7号前，每天晚上八点提醒我跑步", _run_context())

    assert result.content == {
        "action": "clarify",
        "intent_type": "clarify",
        "summary": "跑步有截止条件，请确认截止日期和最后一次提醒时间。",
    }
    assert result.metadata["durable_write"] is False


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
            assert "Complete CRUD decisions must omit workflow_update" in input
            assert (
                "Noisy filler before a concrete clock time is not recurrence evidence"
                in input
            )
            assert "bounded recurring cadence requests with a deadline" in input
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
async def test_reminder_intent_port_timeout_asks_deadline_for_high_frequency_input(
    monkeypatch,
):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    monkeypatch.setenv("COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setenv(
        "COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_RETRY_SECONDS", "0.01"
    )

    class SlowAgent:
        async def arun(self, *, input, session_state):
            await asyncio.sleep(60)

    result = await asyncio.wait_for(
        ReminderIntentPort(
            detector_agent=SlowAgent(),
            retry_agent=SlowAgent(),
        ).run("冥想可以每个小时提醒我做一次冥想吗", _run_context()),
        timeout=0.5,
    )

    assert result.ok is True
    assert result.error is None
    assert result.content["action"] == "clarify"
    assert "持续到什么时候结束" in result.content["summary"]
    assert result.metadata["durable_write"] is False


@pytest.mark.asyncio
async def test_reminder_intent_port_invalid_retry_asks_window_for_whole_hour_input(
    monkeypatch,
):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    monkeypatch.setenv("COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS", "0.01")

    class SlowPrimaryAgent:
        async def arun(self, *, input, session_state):
            await asyncio.sleep(60)

    class InvalidRetryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(content="intentaction create")

    result = await ReminderIntentPort(
        detector_agent=SlowPrimaryAgent(),
        retry_agent=InvalidRetryAgent(),
    ).run("每个整点喊我打卡吧", _run_context())

    assert result.ok is True
    assert result.content["action"] == "clarify"
    assert "从什么时候开始" in result.content["summary"]
    assert "持续到什么时候结束" in result.content["summary"]
    assert result.metadata["durable_write"] is False


@pytest.mark.asyncio
async def test_pending_workflow_retry_detector_receives_active_workflow(monkeypatch):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    monkeypatch.setenv("COKE_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_SECONDS", "0.01")
    active = _active_pending_workflow(revision=2)

    class FakeDAO:
        def load_active_for_conversation(
            self, owner_user_id, conversation_id, now=None
        ):
            return active

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            await asyncio.sleep(60)

    class RetryAgent:
        async def arun(self, *, input, session_state):
            assert "### Active Pending Workflow" in input
            assert '"revision": 2' in input
            assert '"id": "workflow_1"' in input
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_question": "还差结束时间。",
                }
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=RetryAgent(),
        pending_workflow_enabled=True,
        pending_workflow_dao=FakeDAO(),
    ).run("从现在开始", _run_context())

    assert result.content["summary"] == "还差结束时间。"


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


def test_fallback_clarification_for_deadline_without_trigger_asks_when_before_deadline():
    from agent.agno_agent.capabilities.reminder_intent import (
        _fallback_clarification_for_input,
        _invalid_decision_clarification_result,
    )

    result = _fallback_clarification_for_input(
        "提醒我今晚十点半之前完成英语小组作业",
        _invalid_decision_clarification_result(),
    )

    assert result.ok is True
    assert (
        result.content["summary"]
        == "这是截止时间。你想在这个时间之前的什么时候提醒你？"
    )


def test_timeout_fallback_for_date_only_reminder_asks_for_clock_time():
    from agent.agno_agent.capabilities.reminder_intent import (
        _fallback_clarification_for_input,
        _timeout_clarification_result,
    )

    result = _fallback_clarification_for_input(
        "提醒我，我12月18号之前定个蛋糕，17号提醒吧",
        _timeout_clarification_result(),
    )

    assert result.ok is True
    assert result.error is None
    assert result.content["action"] == "clarify"
    assert "几点" in result.content["summary"]


def test_whole_hour_until_phrase_counts_as_bounded_cadence_deadline():
    from agent.agno_agent.capabilities.reminder_intent import (
        _input_has_bounded_cadence_deadline,
    )

    assert _input_has_bounded_cadence_deadline("每个整点让我打卡直到19点") is True


def test_fallback_for_plain_schedule_statement_returns_no_reminder_action():
    from agent.agno_agent.capabilities.reminder_intent import (
        _fallback_clarification_for_input,
        _timeout_clarification_result,
    )

    result = _fallback_clarification_for_input(
        "明天七点起床",
        _timeout_clarification_result(),
    )

    assert result.ok is True
    assert result.error is None
    assert result.content == {"action": "none", "intent_type": "discussion"}


def test_fallback_for_standalone_english_opt_out_returns_no_reminder_action():
    from agent.agno_agent.capabilities.reminder_intent import (
        _fallback_clarification_for_input,
        _invalid_decision_clarification_result,
    )

    result = _fallback_clarification_for_input(
        "All good, no reminders pls",
        _invalid_decision_clarification_result(),
    )

    assert result.error is None
    assert result.content == {"action": "none", "intent_type": "discussion"}


def test_fallback_clarification_for_concrete_time_without_content_asks_task():
    from agent.agno_agent.capabilities.reminder_intent import (
        _fallback_clarification_for_input,
        _invalid_decision_clarification_result,
    )

    result = _fallback_clarification_for_input(
        "周三下午4点提醒我",
        _invalid_decision_clarification_result(),
    )

    assert result.ok is True
    assert result.content["summary"] == "你想让我提醒你做什么？"


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


@pytest.mark.asyncio
async def test_pending_workflow_flag_off_keeps_legacy_clarify_behavior():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class ExplodingDAO:
        def load_active_for_conversation(
            self, owner_user_id, conversation_id, now=None
        ):
            raise AssertionError("flag-off path must not load pending workflows")

        def upsert_new_active_workflow(self, document, now=None):
            raise AssertionError("flag-off path must not persist pending workflows")

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            assert "Active Pending Workflow" not in input
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_question": "什么时候开始？",
                    "workflow_update": _pending_workflow_document(),
                }
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        pending_workflow_enabled=False,
        pending_workflow_dao=ExplodingDAO(),
    ).run("每个整点喊我打卡吧", _run_context())

    assert result.content == {
        "action": "clarify",
        "intent_type": "clarify",
        "summary": "什么时候开始？",
    }
    assert result.metadata["durable_write"] is False


@pytest.mark.asyncio
async def test_pending_workflow_flag_on_persists_clarify_workflow():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    saved = []

    class FakeDAO:
        def load_active_for_conversation(
            self, owner_user_id, conversation_id, now=None
        ):
            assert owner_user_id == "user-1"
            assert conversation_id == "conv-1"
            return None

        def upsert_new_active_workflow(self, document, now=None):
            saved.append(document)
            return True

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            assert "Active Pending Workflow" not in input
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_question": "每个整点打卡要从什么时候开始，持续到什么时候结束？",
                    "workflow_update": _pending_workflow_document(),
                }
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        pending_workflow_enabled=True,
        pending_workflow_dao=FakeDAO(),
    ).run("每个整点喊我打卡吧", _run_context())

    assert (
        result.content["summary"]
        == "每个整点打卡要从什么时候开始，持续到什么时候结束？"
    )
    assert saved[0]["id"] == "workflow_1"
    assert saved[0]["owner_user_id"] == "user-1"
    assert saved[0]["conversation_id"] == "conv-1"
    assert saved[0]["revision"] == 0
    assert saved[0]["document"]["status"] == "awaiting_user"


@pytest.mark.asyncio
async def test_pending_workflow_followup_uses_loaded_workflow_and_cas_updates():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    active = _active_pending_workflow(revision=4)
    updates = []

    class FakeDAO:
        def load_active_for_conversation(
            self, owner_user_id, conversation_id, now=None
        ):
            assert owner_user_id == "user-1"
            assert conversation_id == "conv-1"
            return active

        def cas_update_workflow(
            self,
            workflow_id,
            owner_user_id,
            conversation_id,
            expected_revision,
            document,
        ):
            updates.append(
                (
                    workflow_id,
                    owner_user_id,
                    conversation_id,
                    expected_revision,
                    document,
                )
            )
            return True

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            assert '"revision": 4' in input
            assert '"id": "workflow_1"' in input
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "打卡",
                    "trigger_at": "2026-05-06T02:00:00+00:00",
                    "workflow_update": {
                        **active["document"],
                        "status": "ready_to_execute",
                        "slots": {
                            "title": {"value": "打卡", "status": "filled"},
                            "start_at": {"value": "now", "status": "filled"},
                        },
                        "missing_fields": [],
                        "next_steps": ["execute_now"],
                    },
                }
            )

    class FakeExecutor:
        def execute(self, decision, run_context):
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：打卡"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
        pending_workflow_enabled=True,
        pending_workflow_dao=FakeDAO(),
    ).run("从现在到晚上七点", _run_context())

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：打卡"
    assert updates[0][0] == "workflow_1"
    assert updates[0][1] == "user-1"
    assert updates[0][2] == "conv-1"
    assert updates[0][3] == 4
    assert updates[0][4]["status"] == "ready_to_execute"


@pytest.mark.asyncio
async def test_pending_workflow_successful_execution_marks_workflow_completed():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    active = _active_pending_workflow(revision=4)
    updates = []

    class FakeDAO:
        def load_active_for_conversation(
            self, owner_user_id, conversation_id, now=None
        ):
            return active

        def cas_update_workflow(
            self,
            workflow_id,
            owner_user_id,
            conversation_id,
            expected_revision,
            document,
        ):
            updates.append((expected_revision, document["status"]))
            return True

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "打卡",
                    "trigger_at": "2026-05-06T02:00:00+00:00",
                    "workflow_update": _ready_pending_workflow_document(),
                }
            )

    class FakeExecutor:
        def execute(self, decision, run_context):
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：打卡"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
        pending_workflow_enabled=True,
        pending_workflow_dao=FakeDAO(),
    ).run("从现在到晚上七点", _run_context())

    assert result.ok is True
    assert updates == [(4, "ready_to_execute"), (5, "executing"), (6, "completed")]


@pytest.mark.asyncio
async def test_pending_workflow_terminal_cas_failure_closes_executing_workflow():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    active = _active_pending_workflow(revision=4)
    cas_updates = []
    forced_terminals = []

    class FakeDAO:
        def load_active_for_conversation(
            self, owner_user_id, conversation_id, now=None
        ):
            return active

        def cas_update_workflow(
            self,
            workflow_id,
            owner_user_id,
            conversation_id,
            expected_revision,
            document,
        ):
            cas_updates.append((expected_revision, document["status"]))
            return document["status"] != "completed"

        def mark_terminal_workflow_from_executing(
            self,
            workflow_id,
            owner_user_id,
            conversation_id,
            document,
        ):
            forced_terminals.append(document["status"])
            return True

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "打卡",
                    "trigger_at": "2026-05-06T02:00:00+00:00",
                    "workflow_update": _ready_pending_workflow_document(),
                }
            )

    class FakeExecutor:
        def execute(self, decision, run_context):
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：打卡"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
        pending_workflow_enabled=True,
        pending_workflow_dao=FakeDAO(),
    ).run("从现在到晚上七点", _run_context())

    assert result.ok is True
    assert cas_updates == [(4, "ready_to_execute"), (5, "executing"), (6, "completed")]
    assert forced_terminals == ["completed"]


@pytest.mark.asyncio
async def test_pending_workflow_illegal_transition_preserves_existing_workflow(caplog):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    active = _active_pending_workflow(revision=2)

    class FakeDAO:
        def load_active_for_conversation(
            self, owner_user_id, conversation_id, now=None
        ):
            return active

        def cas_update_workflow(
            self,
            workflow_id,
            owner_user_id,
            conversation_id,
            expected_revision,
            document,
        ):
            raise AssertionError("illegal transition must not be persisted")

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_question": "还需要什么？",
                    "workflow_update": {**active["document"], "status": "completed"},
                }
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        pending_workflow_enabled=True,
        pending_workflow_dao=FakeDAO(),
    ).run("继续", _run_context())

    assert result.content["summary"] == "还需要什么？"
    assert "workflow_invariant_violation" in caplog.text


@pytest.mark.asyncio
async def test_pending_workflow_illegal_slot_transition_preserves_existing_workflow(
    caplog,
):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    active = _active_pending_workflow(
        revision=2,
        document=_pending_workflow_document(
            slots={"title": {"value": "打卡", "status": "filled"}},
            missing_fields=[],
        ),
    )

    class FakeDAO:
        def load_active_for_conversation(
            self, owner_user_id, conversation_id, now=None
        ):
            return active

        def cas_update_workflow(
            self,
            workflow_id,
            owner_user_id,
            conversation_id,
            expected_revision,
            document,
        ):
            raise AssertionError("illegal slot transition must not be persisted")

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_question": "还需要什么？",
                    "workflow_update": {
                        **active["document"],
                        "slots": {"title": {"value": None, "status": "missing"}},
                        "missing_fields": ["title"],
                    },
                }
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        pending_workflow_enabled=True,
        pending_workflow_dao=FakeDAO(),
    ).run("继续", _run_context())

    assert result.content["summary"] == "还需要什么？"
    assert "workflow_invariant_violation" in caplog.text


@pytest.mark.asyncio
async def test_pending_workflow_invalid_schema_is_logged_and_ignored(caplog):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    active = _active_pending_workflow(revision=2)

    class FakeDAO:
        def load_active_for_conversation(
            self, owner_user_id, conversation_id, now=None
        ):
            return active

        def cas_update_workflow(
            self,
            workflow_id,
            owner_user_id,
            conversation_id,
            expected_revision,
            document,
        ):
            raise AssertionError("invalid workflow schema must not be persisted")

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_question": "还差结束时间。",
                    "workflow_update": {"id": "workflow_1", "unexpected": "field"},
                }
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        pending_workflow_enabled=True,
        pending_workflow_dao=FakeDAO(),
    ).run("从现在开始", _run_context())

    assert result.content["summary"] == "还差结束时间。"
    assert "workflow_schema_invalid" in caplog.text


@pytest.mark.asyncio
async def test_pending_workflow_invalid_schema_does_not_block_v0_execution(caplog):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    active = _active_pending_workflow(revision=2)

    class FakeDAO:
        def load_active_for_conversation(
            self, owner_user_id, conversation_id, now=None
        ):
            return active

        def cas_update_workflow(
            self,
            workflow_id,
            owner_user_id,
            conversation_id,
            expected_revision,
            document,
        ):
            raise AssertionError("invalid workflow schema must not be persisted")

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "打卡",
                    "trigger_at": "2026-05-06T02:00:00+00:00",
                    "workflow_update": {"id": "workflow_1", "unexpected": "field"},
                }
            )

    class FakeExecutor:
        def execute(self, decision, run_context):
            return SimpleNamespace(
                name="reminder",
                ok=True,
                content={"summary": "已创建提醒：打卡"},
                error=None,
                metadata={},
            )

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FakeExecutor(),
        pending_workflow_enabled=True,
        pending_workflow_dao=FakeDAO(),
    ).run("从现在到晚上七点", _run_context())

    assert result.ok is True
    assert result.content["summary"] == "已创建提醒：打卡"
    assert "workflow_schema_invalid" in caplog.text


@pytest.mark.asyncio
async def test_pending_workflow_cas_failure_is_logged_and_dropped(caplog):
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    active = _active_pending_workflow(revision=3)

    class FakeDAO:
        def __init__(self):
            self.loads = 0

        def load_active_for_conversation(
            self, owner_user_id, conversation_id, now=None
        ):
            self.loads += 1
            if self.loads == 1:
                return active
            return _active_pending_workflow(
                revision=4,
                document={
                    **active["document"],
                    "slots": {
                        "title": {"value": "打卡", "status": "filled"},
                        "start_at": {"value": "now", "status": "filled"},
                    },
                    "missing_fields": [],
                    "status": "ready_to_execute",
                },
            )

        def cas_update_workflow(
            self,
            workflow_id,
            owner_user_id,
            conversation_id,
            expected_revision,
            document,
        ):
            return False

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "clarify",
                    "action": "",
                    "clarification_question": "还差结束时间。",
                    "workflow_update": {
                        **active["document"],
                        "status": "ready_to_execute",
                        "slots": {
                            "title": {"value": "打卡", "status": "filled"},
                            "start_at": {"value": "now", "status": "filled"},
                        },
                        "missing_fields": [],
                        "next_steps": ["execute_now"],
                    },
                }
            )

    dao = FakeDAO()
    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        pending_workflow_enabled=True,
        pending_workflow_dao=dao,
    ).run("从现在开始", _run_context())

    assert dao.loads == 2
    assert result.content["workflow_status"] == "ready_to_execute"
    assert result.content["missing_fields"] == ()
    assert "workflow_concurrent_write_dropped" in caplog.text


@pytest.mark.asyncio
async def test_pending_workflow_does_not_execute_before_ready():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    saved = []

    class FakeDAO:
        def load_active_for_conversation(
            self, owner_user_id, conversation_id, now=None
        ):
            return None

        def upsert_new_active_workflow(self, document, now=None):
            saved.append(document)
            return True

    class PrimaryAgent:
        async def arun(self, *, input, session_state):
            return SimpleNamespace(
                content={
                    "intent_type": "crud",
                    "action": "create",
                    "title": "打卡",
                    "trigger_at": "2026-05-06T02:00:00+00:00",
                    "workflow_update": _pending_workflow_document(),
                }
            )

    class FailingExecutor:
        def execute(self, decision, run_context):
            raise AssertionError("workflow-backed decisions must be ready to execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FailingExecutor(),
        pending_workflow_enabled=True,
        pending_workflow_dao=FakeDAO(),
    ).run("从现在开始", _run_context())

    assert saved[0]["document"]["status"] == "awaiting_user"
    assert result.ok is False
    assert result.error == "ReminderDetectInvalidDecision"
    assert result.metadata["durable_write"] is False


@pytest.mark.asyncio
async def test_pending_workflow_high_frequency_guard_runs_before_persistence():
    from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort

    class FakeDAO:
        def load_active_for_conversation(
            self, owner_user_id, conversation_id, now=None
        ):
            return None

        def upsert_new_active_workflow(self, document, now=None):
            raise AssertionError("guarded decision must not persist workflow")

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
                    "workflow_update": _ready_pending_workflow_document(),
                }
            )

    class FailingExecutor:
        def execute(self, decision, run_context):
            raise AssertionError("guarded high-frequency decision must not execute")

    result = await ReminderIntentPort(
        detector_agent=PrimaryAgent(),
        retry_agent=None,
        command_executor=FailingExecutor(),
        pending_workflow_enabled=True,
        pending_workflow_dao=FakeDAO(),
    ).run("每小时提醒我冥想", _run_context())

    assert result.ok is True
    assert result.content["action"] == "clarify"
