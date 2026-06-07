# 2026-06-07 Eva Server-Side Real-Account Smoke Evidence

Requested marker: `server-smoke-20260607T024404Z`.

Outcome: hard-stopped before posting any smoke scenario messages. No marked
shared reminders or reminders were created.

## Server And Connector

- `01-stack-ps.txt`: CLEAN compose stack was running on `gcp-coke`.
- `02-healthz.txt`: internal API and public health both returned `{"ok":true}`.
- `03-env-presence.txt`: iLink endpoint URL and provider API key were present;
  `COKE_WEBHOOK_INBOUND_SECRET` was absent in the API container environment.
- `04-ilink-reachability.txt`: `coke-api` could reach the iLink connector
  health endpoint, which reported `connected_session_count=3`.

## Account Discovery

- `07-account-discovery.txt`: active connected `wechat_personal` accounts with
  live context-token observations included:
  - `olivers`: `ae02ff01-6fcd-4d39-a189-e51c8c8a31e6`
  - `eva`: `94566791-4d39-4b28-9d9f-367c1ed0be2c`
  - `lizihao`: `635d3bdc-1b02-4a08-acf4-9940b91a9de5`
- `08-active-friendships.txt`: both `eva`/`olivers` and
  `lizihao`/`olivers` already had active friendships. No sender pair was
  exercised because the smoke hard-stopped before scenario execution.

## Hard Stop

- `05-worker-stream-pending.txt`: `coke.work` consumer group had `pending=2`.
- `06-worker-log-blocker.txt`: the worker was repeatedly failing in
  `reclaim_pending_once` with `conversation_not_found_for_account`.
- `09-poison-outbox-conversation-check.txt`: the two pending
  `turn.notification` outbox events used account ids with no conversation rows.
- `10-poison-notification-recipient-check.txt`: corresponding
  `notification_recipient` rows were still `pending`, with no `turn_id`.
- `11-poison-redis-events.txt`: Redis payloads for the two pending events.

Because the worker loop reclaims pending events before polling new events, a new
real-account smoke turn would be enqueued behind the same blocker. I did not
delete, ack, or mutate unmarked production data to force the smoke forward.

## Cleanup Check

`12-cleanup-marker-check.txt` shows zero `shared_reminder` and zero `reminder`
rows matching `server-smoke-20260607%`.
