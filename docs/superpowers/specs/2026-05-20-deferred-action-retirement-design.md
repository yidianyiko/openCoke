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

## Issues

### Issue 1 — Calendar import metadata would be dropped
**File:** `agent/reminder/models.py`
**Claim:** Calendar import can replace `DeferredActionService.create_imported_*` with `ReminderService.create(...)` and `record_historical_import(...)`, while duplicate detection later reads import metadata from `reminders`.
**Reality:** `connector/clawscale_bridge/google_calendar_import_service.py:181-187` builds import metadata containing `import_provider`, `import_run_id`, `provider_account_email`, `source_event_id`, and `source_original_start_time`. The deferred action path persists that under `payload.metadata` in `agent/agno_agent/tools/deferred_action/service.py:372-383`. `ReminderCreateCommand` only accepts `title`, `schedule`, `agent_output_target`, and `created_by_system` at `agent/reminder/models.py:51-57`, and `ReminderService.create()` hard-codes `metadata={}` plus `origin="user"` at `agent/reminder/service.py:68-73`.
**Fix:** The spec should add a Reminder import write contract that preserves the Google import metadata, either by extending the reminder create/import API or by adding dedicated import methods that write `metadata` and an import-specific origin/source field. Duplicate detection on `reminders` is not viable unless the import metadata is written.

### Issue 2 — ReminderCreateCommand call is missing a required field
**File:** `agent/reminder/models.py`
**Claim:** The new future/recurring calendar import call can construct `ReminderCreateCommand(title, ReminderSchedule(...), AgentOutputTarget(...))`, and `created_by_system` stays `"agent"`.
**Reality:** `ReminderCreateCommand` has no default for `created_by_system`; it is a required fourth dataclass field at `agent/reminder/models.py:51-57`. The literal does accept only `"agent"`, so the value is valid, but the example call omits it.
**Fix:** The spec should show `ReminderCreateCommand(title=..., schedule=..., agent_output_target=..., created_by_system="agent")` for every `ReminderService.create()` import path.

### Issue 3 — Duplicate detection selector is underspecified
**File:** `connector/clawscale_bridge/google_calendar_import_service.py`
**Claim:** `find_imported_reminder_duplicate` currently checks `deferred_actions` and should be migrated to `reminders` via a DAO method or inline query.
**Reality:** The bridge gets `self.deferred_action_service.action_dao`, returns `None` if it has no `find_imported_reminder_duplicate`, and calls it with `user_id`, `import_provider="google_calendar"`, `source_event_id`, and `source_original_start_time` at `connector/clawscale_bridge/google_calendar_import_service.py:240-255`. `DeferredActionDAO.find_imported_reminder_duplicate()` queries `user_id` plus `payload.metadata.import_provider`, `payload.metadata.source_event_id`, and `payload.metadata.source_original_start_time` with no lifecycle filter at `dao/deferred_action_dao.py:135-150`.
**Fix:** The spec should define the exact ReminderDAO selector, for example `owner_user_id` plus the reminder metadata fields that replace `payload.metadata.*`, and should state whether the current no-lifecycle-filter behavior is preserved.

### Issue 4 — Timezone realignment contract does not match ReminderService or Reminder model semantics
**File:** `agent/reminder/service.py`
**Claim:** Timezone realignment should call `ReminderService.list_for_user(owner_user_id=user_id, query=ReminderQuery(lifecycle_states=["active"]))`, detect floating-local reminders by absence of an absolute UTC anchor in the rrule, and call `ReminderService.update(reminder_id, owner_user_id, ReminderPatch(schedule=new_schedule))`.
**Reality:** `ReminderService.list_for_user()` does exist with the claimed keyword-only signature at `agent/reminder/service.py:187-197`, but `ReminderService.update()` is also keyword-only and requires `reminder_id=...`, `owner_user_id=...`, and `patch=...` at `agent/reminder/service.py:92-98`. The Reminder model has only `anchor_at`, `local_date`, `local_time`, `timezone`, and `rrule` in `agent/reminder/models.py:10-17`; there is no `schedule_kind` or `fixed_timezone` field. Recurring reminders already compute from `local_date`, `local_time`, and `timezone` in `agent/reminder/schedule.py:251-270`, while the old floating/fixed distinction exists only on deferred action dictionaries in `agent/agno_agent/tools/deferred_action/service.py:260-312`.
**Fix:** The spec should use the keyword-only update call and should define the new Reminder-side realignment rule in terms of existing Reminder fields. If fixed-vs-floating behavior is required, the spec must add an explicit Reminder model/metadata marker instead of inferring it from rrule text.

