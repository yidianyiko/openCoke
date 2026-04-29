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


def test_reminder_detect_schema_accepts_batch_operation_before_deadline():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    decision = ReminderDetectDecision(
        intent_type="crud",
        action="batch",
        deadline_at="2026-04-29T18:00:00+09:00",
        operations=[
            {
                "action": "create",
                "title": "提醒",
                "trigger_at": "2026-04-29T17:37:00+09:00",
            }
        ],
    )

    assert decision.operations[0].trigger_at == "2026-04-29T17:37:00+09:00"


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
