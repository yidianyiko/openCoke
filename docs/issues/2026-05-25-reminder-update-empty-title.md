---
title: Personal reminder update forwarded empty title fields
kind: active_issue
date: 2026-05-25
status: resolved
affected_surfaces:
  - agent/agno_agent/adapters/reminder_command_executor.py
  - agent/agno_agent/tools/reminder_protocol/tool.py
  - agent/reminder/service.py
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-reminder-crud-20260525t013016Z.json
---

# Personal reminder update forwarded empty title fields

## What Happened

V2 smoke iteration 1 ran `personal_reminder_crud` with batch
`reminder-crud-20260525t013016Z`. Alice created and listed a personal reminder,
then asked: `把刚才那个跑步提醒改到早上 7 点半。`

The assistant replied that it could not find the reminder. Mongo confirmed the
original `跑步 30 分钟` reminder stayed at 07:00 until the later cancel turn.

## Why It Matters

Schedule-only updates are a core personal reminder CRUD path. A user can create
and cancel reminders but cannot reliably adjust the reminder time, even when
the target reminder is unambiguous in recent context.

## Root Cause

`ReminderDetectDecision` represents omitted optional write fields as empty
strings. `ReminderCommandExecutor` forwarded those empty strings directly to the
visible reminder tool. For an update-time-only decision, that produced a
`ReminderPatch(title="")`, and `ReminderService.update` correctly rejected the
patch with `Reminder title must be non-empty`.

## Fix

Normalized omitted optional tool fields to `None` in the command executor,
including batch operations, while preserving the explicit `action` string.

## Verification

- RED: `pytest tests/unit/agent/test_reminder_command_executor.py::test_structured_update_time_decision_does_not_send_empty_title_fields -q`
  failed because `title == ""`.
- GREEN: `pytest tests/unit/agent/test_reminder_command_executor.py -q`
  passed, 11 tests.
- Targeted: `pytest tests/unit/agent/test_reminder_command_executor.py tests/unit/agent/test_visible_reminder_protocol_tool.py -q`
  passed, 43 tests.
- Live rerun: `reminder-crud-20260525t013551Z` no longer failed with
  `Reminder title must be non-empty`; it now fails later with
  `InvalidSchedule` because the detector resolves "早上 7 点半" as today's
  already-past time instead of the existing reminder's date. Track separately
  as the next CRUD bug.

Broader `pytest tests/unit/agent/ -q` is currently red outside this fix: runtime
tests have stale fake `_create_interaction_agent` signatures, and scheduling
type snapshots now include `friend_name/requester_name`.

Fix commit: the commit containing this resolved issue record.
