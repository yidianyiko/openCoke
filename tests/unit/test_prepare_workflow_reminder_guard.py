# -*- coding: utf-8 -*-

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_structured_reminder_detect_decision_executes_visible_tool(monkeypatch):
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    from agent.agno_agent.tools.tool_result import append_tool_result
    from agent.agno_agent.workflows import prepare_workflow
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []
    reminder_response.content = ReminderDetectDecision(
        intent_type="crud",
        action="create",
        title="喝水",
        trigger_at="2026-04-29T18:00:00+09:00",
    )

    calls = []

    def fake_visible_reminder_tool(**kwargs):
        calls.append(kwargs)
        append_tool_result(
            session_state,
            tool_name="提醒操作",
            ok=True,
            result_summary="已创建提醒：喝水",
            extra_notes="action=create",
        )
        return "已创建提醒：喝水"

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日14时27分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    monkeypatch.setattr(
        prepare_workflow.visible_reminder_tool,
        "entrypoint",
        fake_visible_reminder_tool,
    )

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock()
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("18:00提醒我喝水", session_state)

    assert calls == [
        {
            "action": "create",
            "title": "喝水",
            "trigger_at": "2026-04-29T18:00:00+09:00",
            "reminder_id": None,
            "keyword": None,
            "new_title": None,
            "new_trigger_at": None,
            "rrule": None,
            "operations": None,
        }
    ]
    assert result["session_state"]["tool_results"][0]["ok"] is True


@pytest.mark.asyncio
async def test_invalid_structured_reminder_decision_retries_with_fast_agent(
    monkeypatch,
):
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    from agent.agno_agent.tools.tool_result import append_tool_result
    from agent.agno_agent.workflows import prepare_workflow
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    invalid_response = MagicMock()
    invalid_response.metrics = None
    invalid_response.tools = []
    invalid_response.content = {
        "intent_type": "clarify",
        "action": "create",
        "title": "打卡",
    }

    retry_response = MagicMock()
    retry_response.metrics = None
    retry_response.tools = []
    retry_response.content = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        deadline_at="2026-04-29T20:00:00+09:00",
        schedule_basis="explicit_cadence",
        schedule_evidence="每小时",
        operations=[
            {
                "action": "create",
                "title": "打卡",
                "trigger_at": "2026-04-29T16:51:00+09:00",
            }
        ],
    )

    calls = []

    def fake_visible_reminder_tool(**kwargs):
        calls.append(kwargs)
        append_tool_result(
            session_state,
            tool_name="提醒操作",
            ok=True,
            result_summary="已创建提醒：打卡",
            extra_notes="action=create",
        )
        return "已创建提醒：打卡"

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日15时51分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    monkeypatch.setattr(
        prepare_workflow.visible_reminder_tool,
        "entrypoint",
        fake_visible_reminder_tool,
    )

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_retry_agent"
        ) as reminder_detect_retry_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_response = MagicMock()
        orchestrator_response.metrics = None
        orchestrator_response.content = {
            "need_context_retrieve": False,
            "need_reminder_detect": True,
            "need_web_search": False,
            "need_timezone_update": False,
            "timezone_action": "none",
        }
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(return_value=invalid_response)
        reminder_detect_retry_agent.arun = AsyncMock(return_value=retry_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("每小时打卡，到晚上8点", session_state)

    reminder_detect_retry_agent.arun.assert_awaited_once()
    assert result["session_state"]["prepare_reminder_detect_retry_used"] is True
    assert calls[0]["action"] == "batch"
    assert calls[0]["operations"] == [
        {
            "action": "create",
            "title": "打卡",
            "trigger_at": "2026-04-29T16:51:00+09:00",
        }
    ]


@pytest.mark.asyncio
async def test_invalid_structured_reminder_retry_failure_records_tool_result(
    monkeypatch,
):
    from agent.agno_agent.workflows import prepare_workflow
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    invalid_response = MagicMock()
    invalid_response.metrics = None
    invalid_response.tools = []
    invalid_response.content = '{"intent_type":"clarify","action":"create"}'

    async def slow_retry(*_args, **_kwargs):
        await asyncio.sleep(60)

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日15时51分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    monkeypatch.setattr(
        prepare_workflow,
        "_PREPARE_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS",
        0.01,
    )

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_retry_agent"
        ) as reminder_detect_retry_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_response = MagicMock()
        orchestrator_response.metrics = None
        orchestrator_response.content = {
            "need_context_retrieve": False,
            "need_reminder_detect": True,
            "need_web_search": False,
            "need_timezone_update": False,
            "timezone_action": "none",
        }
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(return_value=invalid_response)
        reminder_detect_retry_agent.arun = AsyncMock(side_effect=slow_retry)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("每小时打卡，到晚上8点", session_state)

    reminder_detect_retry_agent.arun.assert_awaited_once()
    [tool_result] = result["session_state"]["tool_results"]
    assert tool_result["ok"] is False
    assert (
        tool_result["extra_notes"]
        == "action=detect; error_code=ReminderDetectInvalidStructuredOutput"
    )


