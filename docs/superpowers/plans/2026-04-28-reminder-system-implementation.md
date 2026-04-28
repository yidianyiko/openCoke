# Reminder System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the V1 Reminder System as a system boundary separate from Agent System, with structured command input, durable Mongo reminder state, APScheduler wake-ups, and structured fired events consumed by Agent System.

**Architecture:** Build a new `agent/reminder/` package for Reminder System domain, persistence, command handling, scheduling, and fired-event protocol. Keep Agent System integration in `agent/agno_agent/tools/` and `agent/runner/` so the LLM and chat output pipeline remain outside Reminder System. V1 uses an in-process fired-event handler and does not add a public MCP server, durable outbox, retry table, or per-occurrence history.

**Tech Stack:** Python 3.12, MongoDB/PyMongo, APScheduler 3.x, python-dateutil, zoneinfo, pytest, pytest-asyncio, Agno tools

---

## Simplification Decision

No architecture simplification is needed before implementation. The system split is necessary:

- Agent System owns natural language, target disambiguation, tool adaptation, and final chat output.
- Reminder System owns durable reminder state, schedule computation, lifecycle, and fire events.

The implementation should stay simple in V1:

- Use an in-process `ReminderFireEventHandler` instead of webhook or queue transport.
- Store one Mongo document per reminder in `reminders`.
- Do not create `reminder_occurrences`, `delivery_attempts`, durable outbox, leases, retries, or multi-worker claiming.
- Leave existing `deferred_actions` runtime in place for internal proactive follow-up until its own redesign.
- Cut only user-visible reminder creation/list/update/cancel/complete to the new Reminder System.

## File Map

Create Reminder System files:

- Create: `agent/reminder/__init__.py`
  Exports the public Reminder System types and `ReminderService`.
- Create: `agent/reminder/errors.py`
  Defines `ReminderError` and stable subclasses/codes.
- Create: `agent/reminder/models.py`
  Defines `Reminder`, `ReminderSchedule`, `AgentOutputTarget`, command envelopes, command results, fired events, and fire results.
- Create: `agent/reminder/schedule.py`
  Owns timezone validation, RRULE subset validation, local intent conversion, and next-fire computation.
- Create: `dao/reminder_dao.py`
  Owns Mongo `reminders` persistence, indexes, owner-scoped queries, and atomic post-fire updates.
- Create: `agent/reminder/service.py`
  Owns command protocol behavior: create, update, cancel, complete, get, list, and batch.
- Create: `agent/runner/reminder_scheduler.py`
  Owns APScheduler registration, startup reconstruction, stale wake-up rejection, and post-event state advance.
- Create: `agent/runner/reminder_event_handler.py`
  Agent System adapter that consumes `ReminderFiredEvent`, resolves conversation context, writes output through the existing output boundary, and returns `ReminderFireResult`.
- Create: `agent/agno_agent/tools/reminder_protocol/__init__.py`
  Exports `visible_reminder_tool` and `set_reminder_session_state`.
- Create: `agent/agno_agent/tools/reminder_protocol/tool.py`
  MCP-compatible Agno tool adapter over the Reminder command protocol.

Modify existing files:

- Modify: `agent/agno_agent/agents/__init__.py`
  Import `visible_reminder_tool` from `agent.agno_agent.tools.reminder_protocol`.
- Modify: `agent/agno_agent/tools/__init__.py`
  Export the new visible reminder tool.
- Modify: `agent/agno_agent/workflows/prepare_workflow.py`
  Set reminder protocol session state before ReminderDetectAgent runs.
- Modify: `agent/prompt/agent_instructions_prompt.py`
  Keep ReminderDetectAgent instructions aligned with ISO datetime, RRULE, batch, and no direct output.
- Modify: `agent/agno_agent/workflows/chat_workflow_streaming.py`
  Preserve the no-success-claim guard for missing reminder tool results.
- Modify: `agent/runner/agent_runner.py`
  Boot `ReminderScheduler` alongside existing deferred-action scheduler.
- Modify: `agent/agno_agent/tools/deferred_action/service.py`
  Keep internal proactive follow-up behavior; stop using it for visible reminder operations.
- Modify: `agent/agno_agent/tools/timezone_tools.py`
  Stop realigning V1 reminders on timezone change; V1 snapshots reminder timezone.
- Modify: `agent/agno_agent/tools/deferred_action/__init__.py`
  Keep deferred-action exports for proactive follow-up callers only.
