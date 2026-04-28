from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from agent.reminder.models import (
    AgentOutputTarget,
    ReminderCreateCommand,
    ReminderSchedule,
)
from scripts import eval_reminder_e2e_cases as e2e_eval


def test_builds_context_from_case_metadata_timestamp():
    case = e2e_eval.ReminderE2ECase(
        input="今天18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={
            "source_id": "conv-1",
            "from_user": "user-1",
            "timestamp": "2025-11-30 17:55:53",
        },
    )

    context = e2e_eval.build_case_context(case, index=7, timezone="Asia/Tokyo")

    assert context["user"]["id"] == "user-1"
    assert context["user"]["effective_timezone"] == "Asia/Tokyo"
    assert context["conversation"]["_id"] == "conv-1"
    assert context["conversation"]["conversation_info"]["time_str"] == (
        "2025年11月30日17时55分"
    )
    assert context["input_timestamp"] == int(
        datetime(2025, 11, 30, 17, 55, 53, tzinfo=e2e_eval.ZoneInfo("Asia/Tokyo"))
        .timestamp()
    )


@pytest.mark.asyncio
async def test_run_eval_processes_cases_concurrently_and_records_outputs():
    cases = [
        e2e_eval.ReminderE2ECase(
            input=f"{hour}:00提醒我喝水",
            expected_intent="reminder",
            matched_keywords=["提醒"],
            metadata={
                "source_id": f"conv-{hour}",
                "from_user": f"user-{hour}",
                "timestamp": "2026-04-28 11:30:00",
            },
        )
        for hour in (18, 19)
    ]
    started = 0
    release = asyncio.Event()

    async def fake_handle_message(context, input_message, **_kwargs):
        nonlocal started
        started += 1
        if started == 2:
            release.set()
        await asyncio.wait_for(release.wait(), timeout=1)
        runtime = e2e_eval.current_case_runtime()
        runtime.service.create(
            owner_user_id=context["user"]["id"],
            command=ReminderCreateCommand(
                title=input_message,
                schedule=ReminderSchedule(
                    anchor_at=datetime(2026, 4, 28, 18, 0, tzinfo=UTC),
                    local_date=datetime(2026, 4, 28, 18, 0, tzinfo=UTC).date(),
                    local_time=datetime(2026, 4, 28, 18, 0, tzinfo=UTC).time(),
                    timezone="UTC",
                    rrule=None,
                ),
                agent_output_target=AgentOutputTarget(
                    conversation_id=context["conversation"]["_id"],
                    character_id=context["character"]["id"],
                    route_key=context["delivery_route_key"],
                ),
                created_by_system="agent",
            ),
        )
        return ([{"message": "已设置提醒", "message_type": "text"}], context, False, False)

    results = await e2e_eval.run_eval(
        cases,
        offset=0,
        limit=None,
        timezone="Asia/Tokyo",
        concurrency=2,
        case_timeout_seconds=2,
        handle_message_func=fake_handle_message,
    )

    assert [result.passed for result in results] == [True, True]
    assert all(result.user_outputs for result in results)
    assert [len(result.created_reminders) for result in results] == [1, 1]
    assert started == 2


@pytest.mark.asyncio
async def test_trigger_validation_fires_created_one_shot_reminder_without_waiting():
    runtime = e2e_eval.CaseRuntime(
        case_index=0,
        now=datetime(2026, 4, 28, 11, 30, tzinfo=UTC),
    )
    reminder = runtime.service.create(
        owner_user_id="user-1",
        command=ReminderCreateCommand(
            title="喝水",
            schedule=ReminderSchedule(
                anchor_at=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
                local_date=datetime(2026, 4, 28, 12, 0, tzinfo=UTC).date(),
                local_time=datetime(2026, 4, 28, 12, 0, tzinfo=UTC).time(),
                timezone="UTC",
                rrule=None,
            ),
            agent_output_target=AgentOutputTarget("conv-1", "char-1", "route-1"),
            created_by_system="agent",
        ),
    )

    errors = await e2e_eval.validate_trigger_delivery(runtime)

    assert errors == []
    assert runtime.fire_events[0]["title"] == "喝水"
    assert runtime.reminder_dao.documents[reminder.id]["lifecycle_state"] == "completed"


def test_result_classification_flags_no_output_and_missing_crud():
    runtime = e2e_eval.CaseRuntime(
        case_index=0,
        now=datetime(2026, 4, 28, 11, 30, tzinfo=UTC),
    )
    case = e2e_eval.ReminderE2ECase(
        input="18:00提醒我喝水",
        expected_intent="reminder",
        matched_keywords=["提醒"],
        metadata={},
    )

    errors = e2e_eval.validate_case_observations(
        case,
        runtime,
        user_outputs=[],
        is_rollback=False,
        is_content_blocked=False,
    )

    assert "no_user_output" in errors
    assert "tool_not_called" in errors


def test_process_timeout_probe_terminates_blocking_worker():
    assert e2e_eval.run_process_timeout_probe(timeout_seconds=0.1) == "timeout"
