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
  reminder_event_handler.py    — message_source default fixed ("reminder")
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
  runtime/__init__.py          — DeferredActionPayload removed
  runtime/inputs.py            — DeferredActionPayload removed
  runtime/agent_runtime.py     — deferred_action.fire input type removed
agent/prompt/
  chat_contextprompt.py        — "deferred_action" message_source renamed "reminder"
agent/util/
  message_util.py              — is_proactive_message check updated
dao/
  deferred_action_dao.py       — DELETED
  deferred_action_occurrence_dao.py — DELETED
connector/clawscale_bridge/
  google_calendar_import_service.py — writes to ReminderService
```

## Module Contracts

### `agent/reminder/service.py` — new surface

Add two methods:

```python
def create_imported_reminder(
    self,
    *,
    owner_user_id: str,
    command: ReminderCreateCommand,
    import_metadata: dict,
) -> Reminder:
```

Like `create()` but writes `import_metadata` to the `metadata` field instead
of `{}`. Computes `next_fire_at`, calls `_call_scheduler` if active. Used for
future and recurring calendar imports.

```python
def record_historical_import(
    self,
    *,
    owner_user_id: str,
    title: str,
    schedule: ReminderSchedule,
    agent_output_target: AgentOutputTarget,
    import_metadata: dict,
) -> Reminder:
```

Writes a `lifecycle_state="completed"` reminder directly via
`reminder_dao.insert_reminder`, with `completed_at=now()`,
`next_fire_at=None`, `metadata=import_metadata`. Does not call
`_call_scheduler`. Returns the mapped `Reminder`.

Used only by calendar import for past events that will never fire.

---

### `dao/reminder_dao.py` — new surface

Add one method:

```python
def find_imported_duplicate(
    self,
    *,
    owner_user_id: str,
    import_provider: str,
    source_event_id: str,
    source_original_start_time: str,
) -> dict | None:
```

Queries `reminders` on `owner_user_id`, `metadata.import_provider`,
`metadata.source_event_id`, `metadata.source_original_start_time`.
No lifecycle filter (preserves the existing behavior where a completed
historical record still blocks re-import).

---

### `connector/clawscale_bridge/google_calendar_import_service.py`

Replace `deferred_action_service: DeferredActionService` with
`reminder_service: ReminderService`.

**Import metadata dict** (built per-event from calendar event fields):
```python
import_metadata = {
    "import_provider": "google_calendar",
    "import_run_id": ...,
    "provider_account_email": ...,
    "source_event_id": ...,
    "source_original_start_time": ...,
}
```

**Call mapping:**

| Old call | New call |
|---|---|
| `create_imported_future_reminder(user_id, character_id, conversation_id, title, dtstart, timezone, metadata)` | `reminder_service.create_imported_reminder(owner_user_id=user_id, command=ReminderCreateCommand(title=title, schedule=ReminderSchedule(anchor_at=dtstart_utc, local_date=local_date, local_time=local_time, timezone=timezone, rrule=None), agent_output_target=AgentOutputTarget(conversation_id=conversation_id, character_id=character_id, route_key=None), created_by_system="agent"), import_metadata=import_metadata)` |
| `create_imported_recurring_reminder(..., rrule)` | Same, with `rrule=rrule` in `ReminderSchedule` |
| `create_imported_historical_reminder(...)` | `reminder_service.record_historical_import(owner_user_id=user_id, title=title, schedule=ReminderSchedule(...), agent_output_target=AgentOutputTarget(...), import_metadata=import_metadata)` |

**Field derivation for `ReminderSchedule`:**
- `anchor_at` = `dtstart.astimezone(UTC)`
- `local_date` = `dtstart.astimezone(ZoneInfo(timezone)).date()`
- `local_time` = `dtstart.astimezone(ZoneInfo(timezone)).time().replace(tzinfo=None)`
- `timezone` = timezone string from calendar event
- `rrule` = rrule string or `None`

**Duplicate detection:** Replace `self.deferred_action_service.action_dao`
lookup with `self.reminder_service.reminder_dao.find_imported_duplicate(
owner_user_id=user_id, import_provider="google_calendar",
source_event_id=source_event_id,
source_original_start_time=source_original_start_time)`.

---

### `agent/agno_agent/capabilities/timezone.py`

Replace `DeferredActionService().realign_visible_reminders_for_timezone_change`
with inline logic using `ReminderService`:

1. Call `reminder_service.list_for_user(owner_user_id=user_id, query=ReminderQuery(lifecycle_states=["active"]))`.
2. For every returned reminder (all active visible reminders are floating-local
   in the Reminder model — there is no `fixed_timezone` concept), recompute
   `anchor_at`:
   ```python
   new_anchor = datetime.combine(
       r.schedule.local_date,
       r.schedule.local_time,
       tzinfo=ZoneInfo(new_timezone),
   ).astimezone(UTC)
   new_schedule = ReminderSchedule(
       anchor_at=new_anchor,
       local_date=r.schedule.local_date,
       local_time=r.schedule.local_time,
       timezone=new_timezone,
       rrule=r.schedule.rrule,
   )
   reminder_service.update(
       reminder_id=r.id,
       owner_user_id=user_id,
       patch=ReminderPatch(schedule=new_schedule),
   )
   ```

`ReminderService` is injected via `TimezoneCapabilityPort`'s
`contract_factory` pattern (already established for other contracts in this
module).

---

### `agent/agno_agent/capabilities/context_retrieve.py`

Replace `DeferredActionDAO.list_visible_actions(user_id)` with
`reminder_dao.list_for_owner(owner_user_id=user_id, lifecycle_states=["active"])`.
`ReminderDAO.list_for_owner` already filters `visibility="visible"`.

Update `_retrieve_confirmed_reminders` formatter to read `next_fire_at`
(reminder document field) instead of `next_run_at` (old deferred action
field).

`ReminderDAO` is injectable via `ContextRetrieveCapabilityPort`.

---

### `agent/runner/reminder_event_handler.py`

Line 110: change `context.setdefault("message_source", "deferred_action")`
to `context.setdefault("message_source", "reminder")`. This is the legacy
output-writer path (non-typed runtime); the typed runtime path already sets
`message_source="reminder"` correctly at line 201.

---

### `agent/prompt/chat_contextprompt.py`

Rename the `"deferred_action"` message_source string to `"reminder"` at lines
40, 51, and 66. After retirement, reminder fires arrive with
`message_source="reminder"`. The prompt behaviour is unchanged; only the
string token changes.

---

### `agent/util/message_util.py`

Line 257: change
```python
is_proactive_message = context.get("message_source") == "deferred_action"
```
to
```python
is_proactive_message = context.get("message_source") in {"deferred_action", "reminder"}
```
This preserves existing behavior during any transition and is correct after
retirement (both fire paths use `"reminder"`).

---

### `agent/agno_agent/runtime/inputs.py`

Remove `DeferredActionPayload` dataclass and `"deferred_action.fire"` from
`AgentInput.input_type` Literal and payload discriminator map.

---

### `agent/agno_agent/runtime/__init__.py`

Remove `DeferredActionPayload` from the import block and from `__all__`.

---

### `agent/agno_agent/runtime/agent_runtime.py`

Remove:
- `"deferred_action.fire"` from `_SUPPORTED_INPUT_TYPES`
- `DeferredActionPayload` import
- The `if agent_input.input_type == "deferred_action.fire":` branch and
  the `elif isinstance(agent_input.payload, DeferredActionPayload):` branch

---

### `agent/agno_agent/adapters/__init__.py`

Remove the entire deferred-action import block:
```python
from agent.agno_agent.adapters.deferred_action_result import (
    DeferredActionFireResult,
    map_agent_result_to_deferred_status,
)
```
Remove both `"DeferredActionFireResult"` and `"map_agent_result_to_deferred_status"`
from `__all__`, leaving only `ReminderCommandExecutor`.

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
| `agent/runner/deferred_action_policy.py` | Used by executor and DeferredActionService; both deleted |
| `agent/agno_agent/tools/deferred_action/service.py` | Write path retired; calendar import redirected to ReminderService |
| `agent/agno_agent/tools/deferred_action/tool.py` | Replaced by reminder_protocol tool |
| `agent/agno_agent/tools/deferred_action/__init__.py` | Package deleted |
| `agent/agno_agent/adapters/deferred_action_result.py` | Only used by executor |
| `dao/deferred_action_dao.py` | No active callers remain after calendar import migration |
| `dao/deferred_action_occurrence_dao.py` | Only used by executor |

---

## Deleted Tests

| Path | Disposition |
|---|---|
| `tests/unit/runner/test_deferred_action_executor.py` | DELETE — tests deleted executor |
| `tests/unit/runner/test_deferred_action_scheduler.py` | DELETE — tests deleted scheduler |
| `tests/unit/runner/test_deferred_action_policy.py` | DELETE — tests deleted policy |
| `tests/unit/dao/test_deferred_action_dao.py` | DELETE — tests deleted DAO |
| `tests/unit/dao/test_deferred_action_occurrence_dao.py` | DELETE — tests deleted DAO |
| `tests/e2e/test_deferred_actions_flow.py` | DELETE — tests deleted execution path |
| `tests/unit/agent/test_visible_reminder_time_parser.py` | DELETE — tests functions in deleted `deferred_action/tool.py` |
| `tests/unit/agent/test_deferred_action_service.py` | DELETE — tests deleted service |
| `tests/unit/runner/test_agent_runner_deferred_actions.py` | DELETE — tests deleted bootstrap |
| `tests/unit/agent/test_agent_runtime_types.py` | REWRITE — remove `DeferredActionPayload` type assertions; retain other runtime-type tests |
| `tests/unit/test_context_retrieve_deferred_reminders.py` | REWRITE — update expectations to use `ReminderDAO.list_for_owner` and `next_fire_at` |
| `tests/unit/test_timezone_tools.py` | REWRITE — update expectations to use `ReminderService.update` |
| `tests/unit/connector/clawscale_bridge/test_google_calendar_import_service.py` | REWRITE — update to inject `ReminderService`; assert import metadata in reminder documents |
| `tests/e2e/test_reminder_system_flow.py` | RETAIN AND UPDATE — remove any `deferred_action` import or patch; keep reminder system assertions |

---

## New Tests

- `tests/unit/reminder/test_service_historical_import.py` — covers
  `record_historical_import`: verify `lifecycle_state="completed"`,
  `completed_at` is set, `next_fire_at=None`, `metadata` contains import
  fields, scheduler not called.
- `tests/unit/reminder/test_service_create_imported.py` — covers
  `create_imported_reminder`: verify `metadata` carries import fields,
  `next_fire_at` is computed, scheduler registers the reminder.
- `tests/unit/dao/test_reminder_dao_find_imported_duplicate.py` — covers
  `find_imported_duplicate`: no-lifecycle-filter behavior, returns None when
  no match.

---

## Import Audit

Files with live deferred_action imports (main branch, excluding worktrees):

| File | Action |
|---|---|
| `connector/clawscale_bridge/google_calendar_import_service.py` | Rewrite to use `ReminderService` |
| `agent/runner/agent_runner.py` | Remove bootstrap |
| `agent/agno_agent/runtime/agent_runtime.py` | Remove `deferred_action.fire` |
| `agent/agno_agent/runtime/inputs.py` | Remove `DeferredActionPayload` |
| `agent/agno_agent/runtime/__init__.py` | Remove `DeferredActionPayload` from imports and `__all__` |
| `agent/agno_agent/adapters/__init__.py` | Remove `DeferredActionFireResult` and `map_agent_result_to_deferred_status` |
| `agent/agno_agent/capabilities/timezone.py` | Delegate to `ReminderService` |
| `agent/agno_agent/capabilities/context_retrieve.py` | Delegate to `ReminderDAO` |

---

## Verification

```bash
.venv/bin/python -m pytest tests/unit/reminder/ tests/unit/connector/ tests/unit/agent/ tests/unit/runner/ tests/unit/dao/ -v
.venv/bin/python -m pytest tests/e2e/ -v
zsh scripts/check
zsh scripts/suggest-verification --base HEAD~1
```

Confirm no deferred-action class or module imports remain:
```bash
grep -rn "from .*deferred_action\|import.*DeferredAction" \
  agent/ connector/ dao/ tests/ --include="*.py" | grep -v __pycache__
```

Note: `message_source == "deferred_action"` string literals in
`reminder_event_handler.py`, `chat_contextprompt.py`, and `message_util.py`
are addressed by the module contracts above and will not appear after this
change.

---

## Non-Goals

- No migration of existing `deferred_actions` MongoDB documents. The
  collection stays in place; existing records simply stop being executed.
- No changes to `agent/reminder/` scheduler, fire consumer, or event handler
  beyond the `message_source` default fix.
- Adding full deduplication features to `ReminderDAO` beyond
  `find_imported_duplicate` is out of scope.