- Modify: `docs/architecture.md`
  Document new Reminder System and note `deferred_actions` remains for proactive follow-up only.
- Modify: `docs/fitness/coke-verification-matrix.md`
  Add focused reminder-system verification commands.
- Modify: `tasks/2026-04-28-reminder-system-protocol-boundary.md`
  Add plan link and implementation handoff status.

Create tests:

- Create: `tests/unit/reminder/test_models.py`
- Create: `tests/unit/reminder/test_schedule.py`
- Create: `tests/unit/dao/test_reminder_dao.py`
- Create: `tests/unit/reminder/test_service.py`
- Create: `tests/unit/runner/test_reminder_scheduler.py`
- Create: `tests/unit/runner/test_reminder_event_handler.py`
- Create: `tests/unit/agent/test_visible_reminder_protocol_tool.py`
- Modify: `tests/unit/agent/test_post_analyze_deferred_actions.py`
- Modify: `tests/unit/test_tool_results_context.py`
- Create: `tests/e2e/test_reminder_system_flow.py`

## Task 1: Reminder Domain Types And Errors

**Files:**

- Create: `agent/reminder/__init__.py`
- Create: `agent/reminder/errors.py`
- Create: `agent/reminder/models.py`
- Test: `tests/unit/reminder/test_models.py`

- [ ] **Step 1: Write the failing model tests**

Create `tests/unit/reminder/test_models.py` with tests that lock the public type contract:

```python
from datetime import UTC, date, datetime, time

from agent.reminder.errors import InvalidArgument, ReminderError
from agent.reminder.models import (
    AgentOutputTarget,
    Reminder,
    ReminderBatchCommandEnvelope,
    ReminderCommand,
    ReminderCommandEnvelope,
    ReminderFiredEvent,
    ReminderFireResult,
    ReminderSchedule,
)


def test_reminder_model_contains_protocol_boundary_fields():
    schedule = ReminderSchedule(
        anchor_at=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        local_date=date(2026, 4, 29),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule=None,
    )
    target = AgentOutputTarget(
        conversation_id="conv-1",
        character_id="char-1",
        route_key="wechat_personal:primary",
    )
    reminder = Reminder(
        id="rem-1",
        owner_user_id="user-1",
        title="drink water",
        schedule=schedule,
        agent_output_target=target,
        created_by_system="agent",
        lifecycle_state="active",
        next_fire_at=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        last_fired_at=None,
        last_event_ack_at=None,
        last_error=None,
        created_at=datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
        completed_at=None,
        cancelled_at=None,
        failed_at=None,
    )

    assert reminder.agent_output_target.conversation_id == "conv-1"
    assert reminder.next_fire_at == schedule.anchor_at
    assert reminder.created_by_system == "agent"


def test_command_envelope_carries_trusted_owner_context():
    command = ReminderCommand(action="list")
    envelope = ReminderCommandEnvelope(owner_user_id="user-1", command=command)
    batch = ReminderBatchCommandEnvelope(owner_user_id="user-1", commands=[command])

    assert envelope.owner_user_id == "user-1"
    assert batch.commands == [command]


def test_fired_event_and_result_use_fire_id_boundary():
    event = ReminderFiredEvent(
        event_type="reminder.fired",
        event_id="evt-1",
        fire_id="rem-1:2026-04-29T01:00:00+00:00",
        reminder_id="rem-1",
        owner_user_id="user-1",
        title="drink water",
        fire_at=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        scheduled_for=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        agent_output_target=AgentOutputTarget("conv-1", "char-1", None),
    )
    result = ReminderFireResult(
        ok=True,
        fire_id=event.fire_id,
        output_reference="output-1",
        error_code=None,
        error_message=None,
    )

    assert result.fire_id == event.fire_id
    assert result.ok is True


def test_reminder_error_exposes_stable_code_and_detail():
    err = InvalidArgument("bad shape", detail={"field": "title"})

    assert isinstance(err, ReminderError)
    assert err.code == "InvalidArgument"
    assert err.user_message == "bad shape"
    assert err.detail == {"field": "title"}
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
pytest tests/unit/reminder/test_models.py -v
```

Expected: fails with `ModuleNotFoundError: No module named 'agent.reminder'`.

- [ ] **Step 3: Implement errors and dataclasses**

Create `agent/reminder/errors.py`:

