# Reminder Temporal Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce one reminder temporal creation contract for recurring first triggers and duration estimates.

**Architecture:** Add a small reminder-domain temporal helper and route service, recurrence, and detector parsing through it. Keep semantic inference in the LLM path and keep runtime validation canonical rather than heuristic.

**Tech Stack:** Python domain services, pytest unit tests, repo-OS docs.

---

### Task 1: Pin Contract With Failing Tests

**Files:**
- Modify: `tests/unit/coke/reminder/test_reminder_service.py`
- Modify: `tests/unit/coke/llm/test_reminder_detector.py`

- [x] Add a service test that a timed create without `duration_minutes` returns `failed` with `missing_duration_minutes` and writes no reminder.
- [x] Add a service test that a no-trigger-time create without `duration_minutes` still succeeds and stores the internal 15-minute value.
- [x] Add service tests for recurring create failures: missing first trigger, non-canonical rule shape, and `kind="recurring"` without a rule.
- [x] Change the detector recurrence test so RRULE-style output raises `LLMOutputError("invalid recurrence_rule")` instead of being repaired.
- [x] Run the focused tests and confirm the new assertions fail before production code changes.

### Task 2: Add Domain Temporal Helper

**Files:**
- Create: `coke/domains/reminder/temporal.py`

- [x] Implement canonical recurrence validation for `frequency`, `interval`, `window_start`, and `window_end`.
- [x] Implement positive duration parsing shared by reminder create/update/conflict code.
- [x] Implement create-time normalization that rejects calendar-visible creates with missing duration, recurring creates without canonical rules, and recurring rules without first trigger.
- [x] Implement detector trigger conversion that treats naive detector datetimes as local wall-clock values in the captured timezone and aware datetimes as absolute instants.

### Task 3: Route Reminder Runtime Through Helper

**Files:**
- Modify: `coke/domains/reminder/service.py`
- Modify: `coke/domains/reminder/recurrence.py`

- [x] Replace scattered create-time kind, recurrence, and duration logic in `ReminderService._create` with helper output.
- [x] Reuse the shared duration parser in update and conflict paths.
- [x] Validate recurrence rules in `next_occurrence_after` through the helper.
- [x] Keep calendar import's event-duration fallback untouched.

### Task 4: Tighten Detector Boundary

**Files:**
- Modify: `coke/llm/reminder_detector.py`

- [x] Parse detector recurrence output with the canonical helper.
- [x] Reject `freq`, `byday`, `hour`, and `minute` output instead of normalizing it.
- [x] Keep the prompt instruction that the model must compute the next concrete trigger for recurring requests like "every Monday at 9 AM".

### Task 5: Verify And Commit

**Files:**
- Update: `docs/issues/2026-06-12-reminder-temporal-contract.md`
- Update: `docs/superpowers/plans/2026-06-12-reminder-temporal-contract.md`

- [x] Run focused reminder detector and reminder service tests.
- [x] Run reminder-domain tests and relevant social scheduling tests.
- [x] Run `py_compile`, `git diff --check`, `zsh scripts/check`, `zsh scripts/suggest-verification --base HEAD~1`, and `zsh scripts/review-trigger --base HEAD~1`.
- [x] Run the suggested verification surface if it is practical in the current workspace; otherwise record the blocker.
- [x] Mark this issue resolved with verification evidence.
- [x] Commit only the scoped temporal contract files.
