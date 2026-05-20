---
title: Deferred Action Full-Stack Retirement
date: 2026-05-20
status: draft
---

# Deferred Action Full-Stack Retirement

## Problem

Two parallel scheduled-event stacks exist: the Reminder Runtime
(`agent/reminder/`, `agent/runner/reminder_*.py`) and the Deferred Action
stack (`agent/runner/deferred_action_*.py`, `agent/agno_agent/tools/deferred_action/`,
`dao/deferred_action_dao.py`). The Reminder Runtime is the canonical path:
it owns user-visible reminders and agent-created internal follow-ups. All
new writes already go through it. The Deferred Action stack remains only
because:

1. `connector/clawscale_bridge/google_calendar_import_service.py` still
   calls `DeferredActionService.create_imported_*`.
2. `agent/agno_agent/capabilities/timezone.py` calls
   `DeferredActionService.realign_visible_reminders_for_timezone_change`.
3. `agent/agno_agent/capabilities/context_retrieve.py` reads active
   reminders via `DeferredActionDAO`.

Goal: retire the Deferred Action stack entirely. No historical data migration
is required.

## Target State

```
agent/reminder/          — canonical runtime (unchanged structure)
agent/runner/
  reminder_event_handler.py    — unchanged
  reminder_fire_consumer.py    — unchanged
  reminder_scheduler.py        — unchanged
  agent_runner.py              — bootstrap_deferred_action_runtime removed
  deferred_action_executor.py  — DELETED
  deferred_action_scheduler.py — DELETED
  deferred_action_policy.py    — DELETED
agent/agno_agent/
  tools/deferred_action/       — DELETED (service.py, tool.py, __init__.py)
  adapters/deferred_action_result.py — DELETED
  adapters/__init__.py         — DeferredActionFireResult exports removed
  capabilities/timezone.py     — realign delegates to ReminderService
  capabilities/context_retrieve.py  — confirmed_reminders reads from ReminderDAO
  runtime/inputs.py            — DeferredActionPayload removed
  runtime/agent_runtime.py     — deferred_action.fire input type removed
dao/
  deferred_action_dao.py       — DELETED
  deferred_action_occurrence_dao.py — DELETED
connector/clawscale_bridge/
  google_calendar_import_service.py — writes to ReminderService
```

## Module Contracts

### `agent/reminder/service.py` — new surface

Add one method:

```python
def record_historical_import(
    self,
    *,
    owner_user_id: str,
    title: str,
    schedule: ReminderSchedule,
    agent_output_target: AgentOutputTarget,
) -> Reminder:
```

Writes a `lifecycle_state="completed"` reminder directly via
`reminder_dao.insert_reminder`, with `completed_at=now()`,
`next_fire_at=None`. Does not call `_call_scheduler`. Returns the mapped
`Reminder`.

Used only by calendar import for past events that will never fire.

---

### `connector/clawscale_bridge/google_calendar_import_service.py`

Replace `deferred_action_service` with `reminder_service: ReminderService`.

| Old call | New call |
|---|---|
| `create_imported_future_reminder(user_id, character_id, conversation_id, title, dtstart, timezone)` | `ReminderService.create(owner_user_id=user_id, command=ReminderCreateCommand(title, ReminderSchedule(anchor_at=dtstart_utc, local_date, local_time, timezone, rrule=None), AgentOutputTarget(conversation_id, character_id, route_key=None)))` |
| `create_imported_recurring_reminder(...)` | Same, with `rrule` set in `ReminderSchedule` |
| `create_imported_historical_reminder(...)` | `ReminderService.record_historical_import(owner_user_id, title, schedule, agent_output_target)` |

Field derivation for `ReminderSchedule`:
- `anchor_at` = `dtstart` converted to UTC (`dtstart.astimezone(UTC)`)
- `local_date` = `dtstart` in the named timezone `.date()`
- `local_time` = `dtstart` in the named timezone `.time()` (no tzinfo)
- `timezone` = timezone string from the calendar event
- `rrule` = rrule string or `None`

`created_by_system` on `ReminderCreateCommand` stays `"agent"` (system
creates on behalf of user). `origin="user"`, `visibility="visible"`,
`fire_mode="notify"` are set automatically by `ReminderService.create()`.

`find_imported_reminder_duplicate` currently checks `deferred_actions` for
duplicate detection. After migration this check reads from `reminders` via
`ReminderDAO`. The DAO method for duplicate detection must be added to
`ReminderDAO` or duplicated inline (see Non-Goals for scope boundary).

---

### `agent/agno_agent/capabilities/timezone.py`

Replace `DeferredActionService().realign_visible_reminders_for_timezone_change`
with a call to `ReminderService`. The equivalent operation:

1. Call `ReminderService.list_for_user(owner_user_id=user_id, query=ReminderQuery(lifecycle_states=["active"]))`.
2. For each reminder where `schedule.rrule` uses floating-local semantics
   (no `BYHOUR` anchoring to UTC — detect by absence of absolute UTC anchor
   in the rrule), recompute `anchor_at` in the new timezone and call
   `ReminderService.update(reminder_id, owner_user_id, ReminderPatch(schedule=new_schedule))`.

`ReminderService` must be injectable into `TimezoneCapabilityPort` (currently
`contract_factory` already handles this pattern).

