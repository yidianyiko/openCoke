---
title: Reminder temporal creation contract drift
kind: incident
status: resolved
area: reminders
created: 2026-06-12
updated: 2026-06-12
---

# Reminder Temporal Creation Contract Drift

## Problem

Two reminder creation paths drifted away from the current product contract:

- A recurring request with an explicit weekday and time, such as
  "every Monday at 9 AM", can still be pushed into a clarification path asking
  which week instead of using the next matching future occurrence as the first
  trigger.
- Conversation-created calendar-visible reminders can still rely on a runtime
  fallback duration instead of requiring the LLM-facing creation path to provide
  an explicit or estimated duration.

The common failure mode is architectural: temporal meaning is split across
prompts, detector parsing, reminder service defaults, recurrence helpers, and
tests. That makes old special cases look harmless even when they override the
product contract.

## Impact

Users see unnecessary clarification for already-specific recurring reminders,
and calendar entries may be stored with the old 15-minute lower-bound default
instead of an LLM-estimated duration.

## Current Status

Resolved. The fix is tracked by
`docs/superpowers/specs/2026-06-12-reminder-temporal-contract-design.md` and
`docs/superpowers/plans/2026-06-12-reminder-temporal-contract.md`.

## Evidence

- `docs/product-requirements/current.md` requires reminder duration to be
  inferred from explicit duration, time range, or LLM task-duration estimation
  for conversation-created reminders.
- Calendar import separately allows a 15-minute default when an imported event
  has no duration. That boundary must not leak into conversation-created
  reminders.

## Resolution

- Added `coke.domains.reminder.temporal` as the reminder-domain temporal
  contract boundary.
- Routed reminder create, recurrence advancement, and detector recurrence
  parsing through the same canonical recurrence and duration validation.
- Removed detector repair of RRULE-style recurrence output.
- Updated tests so conversation-created timed, recurring, and shared reminders
  carry explicit or detector-estimated durations.

## Verification

Passing evidence:

- `.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py tests/unit/coke/llm/test_reminder_detector.py -q`
  passed 45 tests.
- `.venv/bin/python -m pytest tests/unit/coke/reminder -q` passed 50 tests.
- `.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/turn/inbound/test_reminder_handler.py tests/unit/coke/turn/inbound/test_social_handler.py -q`
  passed 84 tests.
- `.venv/bin/python -m pytest tests/unit/coke/calendar_import/test_calendar_import_service.py tests/unit/coke/settings/test_settings_service.py tests/unit/coke/test_delivery_lifecycle_callbacks.py -q`
  passed 26 tests.
- `.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py::test_shared_reminder_detect_tool_defaults_to_current_user_message_and_timezone -q`
  passed.
- `.venv/bin/python -m py_compile coke/domains/reminder/temporal.py coke/domains/reminder/service.py coke/domains/reminder/recurrence.py coke/llm/reminder_detector.py`
  passed.
- `git diff --check` passed.
- `zsh scripts/check` passed.
- `zsh scripts/verify-surface repo-os-docs` passed.

Blocked broader evidence:

- `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` failed in
  `clean-rebuild-backend` with 8 failures, 928 passes, and 1 skipped test. The
  failures were in the concurrent turn close/composition/output-protocol area:
  stale `materialize_staged_command` signatures, recovery staged-command
  status, a missing social-scheduling structured claim, and composition still
  passing `materialize_staged_command` to `CloseCoordinator`.