@pytest.mark.asyncio
async def test_invalid_retry_schedule_evidence_appends_clarification():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    invalid_response = MagicMock()
    invalid_response.metrics = None
    invalid_response.tools = []
    invalid_response.content = '{"intent_type":"clarify","action":"create"}'

    retry_response = MagicMock()
    retry_response.metrics = None
    retry_response.tools = []
    retry_response.content = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="19：00-20：00练腹",
        operations=[
            {
                "action": "create",
                "title": "练腹",
                "trigger_at": "2026-04-29T19:00:00+09:00",
            }
        ],
    )

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日09时47分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_retry_agent"
        ) as reminder_detect_retry_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_response = MagicMock()
        orchestrator_response.metrics = None
        orchestrator_response.content = {
            "need_context_retrieve": False,
            "need_reminder_detect": True,
            "need_web_search": False,
            "need_timezone_update": False,
            "timezone_action": "none",
        }
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(return_value=invalid_response)
        reminder_detect_retry_agent.arun = AsyncMock(return_value=retry_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run(
            "19：00-20：00练腹 请在这些时间点提醒我学习",
            session_state,
        )

    [tool_result] = result["session_state"]["tool_results"]
    assert tool_result == {
        "tool_name": "提醒操作",
        "ok": False,
        "result_summary": "提醒设置还没完成：请确认具体提醒频率或每个提醒时间。",
        "extra_notes": (
            "action=clarify; " "error_code=ReminderDetectInvalidScheduleEvidence"
        ),
    }


def test_bounded_rrule_operation_gets_deadline_until():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()
    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        deadline_at="2026-04-29T20:00:00+09:00",
        schedule_basis="explicit_cadence",
        schedule_evidence="每小时",
        operations=[
            {
                "action": "create",
                "title": "打卡",
                "trigger_at": "2026-04-29T16:00:00+09:00",
                "rrule": "FREQ=HOURLY;INTERVAL=1",
            }
        ],
    )

    assert workflow._dump_reminder_operations(decision) == [
        {
            "action": "create",
            "title": "打卡",
            "trigger_at": "2026-04-29T16:00:00+09:00",
            "rrule": "FREQ=HOURLY;INTERVAL=1;UNTIL=20260429T110000Z",
        }
    ]


def test_reminder_decision_evidence_must_come_from_current_message():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()
    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_cadence",
        schedule_evidence="每10分钟",
        operations=[
            {
                "action": "create",
                "title": "写作",
                "trigger_at": "2026-04-29T10:13:00+09:00",
            },
            {
                "action": "create",
                "title": "写作",
                "trigger_at": "2026-04-29T10:23:00+09:00",
            },
        ],
    )

    assert workflow._validate_reminder_decision_evidence(
        decision,
        "我10：13-11：00要写个个人陈述，提醒我保持专注",
    )


def test_explicit_occurrence_evidence_must_contain_each_create_time():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()
    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="11点10分还有12点提醒我一下",
        operations=[
            {
                "action": "create",
                "title": "提醒",
                "trigger_at": "2026-04-30T11:10:00+09:00",
            },
            {
                "action": "create",
                "title": "提醒",
                "trigger_at": "2026-04-30T12:00:00+09:00",
            },
        ],
    )

    assert not workflow._validate_reminder_decision_evidence(
        decision,
        "11点10分还有12点提醒我一下",
    )

    hallucinated = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="11点10分还有12点提醒我一下",
        operations=[
            {
                "action": "create",
                "title": "提醒",
                "trigger_at": "2026-04-30T11:10:00+09:00",
            },
            {
                "action": "create",
                "title": "提醒",
                "trigger_at": "2026-04-30T11:40:00+09:00",
            },
        ],
    )
    assert workflow._validate_reminder_decision_evidence(
        hallucinated,
        "11点10分还有12点提醒我一下",
    )


