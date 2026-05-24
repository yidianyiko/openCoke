---
title: Reminder list query asks for missing create fields
kind: incident
date: 2026-05-25
status: fix_in_progress
affected_surfaces:
  - agent/agno_agent/capabilities/reminder_intent.py
  - agent/agno_agent/adapters/reminder_command_executor.py
  - tests/unit/agent/test_reminder_intent_capability.py
  - tests/unit/agent/test_reminder_command_executor.py
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260524t172458Z.json
---

# Reminder list query asks for missing create fields

## What happened

Smoke batch `20260524t172458Z` completed the shared-reminder write path:
Postgres showed `shared_reminder_requests.status=accepted`, and Mongo had two
active reminder documents. Bob then asked:

`看看我现在所有的提醒，特别是和 Alice 的那条。`

The assistant replied that it could not load the reminder list.

## Why it matters

After accepting a shared reminder, the user should be able to verify that the
reminder exists in their own reminder list. The database was correct, but the
user-visible read path failed.

## Evidence

`agent_sessions` showed repeated `reminder_domain` calls with model-supplied
`operation=list` / `list_reminders` arguments. The reminder detector returned
`ReminderDetectInvalidDecision` each time, asking for create fields
`title` and `trigger_at` instead of treating the message as a query/list
request.

The command executor's list result also discarded the reminder tool's list
summary and reminder facts from the domain operation, leaving the chat agent
with too little read evidence when list execution succeeds.

## Fix

Explicit reminder-list wording now routes directly to a query/list decision
without running the detector, while shared-reminder wording remains owned by
the scheduling domain. Reminder list domain results preserve the tool summary,
compact reminder facts, and reminder metadata so the interaction agent can
answer from read evidence, including shared-reminder counterparty metadata.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py::test_reminder_intent_port_routes_explicit_list_query_without_detector tests/unit/agent/test_reminder_command_executor.py::test_list_result_preserves_summary_and_reminder_facts -q`
  failed before the fix and passed after it.
- Batch `20260524t173726Z` verified that the reminder list query now returns
  Bob's accepted shared reminder, but also showed that metadata was needed to
  avoid denying the Alice relation; the command-executor regression now covers
  metadata preservation.
