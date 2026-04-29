# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReminderOperation(BaseModel):
    """One executable operation inside a reminder batch decision."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["create", "update", "delete", "cancel", "complete", "list"] = Field(
        description="Flat reminder operation action."
    )
    title: str = Field(default="", description="Create title.")
    trigger_at: str = Field(default="", description="Aware ISO 8601 trigger time.")
    reminder_id: str = Field(default="", description="Exact reminder id if known.")
    keyword: str = Field(default="", description="Reminder target keyword.")
    new_title: str = Field(default="", description="Updated title.")
    new_trigger_at: str = Field(
        default="", description="Aware ISO 8601 updated trigger time."
    )
    rrule: str = Field(default="", description="RFC 5545 RRULE.")

    @model_validator(mode="after")
    def enforce_operation_fields(self) -> "ReminderOperation":
        if self.action == "create" and not (self.title and self.trigger_at):
            raise ValueError("batch create operation requires title and trigger_at")
        return self


class ReminderDetectDecision(BaseModel):
    """Structured no-tool decision for ReminderDetectAgent."""

    model_config = ConfigDict(extra="forbid")

    intent_type: Literal["crud", "clarify", "query", "discussion"] = Field(
        description=(
            "crud when the agent can execute a reminder tool operation; clarify "
            "when required operation details are missing; query for reminder "
            "lookup intent; discussion for plans, capability talk, or ordinary chat."
        )
    )
    action: Literal[
        "", "create", "update", "delete", "cancel", "complete", "list", "batch"
    ] = Field(
        default="",
        description=(
            "Reminder tool action. Only crud may use write actions. Query may "
            "only use list. Clarify and discussion must leave this empty."
        ),
    )
    title: str = Field(default="", description="Create title; crud create only.")
    trigger_at: str = Field(
        default="",
        description="Aware ISO 8601 trigger time; crud create only.",
    )
    reminder_id: str = Field(default="", description="Exact reminder id if known.")
    keyword: str = Field(default="", description="Reminder target keyword for crud.")
    new_title: str = Field(default="", description="Updated title; crud update only.")
    new_trigger_at: str = Field(
        default="",
        description="Aware ISO 8601 updated trigger time; crud update only.",
    )
    rrule: str = Field(
        default="", description="RFC 5545 RRULE; crud create/update only."
    )
    deadline_at: str = Field(
        default="",
        description=(
            "Aware ISO 8601 exclusive deadline for interval/deadline batches. "
            "When set, every create operation trigger_at must be before it."
        ),
    )
    operations: list[ReminderOperation] = Field(
        default_factory=list,
        description=(
            "Flat batch reminder operations; required when action=batch. "
            "Each create operation must include action, title, and trigger_at."
        ),
    )
    clarification_question: str = Field(
        default="",
        description="Short missing-information question for clarify intent.",
    )
    reason: str = Field(default="", description="Brief classification rationale.")

    @model_validator(mode="before")
    @classmethod
    def normalize_intent_from_action(cls, data):
        if not isinstance(data, dict):
            return data
        action = str(data.get("action") or "")
        if action in {"create", "update", "delete", "cancel", "complete", "batch"}:
            return {**data, "intent_type": "crud"}
        if action == "list":
            return {**data, "intent_type": "query"}
        return data

    @model_validator(mode="after")
    def enforce_intent_field_boundaries(self) -> "ReminderDetectDecision":
        write_field_names = (
            "title",
            "trigger_at",
            "reminder_id",
            "keyword",
            "new_title",
            "new_trigger_at",
            "rrule",
            "deadline_at",
            "operations",
        )
        has_write_fields = any(bool(getattr(self, name)) for name in write_field_names)

        if self.intent_type == "crud":
            if not self.action:
                raise ValueError("crud intent requires action")
            if self.action == "batch" and not self.operations:
                raise ValueError("batch action requires operations")
            if self.action == "create" and not (self.title and self.trigger_at):
                raise ValueError("create action requires title and trigger_at")
            self._validate_deadline_operations()
            return self

        if has_write_fields:
            raise ValueError(
                "non-crud reminder decisions must not include executable fields"
            )

        if self.intent_type == "query":
            if self.action not in {"", "list"}:
                raise ValueError("query intent may only use action=list")
            return self

        if self.action:
            raise ValueError("clarify and discussion intents must not include action")

        return self

    def _validate_deadline_operations(self) -> None:
        if not self.deadline_at or not self.operations:
            return
        if self.rrule:
            raise ValueError("deadline_at batch must enumerate one-shot operations")
        deadline = _parse_aware_datetime(self.deadline_at, "deadline_at")
        for operation in self.operations:
            if operation.rrule:
                raise ValueError("deadline_at batch operation must not use rrule")
            if operation.action != "create" or not operation.trigger_at:
                continue
            trigger_at = _parse_aware_datetime(
                operation.trigger_at,
                "operation.trigger_at",
            )
            if trigger_at >= deadline:
                raise ValueError("batch create operation must be before deadline_at")


def _parse_aware_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO 8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone")
    return parsed
