import pytest
from pydantic import ValidationError


def test_reminder_detect_schema_normalizes_write_action_to_crud():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="clarify",
        action="create",
        title="喝水",
        trigger_at="2026-04-29T18:00:00+09:00",
    )

    assert decision.intent_type == "crud"


def test_reminder_detect_schema_rejects_naive_create_trigger_at():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError, match="trigger_at must include timezone"):
        ReminderDetectDecision(
            intent_type="crud",
            action="create",
            title="吃饭",
            trigger_at="2026-04-30T16:37:00",
        )


def test_reminder_detect_schema_requires_batch_operations():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(intent_type="crud", action="batch")


def test_reminder_detect_schema_requires_batch_create_fields():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="crud",
            action="batch",
            operations=[{"action": "create", "title": "提醒"}],
        )


def test_reminder_detect_schema_rejects_batch_operation_after_deadline():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="crud",
            action="batch",
            deadline_at="2026-04-29T18:00:00+09:00",
            operations=[
                {
                    "action": "create",
                    "title": "提醒",
                    "trigger_at": "2026-04-29T18:27:00+09:00",
                }
            ],
        )


def test_reminder_detect_schema_accepts_deadline_batch_rrule_operation():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

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

    assert decision.operations[0].rrule == "FREQ=HOURLY;INTERVAL=1"


def test_reminder_detect_schema_accepts_nightly_cadence_evidence():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="create",
        title="洗漱",
        trigger_at="2026-04-30T22:30:00+09:00",
        rrule="FREQ=DAILY;INTERVAL=1",
        schedule_basis="explicit_cadence",
        schedule_evidence="每晚",
    )

    assert decision.schedule_evidence == "每晚"


def test_reminder_detect_schema_accepts_batch_operation_before_deadline():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        deadline_at="2026-04-29T18:00:00+09:00",
        schedule_basis="explicit_cadence",
        schedule_evidence="每50分钟",
        operations=[
            {
                "action": "create",
                "title": "提醒",
                "trigger_at": "2026-04-29T17:37:00+09:00",
            }
        ],
    )

    assert decision.operations[0].trigger_at == "2026-04-29T17:37:00+09:00"


def test_reminder_detect_schema_rejects_batch_without_schedule_basis():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="crud",
            action="batch",
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


def test_reminder_detect_schema_rejects_single_create_batch_without_schedule_basis():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="crud",
            action="batch",
            operations=[
                {
                    "action": "create",
                    "title": "练腹肌",
                    "trigger_at": "2026-04-29T19:00:00+09:00",
                }
            ],
        )


def test_reminder_detect_schema_rejects_non_concrete_cadence_evidence():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="crud",
            action="batch",
            schedule_basis="explicit_cadence",
            schedule_evidence="keep me focused",
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


def test_reminder_detect_schema_rejects_time_range_as_cadence_evidence():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="crud",
            action="batch",
            schedule_basis="explicit_cadence",
            schedule_evidence="10:13-11:00",
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


def test_reminder_detect_schema_accepts_explicit_occurrence_batch():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

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

    assert decision.schedule_basis == "explicit_occurrences"


def test_reminder_detect_agents_use_structured_decision_schema():
    from agent.agno_agent.agents import (
        reminder_detect_agent,
        reminder_detect_retry_agent,
    )
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    assert reminder_detect_agent.output_schema is ReminderDetectDecision
    assert reminder_detect_retry_agent.output_schema is ReminderDetectDecision
    assert not reminder_detect_agent.tools
    assert not reminder_detect_retry_agent.tools
    assert reminder_detect_agent.structured_outputs is True
    assert reminder_detect_retry_agent.structured_outputs is True
    assert reminder_detect_agent.use_json_mode is False
    assert reminder_detect_retry_agent.use_json_mode is False
    assert reminder_detect_retry_agent.model.max_tokens >= 6000
    assert len(reminder_detect_retry_agent.instructions) < (
        len(reminder_detect_agent.instructions) // 2
    )
    assert "short-context retry" in reminder_detect_retry_agent.instructions


def test_reminder_detect_clarification_question_schema_keeps_current_language():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    description = ReminderDetectDecision.model_fields[
        "clarification_question"
    ].description

    assert "same language as the current user message" in description
    assert "not the profile, prior messages, or retrieved context" in description


def test_reminder_detect_schedule_evidence_schema_rejects_vague_references():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    description = ReminderDetectDecision.model_fields["schedule_evidence"].description

    assert "not vague references like" in description
    assert "these time points" in description


def test_reminder_detect_trigger_schema_rejects_date_only_midnight_defaults():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    description = ReminderDetectDecision.model_fields["trigger_at"].description

    assert "Do not use midnight" in description
    assert "date-only" in description


def test_reminder_operation_schema_marks_update_fields_update_only():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderOperation

    assert "update only" in ReminderOperation.model_fields["new_title"].description
    assert (
        "do not use for create"
        in ReminderOperation.model_fields["new_trigger_at"].description
    )