---

### `agent/agno_agent/capabilities/context_retrieve.py`

Replace `DeferredActionDAO.list_visible_actions(user_id)` with
`ReminderDAO.list_active_visible(owner_user_id)` (add this method to
`ReminderDAO` if it does not already exist). The rest of `_retrieve_confirmed_reminders`
is unchanged — it formats the title/time strings for LLM context.

`ReminderDAO` (or its equivalent read method) is injectable via
`ContextRetrieveCapabilityPort`.

---

### `agent/agno_agent/runtime/inputs.py`

Remove `DeferredActionPayload` dataclass and `"deferred_action.fire"` from
`AgentInput.input_type` Literal and payload discriminator map.

---

### `agent/agno_agent/runtime/agent_runtime.py`

Remove:
- `"deferred_action.fire"` from `_SUPPORTED_INPUT_TYPES`
- `DeferredActionPayload` import
- The `if agent_input.input_type == "deferred_action.fire":` branch and
  the `elif isinstance(agent_input.payload, DeferredActionPayload):` branch

---

### `agent/runner/agent_runner.py`

Remove:
- `bootstrap_deferred_action_runtime()` function
- Its call in `main()` and shutdown in `finally`
- All imports of `DeferredActionExecutor`, `DeferredActionScheduler`,
  `DeferredActionDAO`, `DeferredActionOccurrenceDAO`

---

## Deleted Files

| Path | Reason |
|---|---|
| `agent/runner/deferred_action_executor.py` | Execution path retired |
| `agent/runner/deferred_action_scheduler.py` | Scheduling retired |
| `agent/runner/deferred_action_policy.py` | Policy only used by scheduler |
| `agent/agno_agent/tools/deferred_action/service.py` | Write path retired |
| `agent/agno_agent/tools/deferred_action/tool.py` | Replaced by reminder_protocol tool |
| `agent/agno_agent/tools/deferred_action/__init__.py` | Package deleted |
| `agent/agno_agent/adapters/deferred_action_result.py` | Only used by executor |
| `dao/deferred_action_dao.py` | No active callers remain |
| `dao/deferred_action_occurrence_dao.py` | Only used by executor |

---

## Deleted Tests

| Path | Reason |
|---|---|
| `tests/unit/runner/test_deferred_action_executor.py` | Tests deleted executor |
| `tests/unit/runner/test_deferred_action_scheduler.py` | Tests deleted scheduler |
| `tests/unit/runner/test_deferred_action_policy.py` | Tests deleted policy |
| `tests/unit/dao/test_deferred_action_dao.py` | Tests deleted DAO |
| `tests/unit/dao/test_deferred_action_occurrence_dao.py` | Tests deleted DAO |
| `tests/e2e/test_deferred_actions_flow.py` | Tests deleted end-to-end path |
| `tests/unit/agent/test_visible_reminder_time_parser.py` | Tests functions in deleted `deferred_action/tool.py`; reminder time parsing is covered by reminder_protocol tests |

---

## New Tests

- `tests/unit/reminder/test_service_historical_import.py` — covers
  `record_historical_import`: verify `lifecycle_state="completed"`,
  `completed_at` is set, `next_fire_at=None`, scheduler not called.
- `tests/unit/connector/test_google_calendar_import_reminder.py` — covers
  the three import paths through `ReminderService` (future, recurring,
  historical). Replaces the portion of the old test suite that tested
  calendar import behavior.

---

## Import Audit

Files with live deferred_action imports (main branch, excluding worktrees):

| File | Action |
|---|---|
| `connector/clawscale_bridge/google_calendar_import_service.py` | Rewrite to use `ReminderService` |
| `agent/runner/agent_runner.py` | Remove bootstrap |
| `agent/agno_agent/runtime/agent_runtime.py` | Remove `deferred_action.fire` |
| `agent/agno_agent/runtime/inputs.py` | Remove `DeferredActionPayload` |
| `agent/agno_agent/adapters/__init__.py` | Remove `DeferredActionFireResult` re-exports |
| `agent/agno_agent/capabilities/timezone.py` | Delegate to `ReminderService` |
| `agent/agno_agent/capabilities/context_retrieve.py` | Delegate to `ReminderDAO` |

---

## Verification

```
.venv/bin/python -m pytest tests/unit/reminder/ tests/unit/connector/ tests/unit/agent/ -v
.venv/bin/python -m pytest tests/e2e/ -v
zsh scripts/check
zsh scripts/suggest-verification --base HEAD~1
```

Confirm no `import.*deferred_action` in main branch after the change:
```
grep -rn "deferred_action" agent/ connector/ dao/ tests/ --include="*.py" | grep -v __pycache__
```

---

## Non-Goals

- No migration of existing `deferred_actions` MongoDB documents. The
  collection stays in place; existing records simply stop being executed.
- `find_imported_reminder_duplicate` duplicate-detection logic for calendar
  import is in scope (must be migrated to read `reminders`), but adding full
  deduplication features to `ReminderDAO` beyond what is needed for import is
  out of scope.
- No changes to `agent/reminder/` scheduler, fire consumer, or event handler.
- No changes to `UNSUPPORTED_DEFERRED_ACTION_KINDS` guard (it disappears with
  the executor).