```python
from __future__ import annotations

from typing import Any


class ReminderError(Exception):
    code = "ReminderError"

    def __init__(
        self,
        user_message: str,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail or {}


class InvalidSchedule(ReminderError):
    code = "InvalidSchedule"


class RRULENotSupported(ReminderError):
    code = "RRULENotSupported"


class ReminderNotFound(ReminderError):
    code = "ReminderNotFound"


class OwnershipViolation(ReminderError):
    code = "OwnershipViolation"


class InvalidOutputTarget(ReminderError):
    code = "InvalidOutputTarget"


class InvalidArgument(ReminderError):
    code = "InvalidArgument"


class ReminderFireFailed(ReminderError):
    code = "ReminderFireFailed"
```

Create `agent/reminder/models.py` with the dataclasses named in the test. Use `Literal` values exactly as the spec defines.

- [ ] **Step 4: Export the public API**

Create `agent/reminder/__init__.py`:

```python
from agent.reminder.errors import (
    InvalidArgument,
    InvalidOutputTarget,
    InvalidSchedule,
    OwnershipViolation,
    RRULENotSupported,
    ReminderError,
    ReminderFireFailed,
    ReminderNotFound,
)
from agent.reminder.models import (
    AgentOutputTarget,
    Reminder,
    ReminderBatchCommandEnvelope,
    ReminderCommand,
    ReminderCommandEnvelope,
    ReminderCommandResult,
    ReminderCreateCommand,
    ReminderFiredEvent,
    ReminderFireResult,
    ReminderPatch,
    ReminderQuery,
    ReminderSchedule,
)

__all__ = [
    "AgentOutputTarget",
    "InvalidArgument",
    "InvalidOutputTarget",
    "InvalidSchedule",
    "OwnershipViolation",
    "RRULENotSupported",
    "Reminder",
    "ReminderBatchCommandEnvelope",
    "ReminderCommand",
    "ReminderCommandEnvelope",
    "ReminderCommandResult",
    "ReminderCreateCommand",
    "ReminderError",
    "ReminderFireFailed",
    "ReminderFireResult",
    "ReminderFiredEvent",
    "ReminderNotFound",
    "ReminderPatch",
    "ReminderQuery",
    "ReminderSchedule",
]
```

- [ ] **Step 5: Run the tests and commit**

Run:

```bash
pytest tests/unit/reminder/test_models.py -v
```

Expected: all tests pass.

Commit:

```bash
git add agent/reminder tests/unit/reminder/test_models.py
git commit -m "feat(reminders): add reminder protocol models"
```

## Task 2: Schedule Semantics

**Files:**

- Create: `agent/reminder/schedule.py`
- Test: `tests/unit/reminder/test_schedule.py`

- [ ] **Step 1: Write schedule tests**

Create `tests/unit/reminder/test_schedule.py` covering:

```python
from datetime import UTC, date, datetime, time

import pytest

from agent.reminder.errors import InvalidSchedule, RRULENotSupported
from agent.reminder.models import ReminderSchedule
from agent.reminder.schedule import (
    build_schedule_from_anchor,
    compute_initial_next_fire_at,
    compute_next_fire_after_success,
    validate_rrule_subset,
)


def test_build_schedule_snapshots_local_intent_from_timezone():
    schedule = build_schedule_from_anchor(
        anchor_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        timezone="Asia/Tokyo",
        rrule=None,
    )

    assert schedule.anchor_at == datetime(2026, 4, 29, 10, 0, tzinfo=UTC)
    assert schedule.local_date == date(2026, 4, 29)
    assert schedule.local_time == time(19, 0)
    assert schedule.timezone == "Asia/Tokyo"


def test_one_shot_next_fire_must_be_future():
    schedule = ReminderSchedule(
        anchor_at=datetime(2026, 4, 29, 1, 0, tzinfo=UTC),
        local_date=date(2026, 4, 29),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule=None,
    )

    assert compute_initial_next_fire_at(
        schedule,
        now=datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
    ) == datetime(2026, 4, 29, 1, 0, tzinfo=UTC)

    with pytest.raises(InvalidSchedule):
        compute_initial_next_fire_at(
            schedule,
            now=datetime(2026, 4, 30, 1, 0, tzinfo=UTC),
        )


def test_recurring_schedule_uses_first_future_occurrence():
    schedule = ReminderSchedule(
        anchor_at=datetime(2026, 4, 20, 1, 0, tzinfo=UTC),
        local_date=date(2026, 4, 20),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule="FREQ=DAILY",
    )

    assert compute_initial_next_fire_at(
        schedule,
        now=datetime(2026, 4, 28, 2, 0, tzinfo=UTC),
    ) == datetime(2026, 4, 29, 1, 0, tzinfo=UTC)


def test_supported_and_rejected_rrule_subset():
    assert validate_rrule_subset("FREQ=WEEKLY;BYDAY=MO,WE;INTERVAL=2") == "FREQ=WEEKLY;BYDAY=MO,WE;INTERVAL=2"

    with pytest.raises(RRULENotSupported):
        validate_rrule_subset("FREQ=HOURLY")

    with pytest.raises(RRULENotSupported):
        validate_rrule_subset("FREQ=DAILY;BYHOUR=9")


def test_next_fire_after_success_returns_none_for_exhausted_recurrence():
    schedule = ReminderSchedule(
        anchor_at=datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
        local_date=date(2026, 4, 28),
        local_time=time(10, 0),
        timezone="Asia/Tokyo",
        rrule="FREQ=DAILY;COUNT=1",
    )

    assert compute_next_fire_after_success(
        schedule,
        scheduled_for=datetime(2026, 4, 28, 1, 0, tzinfo=UTC),
        now=datetime(2026, 4, 28, 1, 1, tzinfo=UTC),
    ) is None
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
pytest tests/unit/reminder/test_schedule.py -v
```

