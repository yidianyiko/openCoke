---
title: Empty friend-list reads returned no visible summary
kind: active_issue
date: 2026-05-25
status: resolved
resolved: 2026-05-25
affected_surfaces:
  - agent/agno_agent/capabilities/scheduling.py
  - tests/unit/agent/test_scheduling_capability.py
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260525t034056Z.json
---

# Empty friend-list reads returned no visible summary

## What Happened

In `reject_friend` batch `20260525t034056Z`, Alice rejected Bob's pending friend
request successfully. Her follow-up turn `看看我现在的好友列表。` called
`list_friends` and got an empty list, but the assistant returned the hardcoded
empty fallback.

## Why It Matters

An empty friend list is a valid direct answer. Returning a fallback makes a
successful read look like the agent failed to understand the user.

## Root Cause

`SchedulingCapabilityPort` had visible summaries for selected read operations
and writes, but not for empty `list_friends` results.

## Fix

`list_friends` now adds a visible summary when no friend items are returned.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_scheduling_capability.py -q`
- `git diff --check`
