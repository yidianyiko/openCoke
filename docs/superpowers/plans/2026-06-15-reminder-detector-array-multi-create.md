# Reminder Detector Array Multi-Create Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent detector JSON shape quirks from crashing reminder create turns and ensure coalesced two-reminder create input creates both reminders.

**Architecture:** Keep the existing semantic Planner -> Execute -> Express shape. Strengthen planner guidance and corpus coverage so multiple create requests become `reminder.batch_create` items, then keep each detector call scoped to one item. Add a narrow detector parser tolerance for a single object wrapped in a top-level array; do not accept multi-object arrays as a single detector result because batch ownership belongs at the planner/action layer.

**Tech Stack:** Python, pytest, Coke clean turn runtime, reminder detector JSON client, reminder inbound handler.

---

Plan Status: completed

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