Expected: fails because `agent.reminder.schedule` does not exist.

- [ ] **Step 3: Implement schedule helpers**

Implement these functions in `agent/reminder/schedule.py`:

- `build_schedule_from_anchor(anchor_at: datetime, timezone: str, rrule: str | None) -> ReminderSchedule`
- `validate_timezone(timezone: str) -> str`
- `validate_rrule_subset(rrule: str | None) -> str | None`
- `compute_initial_next_fire_at(schedule: ReminderSchedule, now: datetime) -> datetime`
- `compute_next_fire_after_success(schedule: ReminderSchedule, scheduled_for: datetime, now: datetime) -> datetime | None`

Implementation rules:

- Reject naive datetimes with `InvalidSchedule`.
- Store `anchor_at` as UTC.
- Validate IANA timezone using `zoneinfo.ZoneInfo`.
- Accept only `FREQ=DAILY`, `FREQ=WEEKLY`, `FREQ=MONTHLY`, `FREQ=YEARLY`.
- Accept modifiers `COUNT`, `UNTIL`, `INTERVAL`, and weekly `BYDAY`.
- Reject `BYHOUR`, `BYMINUTE`, `BYMONTH`, `BYMONTHDAY`, `BYSETPOS`, `BYWEEKNO`, `BYYEARDAY`, `WKST`, `EXDATE`, and `RDATE`.

- [ ] **Step 4: Run tests and commit**

Run:

```bash
pytest tests/unit/reminder/test_schedule.py -v
```

Expected: all tests pass.

Commit:

```bash
git add agent/reminder/schedule.py tests/unit/reminder/test_schedule.py
git commit -m "feat(reminders): add schedule policy"
```

## Task 3: Mongo DAO

**Files:**

- Create: `dao/reminder_dao.py`
- Test: `tests/unit/dao/test_reminder_dao.py`

- [ ] **Step 1: Write DAO tests**

Create `tests/unit/dao/test_reminder_dao.py` using `Mock` collection objects. Cover:

- `create_indexes()` creates `{owner_user_id, lifecycle_state, created_at}` and `{lifecycle_state, next_fire_at}`.
- `insert_reminder()` returns string id.
- `get_reminder()` loads by `_id`.
- `get_reminder_for_owner()` includes `owner_user_id`.
- `list_for_owner()` filters by owner and lifecycle states.
- `list_due_active()` filters `lifecycle_state="active"` and `next_fire_at != None`.
- `atomic_apply_fire_success()` uses selector `{"_id", "next_fire_at", "lifecycle_state": "active"}`.
- `atomic_apply_fire_failure()` clears `next_fire_at` and sets failed fields.

- [ ] **Step 2: Run DAO tests and verify they fail**

Run:

```bash
pytest tests/unit/dao/test_reminder_dao.py -v
```

Expected: fails because `dao.reminder_dao` does not exist.

- [ ] **Step 3: Implement DAO**

Create `dao/reminder_dao.py` with class `ReminderDAO`.

Required class and methods:

