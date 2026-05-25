---
status: active
created_at: 2026-05-26
owner: bridge-runtime
kind: bug-design
---

# Bug Y - Placeholder leak after bridge sync timeout

## Problem

When `/bridge/inbound` waits longer than the synchronous reply window, the bridge
returns the receipt `正在处理中，稍后把结果发给你。`. That receipt is useful, but it
must not become the user's final visible answer. The eventual agent reply must
still enter the async push path. The coach-booking smoke batch
`coach-booking-20260525t154642Z.json` shows the receipt leaked as the only
visible reply in slow turns, with 14 string occurrences across the evidence and
affected cases including C2, C3, C4, and C12.

Smoke caveat: these smoke accounts have no gateway `DeliveryRoute`. A correct
late reply should still be promoted and claimed by the bridge dispatcher, then
fail at gateway `/api/outbound` with `404 missing_delivery_route`. That 404 is
the known `wont_fix` fixture gap, not the Bug Y promotion failure.

## Current Behavior

### 1. Inbound request is enqueued

`BusinessOnlyBridgeGateway._enqueue_and_wait` builds `enqueue_payload` and calls
`CokeMessageGateway.enqueue`. The payload includes:

- `coke_account_id` / `customer_id`, tenant/channel/end-user identifiers, and
  `sync_reply_token` / `inbound_event_id` when present.
- `business_conversation_key` and `gateway_conversation_id` only when the
  inbound payload carries them.

`CokeMessageGateway.build_input_message` writes the `inputmessages` row with
`metadata.source=clawscale` and
`metadata.business_protocol.delivery_mode=request_response`.

Evidence:

- C4 input `smoke_evt_70d...` was written and handled.
- C3 input `smoke_evt_6dd...` was initially pending, then later produced output.
- C2 inputs `smoke_evt_a128...` and `smoke_evt_08dc...` were pending in the case
  snapshot and later marked handled.
- C12 had three inputs; two finished inside sync, one timed out.

### 2. Sync wait times out and bridge sends the receipt

`ReplyWaiter.wait_for_reply` queries pending text `outputmessages` with:

- `status=pending`
- `metadata.source=clawscale`
- `metadata.business_protocol.delivery_mode=request_response`
- matching `metadata.business_protocol.causal_inbound_event_id`
- matching `sync_reply_token` when present

On timeout, `_enqueue_and_wait` enters the `except TimeoutError` branch. If
`late_reply_fallback` exists and `customer_id` is a non-empty string, it calls
`late_reply_fallback.start_async(...)` and returns:

```json
{"status": "ok", "reply": "正在处理中，稍后把结果发给你。"}
```

Therefore every observed placeholder reply proves this branch ran and
`start_async` was called. The `/bridge/inbound` route serializes that as the
synchronous JSON reply. It does not write the placeholder to `outputmessages`.

Evidence:

- C4 turn 14, C3 turn 15, C2 turns 27/28, and C12 turn 31 each elapsed about
  25s, returned the placeholder, and had `output_id=null`.

### 3. Agent eventual reply may be written after the receipt

The agent reply is still produced through `agent/util/message_util.py`.
`send_message_via_context` copies ClawScale request-response metadata from the
input, injects `business_conversation_key` into
`metadata.business_protocol.business_conversation_key`, and writes an
`outputmessages` row via `send_message`.

For request-response outputs the row remains `status=pending`; it does not have
top-level `customer_id` / `account_id`, and it does not have top-level push
metadata such as `metadata.delivery_mode`, `metadata.output_id`, or
`metadata.idempotency_key`. Those are expected to be added later by the bridge
late-reply promoter.

Evidence:

- C4 added output `6a146fc000057ec4fa6b9872` with the real clarification text,
  `status=pending`, `to_user=ck_smoke_..._jin`, no top-level `customer_id` or
  `account_id`, and only nested
  `business_protocol.delivery_mode=request_response`.
- C3 later added output `6a146fde00057ec4fa6b98af` with the real refusal text,
  also `status=pending`, no top-level customer/account id, and only nested
  request-response metadata.
- C12's first two parallel turns produced handled sync outputs; the third Kai
  turn timed out and had no output in the case delta by the snapshot.
