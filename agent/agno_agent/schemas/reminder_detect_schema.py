# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    operations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Flat batch reminder operations; crud batch only.",
    )
    clarification_question: str = Field(
        default="",
        description="Short missing-information question for clarify intent.",
    )
    reason: str = Field(default="", description="Brief classification rationale.")

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