def test_explicit_occurrence_evidence_accepts_chinese_daypart_times():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()
    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="晚上9点一次，晚上11点一次，提醒我完成学习任务打卡",
        operations=[
            {
                "action": "create",
                "title": "完成学习任务打卡",
                "trigger_at": "2026-04-29T21:00:00+09:00",
            },
            {
                "action": "create",
                "title": "完成学习任务打卡",
                "trigger_at": "2026-04-29T23:00:00+09:00",
            },
        ],
    )

    assert not workflow._validate_reminder_decision_evidence(
        decision,
        "上午10点一次，中午12点一次，下午5点一次，晚上9点一次，晚上11点一次，提醒我完成学习任务打卡",
    )


def test_explicit_occurrence_evidence_rejects_time_range_boundaries():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()
    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="11-11：30 吃饭",
        operations=[
            {
                "action": "create",
                "title": "吃饭",
                "trigger_at": "2026-04-29T11:00:00+09:00",
            },
            {
                "action": "create",
                "title": "吃饭",
                "trigger_at": "2026-04-29T11:30:00+09:00",
            },
        ],
    )

    assert (
        workflow._validate_reminder_decision_evidence(
            decision,
            "这是我今天的任务 11-11：30 吃饭，请在这些时间点提醒我学习",
        )
        == "explicit_occurrences evidence uses a time range boundary, not a concrete reminder time"
    )


def test_explicit_occurrence_evidence_rejects_colon_time_range_boundary():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()
    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="19：00-20：00练腹",
        operations=[
            {
                "action": "create",
                "title": "练腹",
                "trigger_at": "2026-04-29T19:00:00+09:00",
            }
        ],
    )

    assert (
        workflow._validate_reminder_decision_evidence(
            decision,
            "19：00-20：00练腹 请在这些时间点提醒我学习",
        )
        == "explicit_occurrences evidence uses a time range boundary, not a concrete reminder time"
    )


def test_explicit_occurrence_evidence_accepts_bare_hour_reminder_time():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()
    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        schedule_basis="explicit_occurrences",
        schedule_evidence="11提醒我吃饭",
        operations=[
            {
                "action": "create",
                "title": "吃饭",
                "trigger_at": "2026-04-29T11:00:00+09:00",
            }
        ],
    )

    assert not workflow._validate_reminder_decision_evidence(
        decision,
        "今天11提醒我吃饭",
    )


def test_single_create_rejected_for_multi_clause_reminder_batch():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()
    decision = ReminderDetectDecision(
        intent_type="crud",
        action="create",
        title="练腹肌",
        trigger_at="2026-04-29T19:00:00+09:00",
        schedule_basis="one_shot",
    )

    assert (
        workflow._validate_reminder_decision_evidence(
            decision,
            "你还需要在15：30提醒我吃饭；16：40提醒我洗澡；17：20提醒我看法考网课和做题；19：00提醒我去练腹肌",
        )
        == "multiple reminder clauses require batch operations, not a single create"
    )


def test_retry_input_includes_invalid_schedule_evidence_reason():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()
    retry_input = workflow._build_reminder_retry_input(
        "你还需要在15：30提醒我吃饭；16：40提醒我洗澡",
        {
            "conversation": {
                "conversation_info": {"time_str": "2026年04月29日09时50分"}
            },
            "user": {"timezone": "Asia/Tokyo"},
            "prepare_reminder_detect_invalid_schedule_evidence": (
                "multiple reminder clauses require batch operations, not a single create"
            ),
        },
    )

    assert "Invalid previous decision" in retry_input
    assert "multiple reminder clauses require batch operations" in retry_input


def test_structured_clarify_decision_appends_direct_question():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()
    response = MagicMock()
    response.content = ReminderDetectDecision(
        intent_type="clarify",
        clarification_question="你希望我多久提醒你一次？",
    )
    session_state = {"tool_results": []}

    assert workflow._execute_structured_reminder_decision(
        response,
        session_state,
        "10点到11点写作，提醒我专注",
    )
    assert session_state["tool_results"] == [
        {
            "tool_name": "提醒操作",
            "ok": False,
            "result_summary": "你希望我多久提醒你一次？",
            "extra_notes": "action=clarify; error_code=ReminderDetectClarify",
        }
    ]


