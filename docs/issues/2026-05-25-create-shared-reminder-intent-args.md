---
title: Shared-reminder create drops structured scheduling intent arguments
kind: incident
date: 2026-05-25
status: fix_in_progress
affected_surfaces:
  - agent/agno_agent/runtime/agent_runtime.py
  - tests/unit/agent/test_agent_runtime_construction.py
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260524t171654Z.json
---

# Shared-reminder create drops structured scheduling intent arguments

## What happened

Smoke batch `20260524t171654Z` diverged in Phase 3. Alice asked Coke to create
a shared reminder with Bob for Friday 19:30. The assistant replied:

`日程操作暂时无法完成。`

Postgres showed the Bob friend request was accepted and the friendship was
active, but `shared_reminder_requests` had no row for the batch.

## Why it matters

Shared reminder creation is the handoff between the friend graph and the
invitee confirmation path. Losing the invitee argument makes the gateway fail
closed with `invalid_account`, so the smoke cannot reach the pending shared
reminder state.

## Evidence

`agent_sessions` showed the interaction agent called:

`scheduling_domain(intent={"create_shared_reminder": {"friend_name": "Bob", ...}})`

The runtime normalized that dict intent to only `create_shared_reminder` before
calling the scheduling execution worker. The structured fields that the model
had already supplied (`friend_name`, title, time, duration) were discarded, so
the gateway received no resolvable invitee and returned `invalid_account`.

## Fix

When a scheduling intent is provided as a tool-name keyed dict with nested
arguments, preserve the nested arguments in the normalized intent string. For
`create_shared_reminder`, translate common model field aliases before passing
the intent to the scheduling worker:

- `friend_name` -> `invitee_name`
- `reminder_title` -> `title`
- `reminder_time` -> `fire_at`

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_preserves_tool_key_args -q`
  failed before the fix because the intent was only `create_shared_reminder`.
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_preserves_tool_key_args -q`
  passed after the fix.
