---
title: Personal reminder update treated bare clock as past same-day time
kind: active_issue
date: 2026-05-25
status: resolved
affected_surfaces:
  - agent/agno_agent/capabilities/reminder_intent.py
  - agent/agno_agent/tools/reminder_protocol/tool.py
  - agent/reminder/service.py
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-reminder-crud-20260525t013551Z.json
---

# Personal reminder update treated bare clock as past same-day time

## What Happened

V2 smoke rerun `reminder-crud-20260525t013551Z` asked Alice to update the
existing tomorrow-morning running reminder: `把刚才那个跑步提醒改到早上 7 点半。`

The reminder domain attempted the update with a same-day 07:30 time, which was
already in the past. The assistant asked whether Alice meant tomorrow 07:30,
and Mongo confirmed the reminder stayed at tomorrow 07:00 until it was later
cancelled.

## Why It Matters

Time-only reminder updates are ordinary CRUD behavior. If a user updates a
future reminder from 07:00 to 07:30, the runtime should not reinterpret the bare
clock as an already-past same-day time and refuse the update.

## Root Cause

`ReminderIntentPort` had a post-detector correction for past bare clocks, but
it only applied to `create` and `batch` decisions. Update decisions use
`new_trigger_at`, so the correction did not run and the invalid same-day time
reached the reminder service.

## Fix

Extended past bare-clock normalization to update decisions and update
operations by correcting `new_trigger_at` to the next future occurrence when
the user did not explicitly name a date.

## Verification

- RED: `pytest tests/unit/agent/test_reminder_intent_capability.py::test_reminder_intent_port_normalizes_past_bare_clock_update_time -q`
  failed because `new_trigger_at` stayed at `2026-05-25T07:30:00+09:00`.
- GREEN: same test passed after the normalization fix.
- Targeted: `pytest tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/test_reminder_command_executor.py tests/unit/agent/test_visible_reminder_protocol_tool.py -q`
  passed, 113 tests.
- Live: `reminder-crud-20260525t014221Z` passed the full personal reminder CRUD
  scenario. Mongo confirmed the running reminder was updated to 07:30 then
  cancelled, the weekly stretch reminder has
  `schedule.rrule=FREQ=WEEKLY;BYDAY=MO`, the water reminder is active for
  tomorrow 15:00 local, and the ambiguous update asked which reminder.

Fix commit: the commit containing this resolved issue record.