- Class: `ReminderDAO`
- Constant: `COLLECTION = "reminders"`
- Method: `create_indexes(self) -> None`
- Method: `insert_reminder(self, document: dict) -> str`
- Method: `get_reminder(self, reminder_id: str) -> dict | None`
- Method: `get_reminder_for_owner(self, reminder_id: str, owner_user_id: str) -> dict | None`
- Method: `list_for_owner(self, owner_user_id: str, lifecycle_states: list[str] | None = None) -> list[dict]`
- Method: `list_due_active(self) -> list[dict]`
- Method: `replace_reminder(self, reminder_id: str, owner_user_id: str, updates: dict) -> bool`
- Method: `atomic_apply_fire_success(self, reminder_id: str, expected_next_fire_at: datetime, updates: dict) -> bool`
- Method: `atomic_apply_fire_failure(self, reminder_id: str, expected_next_fire_at: datetime, updates: dict) -> bool`

Use `bson.ObjectId` for `_id` selectors and instantiate `MongoClient` with `tz_aware=True`, matching existing DAO style.

- [ ] **Step 4: Run DAO tests and commit**

Run:

```bash
pytest tests/unit/dao/test_reminder_dao.py -v
```

Expected: all tests pass.

Commit:

```bash
git add dao/reminder_dao.py tests/unit/dao/test_reminder_dao.py
git commit -m "feat(reminders): add reminder Mongo DAO"
```

## Task 4: Reminder Service Command Protocol

**Files:**

- Create: `agent/reminder/service.py`
- Test: `tests/unit/reminder/test_service.py`

- [ ] **Step 1: Write service tests**

Create `tests/unit/reminder/test_service.py` covering:

- `create()` validates output target and writes `next_fire_at`.
- `create()` rejects past one-shot reminders.
- `list_for_user()` returns owner-scoped reminders.
- `update()` rejects owner mismatch as `ReminderNotFound` or `OwnershipViolation` mapped internally.
- `cancel()` sets `cancelled_at` and clears `next_fire_at`.
- `complete()` sets `completed_at` and clears `next_fire_at`.
- `execute_batch()` preserves order and partial failures.
- Timed update calls scheduler `reschedule_reminder()`.

- [ ] **Step 2: Run service tests and verify they fail**

Run:

```bash
pytest tests/unit/reminder/test_service.py -v
```

Expected: fails because `agent.reminder.service` does not exist.

- [ ] **Step 3: Implement `ReminderService`**

Implement class `ReminderService` with these methods:

- `__init__(self, reminder_dao=None, scheduler=None, now_provider=None) -> None`
- `create(self, *, owner_user_id: str, command: ReminderCreateCommand) -> Reminder`
- `update(self, *, reminder_id: str, owner_user_id: str, patch: ReminderPatch) -> Reminder`
- `cancel(self, *, reminder_id: str, owner_user_id: str) -> Reminder`
- `complete(self, *, reminder_id: str, owner_user_id: str) -> Reminder`
- `get(self, *, reminder_id: str, owner_user_id: str) -> Reminder`
- `list_for_user(self, *, owner_user_id: str, query: ReminderQuery) -> list[Reminder]`
- `execute_batch(self, *, owner_user_id: str, commands: list[ReminderCommand]) -> list[ReminderCommandResult]`

Implementation rules:

- Convert DAO documents to `Reminder` dataclasses in one private mapper.
- Validate `AgentOutputTarget.conversation_id` and `character_id` are non-empty.
- Set `created_by_system="agent"` for V1.
- Call scheduler `register_reminder()` on active create.
- Call scheduler `reschedule_reminder()` on active schedule update.
- Call scheduler `remove_reminder()` on cancel/complete.
- Do not import Agno, prompts, or chat workflow modules.

- [ ] **Step 4: Run service tests and commit**

Run:

```bash
pytest tests/unit/reminder/test_service.py -v
```

Expected: all tests pass.

Commit:

```bash
git add agent/reminder/service.py tests/unit/reminder/test_service.py
git commit -m "feat(reminders): add reminder command service"
```

## Task 5: Agent MCP Tool Adapter

**Files:**

- Create: `agent/agno_agent/tools/reminder_protocol/__init__.py`
- Create: `agent/agno_agent/tools/reminder_protocol/tool.py`
- Modify: `agent/agno_agent/agents/__init__.py`
- Modify: `agent/agno_agent/tools/__init__.py`
- Modify: `agent/agno_agent/workflows/prepare_workflow.py`
- Test: `tests/unit/agent/test_visible_reminder_protocol_tool.py`

- [ ] **Step 1: Write adapter tests**

Create `tests/unit/agent/test_visible_reminder_protocol_tool.py` covering:

