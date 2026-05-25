---
title: Empty friend-request reads returned no visible summary
kind: active_issue
date: 2026-05-25
status: resolved
resolved: 2026-05-25
affected_surfaces:
  - agent/agno_agent/capabilities/scheduling.py
  - tests/unit/agent/test_scheduling_capability.py
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260525t033651Z.json
---

# Empty friend-request reads returned no visible summary

## What Happened

In batch `20260525t033651Z`, Alice asked whether she had pending friend requests
or system notifications. The scheduling domain called `list_friend_requests`
and got an empty list, but the final assistant message was empty and the bridge
returned the hardcoded fallback.

## Why It Matters

An empty read is still a successful user-facing answer. Without a visible
summary, a correct backend read can look like a failed turn.

## Root Cause

`SchedulingCapabilityPort` provided fallback summaries for `get_user_link`,
pending shared reminders, and write tools, but not for empty
`list_friend_requests` results.

## Fix

`list_friend_requests` now adds a visible summary when the gateway returns no
pending request items.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_scheduling_capability.py -q`
- `git diff --check`