- C2 had no output rows in the case delta; its inputs were later marked handled.
  That may be an additional agent-runtime or snapshot-timing issue, but it does
  not change the bridge promotion bug for rows that are written.

### 4. Late promoter waits for the real reply

`LateReplyFallbackPromoter.start_async` starts a daemon thread targeting
`_promote_for_async_dispatch`.

`_promote_for_async_dispatch` calls
`ReplyWaiter.wait_for_reply_message(..., consume=False)`. `consume=False` is
important: the promoter does not mark the late reply `handled`; it leaves the
row pending so it can be converted into a push candidate.

The promoter then requires a non-empty nested
`metadata.business_protocol.business_conversation_key`. C4 and C3 rows have
that key, so they pass this gate.

### 5. Route bind preflight can stop promotion before dispatcher can see it

If `delivery_route_client` is configured, `_promote_for_async_dispatch` tries to
bind the delivery route before updating the output row. If `tenant_id`,
`conversation_id`, `channel_id`, `end_user_id`, and `external_end_user_id` are
all non-empty strings, it calls `GatewayDeliveryRouteClient.bind(...)`;
exceptions are logged and promotion continues. Otherwise it logs
`late_clawscale_reply_missing_route_context` and returns `False` before updating
the output row.

The second branch is the observed leak. Smoke inbound metadata has tenant,
channel, end-user, and external id, but not `gateway_conversation_id`. The
promoter therefore returns before writing the push fields.

### 6. Dispatcher cannot claim the stranded row

`ClawScaleOutputDispatcher._claimable_query` only claims rows with:

- top-level `customer_id` or `account_id`
- `metadata.business_conversation_key`
- `metadata.delivery_mode=push`
- `metadata.output_id`
- `status=pending` or stale `dispatching`

The stranded late rows remain request-response-shaped: no top-level
`customer_id` / `account_id`, no `metadata.delivery_mode=push`, no
`metadata.output_id`, and no `metadata.idempotency_key`. The dispatcher never
claims them. Gateway `/api/outbound` is never reached, so smoke cannot show the
expected `failed` push row.

## What Is Broken

The broken step is `_promote_for_async_dispatch` returning `False` when route
bind context is incomplete. This is not primarily an idempotency-key problem:
the intended key is deterministic (`late_sync_reply:<output_id>`) and is written
correctly when the promotion update runs. This is not caused by the placeholder
being stored as a push output; it is sync-only and should remain sync-only. This
is not caused by `ReplyWaiter.wait_for_reply` marking the eventual reply
`handled` after timeout; the late promoter uses `consume=False`.

Rows that never get written by the agent within the late fallback wait window
are a separate failure mode. Bug Y's bridge fix covers the case where the
eventual real reply exists but is stranded before async dispatch.

## Proposed Fix

Keep the placeholder receipt behavior, but make route binding a best-effort
preflight that never blocks promotion of an existing real reply.

Minimal implementation:

1. Keep the `business_conversation_key` gate. Without that key the dispatcher
   cannot call `/api/outbound` correctly.
2. If all route bind fields are present, keep calling
   `delivery_route_client.bind(...)`.
3. If bind raises, keep the existing behavior: log and continue.
4. If route context is incomplete, log
   `late_clawscale_reply_missing_route_context_promoting_without_bind` and
   continue instead of returning `False`.
5. Always run the pending-guarded `mongo.update_one(..., {"$set": ...})`
   promotion update when the message has `business_conversation_key`.

The update must set:

- `customer_id=<coke account id>`
- `metadata.business_conversation_key=<nested business key>`
- `metadata.delivery_mode=push`
- `metadata.output_id=str(outputmessage._id)`
- `metadata.idempotency_key=late_sync_reply:<outputmessage._id>`
- `metadata.trace_id=late_sync_reply:<outputmessage._id>`
- `metadata.causal_inbound_event_id=<inbound event id>`

Expected outcome:

- Real users with a `DeliveryRoute`: the dispatcher claims the row and gateway
  delivers the real late reply.
- Real users where route bind context is present but route does not yet exist:
  bind still creates/refreshes the route before dispatch.
- Smoke accounts with no `DeliveryRoute`: the dispatcher claims the row, POSTs
  `/api/outbound`, receives `404 missing_delivery_route`, and finalizes the row
  as `status=failed`. That is expected evidence for the fixture gap.