- Create derives `owner_user_id`, `AgentOutputTarget`, and timezone from session state.
- LLM arguments cannot override owner or target.
- `delete` maps to canonical `cancel`.
- Keyword update resolves by listing owner reminders and matching title.
- Ambiguous keyword creates an `ok=false` tool result.
- Batch returns ordered partial results.
- Timed create/update sets `session_state["reminder_created_with_time"] = True`.
- List/cancel/complete/title-only update do not set the flag.

- [ ] **Step 2: Run adapter tests and verify they fail**

Run:

```bash
pytest tests/unit/agent/test_visible_reminder_protocol_tool.py -v
```

Expected: fails because `agent.agno_agent.tools.reminder_protocol` does not exist.

- [ ] **Step 3: Implement adapter**

Implement `set_reminder_session_state(session_state: dict) -> None` with `contextvars`, mirroring the old deferred-action tool pattern.

Implement `visible_reminder_tool` with the same public arguments as the spec:

```python
def visible_reminder_tool(
    action: str,
    title: str | None = None,
    trigger_at: str | None = None,
    reminder_id: str | None = None,
    keyword: str | None = None,
    new_title: str | None = None,
    new_trigger_at: str | None = None,
    rrule: str | None = None,
    operations: list[dict[str, Any]] | None = None,
) -> str:
    return _execute_visible_reminder_tool_action(
        action=action,
        title=title,
        trigger_at=trigger_at,
        reminder_id=reminder_id,
        keyword=keyword,
        new_title=new_title,
        new_trigger_at=new_trigger_at,
        rrule=rrule,
        operations=operations,
    )
```

Use `append_tool_result()` for every operation result. Return user-facing summaries only as factual tool summaries for ChatWorkflow context.

- [ ] **Step 4: Cut agent imports to the new adapter**

Modify imports:

- In `agent/agno_agent/agents/__init__.py`, import `visible_reminder_tool` from `agent.agno_agent.tools.reminder_protocol`.
- In `agent/agno_agent/tools/__init__.py`, export the new reminder protocol tool.
- In `agent/agno_agent/workflows/prepare_workflow.py`, replace `set_deferred_action_session_state(session_state)` with `set_reminder_session_state(session_state)`.

- [ ] **Step 5: Run adapter and existing tool-result tests**

Run:

```bash
pytest tests/unit/agent/test_visible_reminder_protocol_tool.py tests/unit/test_tool_results_context.py -v
```

Expected: all tests pass.

Commit:

```bash
git add agent/agno_agent/tools/reminder_protocol agent/agno_agent/agents/__init__.py agent/agno_agent/tools/__init__.py agent/agno_agent/workflows/prepare_workflow.py tests/unit/agent/test_visible_reminder_protocol_tool.py
git commit -m "feat(reminders): add agent reminder command adapter"
```

## Task 6: Reminder Scheduler And Fired-Event Protocol

**Files:**

- Create: `agent/runner/reminder_scheduler.py`
- Create: `agent/runner/reminder_event_handler.py`
- Modify: `agent/runner/agent_runner.py`
- Test: `tests/unit/runner/test_reminder_scheduler.py`
- Test: `tests/unit/runner/test_reminder_event_handler.py`

- [ ] **Step 1: Write scheduler tests**

Create `tests/unit/runner/test_reminder_scheduler.py` covering:

- Startup scans active reminders with `next_fire_at != None`.
- APScheduler job id is `reminder:{reminder_id}`.
- Job payload contains `reminder_id` and `next_fire_at`.
- Stale wake-up does not emit event.
- Successful one-shot event completes reminder and clears `next_fire_at`.
- Successful recurring event advances `next_fire_at`.
- Failed fire result marks reminder failed and clears `next_fire_at`.

- [ ] **Step 2: Write event handler tests**

Create `tests/unit/runner/test_reminder_event_handler.py` covering:

- Handler resolves conversation, user, and character by event target.
- Handler acquires the conversation/output lock.
- Handler writes through the existing agent/chat output boundary.
- Handler returns `ReminderFireResult(ok=True, fire_id="rem-1:2026-04-29T01:00:00+00:00")`.
- Missing conversation or owner mismatch returns `ok=False`.

- [ ] **Step 3: Run scheduler tests and verify they fail**

Run:

```bash
pytest tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py -v
```

Expected: fails because scheduler and event handler modules do not exist.

- [ ] **Step 4: Implement scheduler**

Implement class `ReminderScheduler` with these methods:

