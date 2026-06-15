---
kind: active_issue
status: resolved
surface:
  - turn-planner
  - reminder-runtime
  - production-smoke
severity: P0
created_at: 2026-06-15
updated_at: 2026-06-15
resolved_at: 2026-06-15
---

# 2026-06-15 P0: Planner Extra Param Crashed Date-Scoped Cancel

## What Happened

On deployed build `3d874299`, the user message `今天的提醒全部取消` closed with
grounded failure recovery instead of cancelling reminders. Worker logs showed
`PlannerOutputError: invalid action.params.date_phrase`.

## Why It Matters

A single extra planner parameter should not turn a recoverable structured-action
shape issue into a whole-turn crash. The user-visible result was an internal
failure reply and no reminder cancellation.

## Root Cause

The DeepSeek planner emitted `date_phrase` on a reminder delete/cancel action to
scope `今天的`. `date_phrase` was accepted only on `reminder.list` and
`social_scheduling.availability_query`; `coke/turn/inbound/plan.py` treated any
operation-unknown param key as fatal planner output and raised
`PlannerOutputError`. Even if that key had been dropped, the delete path still
required `match` and did not apply a day window to bulk cancellation.

## Fix

- Unknown planner param keys are dropped and logged instead of raising, while
  domain/operation validation and validation for retained known keys remain
  strict.
- `date_phrase` is accepted on personal reminder delete/complete.
- Plan compile lets date-scoped delete/complete omit `match`; vague deletes
  without a date still require a target.
- The reminder handler resolves `date_phrase` with `date_windows.py` and calls
  domain-service bulk delete/complete over the resolved local-day window.

## Verification

- Focused red/green tests cover unknown-param dropping, date-scoped compile, and
  date-scoped bulk delete.
- Final verification commands and commit hash are recorded in the task handoff.
