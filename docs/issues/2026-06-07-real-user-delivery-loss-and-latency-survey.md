---
kind: investigation
status: open
title: Real-user reply delivery loss (~50%) and turn latency survey on gcp-coke
created_at: 2026-06-07
updated_at: 2026-06-07
surface:
  - clean-rebuild
  - wechat-personal
  - channel-reachability
  - conversation-runtime
  - provider-edge
  - deployment
related:
  - docs/issues/2026-05-27-wechat-ilink-business-failure-delivery.md
  - docs/issues/2026-05-31-wechat-personal-connector-session-expiry-and-poll-defaults.md
  - docs/issues/2026-06-02-shared-reminder-fire-undelivered-no-auto-retry.md
  - docs/issues/2026-06-06-eva-chat-rca.md
---

# Real-User Reply Delivery Loss And Turn Latency Survey

## What Happened

The operator suspected network latency between user-sent and Coke-replied
messages, and possible lost messages. A read-only survey of the production
Postgres on `gcp-coke` (container `coke-clean-postgres-1`, database `coke`) over
the data window `2026-05-30 .. 2026-06-07` (UTC) shows the suspected bottleneck
is **not receive-side network latency**. Two real problems surfaced instead:

1. Real-user replies are lost at send. The only *active* cause is provider send
   rejection with no retry (`ret:-2` / network error), still occurring on
   2026-06-06/07. A separate class of replies with no send attempt at all turned
   out to be a 2026-05-30/05-31 clean-rebuild cutover artifact, resolved since
   2026-06-01 (see bucket 2).
2. Reply latency is dominated by our own turn processing (~20s median, text-only).
   The extreme tails (queue wait, ~2h turns) were cutover backlog and
   late-closed superseded turns, not steady-state behavior (see bucket 3).

## Scope: Who Is A Real User

All real traffic is the three named operator/test users; there are no organic
third-party users yet. Mapped via `user_profile.nickname`:

- `eva`     → account `94566791-4d39-4b28-9d9f-367c1ed0be2c` (29 inbound)
- `olivers` → account `ae02ff01-6fcd-4d39-a189-e51c8c8a31e6` (129 inbound)
- `lizihao` → account `635d3bdc-1b02-4a08-acf4-9940b91a9de5` (60 inbound)

These three account for 218 of 223 inbound. Non-human traffic is ~5 smoke
messages (`wxid_cutover_*`, `wxid_tzfix_*`, whatsapp `155530103547` "UTC Smoke")
plus empty web-first accounts with no messages (`vera`, two
`channel_optional_join_smoke_*`).

Caveat: `olivers` volume is inflated by the codex automation harness (channel
identity `wxid_codex_olivers_*`); it is a real user but its inbound count is not
organic typing. `eva`/`lizihao` inbound text also interleaves scripted smoke
markers (`server-smoke-*`, `server-verify-*`, `connector-fix-*`) with
hand-typed messages.

## Evidence

Totals: 585 messages (223 inbound / 362 outbound).

Delivery attempts: 342 total → 187 `sent`, 155 `failed` (45% failure).
`delivered_at` is NULL for every row — `wechat_personal` has no delivery receipt,
so even `sent` only means ClawScale/iLink accepted the request, not that the user
received it. Each `provider_idempotency_key` has exactly one attempt: **a failed
send is never retried**.

Failure causes (all `wechat_personal` except where noted):

- `ilink_send_failed_ret_-2`        × 97
- `provider_network_error`          × 51
- `provider_not_configured`         × 3  (2026-05-30 only)
- `ilink_send_failed_errcode_-14`   × 1  (session timeout)
- `provider_http_409`               × 1
- `provider_network_error` (whatsapp_evolution) × 2 (2026-05-30 only)

Still failing recently: 2026-06-07 failed 13, 2026-06-06 failed 15. Not historical.

Outbound vs attempts: 362 outbound, 222 have ≥1 delivery attempt, **140 have no
delivery attempt at all** despite `output_disposition = replied` and non-empty
text. The outbox is healthy (all 223 `turn.inbound` rows published/processed, no
`pending`/`failed`, no `last_error`), so the gap is between "turn persisted an
outbound message" and "egress created a delivery attempt", not in trigger
publication.

Per real user (per inbound that produced a reply turn; `got_sent` = at least one
outbound segment confirmed `sent`):