- `__init__(self, reminder_dao, fire_event_handler, scheduler=None, now_provider=None) -> None`
- `start(self) -> None`
- `shutdown(self) -> None`
- `load_from_storage(self) -> None`
- `register_reminder(self, reminder: Reminder | dict) -> None`
- `reschedule_reminder(self, reminder: Reminder | dict) -> None`
- `remove_reminder(self, reminder_id: str) -> None`
- `_execute_job(self, reminder_id: str, next_fire_at: datetime) -> Awaitable[None]`

The scheduler must create `ReminderFiredEvent`, call the event handler, and then use DAO atomic post-fire methods.

- [ ] **Step 5: Implement event handler**

Implement `ReminderFireEventHandler` so V1 uses the existing output path without adding a webhook or queue. Keep this adapter in `agent/runner/` because it is Agent System integration, not Reminder System domain logic.

- [ ] **Step 6: Boot scheduler in runner**

Modify `agent/runner/agent_runner.py`:

- Keep `bootstrap_deferred_action_runtime()` for internal proactive follow-up.
- Add `bootstrap_reminder_runtime()` for new visible reminders.
- Start both runtimes in `main()`.
- Shut both down in `finally`.

- [ ] **Step 7: Run scheduler tests and commit**

Run:

```bash
pytest tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py tests/unit/runner/test_agent_runner_deferred_actions.py -v
```

Expected: all tests pass.

Commit:

```bash
git add agent/runner/reminder_scheduler.py agent/runner/reminder_event_handler.py agent/runner/agent_runner.py tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py
git commit -m "feat(reminders): add reminder scheduler and fired events"
```

## Task 7: Agent Flow, Prompts, And PostAnalyze Guard

**Files:**

- Modify: `agent/prompt/agent_instructions_prompt.py`
- Modify: `agent/agno_agent/workflows/chat_workflow_streaming.py`
- Modify: `agent/agno_agent/workflows/post_analyze_workflow.py`
- Modify: `agent/agno_agent/tools/timezone_tools.py`
- Test: `tests/unit/agent/test_post_analyze_deferred_actions.py`
- Test: `tests/unit/test_tool_results_context.py`

- [ ] **Step 1: Write or update tests**

Update tests to assert:

- ReminderDetectAgent instructions mention ISO 8601 aware datetimes.
- ReminderDetectAgent instructions mention RFC 5545 RRULE.
- ReminderDetectAgent instructions say use batch for multiple operations.
- ChatWorkflow still refuses to claim reminder success when `need_reminder_detect=true` and no reminder tool result exists.
- `reminder_created_with_time=True` still suppresses internal proactive follow-up.
- Timezone changes do not realign V1 reminders.

- [ ] **Step 2: Run focused tests and verify failures**

Run:

```bash
pytest tests/unit/agent/test_post_analyze_deferred_actions.py tests/unit/test_tool_results_context.py tests/unit/agent/test_visible_reminder_protocol_tool.py -v
```

Expected: failures only for expectations not yet updated to new Reminder System wording.

- [ ] **Step 3: Update prompt and workflow behavior**

Apply these behavior rules:

- Orchestrator keeps the existing `need_reminder_detect` gate.
- ReminderDetectAgent remains the only agent-facing reminder write path.
- ChatResponseAgent never writes reminders directly.
- PostAnalyze skips internal proactive follow-up when `session_state["reminder_created_with_time"]` is true.
- Timezone tool updates user timezone but does not call reminder realignment for new V1 reminders.

- [ ] **Step 4: Run focused tests and commit**

Run:

```bash
pytest tests/unit/agent/test_post_analyze_deferred_actions.py tests/unit/test_tool_results_context.py tests/unit/agent/test_visible_reminder_protocol_tool.py -v
```

Expected: all tests pass.

Commit:

```bash
git add agent/prompt/agent_instructions_prompt.py agent/agno_agent/workflows/chat_workflow_streaming.py agent/agno_agent/workflows/post_analyze_workflow.py agent/agno_agent/tools/timezone_tools.py tests/unit/agent/test_post_analyze_deferred_actions.py tests/unit/test_tool_results_context.py
git commit -m "feat(reminders): align agent flow with reminder protocol"
```

## Task 8: End-To-End Flow And Legacy Boundary

**Files:**

- Create: `tests/e2e/test_reminder_system_flow.py`
- Modify: `tests/e2e/test_deferred_actions_flow.py`
- Modify: `docs/architecture.md`
- Modify: `docs/fitness/coke-verification-matrix.md`
- Modify: `tasks/2026-04-28-reminder-system-protocol-boundary.md`

