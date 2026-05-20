---
title: Deferred Action Full-Stack Retirement
date: 2026-05-20
status: complete
spec: docs/superpowers/specs/2026-05-20-deferred-action-retirement-design.md
---
# Execution Plan
## Steps
### Step 1 — Add imported reminder service methods
**Action:** Add `create_imported_reminder` and `record_historical_import` after the existing `create()` method so calendar imports can write visible reminders through `ReminderService`.
**Files:** `agent/reminder/service.py`
**Verify:** `python -c "import agent.reminder.service"` after each step

### Step 2 — Add imported duplicate lookup
**Action:** Add `find_imported_duplicate` to `ReminderDAO` using the import metadata fields without a lifecycle filter.
**Files:** `dao/reminder_dao.py`
**Verify:** `python -c "import dao.reminder_dao"` after each step

### Step 3 — Rewrite Google Calendar import to use reminders
**Action:** Replace `deferred_action_service` with `reminder_service`, create `ReminderCreateCommand` and `ReminderSchedule` objects for future and recurring events, record historical imports as completed reminders, and route duplicate checks through `ReminderDAO.find_imported_duplicate`.
**Files:** `connector/clawscale_bridge/google_calendar_import_service.py`
**Verify:** `python -c "import connector.clawscale_bridge.google_calendar_import_service"` after each step

### Step 4 — Update timezone realignment to use ReminderService
**Action:** Replace the deferred-action timezone realignment call with inline `ReminderService.list_for_user` and `ReminderService.update` logic.
**Files:** `agent/agno_agent/capabilities/timezone.py`
**Verify:** `python -c "import agent.agno_agent.capabilities.timezone"` after each step

### Step 5 — Update context retrieval to use ReminderDAO
**Action:** Remove `DeferredActionDAO` wiring, instantiate `ReminderDAO`, list active owner reminders, and format `next_fire_at`.
**Files:** `agent/agno_agent/capabilities/context_retrieve.py`
**Verify:** `python -c "import agent.agno_agent.capabilities.context_retrieve"` after each step

### Step 6 — Fix reminder event message source default
**Action:** Change the legacy event handler message source default from `deferred_action` to `reminder`.
**Files:** `agent/runner/reminder_event_handler.py`
**Verify:** `python -c "import agent.runner.reminder_event_handler"` after each step

### Step 7 — Fix prompt and message utility message source strings
**Action:** Replace prompt references to `deferred_action` with `reminder`, and allow `message_util` proactive detection to accept both transition strings.
**Files:** `agent/prompt/chat_contextprompt.py`, `agent/util/message_util.py`
**Verify:** `python -c "import agent.prompt.chat_contextprompt; import agent.util.message_util"` after each step

### Step 8 — Remove DeferredActionPayload from runtime inputs
**Action:** Delete `DeferredActionPayload` and remove its discriminator entry.
**Files:** `agent/agno_agent/runtime/inputs.py`, `agent/agno_agent/runtime/__init__.py`
**Verify:** `python -c "import agent.agno_agent.runtime.inputs; import agent.agno_agent.runtime"` after each step

### Step 9 — Remove deferred-action fire handling from agent runtime
**Action:** Remove `deferred_action.fire` from supported input types, imports, and payload handling branches.
**Files:** `agent/agno_agent/runtime/agent_runtime.py`
**Verify:** `python -c "import agent.agno_agent.runtime.agent_runtime"` after each step

### Step 10 — Remove deferred-action adapter exports
**Action:** Remove `deferred_action_result` imports and exported symbols.
**Files:** `agent/agno_agent/adapters/__init__.py`
**Verify:** `python -c "import agent.agno_agent.adapters"` after each step

### Step 11 — Remove deferred-action bootstrap from runner
**Action:** Remove `bootstrap_deferred_action_runtime`, its startup and shutdown calls, and unused DAO/executor/scheduler imports.
**Files:** `agent/runner/agent_runner.py`
**Verify:** `python -c "import agent.runner.agent_runner"` after each step

### Step 12 — Delete retired deferred-action implementation files
**Action:** Delete the deferred action executor, scheduler, policy, tool package, adapter, and DAO files listed in the design.
**Files:** `agent/runner/deferred_action_executor.py`, `agent/runner/deferred_action_scheduler.py`, `agent/runner/deferred_action_policy.py`, `agent/agno_agent/tools/deferred_action/service.py`, `agent/agno_agent/tools/deferred_action/tool.py`, `agent/agno_agent/tools/deferred_action/__init__.py`, `agent/agno_agent/adapters/deferred_action_result.py`, `dao/deferred_action_dao.py`, `dao/deferred_action_occurrence_dao.py`
**Verify:** `python -c "import agent.runner.agent_runner"` after each step

### Step 13 — Delete or rewrite deferred-action tests
**Action:** Delete tests that only cover retired modules, then rewrite retained tests to remove deferred-action references while preserving their remaining assertions.
**Files:** `tests/unit/runner/test_deferred_action_executor.py`, `tests/unit/runner/test_deferred_action_scheduler.py`, `tests/unit/runner/test_deferred_action_policy.py`, `tests/unit/dao/test_deferred_action_dao.py`, `tests/unit/dao/test_deferred_action_occurrence_dao.py`, `tests/e2e/test_deferred_actions_flow.py`, `tests/unit/agent/test_visible_reminder_time_parser.py`, `tests/unit/agent/test_deferred_action_service.py`, `tests/unit/runner/test_agent_runner_deferred_actions.py`, `tests/unit/agent/test_agent_runtime_types.py`, `tests/unit/test_context_retrieve_deferred_reminders.py`, `tests/unit/test_timezone_tools.py`, `tests/unit/connector/clawscale_bridge/test_google_calendar_import_service.py`, `tests/e2e/test_reminder_system_flow.py`
**Verify:** `python -c "import agent.agno_agent.runtime.inputs; import connector.clawscale_bridge.google_calendar_import_service"` after each step

### Step 14 — Write reminder import tests
**Action:** Add focused tests for historical import recording, active imported reminder creation, and imported duplicate lookup.
**Files:** `tests/unit/reminder/test_service_historical_import.py`, `tests/unit/reminder/test_service_create_imported.py`, `tests/unit/dao/test_reminder_dao_find_imported_duplicate.py`
**Verify:** `python -c "import agent.reminder.service; import dao.reminder_dao"` after each step

### Step 15 — Run full targeted suite and fix import-path errors
**Action:** Run the requested test command, fix only import-path errors, and leave unrelated behavior failures reported.
**Files:** Any files needed only for import-path cleanup in the touched surfaces.
**Verify:** `python -c "import agent.reminder.service"` after each step
