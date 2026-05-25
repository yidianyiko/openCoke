---
title: Friend request accept wording routed as list-only query
kind: incident
date: 2026-05-25
status: fix_implemented_pending_verification
affected_surfaces:
  - agent/agno_agent/runtime/agent_runtime.py
  - tests/unit/agent/test_agent_runtime_construction.py
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-badminton-20260525t054250Z.json
---

# Friend request accept wording routed as list-only query

## What happened

In badminton batch `badminton-20260525t054250Z`, Alice said:

> 我有没有未处理的好友请求？通过 Bob 的。

The chat agent called `scheduling_domain` with
`list_friend_requests(status=pending, from_friend_name=Bob)` instead of
`accept_friend_request`. The reply only listed the pending request and the
friend graph stayed pending, so the later calendar facts and shared-reminder
turns all failed downstream.

## Root cause

The deterministic runtime intent inference already recognizes the text as
`accept_friend_request`, but `_normalize_scheduling_intent` trusted a
model-supplied `list_friend_requests` mapping before checking whether the user
message contained explicit friend-request write wording.

## Fix

When the model supplies `list_friend_requests`, the runtime now lets explicit
accept, reject, or cancel wording in the user message override that read intent.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_scheduling_intent_normalization_prefers_explicit_friend_request_accept_over_list -q`