- [ ] **Step 1: Write E2E tests**

Create `tests/e2e/test_reminder_system_flow.py` covering:

- User-visible reminder create writes to `reminders`, not `deferred_actions`.
- Scheduler restart reconstructs jobs from `reminders.next_fire_at`.
- One-shot fired event enters Agent System event handler and completes the reminder.
- Recurring reminder advances `next_fire_at`.
- Failed event handling marks reminder failed.
- Existing internal proactive follow-up tests still use `deferred_actions`.

- [ ] **Step 2: Run E2E tests and verify failures**

Run:

```bash
pytest tests/e2e/test_reminder_system_flow.py -v
```

Expected: fails until all runtime wiring is complete.

- [ ] **Step 3: Update docs**

Update `docs/architecture.md`:

- Add Reminder System under worker runtime.
- State `reminders` collection stores visible reminders.
- State `deferred_actions` remains for internal proactive follow-up until that redesign.
- State Reminder fired events return to Agent System for final output.

Update `docs/fitness/coke-verification-matrix.md` with focused reminder commands:

```bash
pytest tests/unit/reminder/ tests/unit/dao/test_reminder_dao.py -v
pytest tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py -v
pytest tests/unit/agent/test_visible_reminder_protocol_tool.py tests/unit/test_tool_results_context.py -v
pytest tests/e2e/test_reminder_system_flow.py -v
```

Update `tasks/2026-04-28-reminder-system-protocol-boundary.md` with the implementation status and plan link.

- [ ] **Step 4: Run full focused reminder verification**

Run:

```bash
pytest tests/unit/reminder/ tests/unit/dao/test_reminder_dao.py -v
pytest tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py -v
pytest tests/unit/agent/test_visible_reminder_protocol_tool.py tests/unit/test_tool_results_context.py -v
pytest tests/e2e/test_reminder_system_flow.py -v
zsh scripts/check
```

Expected: all commands pass.

Commit:

```bash
git add tests/e2e/test_reminder_system_flow.py tests/e2e/test_deferred_actions_flow.py docs/architecture.md docs/fitness/coke-verification-matrix.md tasks/2026-04-28-reminder-system-protocol-boundary.md
git commit -m "test(reminders): verify reminder system flow"
```

## Final Verification

Run the worker-runtime reminder command set:

```bash
pytest tests/unit/reminder/ tests/unit/dao/test_reminder_dao.py -v
pytest tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py tests/unit/runner/test_agent_runner_deferred_actions.py -v
pytest tests/unit/agent/test_visible_reminder_protocol_tool.py tests/unit/agent/test_post_analyze_deferred_actions.py tests/unit/test_tool_results_context.py -v
pytest tests/e2e/test_reminder_system_flow.py tests/e2e/test_deferred_actions_flow.py -v
zsh scripts/check
```

Expected evidence:

- New reminder domain, DAO, service, scheduler, event handler, and adapter tests pass.
- Existing deferred-action tests for internal proactive follow-up still pass.
- E2E reminder flow uses `reminders` for visible reminders.
- Repo documentation checks pass.

## Self-Review

Spec coverage:

- Separate Agent System and Reminder System boundary: Tasks 5, 6, 7.
- Command protocol and owner envelope: Tasks 1, 4, 5.
- Fired-event protocol and fire result: Tasks 1, 6.
- Durable Mongo reminder state: Tasks 3, 4, 8.
- APScheduler wake-up only: Task 6.
- User association through `owner_user_id`, `reminder_id`, `agent_output_target`, title/schedule: Tasks 1, 4, 5, 8.
- Agent-owned final output: Task 6.
- No direct Agent Mongo writes: Tasks 3, 4, 8.
- PostAnalyze suppression: Task 7.
- Existing proactive follow-up preserved: Tasks 6, 8.

Implementation risks:

- The old `deferred_actions` code currently mixes visible reminders and internal proactive follow-up. Task 8 must prove visible reminders moved to `reminders` while proactive follow-up remains stable.
- The fired-event handler needs a narrow output boundary. If the existing output helper is not isolated enough, split the handler behind an injected callable before touching broader chat workflow code.
- Google Calendar import currently has historical hooks into deferred visible reminders. This plan intentionally leaves Google Calendar import out of scope; if current production code depends on it, handle that in a separate import redesign before deleting old import helpers.
