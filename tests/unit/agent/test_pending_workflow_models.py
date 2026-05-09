from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError


def _workflow_payload(**overrides):
    now = datetime(2026, 5, 9, 1, 0, tzinfo=UTC)
    payload = {
        "id": "workflow_1",
        "kind": "reminder_create",
        "status": "awaiting_user",
        "origin": {
            "conversation_id": "conv-1",
            "message_ids": ["msg-1"],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
        },
        "goal": "Set up hourly check-in reminders",
        "slots": {
            "title": {"value": "打卡", "status": "filled"},
            "start_at": {"value": None, "status": "missing"},
            "deadline_at": {"value": None, "status": "missing"},
        },
        "missing_fields": ["start_at", "deadline_at"],
        "assumptions": [],
        "constraints": [],
        "next_steps": ["ask_user"],
        "payload": {"reminder": {"draft_operations": []}},
    }
    payload.update(overrides)
    return payload


def test_pending_workflow_model_accepts_spec_shape():
    from agent.agno_agent.runtime.pending_workflow import PendingWorkflowEnvelope

    workflow = PendingWorkflowEnvelope.model_validate(_workflow_payload())

    assert workflow.id == "workflow_1"
    assert workflow.kind == "reminder_create"
    assert workflow.missing_fields == ("start_at", "deadline_at")
    assert workflow.payload.reminder.draft_operations == ()


def test_pending_workflow_model_accepts_typed_draft_operations():
    from agent.agno_agent.runtime.pending_workflow import PendingWorkflowEnvelope

    workflow = PendingWorkflowEnvelope.model_validate(
        _workflow_payload(
            payload={
                "reminder": {
                    "draft_operations": [
                        {
                            "action": "create",
                            "title": "打卡",
                            "trigger_at": "2026-05-09T02:00:00+00:00",
                        }
                    ]
                }
            }
        )
    )

    assert workflow.payload.reminder.draft_operations[0].action == "create"
    assert workflow.payload.reminder.draft_operations[0].title == "打卡"


def test_pending_workflow_model_rejects_unknown_fields():
    from agent.agno_agent.runtime.pending_workflow import PendingWorkflowEnvelope

    with pytest.raises(ValidationError):
        PendingWorkflowEnvelope.model_validate(
            _workflow_payload(unexpected="not allowed")
        )


def test_ready_with_missing_fields_is_normalized_to_awaiting_user():
    from agent.agno_agent.runtime.pending_workflow import (
        PendingWorkflowEnvelope,
        normalize_workflow_invariants,
    )

    workflow = PendingWorkflowEnvelope.model_validate(
        _workflow_payload(status="ready_to_execute")
    )

    normalized, violations = normalize_workflow_invariants(workflow)

    assert normalized.status == "awaiting_user"
    assert violations == ("ready_with_missing_fields",)


def test_illegal_status_transition_is_rejected():
    from agent.agno_agent.runtime.pending_workflow import (
        PendingWorkflowEnvelope,
        validate_status_transition,
    )

    current = PendingWorkflowEnvelope.model_validate(_workflow_payload())
    proposed = PendingWorkflowEnvelope.model_validate(
        _workflow_payload(status="completed", missing_fields=[])
    )

    assert validate_status_transition(current.status, proposed.status) is False


def test_legal_ready_to_executing_transition_is_allowed():
    from agent.agno_agent.runtime.pending_workflow import validate_status_transition

    assert validate_status_transition("ready_to_execute", "executing") is True


def test_pending_workflow_schema_has_typed_slot_values_and_draft_operations():
    from agent.agno_agent.runtime.pending_workflow import PendingWorkflowEnvelope

    schema = PendingWorkflowEnvelope.model_json_schema()

    slot_value_schema = schema["$defs"]["WorkflowSlot"]["properties"]["value"]
    assert {"type": "string"} in slot_value_schema["anyOf"]
    assert {"type": "integer"} in slot_value_schema["anyOf"]
    assert {"type": "null"} in slot_value_schema["anyOf"]

    draft_operation_items = schema["$defs"]["ReminderWorkflowPayload"]["properties"][
        "draft_operations"
    ]["items"]
    assert draft_operation_items["$ref"] == "#/$defs/ReminderDraftOperation"
    assert "title" in schema["$defs"]["ReminderDraftOperation"]["properties"]