def test_invalid_schedule_evidence_retry_failure_appends_clarification():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()
    session_state = {
        "prepare_reminder_detect_invalid_schedule_evidence": (
            "schedule_evidence is not present in the current message"
        ),
        "tool_results": [],
    }

    assert workflow._append_invalid_schedule_evidence_clarification(session_state)
    assert session_state["tool_results"] == [
        {
            "tool_name": "提醒操作",
            "ok": False,
            "result_summary": "提醒设置还没完成：请确认具体提醒频率或每个提醒时间。",
            "extra_notes": (
                "action=clarify; " "error_code=ReminderDetectInvalidScheduleEvidence"
            ),
        }
    ]
    assert "prepare_reminder_detect_invalid_schedule_evidence" not in session_state


def test_bounded_rrule_operation_keeps_existing_count():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    assert (
        workflow._bound_rrule_to_deadline(
            "FREQ=HOURLY;COUNT=2",
            "2026-04-29T20:00:00+09:00",
        )
        == "FREQ=HOURLY;COUNT=2"
    )


def test_bounded_rrule_operation_rewrites_non_utc_until():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    assert (
        workflow._bound_rrule_to_deadline(
            "FREQ=HOURLY;UNTIL=2026-04-29T20:00:00+09:00",
            "2026-04-29T20:00:00+09:00",
        )
        == "FREQ=HOURLY;UNTIL=20260429T110000Z"
    )


def test_rrule_operation_normalizes_iso_until_without_deadline():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    assert (
        workflow._bound_rrule_to_deadline(
            "FREQ=HOURLY;UNTIL=2026-04-29T20:00:00+09:00",
            "",
        )
        == "FREQ=HOURLY;UNTIL=20260429T110000Z"
    )


def test_bounded_rrule_operation_keeps_valid_utc_until():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    assert (
        workflow._bound_rrule_to_deadline(
            "FREQ=HOURLY;UNTIL=20260429T110000Z",
            "2026-04-29T20:00:00+09:00",
        )
        == "FREQ=HOURLY;UNTIL=20260429T110000Z"
    )


@pytest.mark.asyncio
async def test_explicit_reminder_request_skips_orchestrator_and_runs_detector_fast():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日14时27分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock()
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("11点10分还有12点提醒我一下", session_state)

    orchestrator_agent.arun.assert_not_awaited()
    reminder_detect_agent.arun.assert_awaited_once()
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is True
    assert result["session_state"]["orchestrator"]["need_context_retrieve"] is False


@pytest.mark.asyncio
async def test_no_disturb_reminder_stop_request_skips_orchestrator_and_runs_detector():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日14时27分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock()
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("今天学习结束，晚安，不要打扰我了", session_state)

    orchestrator_agent.arun.assert_not_awaited()
    reminder_detect_agent.arun.assert_awaited_once()
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is True
    assert result["session_state"]["prepare_reminder_intent_hint"] == "stop_or_cancel"


@pytest.mark.asyncio
async def test_explicit_reminder_request_runs_detector_when_orchestrator_misses_it():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "普通对话",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": False,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时14分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run(
            "请在一分钟后提醒我：这是本地一分钟主动提醒烟测。",
            session_state,
        )

    reminder_detect_agent.arun.assert_awaited_once()
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is True


@pytest.mark.asyncio
async def test_nickname_only_call_me_does_not_run_reminder_detector():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "用户希望被称呼为小凡",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": False,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时14分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("叫我小凡就行了", session_state)

    reminder_detect_agent.arun.assert_not_awaited()
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is False


@pytest.mark.asyncio
async def test_call_me_with_time_runs_reminder_detector_when_orchestrator_misses_it():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "普通对话",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": False,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时14分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("七点叫我可以么", session_state)

    reminder_detect_agent.arun.assert_awaited_once()
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is True


@pytest.mark.asyncio
async def test_vague_reminder_capability_question_uses_detector_not_direct_reply():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "用户询问提醒能力",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": True,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时14分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("你可以循环提醒我吗", session_state)

    reminder_detect_agent.arun.assert_awaited_once()
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is True
    assert "direct_reply" not in result["session_state"]


@pytest.mark.asyncio
async def test_underspecified_reminder_request_uses_detector_not_direct_reply():
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "bare reminder request",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": True,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时14分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("你提醒我一下", session_state)

    reminder_detect_agent.arun.assert_awaited_once()
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is True
    assert "direct_reply" not in result["session_state"]


@pytest.mark.asyncio
async def test_orchestrator_timeout_still_runs_detector_for_explicit_reminder(
    monkeypatch,
):
    from agent.agno_agent.workflows import prepare_workflow
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    async def slow_orchestrator(*_args, **_kwargs):
        await asyncio.sleep(60)

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时30分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    monkeypatch.setattr(
        prepare_workflow,
        "_PREPARE_ORCHESTRATOR_TIMEOUT_SECONDS",
        0.01,
    )

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(side_effect=slow_orchestrator)
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run(
            "今天17:57提醒我喝水，17:58提醒我锻炼",
            session_state,
        )

    assert result["session_state"]["prepare_orchestrator_skipped_for_reminder"] is True
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is True
    reminder_detect_agent.arun.assert_awaited_once()


