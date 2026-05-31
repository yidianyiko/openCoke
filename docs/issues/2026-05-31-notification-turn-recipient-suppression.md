---
kind: active_issue
status: resolved
surface:
  - worker-runtime
  - social-scheduling
  - product-notification
created_at: 2026-05-31
updated_at: 2026-05-31
---

# 2026-05-31 Notification Turn Suppressed Shared-Reminder Recipient Delivery

## What Happened

Production shared reminder `654c9b24-5318-4619-875b-773f08212590` was created
successfully by `lizihao` for `olivers`. The shared reminder and both reminder
projections were active, and a `shared_reminder_created` notification fact was
written.

The corresponding `turn.notification` outbox row was published, processed, and
acked. The worker started a `NotificationTurn`, but the Interaction Agent
returned:

```json
{"type":"no_reply","reason":"intentional_no_reply"}
```

The runtime accepted that as a valid turn outcome. No outbound message or
delivery attempt was created for `olivers`, and both `notification_recipient`
rows stayed `pending` with no `turn_id`.

## Why It Matters

The target architecture says `notification_fact` fans out to per-recipient
`notification_recipient` state. A `NotificationTurn` may fail delivery for one
recipient and succeed for another, but it must not collapse pending recipient
delivery into an intentional no-reply. A creator-side synchronous confirmation
also must not suppress the receiver's product notification.

## Affected Surfaces

- `coke/worker/__main__.py`
- `coke/turn/runner.py`
- `coke/llm/agno_interaction_agent.py`
- `tests/integration/coke/test_composition_turn_integration.py`
- `tests/unit/coke/worker/test_notification_render_trigger.py`

## Current Diagnosis

The worker rendered one multi-recipient notification in the first recipient's
conversation. In the production case, that first recipient was also the creator,
so Agno history contained the preceding requester confirmation. The model
treated the notification as redundant and returned `intentional_no_reply`.

Two runtime guardrails are missing:

1. Multi-recipient `turn.notification` events should be rendered per recipient,
   using each recipient's account and conversation.
2. `NotificationTurn` output for pending notification recipients should require
   visible rendered facts. `intentional_no_reply` is not a valid completion for
   that output class.

## Desired Fix

Keep final prose owned by the Interaction Agent, but enforce the product
notification lifecycle in the runtime:

- fan out one notification fact into recipient-scoped render turns;
- make each recipient render turn use that recipient's conversation and a
  stable recipient-specific trigger id;
- reject `NotificationTurn` `no_reply` as a protocol violation, retry once with
  explicit guidance, and fail closed if the agent still refuses to render.

## Verification Plan

- Add a worker regression test proving one `turn.notification` event invokes
  recipient-scoped render turns.
- Add a TurnRunner regression test proving `NotificationTurn` no-reply is
  retried and recipient delivery state is updated after a valid render.
- Run the focused worker/composition tests, then route verification with
  `zsh scripts/suggest-verification --base HEAD~1`.

## Resolution

Implemented a recipient-scoped notification render boundary:

- worker `turn.notification` handling expands multi-recipient notification facts
  into stable recipient-specific render turns;
- `NotificationTurn` now rejects `no_reply` as a protocol violation, retries
  once, and fails closed if the retry still does not produce visible facts;
- notification render failures update `notification_recipient` as `failed` with
  structured `notification_render_failed` error facts instead of leaving pending
  rows invisible.

## Verification

- Targeted regression: `5 passed in 2.07s`.
- Affected-file regression: `86 passed in 2.21s`.
- Surface verification:
  `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed with
  `549 passed in 17.22s` and `scripts/check` passed.
- Evidence artifact:
  `artifacts/evidence/shared-reminder-real-user-smoke/2026-05-31-notification-turn-recipient-suppression.md`.
