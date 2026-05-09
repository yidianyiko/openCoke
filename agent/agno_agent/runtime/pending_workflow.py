from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

WorkflowKind = Literal[
    "reminder_create",
    "reminder_update",
    "reminder_cancel",
    "reminder_complete",
    "reminder_plan",
]
WorkflowStatus = Literal[
    "draft",
    "awaiting_user",
    "ready_to_execute",
    "executing",
    "completed",
    "cancelled",
    "expired",
    "failed",
]
SlotStatus = Literal[
    "missing",
    "filled",
    "assumed",
    "needs_confirmation",
    "invalid",
]
NextStep = Literal[
    "ask_user",
    "display_preview",
    "execute_now",
    "show_confirmation",
    "offer_modification",
    "notify_error",
    "no_action",
]
SlotValue = str | int | float | bool | None

ACTIVE_WORKFLOW_STATUSES = (
    "draft",
    "awaiting_user",
    "ready_to_execute",
    "executing",
)
TERMINAL_WORKFLOW_STATUSES = ("completed", "cancelled", "expired", "failed")

_LEGAL_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"awaiting_user", "ready_to_execute"},
    "awaiting_user": {"awaiting_user", "ready_to_execute", "cancelled", "expired"},
    "ready_to_execute": {"executing", "awaiting_user", "expired"},
    "executing": {"completed", "failed", "awaiting_user"},
    "completed": set(),
    "cancelled": set(),
    "expired": set(),
    "failed": set(),
}
_LEGAL_SLOT_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "missing": {"filled", "assumed", "needs_confirmation", "invalid"},
    "assumed": {"filled", "invalid"},
    "needs_confirmation": {"filled", "invalid"},
    "invalid": {"filled", "missing"},
    "filled": {"needs_confirmation", "invalid"},
}


class WorkflowOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    message_ids: tuple[str, ...] = Field(default_factory=tuple)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class WorkflowSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: SlotValue = None
    status: SlotStatus


class ReminderDraftOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["", "create", "update", "delete", "cancel", "complete", "list"] = ""
    title: str = ""
    trigger_at: str = ""
    reminder_id: str = ""
    keyword: str = ""
    new_title: str = ""
    new_trigger_at: str = ""
    rrule: str = ""
    deadline_at: str = ""


class ReminderWorkflowPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_operations: tuple[ReminderDraftOperation, ...] = Field(default_factory=tuple)


class WorkflowPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reminder: ReminderWorkflowPayload


class PendingWorkflowEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: WorkflowKind
    status: WorkflowStatus
    origin: WorkflowOrigin
    goal: str
    slots: dict[str, WorkflowSlot]
    missing_fields: tuple[str, ...] = Field(default_factory=tuple)
    assumptions: tuple[str, ...] = Field(default_factory=tuple)
    constraints: tuple[str, ...] = Field(default_factory=tuple)
    next_steps: tuple[NextStep, ...] = Field(default_factory=tuple)
    payload: WorkflowPayload

    @model_validator(mode="after")
    def enforce_conversation_and_slots(self) -> "PendingWorkflowEnvelope":
        if not self.id.strip():
            raise ValueError("workflow id is required")
        if not self.origin.conversation_id.strip():
            raise ValueError("origin.conversation_id is required")
        for field_name in self.missing_fields:
            slot = self.slots.get(field_name)
            if slot is None:
                raise ValueError(f"missing field {field_name!r} has no slot")
        return self


def validate_status_transition(current: str | None, proposed: str) -> bool:
    if current is None:
        return proposed in {"draft", "awaiting_user", "ready_to_execute"}
    return proposed in _LEGAL_STATUS_TRANSITIONS.get(current, set())


def validate_slot_transitions(
    current: PendingWorkflowEnvelope | None,
    proposed: PendingWorkflowEnvelope,
) -> tuple[str, ...]:
    if current is None:
        return ()
    violations: list[str] = []
    for field_name, proposed_slot in proposed.slots.items():
        current_slot = current.slots.get(field_name)
        if current_slot is None or current_slot.status == proposed_slot.status:
            continue
        if proposed_slot.status not in _LEGAL_SLOT_STATUS_TRANSITIONS.get(
            current_slot.status,
            set(),
        ):
            violations.append(
                f"{field_name}:{current_slot.status}->{proposed_slot.status}"
            )
    return tuple(violations)


def normalize_workflow_invariants(
    workflow: PendingWorkflowEnvelope,
) -> tuple[PendingWorkflowEnvelope, tuple[str, ...]]:
    violations: list[str] = []
    has_unusable_slot = any(
        slot.status in {"missing", "invalid"} for slot in workflow.slots.values()
    )
    if workflow.status == "ready_to_execute" and (
        workflow.missing_fields or has_unusable_slot
    ):
        workflow = workflow.model_copy(update={"status": "awaiting_user"})
        violations.append("ready_with_missing_fields")
    return workflow, tuple(violations)


def workflow_to_document(workflow: PendingWorkflowEnvelope) -> dict[str, Any]:
    return workflow.model_dump(mode="json")
