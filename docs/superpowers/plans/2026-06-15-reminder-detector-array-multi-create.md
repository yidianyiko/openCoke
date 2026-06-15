# Reminder Detector Array Multi-Create Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent detector JSON shape quirks from crashing reminder create turns and ensure coalesced two-reminder create input creates both reminders.

**Architecture:** Keep the existing semantic Planner -> Execute -> Express shape. Planner guidance and corpus coverage still prefer multiple create requests as `reminder.batch_create` items, but Execute must not depend on the planner reliably splitting. The detector now has both a single-result API (`extract`) and an explicit multi-result API (`extract_many`). Create, batch-create, and domain `detect_and_create` flatten valid detector arrays into existing `ReminderBatchItem`s, while malformed detector output still becomes `invalid_detector_output`.

**Tech Stack:** Python, pytest, Coke clean turn runtime, reminder detector JSON client, reminder inbound handler.

---

Plan Status: completed

### Follow-up: Multi-Object Detector Array Is Valid Batch Input

Live verification against deployed `364c61b9` showed that the original
planner-first design was insufficient: DeepSeek can return a valid multi-object
detector array for a coalesced two-reminder create, and the planner does not
reliably split first.

- [x] Add a handler-level red test where the actual JSON completion parser sees
  a two-object `detected_reminder_fields` array and one create action creates
  both reminders.
- [x] Add a service-level red test where one `detect_and_create` item expands a
  two-field detector result into two batch item results.
- [x] Add `AgnoJSONCompletionClient.complete_json_list()` without weakening
  `complete_json()` single-mapping behavior.
- [x] Add `SiliconFlowReminderDetector.extract_many()` and keep `extract()` as a
  single-result API.
- [x] Flatten multi-detected fields in reminder create, batch-create, and domain
  `detect_and_create` paths.
- [x] Run the user-requested unit command.
- [x] Run `black . && isort .`; revert formatter-only churn outside scope.
- [x] Commit the follow-up fix.

### Task 1: Pin Detector Array Tolerance

**Files:**
- Modify: `tests/unit/coke/llm/test_reminder_detector.py`
- Modify: `coke/llm/json_completion.py`

- [x] Add a detector test where the JSON client returns a single-object list and `SiliconFlowReminderDetector.extract()` returns normal `DetectedReminderFields`.
- [x] Run the focused detector test and confirm it fails with `LLMOutputError("invalid detected_reminder_fields shape")`.
- [x] Update `_mapping_from_content()` to unwrap exactly one mapping from a top-level list or tuple.
- [x] Run the focused detector test and confirm it passes.

### Task 2: Pin Coalesced Multi-Create Execution

**Files:**
- Modify: `tests/unit/coke/turn/inbound/test_pipeline.py`
- Modify: `tests/unit/coke/turn/inbound/test_plan.py`
- Modify: `tests/unit/coke/turn/inbound/test_plan_cases.py`
- Modify: `coke/turn/inbound/plan.py`

- [x] Add a pipeline test with two current input messages and a `reminder.batch_create` plan. Use the real `ReminderActionHandler`, `ReminderService`, and `InMemoryReminderRepository`; stub only the detector and Express boundary. Assert both reminders are created with `2026-06-15T09:00:00+08:00` and `2026-07-03T14:00:00+08:00`.
- [x] Add planner prompt/corpus coverage requiring separate requested reminders in one input window to be represented as `reminder.batch_create` items.
- [x] Run the focused pipeline/planner tests and confirm the new prompt assertion fails before prompt changes.
- [x] Update planner prompt text to explicitly route multiple personal reminder creates in one turn to one `reminder.batch_create` action with one item per reminder.
- [x] Run the focused pipeline/planner tests and confirm they pass.

### Task 3: Preserve Single Create And Verify Scope

**Files:**
- Modify: `tests/unit/coke/turn/inbound/test_pipeline.py`
- Modify: `docs/issues/2026-06-15-reminder-detector-array-multi-create.md`
- Modify: `docs/superpowers/plans/2026-06-15-reminder-detector-array-multi-create.md`

- [x] Add or keep a single-create turn-path test proving existing single reminder creation still creates one reminder.
- [x] Investigate other detector parser consumers and record whether they share the top-level shape brittleness.
- [x] Run the user-requested unit command from the worktree root.
- [x] Run `black .` and `isort .`, then revert any formatter-only churn outside scope.
- [x] Run diff-aware routing and risk report.
- [x] Run the suggested `clean-rebuild-backend repo-os-docs` surface.
- [x] Update this plan and the issue with final verification.
- [x] Commit the scoped change.
