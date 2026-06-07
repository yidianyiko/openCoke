---
kind: investigation
status: resolved
title: shared reminder retry falsely confirms active duplicate without durable row
created_at: 2026-06-07
updated_at: 2026-06-07
surface:
  - conversation-runtime
  - social-scheduling
  - output-protocol
related:
  - docs/issues/2026-06-06-eva-chat-rca.md
  - docs/superpowers/specs/2026-06-07-response-contract-recovery-design.md
---

# Shared Reminder False Success On Retry

## What Happened

Eva sent `约olivers 12:30吃饭` at 11:38. The turn failed with
`invalid_output_protocol`; its social-scheduling command remained staged and did
not materialize. Eva resent the same text at 11:41. The retry replied that the
shared reminder already existed and had been created, but there was no durable
active `shared_reminder` row.

## Why It Matters

This is a trust-critical false success: the user was told a shared lunch
reminder existed when the durable product state had no active shared reminder.

## Current Classification

The social-scheduling service duplicate path queries
`get_duplicate_active_shared_reminder`, which is active-row based. The weaker
layer is the reply/output contract: `duplicate_active` and `created_active`
claims must require a durable active shared-reminder fact, and a create intent
with no social-scheduling outcome must fail closed instead of allowing pure
language inference from a duplicated input window.

## Acceptance

- A retry after a failed, unmaterialized staged command must not deliver an
  already-exists or created reply when no active shared reminder exists.
- A legitimate `duplicate_active` claim is allowed only when it references an
  active shared reminder visible to the current user.
- Verification includes targeted regression tests, unit suite, and diff-aware
  surface routing.

## Resolution

Fix commit: this branch handoff commit,
`fix: fail closed on shared reminder false success`.

The fix is in the output-protocol and TurnRunner close-boundary validation
layer:

- `created_active` and `duplicate_active` social-scheduling claims now require
  `shared_reminder_id` in the trusted outcome.
- The TurnRunner validates active shared-reminder ids through
  `SocialSchedulingService.view_shared_reminder` for the current account when a
  social-scheduling service is available.
- A shared-reminder create intent with enabled social-scheduling tools now
  requires a social-scheduling outcome unless the current turn has actually
  staged a fresh social-scheduling create command for close materialization.

## Verification

- RED evidence: targeted regression run initially failed because unbacked
  `created_active` / `duplicate_active` outcomes were accepted and the retry
  false-success path replied.
- Targeted green:
  `.venv/bin/python -m pytest tests/unit/coke/turn/test_output_protocol.py::test_social_scheduling_claim_rejects_created_outcome_without_shared_reminder_id tests/unit/coke/turn/test_output_protocol.py::test_social_scheduling_claim_rejects_duplicate_outcome_without_shared_reminder_id tests/unit/coke/turn/test_output_protocol.py::test_social_scheduling_claim_accepts_duplicate_outcome_with_shared_reminder_id tests/unit/coke/turn/test_turn_runner.py::test_shared_reminder_retry_false_duplicate_without_active_row_fails_closed tests/unit/coke/turn/test_turn_runner.py::test_duplicate_active_reply_allowed_when_active_shared_reminder_exists -q`
  passed: 5 passed in 2.59s.
- Full unit suite:
  `.venv/bin/python -m pytest tests/unit/coke -q` passed: 819 passed in
  21.51s.
- Suggested surface:
  `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed:
  backend 819 passed in 19.66s and `scripts/check` passed.
- Risk report:
  `zsh scripts/review-trigger --base HEAD~1` returned
  `human_review_required: no`; medium non-blocking triggers were repo-OS docs
  and evidence-gap warnings.
