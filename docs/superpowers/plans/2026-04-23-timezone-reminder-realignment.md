# Timezone Reminder Realignment

## Goal

When a user changes timezone, future active visible reminders with floating
local-time semantics should be reinterpreted in the new timezone and
rescheduled accordingly.

## Scope

- In scope:
  - Active visible `user_reminder` actions with `schedule_kind=floating_local`
    and `fixed_timezone=false`
  - User-driven timezone change paths that already persist canonical timezone
    state
  - Scheduler rescheduling after reminder realignment
- Out of scope:
  - Internal proactive followups
  - Fixed-timezone reminders
  - Absolute-delay reminders
  - New UI behavior

## Inputs

- Related task: `tasks/2026-04-23-timezone-reminder-realignment.md`
- Related references:
  - `docs/superpowers/specs/2026-04-23-user-timezone-system-design.md`
  - `docs/exec-plans/2026-04-23-user-timezone-system.md`

## Touched Surfaces

- worker-runtime
- repo-os

## Work Breakdown

1. Add a reminder realignment method in deferred-action service, with tests for
   floating-local reschedule and absolute-delay/fixed-timezone no-op behavior.
2. Call the realignment method from explicit timezone-change paths, with tests
   for direct set and confirmation acceptance.
3. Verify targeted timezone/reminder suites and update task state.

## Verification

- Command: `pytest tests/unit/agent/test_deferred_action_service.py tests/unit/test_timezone_tools.py tests/unit/test_prepare_workflow_timezone.py -v`
- Expected evidence: floating reminder realignment and timezone update trigger
  paths pass together.
- Command: `pytest tests/unit/test_user_dao_timezone.py tests/unit/agent/test_timezone_service.py tests/unit/runner/test_identity.py tests/unit/test_context_timezone.py tests/unit/test_prepare_workflow_timezone.py tests/unit/test_timezone_tools.py tests/unit/test_tool_results_context.py tests/unit/agent/test_deferred_action_service.py tests/unit/agent/test_visible_reminder_time_parser.py -v`
- Expected evidence: timezone-system targeted suite remains green.

## Notes

- Realignment preserves local wall-clock fields for floating reminders and
  recomputes `next_run_at` from the updated `dtstart`.
