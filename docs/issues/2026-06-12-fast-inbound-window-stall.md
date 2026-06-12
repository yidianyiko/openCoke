---
kind: active_issue
status: in_progress
surface:
  - conversation-runtime
  - worker-runtime
  - production-smoke
severity: P0
created_at: 2026-06-12
updated_at: 2026-06-12
---

# 2026-06-12 P0: Fast Consecutive Inbound Window Stalled

## What Happened

A real user sent three WeChat personal inbound messages in the same
conversation within a short interval:

- seq `214`, `2026-06-12 10:27:06.939536Z`, text `晚上好`
- seq `215`, `2026-06-12 10:27:07.088117Z`, text `我现在有几个提醒？`
- seq `216`, `2026-06-12 10:27:07.158531Z`, text
  `和eva约一个今天晚上七点半点的晚饭`

The conversation stayed open at `last_closed_inbound_seq=213` and
`latest_inbound_seq=216`. The active turn had claimed the full input window
`214..216`, but later outbox events for seq `215` and `216` still caused the
supervisor to cancel/restart work. The user received waiting-message behavior
without the expected final reply.

## Why It Matters

Fast consecutive user messages are a normal chat pattern. The turn runtime must
process the full open input window, publish coalesced waiter results, and close
the conversation window. A single older or duplicate outbox event must never
hold the user-visible reply path hostage.

## Root Cause

Two B2 eager-execute boundaries were unsafe together:

1. `TurnRunner.run_inbound_turn_async` caught the newer-inbound
   `CancelledError` and called `mark_superseded` plus the close-boundary
   committer from the same shared turn session. Under B2, Execute-time domain
   writes are intentionally uncommitted until close, so committing from this
   cancellation path could persist or block behind half-finished work instead of
   rolling it back.
2. The worker submitted every interactive inbound outbox event to the
   supervisor, even when an already active interactive turn had claimed an input
   window that covered the event's message sequence and the event's
   `latest_inbound_seq`. For a fast triplet, the first worker task can already
   cover all three messages, so seq `215` and `216` events should be acked as
   covered instead of cancelling the active full-window turn.

## Fix

- Runner cancellation now propagates without recording superseded or committing
  the close boundary from the cancelled shared turn transaction.
- The interactive supervisor rolls back the child session first; only after
  rollback does it attempt an idempotent superseded cleanup in a fresh
  transaction.
- The worker detects interactive inbound outbox events already covered by an
  active turn's input window and acks them without resubmitting or cancelling
  provider runs.
- The B2 eager-execute supersession spec was updated to state that cancelled
  Execute-time writes roll back before any superseded cleanup.

## Verification

Pending final deployment and production 1ms three-message smoke.
