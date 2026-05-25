---
title: Product notification pending messages interrupted direct user turns
kind: active_issue
date: 2026-05-25
status: resolved
resolved: 2026-05-25
affected_surfaces:
  - agent/runner/rollback_detection.py
  - tests/unit/runner/test_rollback_detection.py
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260525t035044Z.json
---

# Product notification pending messages interrupted direct user turns

## What Happened

In `reject_friend` batch `20260525t035044Z`, Alice sent
`拒绝 Bob 的好友请求。`. The direct request/response turn returned empty after
about 205 seconds. Postgres still showed Bob's request as `pending`, and Bob's
follow-up also saw it as pending.

Worker logs showed the direct turn repeatedly rolled back before the agent
runtime started because a pending `product-notification:*` message for Alice was
treated as a newer user message. After the maximum rollback count, the direct
turn was force-completed without executing.

## Why It Matters

A product notification should not preempt or cancel a live request/response
user command. Otherwise the user can issue an explicit write action, receive no
reply, and the durable state stays unchanged.

## Root Cause

`is_new_message_coming_in` treated every pending inputmessage for the same user
and character as an interrupt after excluding only the current message ids. It
did not exclude pending product-notification business conversations.

## Fix

Rollback detection now ignores pending messages whose business conversation key
is `product-notification:*` when deciding whether a new user message has
arrived.

## Verification

- `.venv/bin/python -m pytest tests/unit/runner/test_rollback_detection.py tests/unit/runner/test_message_acquirer_clawscale.py tests/unit/runner/test_agent_handler_inflight_interrupt.py -q`
- `git diff --check`
