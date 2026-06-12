---
kind: active_issue
status: resolved
surface:
  - conversation-runtime
  - worker-runtime
  - production-smoke
severity: P0
created_at: 2026-06-12
updated_at: 2026-06-12
resolved_at: 2026-06-12
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
3. Worker startup recovery used a deterministic
   `recover:<conversation>:<latest_seq>` trigger id. If that recovery turn had
   already reached `pending_async_reply`, a restarted worker replayed the
   pending disposition instead of making a fresh attempt to close the still-open
   window.

## Fix

- Runner cancellation now propagates without recording superseded or committing
  the close boundary from the cancelled shared turn transaction.
- The interactive supervisor rolls back the child session first; only after
  rollback does it attempt an idempotent superseded cleanup in a fresh
  transaction.
- The worker detects interactive inbound outbox events already covered by an
  active turn's input window and acks them without resubmitting or cancelling
  provider runs.
- Startup recovery now uses a fresh synthetic recovery trigger id per attempt,
  so a stale `pending_async_reply` recovery turn cannot permanently short-circuit
  open-window convergence.
- The B2 eager-execute supersession spec was updated to state that cancelled
  Execute-time writes roll back before any superseded cleanup.

## Verification

- Fixed by commits `ccfa56ec032eff7e457c0d067e4c4ce71baef9cf`
  (`fix(worker): avoid stuck fast inbound windows`) and
  `c30a58f46995173abf6215d53a45244b084721a5`
  (`fix(worker): make open-window recovery retryable`).
- Final deployed backend SHA:
  `c30a58f46995173abf6215d53a45244b084721a5`.
- The original stuck window recovered from `latest_inbound_seq=216`,
  `last_closed_inbound_seq=213` to `last_closed_inbound_seq=216`,
  `open_lag=0`; its final WeChat delivery attempt was `status=sent`.
- A production three-message simulation against the same conversation recorded
  seq `217`, `218`, and `219` with `time.sleep(0.001)` between commits. The
  worker processed the full window `217..219` as one interactive turn,
  acked the two later outbox events as already covered by the active window,
  closed the conversation to `open_lag=0`, and sent both reply segments.
- Final production health checks showed active interactive turns `0`, Redis
  `XPENDING coke.work workers=0`, Redis group `pending=0`, `lag=0`, Postgres
  `lock_waits=0`, and `long_idle_xacts=0`.
- Full evidence:
  `artifacts/evidence/2026-06-12-fast-inbound-window-stall.md`.
