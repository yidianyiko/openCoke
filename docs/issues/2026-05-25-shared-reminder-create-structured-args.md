---
title: Shared reminder create dropped structured scheduling args
status: resolved
kind: incident
affected_surfaces:
  - agent_runtime
  - scheduling_domain
---

# Shared reminder create dropped structured scheduling args

## What happened

Batch `20260525t044322Z` reached an active Alice/Bob friendship. Alice then
asked to create a shared reminder:

`我想约 Bob 这周五晚上 19:30 一起在小区操场跑步 40 分钟，帮我们两个建一个共享提醒。`

The outer chat agent called `scheduling_domain` with structured
`create_shared_reminder` args:

- `invitee_name = Bob`
- `time = 2026-05-29T19:30:00`
- `duration = 40`
- `activity = 跑步`
- `location = 小区操场`

The runtime converted those args into an intent string and sent the inner
scheduling worker back through model parsing. The gateway received an invalid
body and no `shared_reminder_requests` row was created.

## Why it mattered

Shared-reminder reject/cancel/accept scenarios cannot run unless creation
lands in Postgres. Users also receive a fallback after giving all required
details.

## Root cause

Structured scheduling args were normalized into an intent string but not passed
as trusted `forced_args` to the scheduling capability port. Common model aliases
for shared-reminder creation (`time`, `duration`, `activity`, `location`) were
also not normalized to the gateway contract (`fire_at`, `duration_minutes`,
`title`).

## Fix

When scheduling intent normalization produces structured args, the runtime now
splits the tool name from the args and calls the exact scheduling capability
with `forced_args`. Shared-reminder creation aliases are normalized before the
capability call.

Fix commit: this commit.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_preserves_tool_key_args tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_normalizes_common_create_aliases -q`
- Fresh live batch `20260525t045704Z` after `pm2 restart coke-agent`:
  Alice created a shared reminder with Bob and received
  `已提交共享提醒请求。`. Postgres showed one
  `pending_invitee_confirmation` row with title `小区操场跑步`.
- Same batch invitee-reject continuation: Bob said
  `拒绝 Alice 那条共享提醒。`, the assistant replied
  `已拒绝共享提醒并取消你的提醒。`, Postgres showed
  `shared_reminder_requests.status = rejected`, and Mongo showed only Alice's
  requester reminder in `cancelled` state with no Bob reminder.