| user    | inbound w/reply | got_sent | only_failed | no_attempt | e2e p50 | e2e p90 |
|---------|-----------------|----------|-------------|------------|---------|---------|
| eva     | 29              | 29       | 0           | 0          | 20.3s   | 20.5s   |
| lizihao | 54              | 22       | 1           | 31         | 24.0s   | 96.1s   |
| olivers | 119             | 51       | 28          | 40         | 21.1s   | 55.5s   |

The `no_attempt` column (lizihao 31, olivers 40) is the cutover artifact from
bucket 2 (almost all 2026-05-30/05-31), not an active loss. Even `eva` (100%
got_sent at the inbound level) had ~20 failed reply *segments*, i.e. multi-part
replies where some segments dropped → possible truncated replies.

Latency (all turns):

- Queue, inbound → turn start: p50 0.3s, p90 1018s (~17 min tail).
- Turn, start → complete: p50 19.6s, p90 53.4s, p95 74.5s, max 7086.7s (n=330).
- E2E, inbound → first reply created: p50 ~20s.

E2E ≈ turn duration and turn batching is negligible (avg `input_to_seq -
input_from_seq` ≈ 0.16), so the ~20s median is genuine per-message processing,
not an intentional input-debounce window.

## Measurement Limitations

- `wechat_personal` inbound carries no provider send timestamp (the adapter sets
  `received_at = now()`), so true "user pressed send → we received" network
  latency is unmeasurable on the dominant channel.
- `wechat_personal` has no delivery receipt (`delivered_at` always NULL), so
  "we sent → user received" network latency is unmeasurable and no send can be
  positively confirmed as received.
- Data is single-operator dev-phase traffic over 8 days; numbers are directional.

## Root-Cause Buckets

1. **Provider send rejection, no retry (ACTIVE).** `ilink_send_failed_ret_-2`
   (WeChat rejects with HTTP 200 body `{"ret":-2}`) and `provider_network_error`.
   The adapter now correctly surfaces these as failures (see
   `2026-05-27-wechat-ilink-business-failure-delivery.md`,
   `2026-05-31-wechat-personal-connector-session-expiry-and-poll-defaults.md`),
   but the underlying rejection is still occurring at scale (2026-06-06 failed
   15, 2026-06-07 failed 13) and ordinary conversation replies have no
   auto-retry. Only `turn.undelivered_resend` (14 rows, from the `2026-06-02`
   shared-reminder fix) provides resend, and it does not cover normal chat
   replies. This is the only delivery problem still occurring.
2. **Outbound with zero send attempt — RESOLVED (cutover artifact).** The 140
   outbound messages (≈71 real-user replies) with no `delivery_attempt` are
   almost entirely on `2026-05-30` (127) and `2026-05-31` (13); from
   `2026-06-01` onward every outbound message produces a delivery attempt. This
   tracks the clean-rebuild cutover day (`wxid_cutover_20260530T101003Z`,
   3× `provider_not_configured` on 05-30) before egress delivery-attempt
   recording and connector config were live. Not an active bug.
3. **Latency — steady turn compute is the only persistent cost.** Turn
   processing (start → complete) is consistently p50 ~10–20s, p90 ~40–70s every
   day including 2026-06-07 (p50 20.8s, p90 59.6s). For text-only recent turns
   the median is ~18s, so it is the core LLM/turn pipeline, not media (voice/image
   VL) processing. No turn is stuck (332/332 have `completed_at`). The queue-wait
   tail (p90 ~17 min, max ~11h) was a 2026-05-30/05-31 cutover backlog only —
   from 2026-06-01 queue wait p90 is sub-second. The extreme turn-duration
   outliers (1970s, 7087s on 2026-06-06) are all `superseded` interactive turns
   whose `completed_at` reflects late closure after interruption, not active
   compute — a measurement artifact, not real latency.

## provider_network_error Root Cause: Worker↔Connector Timeout Cascade

`provider_network_error` is now the dominant active failure (2026-06-06 15×,
2026-06-07 11×). Root cause is a timeout mismatch between the worker and the
WeChat personal connector, not a dead connector.

Evidence (gcp-coke, 2026-06-07 14:48 UTC):

