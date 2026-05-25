# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReminderOperation(BaseModel):
    """One executable operation inside a reminder batch decision."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["create", "update", "delete", "cancel", "complete", "list"] = Field(
        description="Flat reminder operation action."
    )
    title: str = Field(
        default="",
        description=(
            "Create title. Exclude sentence-final modal particles, but preserve "
            "meaningful quoted or parenthetical text that belongs to the reminder "
            "content. Prefer the task governed by the reminder verb over trailing "
            "context or reason text."
        ),
    )
    trigger_at: str = Field(default="", description="Aware ISO 8601 trigger time.")
    duration_minutes: int | None = Field(
        default=None,
        description="Optional positive duration in minutes for create operations.",
    )
    reminder_id: str = Field(default="", description="Exact reminder id if known.")
    keyword: str = Field(default="", description="Reminder target keyword.")
    target_title: str | None = Field(
        default=None,
        description="Structured write target title or fuzzy title phrase.",
    )
    target_local_date: str | None = Field(
        default=None,
        description="Structured write target local date in YYYY-MM-DD.",
    )
    target_local_time: str | None = Field(
        default=None,
        description="Structured write target local clock in HH:MM.",
    )
    target_rrule: str | None = Field(
        default=None,
        description='Structured write target recurrence selector such as "FREQ=DAILY".',
    )
    target_scope: Literal["current_conversation", "recent_active", "all_active"] | None = (
        Field(default=None, description="Structured write target search scope.")
    )
    new_title: str = Field(
        default="",
        description="Updated title; update only, do not use for create.",
    )
    new_trigger_at: str = Field(
        default="",
        description=(
            "Aware ISO 8601 updated trigger time; update only, do not use for create."
        ),
    )
    rrule: str = Field(
        default="",
        description=(
            "RFC 5545 RRULE. For bounded recurring cadence, include the RRULE "
            "and set top-level deadline_at."
        ),
    )

    @model_validator(mode="after")
    def enforce_operation_fields(self) -> "ReminderOperation":
        if self.action == "create" and not (self.title and self.trigger_at):
            raise ValueError("batch create operation requires title and trigger_at")
        if self.action == "create" and _is_generic_reminder_title(self.title):
            raise ValueError("batch create operation requires non-generic title")
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
    title: str = Field(
        default="",
        description=(
            "Create title; crud create only. Exclude sentence-final modal particles, "
            "but preserve meaningful quoted or parenthetical text that belongs to "
            "the reminder content. Prefer the task governed by the reminder verb "
            "over trailing context or reason text."
        ),
    )
    trigger_at: str = Field(
        default="",
        description=(
            "Aware ISO 8601 trigger time; crud create only. Do not use midnight "
            "as a default for date-only reminder requests."
        ),
    )
    duration_minutes: int | None = Field(
        default=None,
        description=(
            "Optional positive duration in minutes; crud create only. "
            "Use when the user explicitly states how long the reminder lasts."
        ),
    )
    reminder_id: str = Field(default="", description="Exact reminder id if known.")
    keyword: str = Field(default="", description="Reminder target keyword for crud.")
    target_title: str | None = Field(
        default=None,
        description="Structured write target title or fuzzy title phrase.",
    )
    target_local_date: str | None = Field(
        default=None,
        description="Structured write target local date in YYYY-MM-DD.",
    )
    target_local_time: str | None = Field(
        default=None,
        description="Structured write target local clock in HH:MM.",
    )
    target_rrule: str | None = Field(
        default=None,
        description='Structured write target recurrence selector such as "FREQ=DAILY".',
    )
    target_scope: Literal["current_conversation", "recent_active", "all_active"] | None = (
        Field(default=None, description="Structured write target search scope.")
    )
    new_title: str = Field(default="", description="Updated title; crud update only.")
    new_trigger_at: str = Field(
        default="",
        description="Aware ISO 8601 updated trigger time; crud update only.",
    )
    rrule: str = Field(
        default="",
        description=(
            "RFC 5545 RRULE; crud create/update only. For bounded recurring "
            "cadence, include RRULE and top-level deadline_at."
        ),
    )
    deadline_at: str = Field(
        default="",
        description=(
            "Aware ISO 8601 deadline for bounded recurring cadence or "
            "interval/deadline batches. When set, every create operation "
            "trigger_at must be at or before it."
        ),
    )
    schedule_basis: Literal[
        "", "one_shot", "explicit_occurrences", "explicit_cadence"
    ] = Field(
        default="",
        description=(
            "How the create/update schedule was authorized by the user. Use one_shot "
            "for a single concrete trigger, explicit_occurrences when the user "
            "listed each occurrence time, and explicit_cadence only when the "
            "user supplied a concrete frequency or interval. Leave empty for "
            "non-scheduling actions."
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
    clarification_reason: Literal[
        "",
        "date_only_missing_time",
        "ambiguous_time_range",
        "completion_condition_missing_time",
        "status_only_content",
        "deadline_without_trigger",
        "advance_offset_missing",
        "high_frequency_requires_end",
        "missing_reminder_content",
        "ambiguous_request",
    ] = Field(
        default="",
        description=(
            "Reason code that selects the clarification template. "
            "Must be non-empty when intent_type='clarify'; must be empty otherwise."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_intent_from_action(cls, data):
        if not isinstance(data, dict):
            return data
        action = str(data.get("action") or "")
        explicit_intent = str(data.get("intent_type") or "").strip()
        clarification_reason = str(data.get("clarification_reason") or "").strip()
        executable_field_names = (
            "title",
            "trigger_at",
            "duration_minutes",
            "reminder_id",
            "keyword",
            "target_title",
            "target_local_date",
            "target_local_time",
            "target_rrule",
            "target_scope",
            "new_title",
            "new_trigger_at",
            "rrule",
            "deadline_at",
            "schedule_basis",
            "schedule_evidence",
            "operations",
        )
        has_executable_fields = any(
            bool(data.get(name)) for name in executable_field_names
        )
        if explicit_intent == "clarify" and not has_executable_fields:
            return _strip_executable_fields_for_clarification(data)
        if action in {"create", "update", "delete", "cancel", "complete", "batch"}:
            return {**data, "intent_type": "crud"}
        if action == "list":
            return {**data, "intent_type": "query"}
        if clarification_reason and not action and not has_executable_fields:
            return {**data, "intent_type": "clarify", "action": ""}
        return data

    @model_validator(mode="after")
    def enforce_intent_field_boundaries(self) -> "ReminderDetectDecision":
        write_field_names = (
            "title",
            "trigger_at",
            "duration_minutes",
            "reminder_id",
            "keyword",
            "target_title",
            "target_local_date",
            "target_local_time",
            "target_rrule",
            "target_scope",
            "new_title",
            "new_trigger_at",
            "rrule",
            "deadline_at",
            "schedule_basis",
            "schedule_evidence",
            "operations",
        )
        has_write_fields = any(bool(getattr(self, name)) for name in write_field_names)

        if self.intent_type == "clarify" and not self.clarification_reason:
            raise ValueError("clarify intent requires clarification_reason")
        if self.intent_type != "clarify" and self.clarification_reason:
            raise ValueError(
                "clarification_reason is only allowed for intent_type='clarify'"
            )

        if self.intent_type == "crud":
            if not self.action:
                raise ValueError("crud intent requires action")
            if self.action == "batch" and not self.operations:
                raise ValueError("batch action requires operations")
            if self.action == "create" and not (self.title and self.trigger_at):
                raise ValueError("create action requires title and trigger_at")
            if self.action == "create" and _is_generic_reminder_title(self.title):
                raise ValueError("create action requires non-generic title")
            self._validate_executable_datetimes()
            self._validate_target_selector()
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

    def _validate_executable_datetimes(self) -> None:
        for field_name in ("trigger_at", "new_trigger_at", "deadline_at"):
            value = str(getattr(self, field_name) or "").strip()
            if value:
                _parse_aware_datetime(value, field_name)
        for index, operation in enumerate(self.operations):
            for field_name in ("trigger_at", "new_trigger_at"):
                value = str(getattr(operation, field_name) or "").strip()
                if value:
                    _parse_aware_datetime(
                        value,
                        f"operations[{index}].{field_name}",
                    )

    def _validate_target_selector(self) -> None:
        local_date = str(self.target_local_date or "").strip()
        if local_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", local_date):
            raise ValueError("target_local_date must be YYYY-MM-DD")
        local_time = str(self.target_local_time or "").strip()
        if local_time and not re.fullmatch(r"\d{2}:\d{2}", local_time):
            raise ValueError("target_local_time must be HH:MM")

        for index, operation in enumerate(self.operations):
            operation_date = str(operation.target_local_date or "").strip()
            if operation_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", operation_date):
                raise ValueError(
                    f"operations[{index}].target_local_date must be YYYY-MM-DD"
                )
            operation_time = str(operation.target_local_time or "").strip()
            if operation_time and not re.fullmatch(r"\d{2}:\d{2}", operation_time):
                raise ValueError(
                    f"operations[{index}].target_local_time must be HH:MM"
                )

    def _validate_schedule_basis(self) -> None:
        if self.action not in {"create", "update", "batch"}:
            if self.schedule_basis or self.schedule_evidence:
                raise ValueError(
                    "schedule_basis and schedule_evidence are only for scheduling decisions"
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
                "multi-occurrence or bounded schedules require explicit schedule_basis"
            )
        if not self.schedule_evidence.strip():
            raise ValueError(
                "multi-occurrence or bounded schedules require schedule_evidence"
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
            if trigger_at > deadline:
                raise ValueError(
                    "batch create operation must be at or before deadline_at"
                )


def _parse_aware_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO 8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone")
    return parsed


def _strip_executable_fields_for_clarification(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    normalized["intent_type"] = "clarify"
    normalized["action"] = ""
    for field_name in (
        "title",
        "trigger_at",
        "reminder_id",
        "keyword",
        "target_title",
        "target_local_date",
        "target_local_time",
        "target_rrule",
        "new_title",
        "new_trigger_at",
        "rrule",
        "deadline_at",
        "schedule_basis",
        "schedule_evidence",
    ):
        normalized[field_name] = ""
    for field_name in (
        "target_title",
        "target_local_date",
        "target_local_time",
        "target_rrule",
        "target_scope",
    ):
        normalized[field_name] = None
    normalized["operations"] = []
    return normalized


def _is_generic_reminder_title(value: str) -> bool:
    normalized = re.sub(r"[\s，,。.!！?？]+", "", str(value or "").strip())
    return normalized in {"提醒", "提醒我", "提醒一下", "提醒一下我"}


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
        "每晚",
        "每夜",
        "每小时",
        "每分钟",
        "每隔",
        "每个整点",
        "整点",
        "每个周",
        "每个星期",
        "每个礼拜",
    )
    if any(token in text for token in concrete_tokens):
        return True
    if re.search(r"每(?:个)?(?:周|星期|礼拜)", text):
        return True
    if len(set(re.findall(r"周[一二三四五六日天]", text))) >= 2:
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
