import pytest
from pydantic import ValidationError


def test_reminder_detect_schema_disallows_write_fields_for_clarify():
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    with pytest.raises(ValidationError):
        ReminderDetectDecision(
            intent_type="clarify",
            action="create",
            title="喝水",
            trigger_at="2026-04-29T18:00:00+09:00",
        )


def test_reminder_detect_agents_use_structured_decision_schema():
    from agent.agno_agent.agents import (
        reminder_detect_agent,
        reminder_detect_retry_agent,
    )
    from agent.agno_agent.schemas.reminder_detect_schema import ReminderDetectDecision

    assert reminder_detect_agent.output_schema is ReminderDetectDecision
    assert reminder_detect_retry_agent.output_schema is ReminderDetectDecision
    assert reminder_detect_agent.structured_outputs is True
    assert reminder_detect_retry_agent.structured_outputs is True
    assert reminder_detect_agent.use_json_mode is False
    assert reminder_detect_retry_agent.use_json_mode is False
