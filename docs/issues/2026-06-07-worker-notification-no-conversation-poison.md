---
title: Worker notification dispatch poison-pill when recipient has no conversation
kind: incident
status: fixed_pending_deploy
area: worker-runtime, social-scheduling
created: 2026-06-07
updated: 2026-06-07
---

# Worker Notification No-Conversation Poison-Pill

## What Happened

A `turn.notification` Redis stream event can target an account that exists as a
friend-link joiner but has never connected a channel. In that channel-optional
join path, the recipient account has no conversation row.

Before this fix, worker dispatch tried to resolve a conversation by recipient
account and raised `conversation_not_found_for_account:<account_id>` when none
existed. The exception happened before a `NotificationTurn` was created, so the
Track F terminal notification-recipient settlement path never ran.

## Why It Matters

The raised exception rolls back the worker transaction and prevents the Redis
stream event from being acknowledged. Because the worker reclaims pending work
before polling new work, the same notification event can be reclaimed and fail
forever, blocking later turn processing behind a poison pill.

## Affected Surfaces

- `coke-worker`: notification render dispatch in `coke/worker/__main__.py`.
- `SocialSchedulingService`: notification-recipient settlement ledger.
- Redis work stream: pending notification events in `coke.work`.

## Root Cause

Track F settled terminal `NotificationTurn` outcomes, but this failure occurs
earlier in dispatch. The no-conversation recipient has no turn to run and no
conversation lock to take, so raising from dispatch skipped both turn execution
and notification-recipient accounting.

## Fix

For `turn.notification` only, when dispatch cannot find a recipient conversation
by account, the worker now calls
`SocialSchedulingService.record_notification_delivery(...)` for that
notification fact and recipient with `delivery_state="failed"` and structured
error facts:

```json
{"type": "channel_optional_join_no_conversation", "reason_code": "conversation_not_found"}
```

After settlement, dispatch yields no `TurnTrigger` for that recipient. The
worker can commit the settlement and return normally, allowing the stream event
to be acknowledged. Non-notification render topics still raise on missing
account conversation, and explicit conversation lookup behavior is unchanged.

Fix commit: `fd9f2268 fix(worker): drain no-conversation notification recipients`.

## Evidence

- TDD red check:
  `.venv/bin/python -m pytest tests/unit/coke/worker/test_notification_render_trigger.py -q`
  failed before the fix in
  `test_notification_without_recipient_conversation_settles_failed_and_drains`
  with `RuntimeError: conversation_not_found_for_account:receiver_1`.
- Focused worker regression:
  `.venv/bin/python -m pytest tests/unit/coke/worker/test_notification_render_trigger.py -q`
  passed with `6 passed`.
- Full unit suite:
  `.venv/bin/python -m pytest tests/unit/coke -q` passed with
  `814 passed, 1 warning`. The warning was an existing unraisable coroutine
  warning in
  `tests/unit/coke/worker/test_interactive_supervisor.py::test_provider_cancel_failure_is_reported_with_cancelled_trigger`.
- Diff-aware routing:
  `zsh scripts/suggest-verification --base HEAD~1` suggested
  `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs`.
- Suggested surface:
  `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed:
  backend `814 passed`; repo docs `scripts/check` ended with `check passed`.