### Issue 5 — Context retrieval cannot keep the formatter unchanged
**File:** `agent/agno_agent/capabilities/context_retrieve.py`
**Claim:** Replace `DeferredActionDAO.list_visible_actions(user_id)` with `ReminderDAO.list_active_visible(owner_user_id)` and leave the rest of `_retrieve_confirmed_reminders` unchanged.
**Reality:** `ReminderDAO` does not have `list_active_visible`, but it does have an equivalent `list_for_owner(owner_user_id, lifecycle_states=...)` that already filters `visibility="visible"` at `dao/reminder_dao.py:74-80`. The existing formatter reads deferred action dictionaries and expects `next_run_at` at `agent/agno_agent/capabilities/context_retrieve.py:146-169`; reminder documents and models use `next_fire_at`, as shown by `ReminderService.create()` writing it at `agent/reminder/service.py:75` and `_map_document()` reading it at `agent/reminder/service.py:593`.
**Fix:** The spec should say to use `ReminderDAO.list_for_owner(owner_user_id, lifecycle_states=["active"])` or an explicit wrapper, and update the formatter to read `next_fire_at` from reminder documents or `Reminder.next_fire_at` from service results.

### Issue 6 — Adapter export cleanup is incomplete
**File:** `agent/agno_agent/adapters/__init__.py`
**Claim:** Remove `DeferredActionFireResult` re-exports from `agent/agno_agent/adapters/__init__.py`.
**Reality:** The file imports and exports both `DeferredActionFireResult` and `map_agent_result_to_deferred_status` from `agent.agno_agent.adapters.deferred_action_result` at `agent/agno_agent/adapters/__init__.py:1-10`.
**Fix:** The spec should say to remove the deferred-action import block and both `DeferredActionFireResult` and `map_agent_result_to_deferred_status` from `__all__`, leaving `ReminderCommandExecutor`.

### Issue 7 — deferred_action_policy is not only used by the scheduler/executor
**File:** `agent/agno_agent/tools/deferred_action/service.py`
**Claim:** `agent/runner/deferred_action_policy.py` is "Policy only used by scheduler" / only used by the scheduler and executor.
**Reality:** `grep` shows `deferred_action_policy` is imported by `agent/runner/deferred_action_executor.py:13`, `agent/agno_agent/tools/deferred_action/service.py:7`, and `tests/unit/runner/test_deferred_action_policy.py:5`. The scheduler does not import it; `DeferredActionService` uses it for create/update next-run calculation at `agent/agno_agent/tools/deferred_action/service.py:79`, `236`, `293`, and `417`.
**Fix:** The spec should describe the policy as used by the executor and deferred action service. It can still be deleted, but only because both runtime users disappear or are rewritten.

### Issue 8 — Import audit misses runtime package exports
**File:** `agent/agno_agent/runtime/__init__.py`
**Claim:** The import audit table lists the live deferred-action imports that need removal.
**Reality:** `agent/agno_agent/runtime/__init__.py` imports `DeferredActionPayload` from `agent.agno_agent.runtime.inputs` at `agent/agno_agent/runtime/__init__.py:8-13` and exports it in `__all__` at `agent/agno_agent/runtime/__init__.py:23-39`. This file is not in the import audit table.
**Fix:** Add `agent/agno_agent/runtime/__init__.py` to the import audit and remove `DeferredActionPayload` from both the import block and `__all__`.

### Issue 9 — Deleted tests list is incomplete
**File:** `tests/`
**Claim:** The Deleted Tests section lists the tests that should be deleted with the deferred action stack.
**Reality:** All listed test files exist, but the required grep shows additional unlisted tests still importing, patching, or asserting deferred-action runtime surfaces: `tests/unit/agent/test_deferred_action_service.py`, `tests/unit/agent/test_agent_runtime_types.py`, `tests/unit/runner/test_agent_runner_deferred_actions.py`, `tests/unit/test_context_retrieve_deferred_reminders.py`, `tests/unit/test_timezone_tools.py`, `tests/unit/connector/clawscale_bridge/test_google_calendar_import_service.py`, and `tests/e2e/test_reminder_system_flow.py`.
**Fix:** The spec should classify these tests explicitly as delete, rewrite, or retain-with-updated-assertions. In particular, service/runtime-type/bootstrap tests should be deleted or rewritten, while calendar import, context retrieval, timezone, and reminder-system tests need Reminder-based expectations.

### Issue 10 — Verification grep is broader than the stated import check
**File:** `docs/superpowers/specs/2026-05-20-deferred-action-retirement-design.md`
**Claim:** The verification section says to "Confirm no `import.*deferred_action`" but gives `grep -rn "deferred_action" agent/ connector/ dao/ tests/ --include="*.py" | grep -v __pycache__`.
**Reality:** The required grep output includes non-import string references such as `agent/util/message_util.py:257`, `agent/runner/reminder_event_handler.py:110`, `agent/runner/agent_handler.py:255`, and `agent/prompt/chat_contextprompt.py:40-66`. That command will fail even if imports are removed unless those message-source strings are also migrated or the grep is narrowed.
**Fix:** Either add explicit cleanup for the remaining `message_source == "deferred_action"` string contract, or change the verification command to check imports/classes only, such as `grep -rn "from .*deferred_action\\|import .*deferred_action\\|DeferredAction" ...`.