@pytest.mark.asyncio
async def test_orchestrator_timeout_routes_time_prefixed_reminder_to_detector(
    monkeypatch,
):
    from agent.agno_agent.workflows import prepare_workflow
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    async def slow_orchestrator(*_args, **_kwargs):
        await asyncio.sleep(60)

    reminder_response = MagicMock()
    reminder_response.metrics = None
    reminder_response.tools = []

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日11时51分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    monkeypatch.setattr(
        prepare_workflow,
        "_PREPARE_ORCHESTRATOR_TIMEOUT_SECONDS",
        0.01,
    )

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(side_effect=slow_orchestrator)
        reminder_detect_agent.arun = AsyncMock(return_value=reminder_response)
        context_retrieve_tool.return_value = {}

        result = await workflow.run(
            "另外10:40提醒思考一个问题：工作应该去做“非我不可”的事情",
            session_state,
        )

    assert result["session_state"]["prepare_orchestrator_skipped_for_reminder"] is True
    assert result["session_state"]["orchestrator"]["need_reminder_detect"] is True
    reminder_detect_agent.arun.assert_awaited_once()


@pytest.mark.asyncio
async def test_reminder_detect_timeout_records_failed_tool_result(monkeypatch):
    from agent.agno_agent.workflows import prepare_workflow
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "提醒请求",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": True,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    async def slow_reminder_detect(*_args, **_kwargs):
        await asyncio.sleep(60)

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时30分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    monkeypatch.setattr(
        prepare_workflow,
        "_PREPARE_REMINDER_DETECT_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        prepare_workflow,
        "_PREPARE_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS",
        0.01,
    )

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_retry_agent"
        ) as reminder_detect_retry_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(side_effect=slow_reminder_detect)
        reminder_detect_retry_agent.arun = AsyncMock(side_effect=slow_reminder_detect)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("稍后提醒我喝水", session_state)

    [tool_result] = result["session_state"]["tool_results"]
    assert result["session_state"]["prepare_reminder_detect_timeout"] is True
    assert tool_result["tool_name"] == "提醒操作"
    assert tool_result["ok"] is False
    assert "提醒识别超时" in tool_result["result_summary"]


def test_reminder_detect_retry_default_timeout_allows_fast_llm_budget():
    from agent.agno_agent.workflows import prepare_workflow

    assert prepare_workflow._PREPARE_REMINDER_DETECT_TIMEOUT_SECONDS <= 30.0
    assert prepare_workflow._PREPARE_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS >= 80.0
    assert (
        prepare_workflow._PREPARE_REMINDER_DETECT_TIMEOUT_SECONDS
        + prepare_workflow._PREPARE_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS
        <= 110.0
    )


