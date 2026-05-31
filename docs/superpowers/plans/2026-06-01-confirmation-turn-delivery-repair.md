# Confirmation Turn Delivery Repair

**Plan Status:** completed
**Status Date:** 2026-06-01
**Freshness Check:** Verified against current `main`, `docs/ARCHITECTURE.md`,
and touched code before execution.

## Goal

The production confirmation flow should handle a short affirmative reply after
a shared-reminder clarification, create the intended shared reminder when the
tool succeeds, and deliver visible requester feedback. Waiting replies should
use compact idempotency keys and no longer fail because of raw provider trigger
ids.

## Scope

- In scope:
  - Waiting-reply idempotency keys in the turn runner and waiting dispatcher.
  - Short affirmative confirmation handling when semantic routing reports
    missing context.
  - Explicit retry guidance for serialized textual tool-call markup.
  - Production deployment and marked real-user smoke verification.
- Out of scope:
  - Replacing the semantic interpreter.
  - Changing provider connector delivery semantics beyond idempotency key shape.
  - Manual deletion of unmarked user data.

## Inputs

- Related incident: `docs/issues/2026-06-01-confirmation-turn-no-reaction.md`
- Related issue: `docs/issues/2026-05-28-serialized-tool-call-output-leak.md`
- Related issue: `docs/issues/2026-05-31-shared-reminder-no-reply-and-delivery-receipt.md`
- Canonical architecture: `docs/ARCHITECTURE.md`

## Touched Surfaces

- worker-runtime
- agent-runtime
- conversation-runtime
- repo-os

## Work Breakdown

1. Add failing regression tests for compact waiting idempotency keys.
2. Add a failing regression test proving short affirmative confirmations keep
   interactive tools available instead of becoming clarification-only turns.
3. Add a failing regression test for serialized textual tool-call retry
   guidance.
4. Implement the narrow runtime fixes.
5. Run focused tests, diff-aware verification, and risk report.
6. Commit, deploy to production, and run a marked real-user flow smoke.
7. Update the incident record with commit, deployed SHA, and smoke evidence.

## Verification

- Command: focused pytest for touched unit tests.
- Command: `git diff --check`.
- Command: `zsh scripts/suggest-verification --base HEAD~1`.
- Command: suggested surface verification commands.
- Command: `zsh scripts/review-trigger --base HEAD~1`.
- Command: production deployment and marked real-user smoke against `gcp-coke`.

## Notes

The production user can receive real WeChat messages during the smoke. The
smoke must use a unique marker and clean up any active shared reminder it
creates through the product path.

## Completion Evidence

- Final deployed SHA: `1187295f1f89544b1bb4672c2ace35db0541518c`.
- Full backend verification: `zsh scripts/verify-surface clean-rebuild-backend`
  passed with 687 tests.
- Production smoke marker: `server-smoke-20260531T192030Z`.
- Smoke outcome:
  - The first two rapid question turns were superseded by the later command.
  - The command turn produced the expected merged visible reply and friend
    clarification.
  - The follow-up `是的` created the shared reminder for `lizihao` without
    falling through to the semantic LLM or waiting timer.
  - Smoke shared reminder `8c418dea-287c-46d2-a76a-522e8369c44f` was cancelled
    after verification.
- Delivery caveat: provider sends in the synthetic smoke failed with
  `ilink_send_failed_ret_-2` due the stale smoke `context_token`; persisted
  runtime state and domain mutation were verified in Postgres.
