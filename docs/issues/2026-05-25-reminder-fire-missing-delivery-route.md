---
kind: active_issue
status: open
surface:
  - agent-runtime
  - gateway
created_at: 2026-05-25
updated_at: 2026-05-25
---

# 2026-05-25 Reminder Fire Drops for Users Without ClawScale Channel Binding

## What Happened

When the in-process `ReminderScheduler` fires a personal reminder for an
account that has no `DeliveryRoute` row in postgres, the fire output is
written to mongo with the correct text and metadata, the bridge dispatcher
POSTs it to the gateway at `/api/outbound`, and the gateway responds
`404 missing_delivery_route`. The dispatcher then finalizes the
`outputmessages` row as `status=failed`. The user never sees the reminder.

Smoke test `tools/agent_smoke/_runner_fire_scenario.py` reproduces this on
every fresh account it provisions. Production-shaped users who only completed
the customer-claim (web/SSO) flow without ever sending an inbound message
through a real WeChat/WhatsApp/Linq channel are in the same state — verified
with `ck_3rHT5Opcoz6paaDzrWgpI` in the local dev env, which also has all
fires failed.

## Why It Matters

The fire pipeline upstream of the gateway is correct (scheduler →
`ReminderFireEventHandler` → `send_message_via_context` → bridge dispatcher).
The contract gap is between "user has a coke account" and "user can receive
a proactive push". Today, `DeliveryRoute` rows are only created from inbound
webhook traffic via `upsertCokeDeliveryRoute` / `upsertDirectDeliveryRoute`,
both of which need a real `Channel` + `EndUser` already on file.

Two separate concerns:

1. **Real product UX:** if a customer can set up reminders before any
   messenger binding exists (e.g., dashboard / claim-only flow), every fire
   silently drops. Need to decide whether to (a) gate reminder creation on
   an existing delivery route, (b) defer/queue fires until a route appears,
   or (c) accept the gap and surface it explicitly to the user.
2. **Smoke fixture limitation:** `tools/agent_smoke` can never verify
   end-to-end fire delivery without seeding a `Channel` + `DeliveryRoute`,
   or stubbing the gateway outbound path.

## Affected Surfaces

- agent-runtime (`agent/runner/reminder_event_handler.py`,
  `agent/util/message_util.py`)
- gateway (`gateway/packages/api/src/routes/outbound.ts`,
  `gateway/packages/api/src/lib/business-conversation.ts`)
- smoke (`tools/agent_smoke/_runner_fire_scenario.py`)

## Evidence

Recent fire outputmessages in this dev env (all failed):

```
6a13f76b45b630f6ea018b78 status=failed account_id=ck_smoke_...alice msg='到点喝水啦~'
6a13f37c76e08002a4d9b42f status=failed account_id=ck_3rHT5Opcoz6paaDzrWgpI msg='提醒一下…'
... (every fire output to date is status=failed)
```

Gateway log:

```
<-- POST /api/outbound
--> POST /api/outbound 404 25ms
```

Postgres:

```
SELECT count(*) FROM delivery_routes;  -- 0
SELECT count(*) FROM channels;          -- 0
```

Outputmessage metadata for the smoke fire shows correct delivery payload
(`business_conversation_key`, `delivery_mode=push`, `output_id`,
`idempotency_key`, `trace_id`, `reminder_id`, `fire_at`). So the failure
mode is downstream of correct dispatch.

## Current Status

- Open. Root cause confirmed; no fix in code yet.
- Smoke fixture caveat: `_runner_fire_scenario.py` currently reports FAILED
  for the wrong reason — it doesn't yet distinguish "pipeline broken" from
  "no DeliveryRoute available". Either teach the runner to PASS when fire
  reached the gateway with correct content, or seed a stub channel.

## Resolution

(unfilled)
