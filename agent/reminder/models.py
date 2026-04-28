from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal

from agent.reminder.errors import ReminderError


@dataclass
class ReminderSchedule:
    anchor_at: datetime
    local_date: date
    local_time: time
    timezone: str
    rrule: str | None


@dataclass
class AgentOutputTarget:
    conversation_id: str
    character_id: str
    route_key: str | None


@dataclass
class Reminder:
    id: str
    owner_user_id: str
    title: str
    schedule: ReminderSchedule
    agent_output_target: AgentOutputTarget
    created_by_system: Literal["agent"]
    lifecycle_state: Literal["active", "completed", "cancelled", "failed"]
    next_fire_at: datetime | None
    last_fired_at: datetime | None
    last_event_ack_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    failed_at: datetime | None


@dataclass
class ReminderCreateCommand:
    title: str
    schedule: ReminderSchedule
    agent_output_target: AgentOutputTarget
    created_by_system: Literal["agent"]


@dataclass
class ReminderPatch:
    title: str | None = None
    schedule: ReminderSchedule | None = None


@dataclass
class ReminderQuery:
    lifecycle_states: list[str] | None = None


@dataclass
class ReminderCommand:
    action: Literal["create", "update", "cancel", "complete", "list"]
    reminder_id: str | None = None
    create: ReminderCreateCommand | None = None
    patch: ReminderPatch | None = None
    query: ReminderQuery | None = None


@dataclass
class ReminderCommandEnvelope:
    owner_user_id: str
    command: ReminderCommand


@dataclass
class ReminderBatchCommandEnvelope:
    owner_user_id: str
    commands: list[ReminderCommand]


@dataclass
class ReminderCommandResult:
    ok: bool
    action: str
    reminder: Reminder | None
    reminders: list[Reminder] | None
    error: ReminderError | None


@dataclass
class ReminderFiredEvent:
    event_type: Literal["reminder.fired"]
    event_id: str
    fire_id: str
    reminder_id: str
    owner_user_id: str
    title: str
    fire_at: datetime
    scheduled_for: datetime
    agent_output_target: AgentOutputTarget


@dataclass
class ReminderFireResult:
    ok: bool
    fire_id: str
    output_reference: str | None
    error_code: str | None
    error_message: str | None
