# Task: Reminder System Protocol Boundary

- Status: Implementation complete and verified
- Owner: Task 8 implementer
- Date: 2026-04-28

## Goal

Verify the end-to-end Reminder System boundary and keep legacy internal
proactive follow-up scoped to `deferred_actions`.

## Scope

- In scope: Reminder System E2E coverage, legacy deferred-action boundary
  assertion, architecture documentation, and focused verification mapping.
- Out of scope: Reminder System production refactors, deferred-action redesign,
  Mongo/Redis integration tests, and gateway or bridge behavior changes.

## Touched Surfaces

- worker-runtime
- repo-os

## Acceptance Criteria

- User-visible reminder creation writes to `reminders`, not `deferred_actions`.
- Scheduler restart reconstructs jobs from `reminders.next_fire_at`.
- One-shot fired events enter the Agent System event handler and complete the
  reminder.
- Recurring reminders advance `next_fire_at`.
- Failed event handling marks the reminder failed.
- Existing internal proactive follow-up E2E coverage still proves
  `deferred_actions` remains the legacy boundary for that behavior.
- Architecture and verification docs name the Reminder System boundary.

## Verification

- Command: `pytest tests/e2e/test_reminder_system_flow.py -v`
- Expected evidence: reminder-system E2E flow passes.
- Command: `pytest tests/e2e/test_deferred_actions_flow.py -v`
- Expected evidence: legacy deferred-action E2E flow passes.
- Command: `pytest tests/unit/reminder/ tests/unit/dao/test_reminder_dao.py -v`
- Expected evidence: Reminder domain/service/DAO unit tests pass.
- Command: `pytest tests/unit/runner/test_reminder_scheduler.py tests/unit/runner/test_reminder_event_handler.py -v`
- Expected evidence: Reminder scheduler and Agent System handler unit tests pass.
- Command: `pytest tests/unit/agent/test_visible_reminder_protocol_tool.py tests/unit/test_tool_results_context.py -v`
- Expected evidence: visible reminder tool and tool-result context tests pass.
- Command: `zsh scripts/check`
- Expected evidence: repository structure and task/docs checks pass.

## References

- Plan: `docs/superpowers/plans/2026-04-28-reminder-system-implementation.md`
- Design: `docs/superpowers/specs/2026-04-28-reminder-system-design.md`

## Notes

- Task 8 adds E2E coverage and docs for the Reminder System vs. legacy
  deferred-action boundary.
- Current implementation keeps Reminder fired events in-process through
  `ReminderFireEventHandler`.