- Connector container `wechat-personal-connector-*` is up since 2026-06-01
  05:33 and healthy now: `/healthz` returns in ~45ms,
  `{"connected":true,"connected_session_count":3,"status":"connected"}` on a
  live probe from inside `coke-clean-coke-worker-1`.
- Connector gunicorn config: `--workers 1 --threads 4 --timeout 90` (single
  worker, synchronous).
- Connector `/send` calls upstream iLink `…/ilink/bot/sendmessage` with
  `timeout=30.0` and retries `max_attempts=2`
  (`provider_edges/wechat_personal_connector/app.py`), so one `/send` can block
  up to ~60s upstream before returning.
- Worker-side adapter is constructed with no timeout override
  (`coke/composition.py` ~L1646 → `WeChatPersonalAdapter` default
  `timeout=10.0` in `coke/providers/wechat_personal.py`), so the worker waits
  only 10s for `/send`.
- Connector logs over the last 6 days contain only a handful of `ret:-2`
  warnings (06-02, 06-07 03:46) and NO entries for the 26
  `provider_network_error` timestamps — consistent with worker-side timeouts on
  slow iLink calls that the connector neither rejected nor finished within 10s.

Mechanism: when upstream iLink is slow (>10s), the worker's `httpx` POST to the
connector raises `httpx.HTTPError` → `post_json_send` returns
`error_code="provider_network_error"` (`coke/providers/base.py:245`), while the
connector keeps working for up to ~60s. Two consequences:

1. **False negatives.** If the connector eventually succeeds after the worker
   gave up, the user received the message but Coke recorded `failed`. So the
   real send-failure rate is unknown and the "undelivered" set is partly
   delivered. (`delivered_at` is always NULL anyway — no receipt.)
2. **Connector saturation.** A single gunicorn worker with synchronous ~30–60s
   iLink calls is easily blocked by concurrent/multi-segment sends, amplifying
   timeouts (paired same-second `provider_network_error` rows match multi-segment
   replies failing together).

`provider_network_error` and `ilink_send_failed_ret_-2` share the same upstream
cause: an intermittently slow / rejecting iLink (WeChat personal) backend. iLink
slow → worker timeout (`provider_network_error`); iLink rejects → `ret:-2`.

Fix directions: (a) align timeouts — raise the worker→connector send timeout
above the connector's worst case (≥60–90s), or make `/send` ack fast (202) and
report true delivery via the existing `/internal/outbound/delivery-callback`
async path instead of blocking; (b) increase connector concurrency
(workers/threads) or make iLink calls async; (c) investigate iLink-side health
(why it is slow / returns `ret:-2`: account risk-control, session, rate limit).

**Fix applied (2026-06-08, fix direction (a)):** the worker→connector send
timeout is now configurable via `COKE_PROVIDER_WECHAT_PERSONAL_SEND_TIMEOUT_S`
and defaults to 45s (`coke/config.py`
`DEFAULT_WECHAT_PERSONAL_SEND_TIMEOUT_S`), wired into `WeChatPersonalAdapter`
in `coke/composition.py`; the adapter default floor was also raised from 10s to
45s. 45s captures slow-but-successful iLink sends that previously false-failed at
10s, and stays below the 60s stream reclaim idle (`worker_reclaim_idle_ms`) so an
in-flight send is never re-delivered to a second worker (the connector does not
dedupe on `Idempotency-Key`, so a longer timeout that crossed the reclaim window
would risk duplicate sends). Fix directions (b) connector concurrency / async
and (c) iLink-side health remain open. The residual false-negative window is
iLink responses in 45–90s, which are rare.

## Resend Mechanism Does Not Recover ret:-2 / network Failures

The `turn.undelivered_resend` / `UndeliveredResendTurn` path (from the
`2026-06-02` shared-reminder fix) does not meaningfully recover the active
send-failure modes (`ilink_send_failed_ret_-2`, `provider_network_error`):

- **No coverage for chat replies.** It only re-renders undelivered *reminder
  fires* (`fire_ids`) and *notification facts* (`notification_fact_ids`)
  (`coke/composition.py` `record_inbound_reply_completed`, `runner.py:2530`
  "Render previously undelivered reminder facts"). An ordinary conversation
  reply that hits `ret:-2` is dropped permanently. Most real-user traffic is
  chat, so this is the dominant gap.
