---
kind: incident
status: fixed_deployed
surface: conversation-runtime, social-scheduling, notification-delivery
created: 2026-05-31
fixed_commit: 97efc4115194b6cbad89bd32ba90a690496a9fb3
deployed_sha: 97efc4115194b6cbad89bd32ba90a690496a9fb3
---

# Shared Reminder Follow-Up No-Reply And Missing Creator Receipt

## What Happened

A shared-reminder recipient received the invitation notification, replied
`好的`, and got no visible response. Production state showed the inbound turn
completed as `no_reply / intentional_no_reply`.

The creator had received the original creation confirmation, but had no visible
evidence that the recipient notification was delivered.

## Why It Mattered

Legacy allowed no-reply for natural conversation endings and repeated-input
handling, but it made that decision inside the chat workflow after full context
was available. The clean runtime was stricter because `SemanticInterpreter`
could close an inbound user turn as `intentional_no_reply` before the
Interaction Agent saw recent product-notification context.

For shared reminders, the creator needs a visible delivery result such as the
recipient being notified. The notification delivery state existed in Postgres,
but no creator-facing receipt was emitted.

## Fix

- Inbound semantic `intentional_no_reply` is converted back to
  `reply_needed` before Interaction Agent invocation. The Interaction Agent may
  still intentionally no-reply after seeing full context.
- The Interaction Agent output contract now limits no-reply to meaningless
  content, natural endings, or explicit no-disturb requests, and forbids
  no-reply for post-notification acknowledgements, delivery/status questions,
  or challenges.
- Shared-reminder creation notifications target receivers only; the creator's
  initial confirmation remains the original interactive reply.
- When a receiver's shared-reminder-created notification is delivered, Social
  Scheduling emits a structured `shared_reminder_delivery_confirmed`
  notification to the creator.

## Evidence

- Focused regression tests cover the no-reply routing and creator receipt
  behavior.
- `scripts/deploy-compose-to-gcp.sh` deployed
  `97efc4115194b6cbad89bd32ba90a690496a9fb3`; remote `.deployed-sha` matches
  that commit.
- Production `docker compose ps` showed `coke-api` healthy and worker, outbox
  relay, and scheduler up after deployment.
- The historical receiver delivery for notification
  `069f3fbd-8852-4290-a62a-13ac070b3b3f` was replayed through
  `SocialSchedulingService.record_notification_delivery`.
- Production created `shared_reminder_delivery_confirmed`
  `cf11766a-b8aa-4386-bbb0-2297aeb4cdb5` for creator account
  `635d3bdc-1b02-4a08-acf4-9940b91a9de5`; outbound message
  `03c92b4c-37e3-4853-a47b-f73ee81b94bf` was sent with provider id
  `coke-1780228670318-2e4dc32da443`.