@pytest.mark.asyncio
async def test_reminder_detect_timeout_retries_with_short_context_llm(monkeypatch):
    from agent.agno_agent.tools.tool_result import append_tool_result
    from agent.agno_agent.workflows import prepare_workflow
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "提醒请求",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": True,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    async def slow_reminder_detect(*_args, **_kwargs):
        await asyncio.sleep(60)

    retry_response = MagicMock()
    retry_response.metrics = None
    retry_response.tools = [{"tool_name": "visible_reminder_tool"}]

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时30分",
                "chat_history": [{"role": "user", "content": "old context"}],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }

    async def retry_detect(*_args, **_kwargs):
        append_tool_result(
            session_state,
            tool_name="提醒操作",
            ok=True,
            result_summary="已创建提醒：喝水",
        )
        return retry_response

    monkeypatch.setattr(
        prepare_workflow,
        "_PREPARE_REMINDER_DETECT_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        prepare_workflow,
        "_PREPARE_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS",
        0.01,
    )

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_retry_agent"
        ) as reminder_detect_retry_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(side_effect=slow_reminder_detect)
        reminder_detect_retry_agent.arun = AsyncMock(side_effect=retry_detect)
        context_retrieve_tool.return_value = {}

        result = await workflow.run("稍后提醒我喝水", session_state)

    retry_input = reminder_detect_retry_agent.arun.await_args.kwargs["input"]
    assert "最近对话上下文" not in retry_input
    assert "当前用户消息" in retry_input
    assert "invalid structured output" in retry_input
    assert "ReminderDetectDecision" in retry_input
    assert "explicitly asks for a reminder" in retry_input
    assert 'action="delete"' in retry_input
    assert "不用叫我" in retry_input
    assert "asks to update, complete, or list reminders" in retry_input
    assert "enumerate each concrete one-shot occurrence" in retry_input
    assert "Do not use RRULE for bounded cadence" in retry_input
    assert "schedule_basis" in retry_input
    assert "schedule_evidence" in retry_input
    assert "same-message stop boundary" in retry_input
    assert "not as delete/cancel" in retry_input
    assert "skip past occurrences" in retry_input
    assert "create only future occurrences" in retry_input
    assert "without concrete occurrence" in retry_input
    assert "Do not infer numeric intervals" in retry_input
    assert "semantically modifies" in retry_input
    assert "neighboring independent schedule item" in retry_input
    assert "task time range supplies boundaries" in retry_input
    assert "schedule-only items" in retry_input
    assert 'Never return action="batch" with operations=[]' in retry_input
    assert "not enough schedule_evidence" in retry_input
    assert "one create operation for each safe clause" in retry_input
    assert "Do not keep only the last item" in retry_input
    assert "action=create is invalid" in retry_input
    assert (
        "operations count must equal the number of safe reminder clauses" in retry_input
    )
    assert "Chinese semicolon lists may omit the repeated reminder verb" in retry_input
    assert "same language" in retry_input
    assert "15:57, 16:47, 17:37" in retry_input
    assert result["session_state"]["prepare_reminder_detect_timeout"] is True
    assert result["session_state"]["prepare_reminder_detect_retry_used"] is True
    assert result["session_state"]["tool_results"][0]["ok"] is True
    assert (
        "提醒识别超时"
        not in result["session_state"]["tool_results"][0]["result_summary"]
    )


@pytest.mark.asyncio
async def test_reminder_detect_timeout_does_not_create_with_local_parser(monkeypatch):
    from agent.agno_agent.workflows import prepare_workflow
    from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

    workflow = PrepareWorkflow()

    orchestrator_response = MagicMock()
    orchestrator_response.content = MagicMock()
    orchestrator_response.metrics = None
    orchestrator_response.content.model_dump.return_value = {
        "inner_monologue": "提醒请求",
        "need_context_retrieve": False,
        "context_retrieve_params": {},
        "need_reminder_detect": True,
        "need_web_search": False,
        "web_search_query": "",
        "need_timezone_update": False,
        "timezone_action": "none",
        "timezone_value": "",
    }

    async def slow_reminder_detect(*_args, **_kwargs):
        await asyncio.sleep(60)

    session_state = {
        "message_source": "user",
        "conversation": {
            "conversation_info": {
                "time_str": "2026年04月29日02时30分",
                "chat_history": [],
            }
        },
        "character": {"_id": "char-1"},
        "user": {"id": "user-1", "timezone": "Asia/Tokyo"},
    }
    local_tool_calls = []

    def fake_visible_reminder_tool(**kwargs):
        local_tool_calls.append(kwargs)
        return "should not be called"

    monkeypatch.setattr(
        prepare_workflow,
        "_PREPARE_REMINDER_DETECT_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        prepare_workflow,
        "_PREPARE_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        prepare_workflow,
        "visible_reminder_tool",
        fake_visible_reminder_tool,
        raising=False,
    )

    with (
        patch(
            "agent.agno_agent.workflows.prepare_workflow.orchestrator_agent"
        ) as orchestrator_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_agent"
        ) as reminder_detect_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.reminder_detect_retry_agent"
        ) as reminder_detect_retry_agent,
        patch(
            "agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool"
        ) as context_retrieve_tool,
    ):
        orchestrator_agent.arun = AsyncMock(return_value=orchestrator_response)
        reminder_detect_agent.arun = AsyncMock(side_effect=slow_reminder_detect)
        reminder_detect_retry_agent.arun = AsyncMock(side_effect=slow_reminder_detect)
        context_retrieve_tool.return_value = {}

        result = await workflow.run(
            "明天继续提醒我看文章，要看完，然后要写学习笔记。小说明天也继续写！",
            session_state,
        )

    assert local_tool_calls == []
    [tool_result] = result["session_state"]["tool_results"]
    assert result["session_state"]["prepare_reminder_detect_timeout"] is True
    assert tool_result["ok"] is False
    assert "提醒识别超时" in tool_result["result_summary"]