- **Self-defeating gate for reminders/notifications.** Enqueue is gated on
  `if not delivered: return` (`composition.py` ~L368): the resend is piggybacked
  onto the *next* inbound turn and only if that turn's own reply was delivered.
  During a `ret:-2` / network outage that triggering reply also fails, so the
  gate stays closed and no resend is enqueued — the recovery path is disabled
  exactly when the failure is happening.
- **Pull-based, not scheduled.** It waits for the user to send another message;
  there is no automatic retry timer. If the user goes quiet, nothing resends.
  The resend also uses the same provider path, so a persistent failure makes the
  resend fail too with no further retry.

Evidence: 14 `UndeliveredResendTurn` turns over the window produced only 3
`sent` outbound messages. `ret:-2` was a cutover-period storm (93 of 97 on
2026-05-30/05-31) — the exact window where blanket delivery failure kept the
gate closed. All 15 `reminder_fire` rows now show `delivered`, but that is
eventual recovery after the channel healed and users messaged again, not the
resend rescuing deliveries during the outage. Current failures (2026-06-06:
15× `provider_network_error`; 2026-06-07: 11× `provider_network_error` + 2×
`ret:-2`) hit the same gate and are equally uncovered.

## Open Questions / Next Steps

- Why does WeChat iLink return `ret:-2` now (recipient not a friend, account
  风控/limit, stale session)? Needs connector + iLink logs. This is the live
  delivery-loss root cause.
- Redesign resend so it actually recovers send failures: (a) cover ordinary
  chat replies, not just reminder/notification facts; (b) remove the
  `if not delivered: return` gate that disables resend during an outage;
  (c) make it scheduler/timer-driven (push) instead of waiting for the next
  inbound (pull), with bounded automatic retries on `ret:-2` /
  `provider_network_error`.
- Reduce the ~18–20s median text turn latency: needs worker/egress
  instrumentation to break the turn into LLM-call vs tool-call vs model latency
  (no sub-turn timing exists in the DB today).
- Tail outliers are interruption-driven (superseded turns close late). Low
  priority; consider closing superseded turns promptly so duration metrics are
  not polluted.

## Reminder Fire Latency (measured 2026-06-08)

Operator-reported reminder slowness ("feels like 2-3 min"). Measured on
`reminder_fire` (gcp-coke prod), n=13 delivered fires over 14 days, excluding one
53-min cutover-period outlier (2026-06-02). The runtime tracks fire lifecycle via
`created_at` (scheduler claimed the due fire) and `updated_at` (delivered);
`handled_at`/`completed_at` columns exist but are never populated.

| Phase | source | p50 | p90 |
|-------|--------|-----|-----|
| Detection lag | `created_at - due_at` | 37s | 43s |
| Render + send | `updated_at - created_at` | 26s | 38s |
| Total (fire -> send) | `updated_at - due_at` | 58s | 81s |

Steady-state median is ~1 min, not 2-3 min, but perceived latency is inflated by
(a) co-due reminders queueing (same-minute fires took 78-99s for the later one),
(b) no delivery receipt (`updated_at` is when we sent, not when iLink delivered),
and (c) the 53-min tail outlier.

Root cause of the floor: `scheduler_interval_s` defaulted to **60s**, so the
scheduler scans for due reminders only once per minute. That detection lag
(p50 37s) was the single largest latency component — pure wait before any
render/send work begins. Render+send (~26s) is dominated by the same ~18-20s LLM
turn floor as chat (bucket 3).

**Fix applied (2026-06-08):** lowered `scheduler_interval_s` default 60 -> 15
(`coke/config.py`; prod has `COKE_SCHEDULER_INTERVAL_S` unset, so the default
governs). Expected detection lag p50 ~7.5s, cutting ~30s off every reminder
(total ~58s -> ~30s). The indexed `due_at` scan stays cheap at 15s cadence.
Remaining latency is the LLM render turn; templating reminder copy to skip the
LLM is a separate product decision (not done here).

## Verification Method (reproducible)

Read-only `psql` against `coke-clean-postgres-1` on `gcp-coke`. Key joins:
inbound→turn via `turn.conversation_id` + `seq BETWEEN input_from_seq AND
input_to_seq`; turn→outbound via `message.turn_id`; outbound→delivery via
`delivery_attempt.message_id`; user identity via `user_profile.nickname`.
`outbound.causal_inbound_event_id` is NULL and must not be used to link replies.
