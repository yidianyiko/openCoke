---
kind: progress_note
status: resolved
title: Personal reminder list query failed in production real-user smoke
created_at: 2026-05-27
updated_at: 2026-05-27
surface:
  - agent-runtime
  - reminder-runtime
  - production-smoke
evidence:
  - ../../artifacts/evidence/shared-reminder-real-user-smoke/2026-05-27-personal-crud-happy-path-smoke.md
---

# Personal Reminder List Query Real-User Regression

## Problem

Production real-user smoke with `olivers` exposed that `列一下我的提醒。`
did not reliably produce a grounded reminder list.

The first failing marker was `happy-list-20260527T094247Z`. The user-visible
reply mixed languages and described a technical problem while listing reminders
from conversation history instead of the durable list result.

## Root Cause

There were two separate issues.

1. `ReminderDetectAgent` correctly selected a query/list intent, but its
   structured payload included executor-style default fields such as
   `target_scope=recent_active` and `list_states=[]`. The schema rejected the
   decision as non-CRUD executable content, so the runtime returned
   `ReminderDetectInvalidDecision`.
2. After normalizing that schema shape, the durable list operation succeeded,
   but `AgentRuntime` still preferred a non-empty model answer over the
   reminder list operation's `visible_summary`. The model reintroduced old
   failure context into the visible reply.

## Fix

- Normalize query/list detector payloads by stripping executable fields and
  treating empty list defaults as unspecified query scope.
- Treat successful reminder list read results as authoritative visible text, so
  final output is grounded in the domain `visible_summary` instead of model
  reconstruction.

## Verification

Local:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_reminder_detect_structured_output.py \
  tests/unit/agent/test_reminder_intent_capability.py \
  tests/unit/agent/test_agent_runtime_construction.py \
  tests/unit/agent/test_agent_runtime_output_rules.py -q
```

Result: `255 passed`.

Production:

- Deployed with `./scripts/deploy-compose-to-gcp.sh --restart`.
- Final passing marker: `happy-list-fix3-20260527T102900Z`.
- List reply contained the active marker.
- List reply did not contain technical issue text.
- List reply did not contain old cancelled list markers.
- Test reminder was cancelled through the internal reminder API.

