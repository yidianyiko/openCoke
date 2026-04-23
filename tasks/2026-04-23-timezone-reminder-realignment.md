# Task: Timezone Reminder Realignment

- Status: Completed
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
- Evidence: `32 passed` on 2026-04-23 after closing keyword-call,
  confirmation-branch, and legacy-metadata gaps.
- Command: `pytest tests/unit/test_user_dao_timezone.py tests/unit/agent/test_timezone_service.py tests/unit/runner/test_identity.py tests/unit/test_context_timezone.py tests/unit/test_prepare_workflow_timezone.py tests/unit/test_timezone_tools.py tests/unit/test_tool_results_context.py tests/unit/agent/test_deferred_action_service.py tests/unit/agent/test_visible_reminder_time_parser.py -v`
- Evidence: `80 passed` on 2026-04-23.
- Command: `pytest tests/unit/test_repo_os_structure.py -v`
- Evidence: `4 passed` on 2026-04-23 after task-state update.
- Command: `zsh scripts/check`
- Evidence: `check passed` on 2026-04-23.

## Notes

- Plan lives in `docs/exec-plans/2026-04-23-timezone-reminder-realignment.md`.
- Floating-local visible reminders now realign on direct timezone changes and
  accepted confirmation replies only.
- Absolute-delay, fixed-timezone, inactive, and internal followup actions stay
  unchanged.
- Legacy reminders missing `schedule_kind` / `fixed_timezone` metadata are
  treated as floating-local defaults during realignment.
