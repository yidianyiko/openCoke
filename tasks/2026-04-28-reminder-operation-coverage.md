# Task: Reminder Operation Coverage

## Goal

Restore the real user reminder input corpus and create a reminder-tool-only
evaluation path for ReminderDetectAgent and visible reminder tooling.

## Scope

- Restore `scripts/reminder_test_cases.json`.
- Evaluate only ReminderDetectAgent plus a fake `visible_reminder_tool`
  recorder.
- Keep ChatResponse, Interact, PostAnalyze, Mongo writes, and outbound delivery
  out of this evaluation.
- Use the new tool contract: `trigger_at` / `new_trigger_at` as ISO 8601 aware
  datetimes and RFC 5545 `RRULE` strings for recurrence.

## Non-Goals

- Replacing generic LLM chat response cases.
- Preserving the old `trigger_time` / natural-language parser contract.

## Validation Notes

- Corpus syntax validated as JSON.
- Eval helper tests validate corpus loading and deterministic case selection.
- Real MiniMax smoke runs against the fake reminder tool recorder only.