Do not create a synthetic `DeliveryRoute` for smoke. Do not write the
placeholder to `outputmessages`. Do not change model selection; the LLM remains
GLM-5.1 thinking-off.

## Risk Analysis

Commit `9fe8a907 fix: send processing receipt on bridge reply timeout` changed
the timeout branch from returning only `{"ok": true}` to returning a visible
processing receipt. The older behavior was worse because a slow turn could
leave the user with no visible feedback inside ClawScale's request-response
window.

The fix must preserve that benefit: keep returning the placeholder immediately,
start late promotion exactly as today, and do not delay the HTTP response while
trying to bind routes or dispatch.

The new risk is duplicate delivery if a late reply is both consumed sync and
promoted push. The existing status guard controls this: the promotion update
matches only `{"_id": message["_id"], "status": "pending"}`. If the sync waiter
already consumed the row, the update does not fire.

The other risk is surfacing smoke-only 404s as test failures. Verification must
classify them correctly: `status=failed` with correct push metadata is success
for smoke promotion; missing or unclaimed push metadata is Bug Y still present.

## Verification Plan

### Unit test sketch

Add a focused bridge unit test near the existing late-reply tests:

`test_late_reply_fallback_promotes_reply_when_route_context_missing`

Setup: `reply_waiter.wait_for_reply_message` returns a pending request-response
output with `_id=out_late_missing_ctx` and nested
`business_protocol.business_conversation_key=bc_late_missing_ctx`; call
`_promote_for_async_dispatch` with tenant/channel/end-user ids but
`conversation_id=None`.

Assert: returned value is `True`; `delivery_route_client.bind` is not called;
`mongo.update_one` uses the pending-status guard and all push metadata fields;
the idempotency key equals `late_sync_reply:out_late_missing_ctx`.

Keep the existing test where bind raises and promotion continues.

### Dispatcher unit check

Use an existing or new output-dispatcher test to assert that a promoted late row
with `customer_id`, `metadata.business_conversation_key`,
`metadata.delivery_mode=push`, `metadata.output_id`, and
`metadata.idempotency_key` is claimable and is posted to the gateway client.

This proves the bridge update shape matches `_claimable_query`.

### Smoke assertion

After a slow turn that returns the placeholder:

1. Poll mongo for a non-placeholder `outputmessages` row whose nested
   `metadata.business_protocol.causal_inbound_event_id` equals the slow turn's
   inbound event id.
2. Assert the row has non-empty `metadata.business_conversation_key`,
   `metadata.delivery_mode=push`, `metadata.output_id=str(_id)`,
   `metadata.idempotency_key=late_sync_reply:<_id>`,
   `metadata.trace_id=metadata.idempotency_key`,
   `metadata.causal_inbound_event_id=<inbound event id>`, and top-level
   `customer_id=<smoke coke_account_id>`.
3. Run or wait for the dispatcher.
4. For smoke accounts, assert the same row reaches `status=failed` and gateway
   logs show `/api/outbound` returned `404 missing_delivery_route` for the same
   `customer_id` and `business_conversation_key`.
5. Assert no `outputmessages` row with message equal to
   `正在处理中，稍后把结果发给你。` has `metadata.delivery_mode=push` or
   `status=failed`. The placeholder remains a sync-only receipt.

### Real-user smoke

For an account with an active `DeliveryRoute`, force or simulate a slow bridge
turn:

- `/bridge/inbound` returns the placeholder inside the sync window.
- The eventual real reply row is promoted to push.
- Dispatcher finalizes it as `status=handled`.
- Gateway outbound delivery uses the existing exact `DeliveryRoute`.

## Reviewable summary

- The placeholder is returned only after sync timeout and is not written to
  `outputmessages`.
- The agent can still write the real reply later as a pending request-response
  output row.
- The current leak is the promoter's early return on missing route bind context,
  before it adds push metadata.
- The minimal fix is to keep route binding best-effort and always promote rows
  that have `business_conversation_key`.
- Smoke success means a real-reply push row is claimed and then fails with
  `missing_delivery_route`, not that the user receives it.
- The placeholder must never become a failed push row.
