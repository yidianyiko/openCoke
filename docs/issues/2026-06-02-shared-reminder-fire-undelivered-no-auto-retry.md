---
kind: incident
status: open
title: Shared reminder fire reached only one participant after provider failure
created_at: 2026-06-02
updated_at: 2026-06-02
surface:
  - clean-rebuild
  - reminder
  - social-scheduling
  - channel-reachability
  - wechat-personal
related:
  - docs/issues/2026-05-31-implementation-conformance-audit.md#G-009
  - docs/issues/2026-05-27-wechat-ilink-business-failure-delivery.md
---

# Shared Reminder Fire Undelivered Without Auto Retry

## What Happened

Production shared reminder `94ab5a8e-327d-445a-b31c-f43b544e437d`
(`和lizihao约音乐课`) was scheduled for `2026-06-02 22:30 Asia/Shanghai`
and had active projections for both participants:

- `lizihao` account `635d3bdc-1b02-4a08-acf4-9940b91a9de5`
- `olivers` account `ae02ff01-6fcd-4d39-a189-e51c8c8a31e6`

At fire time, the scheduler created two reminder-fire turns. Both turns rendered
outbound reminder text, but only `olivers` got a successful provider send.
`lizihao`'s provider attempt failed with `ilink_send_failed_ret_-2`, leaving
that reminder fire in `delivery_result='undelivered'`.

## Why It Matters

Shared reminder fire delivery is participant-scoped. A provider failure for one
participant must not make the shared reminder appear globally successful, and it
must not silently wait for the missed participant to send a later inbound message
before any recovery is attempted.

This is user-visible data loss for a due reminder: one participant receives the
time-sensitive message, while the other participant misses it.

## Affected Surfaces

- `coke-scheduler`: enqueued both `turn.reminder_fire` events.
- `coke-worker` / `TurnRunner`: rendered both `ReminderFireTurn` messages.
- `ChannelReachabilityService`: persisted one failed and one sent delivery
  attempt.
- `ReminderService.record_fire_delivery`: recorded the failed participant as
  `undelivered`.
- Provider webhook recovery: current `UndeliveredResendTurn` is only queued
  after a later inbound webhook, not immediately after a failed proactive send.

## Evidence

Live host: `gcp-coke`, active compose path `/home/whoami/coke-clean`, clean
containers `coke-clean-*`.

Shared reminder and projections:

- `shared_reminder.id = 94ab5a8e-327d-445a-b31c-f43b544e437d`
- title `和lizihao约音乐课`
- local trigger `2026-06-02 22:30:00`, timezone `Asia/Shanghai`
- projections:
  - lizihao reminder `06e6e37d-55d4-43a5-8603-a23250efc244`
  - olivers reminder `bceac9e1-8f1f-4d0b-bd1c-7013a3ae18bd`

Reminder fire rows:

- lizihao fire `aaa6f1a7-358d-48e9-9e41-8aa3c9425aa3`
  - due `2026-06-02 14:30:00+00`
  - `fire_state='claimed'`
  - `delivery_result='undelivered'`
- olivers fire `abe83b9a-8267-4fdb-bb09-83002acfd6bd`
  - due `2026-06-02 14:30:00+00`
  - `fire_state='claimed'`
  - `delivery_result='delivered'`

Outbound messages:

- lizihao message `07d23d42-aac5-4b20-8006-dd8262356be4`
  - turn `7047a0f9-34f8-4270-ac4c-ab91acb2f360`
  - text `提醒你：和lizihao约音乐课，时间到了！`
  - created `2026-06-02 14:30:23.223959+00`
- olivers message `4b60d5d3-cc95-47dd-8f96-b77e45adc9a1`
  - turn `3d7d7f2d-0044-49c4-b950-250e718a0c59`
  - text `到点啦～和lizihao的音乐课时间到了!`
  - created `2026-06-02 14:30:34.203055+00`

Delivery attempts:

- lizihao route: `status='failed'`,
  `error_code='ilink_send_failed_ret_-2'`, no provider message id,
  attempted `2026-06-02 14:30:24.596309+00`
- olivers route: `status='sent'`, provider message id present,
  attempted `2026-06-02 14:30:35.145612+00`

Provider logs around the failure:

- `coke-worker`: `POST http://host.docker.internal:8095/send` returned
  `502 BAD GATEWAY` for the lizihao send.
- `wechat-personal-connector`: two iLink send attempts returned `{"ret": -2}`
  at `2026-06-02 14:30:24`.
- The next olivers send returned `202 ACCEPTED`.

Outbox:

- Two `turn.reminder_fire` rows were created at `2026-06-02 14:30:02+00`.
- No `turn.undelivered_resend` row was created after `2026-06-02 14:30:00+00`.
- This matches code in `coke/api/provider_webhooks.py`: undelivered resend is
  enqueued from inbound provider webhooks, not from the failed outbound send.

## Root Cause

The immediate failure was a provider-side iLink business failure for lizihao:
`ret=-2`, surfaced through the connector as HTTP `502` and recorded in Coke as
`delivery_attempt.status='failed'` with
`error_code='ilink_send_failed_ret_-2'`.

The product bug is the missing automatic recovery path for active reminder-fire
delivery failures. Coke correctly records the lizihao fire as `undelivered`, but
the only implemented resend trigger for undelivered reminder facts is tied to a
later inbound webhook from that same account. A time-sensitive shared reminder
fire therefore stays missed unless the missed user speaks again.

The shared reminder data model and scheduler fanout worked: both projections,
both reminder-fire rows, and both render turns existed. The failure boundary is
delivery recovery after one participant's provider send fails.

## Current Status

Open. The missed lizihao fire remains `delivery_result='undelivered'`. No code
fix or manual repair was applied during this investigation.

## Fix Direction

Implement an automatic bounded retry or delayed resend path for failed
`ReminderFireTurn` deliveries that have `delivery_result='undelivered'`.

The fix should preserve the existing participant-scoped lifecycle:

- do not re-render or resend the already delivered participant's reminder;
- retry only the undelivered fire/account;
- keep idempotency stable so a retried send cannot duplicate visible messages
  after a provider accepts the original attempt;
- keep provider business failures visible in `delivery_attempt`;
- treat `ret=-2` as a retryable send failure, not as a successful delivery and
  not as a session-expiry event.

Verification should include a production-like shared reminder fire where one
participant's provider send fails first, then succeeds through the retry path,
while the other participant is not resent.
