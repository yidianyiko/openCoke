---
kind: incident
status: fixed_pending_deploy
surface: conversation-runtime, social-scheduling, notification-delivery
created: 2026-05-31
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
- Deployment and production repair evidence should be appended after rollout.
