---
title: ClawScale request-response batching mixed product notifications with user turns
kind: active_issue
date: 2026-05-25
status: resolved
resolved: 2026-05-25
affected_surfaces:
  - agent/runner/message_processor.py
  - tests/unit/runner/test_message_acquirer_clawscale.py
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260525t014635Z.json
---

# ClawScale request-response batching mixed product notifications with user turns

## What Happened

V2 smoke iteration 2 ran `reject_friend` with batch `20260525t014635Z`.
Postgres ended in the correct state (`friend_requests.status=rejected`,
`friendships=0`), and Bob later saw that Alice rejected the request.

Alice's explicit turn `拒绝 Bob 的好友请求。` returned an empty synchronous reply
after roughly 205 seconds. Mongo showed product-notification outputs for Alice
(`已拒绝好友请求。` and a failure message) but no output tied to Alice's direct
bridge causal id.

## Why It Matters

The database write can succeed while the request-response user sees no reply.
That makes the live path look broken and can trigger duplicate user retries.

## Root Cause

`MessageAcquirer` selected a top ClawScale request-response message and then
called `read_all_inputmessages(from_user, to_user, platform, pending)`. That
batched every pending message from the same Coke account, even when one pending
message belonged to a product-notification business conversation and another
belonged to Alice's direct bridge causal event.

The runtime then emitted output against the product-notification conversation
instead of Alice's direct request-response causal id.

## Status

Resolved by filtering acquired ClawScale request-response batches to the same
stable business thread as the top message. The thread key uses
`business_conversation_key`, `gateway_conversation_id`,
`causal_inbound_event_id`, or the legacy ClawScale conversation identifiers in
that order.

## Verification

- `.venv/bin/python -m pytest tests/unit/runner/test_message_acquirer_clawscale.py -q`
