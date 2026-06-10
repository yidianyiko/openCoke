---
kind: incident
status: resolved
surface:
  - clean-rebuild-backend
  - social-scheduling
severity: P1
created_at: 2026-06-10
updated_at: 2026-06-10
---

# 2026-06-10 P1: Social Scheduling Crashed On Dashed Account UUIDs

## What Happened

`coke.domains._pg.db_id(...)` stores account UUIDs in undashed form, and the
Postgres UUID columns compare dashed and undashed UUIDs equivalently. The
social scheduling repository therefore returned domain objects whose account
ids were undashed even when a caller used a dashed UUID.

The service and model layer still compared raw Python strings. A dashed caller
id did not match an undashed `Friendship.account_low_id` or
`Friendship.account_high_id`, so friend listing and friend-reference
resolution could raise or misclassify `friendship_not_found`. Shared-reminder
participant membership checks could similarly return a false not-found.

Production WeChat currently passes undashed account ids, so the bug was latent
there. Web/API-shaped callers and parity probes can pass dashed UUIDs and hit
the mismatch.

## Why It Matters

Account id formatting is a boundary concern. Letting service code compare both
forms directly makes runtime behavior depend on the caller path instead of the
canonical durable identity.

## Affected Surfaces

- `coke/domains/social_scheduling/models.py`
- `coke/domains/social_scheduling/service.py`
- Friend listing and friend-reference resolution
- Shared-reminder participant membership and notification recipient lookups

## Resolution

- `Friendship.other_account_id(...)` now compares dash-stripped ids as a
  defensive guard.
- `SocialSchedulingService` now canonicalizes incoming account-id parameters
  through `db_id(...)` at public service boundaries before repository calls,
  Python membership checks, participant-set construction, or notification
  recipient lookups.
- Recoverable-intent unit fixtures that created friendships directly now use
  canonical fake account ids.

## Verification

- RED: `.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_friend_list_and_reference_resolution_accept_dashed_account_id -q`
  failed with `assert [] == ['ae02ff016fcd4d39a189e51c8c8a31e6']`.
- GREEN focused: same command passed with `1 passed`.
- Social scheduling surface:
  `.venv/bin/python -m pytest tests/unit/coke/social_scheduling -q` passed with
  `51 passed`.
- Required backend unit suite:
  `.venv/bin/python -m pytest tests/unit/coke -q` passed with
  `1029 passed, 1 warning`.
- Diff-aware routing: `zsh scripts/suggest-verification --base HEAD~1`
  suggested `clean-rebuild-backend`; `zsh scripts/review-trigger --base HEAD~1`
  reported no human review required.
