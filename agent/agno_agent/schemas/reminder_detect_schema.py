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
    rrule: str = Field(
        default="",
        description=(
            "RFC 5545 RRULE. Leave empty for bounded cadence/deadline batches; "
            "enumerate those as one-shot operations."
        ),
    )

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
        description=(
            "Aware ISO 8601 trigger time; crud create only. Do not use midnight "
            "as a default for date-only reminder requests."
        ),
    )
    reminder_id: str = Field(default="", description="Exact reminder id if known.")
    keyword: str = Field(default="", description="Reminder target keyword for crud.")
    new_title: str = Field(default="", description="Updated title; crud update only.")
    new_trigger_at: str = Field(
        default="",
        description="Aware ISO 8601 updated trigger time; crud update only.",
    )
    rrule: str = Field(
        default="",
        description=(
            "RFC 5545 RRULE; crud create/update only. Leave empty for bounded "
            "cadence/deadline requests and enumerate one-shot operations instead."
        ),
    )
    deadline_at: str = Field(
        default="",
        description=(
            "Aware ISO 8601 exclusive deadline for interval/deadline batches. "
            "When set, every create operation trigger_at must be before it."
        ),
    )
    schedule_basis: Literal[
        "", "one_shot", "explicit_occurrences", "explicit_cadence"
    ] = Field(
        default="",
        description=(
            "How the create schedule was authorized by the user. Use one_shot "
            "for a single concrete trigger, explicit_occurrences when the user "
            "listed each occurrence time, and explicit_cadence only when the "
            "user supplied a concrete frequency or interval. Leave empty for "
            "non-create actions."
        ),
    )
    schedule_evidence: str = Field(
        default="",
        description=(
            "Exact user wording that authorizes explicit_occurrences or "
            "explicit_cadence. For cadence, this must be the concrete "
            "frequency/interval text, not a vague supervision request. Use "
            "concrete time or interval wording, not vague references like "
            "'these time points'."
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
        description=(
            "Short missing-information question for clarify intent. Use the "
            "same language as the current user message, not the profile, prior "
            "messages, or retrieved context."
        ),
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
            "schedule_basis",
            "schedule_evidence",
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
            self._validate_schedule_basis()
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

    def _validate_schedule_basis(self) -> None:
        if self.action not in {"create", "batch"}:
            if self.schedule_basis or self.schedule_evidence:
                raise ValueError(
                    "schedule_basis and schedule_evidence are only for create batches"
                )
            return

        create_operations = (
            [operation for operation in self.operations if operation.action == "create"]
            if self.action == "batch"
            else []
        )
        has_recurring_create = bool(self.rrule) or any(
            bool(operation.rrule) for operation in create_operations
        )
        requires_authorized_schedule = (
            has_recurring_create
            or bool(self.deadline_at)
            or (self.action == "batch" and bool(create_operations))
        )

        if not requires_authorized_schedule:
            return

        if self.schedule_basis not in {"explicit_occurrences", "explicit_cadence"}:
            raise ValueError(
                "multi-occurrence or bounded create schedules require explicit schedule_basis"
            )
        if not self.schedule_evidence.strip():
            raise ValueError(
                "multi-occurrence or bounded create schedules require schedule_evidence"
            )
        if (
            self.schedule_basis == "explicit_cadence"
            and not _looks_like_concrete_cadence(self.schedule_evidence)
        ):
            raise ValueError(
                "explicit_cadence schedule_evidence must contain a concrete frequency or interval"
            )

    def _validate_deadline_operations(self) -> None:
        if not self.deadline_at or not self.operations:
            return
        deadline = _parse_aware_datetime(self.deadline_at, "deadline_at")
        for operation in self.operations:
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


def _looks_like_concrete_cadence(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    concrete_tokens = (
        "daily",
        "weekly",
        "monthly",
        "hourly",
        "minutely",
        "once",
        "twice",
        "每天",
        "每日",
        "每周",
        "每月",
        "每年",
        "每小时",
        "每分钟",
        "每隔",
    )
    if any(token in text for token in concrete_tokens):
        return True
    interval_units = (
        "minute",
        "minutes",
        "min",
        "mins",
        "hour",
        "hours",
        "day",
        "days",
        "week",
        "weeks",
        "month",
        "months",
        "分钟",
        "小时",
        "天",
        "周",
        "月",
    )
    return any(char.isdigit() for char in text) and any(
        unit in text for unit in interval_units
    )
