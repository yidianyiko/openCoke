---
kind: incident
status: fixed_deployed
title: Shared reminder fire reached only one participant after provider failure
created_at: 2026-06-02
updated_at: 2026-06-03
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

Follow-up after lizihao sent a fresh inbound message:

- lizihao inbound message `508e4c0f-7eba-4f24-a899-91b1812321d6`
  (`Hi`) was recorded at `2026-06-02 15:17:48.087904+00`.
- The normal inbound reply turn
  `acdddeb8-7945-4ed0-91ab-159a6a9e0844` replied with
  `嗨～有什么事找我？` and sent successfully at
  `2026-06-02 15:18:03.246476+00`.
- The webhook-created `turn.undelivered_resend` outbox row
  `a5c9ce25-a4eb-4d43-bf1c-5f9dbdcf1afb` was also processed, but its render
  turn `81fb86d8-2b53-44a0-a96c-73d8a6a9b6ad` failed with
  `output_disposition.reason_code='conversation_lock_unavailable'`.
- No outbound message or delivery attempt was created for that failed resend
  turn, and the outbox row was acked.

Manual repair:

- A replacement `turn.undelivered_resend` outbox row was inserted after the
  inbound reply completed:
  `manual_undelivered_resend:635d3bdc1b024a08acf49940b91a9de5:20260602T1521Z`.
- It rendered turn `10c14499-ccf4-4133-8d81-6747a64ce019`, outbound message
  `9752b068-8c0f-4aae-9b7f-953cddf53cbf`, text
  `之前有条提醒没送到：和lizihao约音乐课，22:30 的时间到了`.
- Delivery attempt `12707ec5-1f77-4d8c-8e0d-f758484dfb9d` returned
  `status='sent'` with provider message id
  `coke-1780413836625-31b64620845d`.
- The original fire `aaa6f1a7-358d-48e9-9e41-8aa3c9425aa3` moved to
  `delivery_result='delivered'` at `2026-06-02 15:23:57.538307+00`.

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

The follow-up user-reply recovery exposed a second root cause in that recovery
path: the provider webhook enqueued `turn.undelivered_resend` immediately after
recording the inbound message, before the normal `InboundTurn` finished replying
to the user. The worker can process the resend event concurrently with the
ordinary user reply turn. In this incident, the resend render could not acquire
the conversation lock, was marked `failed / conversation_lock_unavailable`, and
the outbox event was acked without producing a visible message. The correct
recovery point is after the inbound reply delivery lifecycle, not inside webhook
ingress.

The shared reminder data model and scheduler fanout worked: both projections,
both reminder-fire rows, and both render turns existed. The failure boundary is
delivery recovery after one participant's provider send fails.

## Current Status

Fixed and deployed for inbound-recovery resend. The missed lizihao fire was
manually repaired and is now `delivery_result='delivered'`.

The deployed production fix moves undelivered resend enqueueing from webhook
ingress to inbound reply completion. If a channel/provider failure leaves
reminder fires or notification facts undelivered, the next successful inbound
reply from that account now schedules `turn.undelivered_resend` only after the
normal user reply delivery lifecycle has completed.

This fix does not implement an immediate delayed retry loop for users who never
send a later inbound message. That remains a separate follow-up capability if
the product wants channel failures to recover without any subsequent user
contact.

## Fix Direction

Implement an automatic bounded retry or delayed resend path for failed
`ReminderFireTurn` deliveries that have `delivery_result='undelivered'`.

The first production fix is to preserve the existing "resend after the user
refreshes the channel" behavior but move the enqueue point:

- webhook ingress records the inbound message only;
- the normal inbound turn replies to the user first;
- after reply delivery succeeds, `OutputLifecycleDeliveryCallbacks` queries
  undelivered reminder fires and notification facts for that account;
- it enqueues one `turn.undelivered_resend` with the original inbound event id
  as the idempotency key suffix;
- the resend outbox row is committed only after the turn runner has released the
  conversation lock, preventing the observed lock race.

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

## Resolution

Fix commit: `a101d0302b313c0a0c3893f044d88cbc436c80c6`
(`Fix resend timing after restored inbound delivery`).

Implemented changes:

- `coke/api/provider_webhooks.py` now records provider inbound messages without
  immediately enqueueing undelivered resend work.
- `coke/turn/runner.py` invokes an inbound-reply-completed lifecycle hook after
  successful reply delivery.
- `coke/composition.py` queries undelivered reminder fires and notification
  facts at that lifecycle point, then enqueues one idempotent
  `turn.undelivered_resend`.
- `coke/worker/__main__.py` carries the inbound event traceparent into the turn
  trigger so the deferred resend keeps trace context.

Local verification:

- `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs`
  - `757 passed in 20.20s`
  - `scripts/check` passed
- `git diff --check` passed.
- `zsh scripts/review-trigger --base HEAD~1` reported
  `human_review_required: no`.

Production deployment:

- deployed to `gcp-coke:/home/whoami/coke-clean`
- deployed SHA:
  `a101d0302b313c0a0c3893f044d88cbc436c80c6`
- `bash scripts/deploy-compose-to-gcp.sh` selected backend tier and recreated
  `coke-api`, `coke-worker`, `coke-scheduler`, and `coke-outbox-relay`.
- Deploy health checks passed.

Production verification after deploy:

- `coke-api` `/healthz` returned `{"ok":true}`.
- web login route returned HTTP `200`.
- clean backend containers were running, with `coke-api` healthy.
- lizihao fire `aaa6f1a7-358d-48e9-9e41-8aa3c9425aa3` was
  `delivery_result='delivered'` at `2026-06-02 15:23:57.538307+00`.
- manual补发 delivery attempt `12707ec5-1f77-4d8c-8e0d-f758484dfb9d`
  was `status='sent'` with provider message id
  `coke-1780413836625-31b64620845d`.
- `turn.undelivered_resend` had `0` unprocessed rows after deploy.
