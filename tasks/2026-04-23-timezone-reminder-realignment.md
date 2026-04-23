# Task: Timezone Reminder Realignment

- Status: In Progress
- Owner: Codex
- Date: 2026-04-23

## Goal

Make future visible floating-local reminders follow the user's latest timezone
after an explicit timezone change.

## Scope

- In scope:
  - Active visible floating-local reminders
  - Direct timezone updates and accepted timezone confirmations
  - Scheduler rescheduling after reminder realignment
- Out of scope:
  - Internal followups
  - Fixed-timezone reminders
  - Absolute-delay reminders

## Touched Surfaces

- worker-runtime
- repo-os

## Acceptance Criteria

- Updating a user's timezone realigns active visible floating-local reminders to
  the new timezone while preserving local wall-clock meaning.
- Absolute-delay and fixed-timezone reminders are left unchanged.
- Rescheduled reminders get recomputed `next_run_at` values and scheduler
  updates.

## Verification

- Command: `pytest tests/unit/agent/test_deferred_action_service.py tests/unit/test_timezone_tools.py tests/unit/test_prepare_workflow_timezone.py -v`
- Expected evidence: reminder realignment and timezone update integration tests
  pass.

## Notes

- Plan lives in `docs/exec-plans/2026-04-23-timezone-reminder-realignment.md`.
