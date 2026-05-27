---
title: Shared-reminder create may retry on stale friend_id args and accept does not notify requester
kind: incident
date: 2026-05-27
status: resolved
resolved_at: 2026-05-27T03:45:00Z
fix_commits:
  - gateway: fc1dfa26
  - root: f28566b1
affected_surfaces:
  - agent/agno_agent/runtime/agent_runtime.py
  - agent/agno_agent/runtime/execution_agents.py
  - gateway/packages/api/src/routes/internal-scheduling-routes.ts
  - gateway/packages/api/src/scheduling/friend-target-resolver.ts
  - gateway/packages/api/src/scheduling/shared-reminder-service.ts
  - tests/unit/agent/test_agent_runtime_construction.py
  - gateway/packages/api/src/routes/internal-scheduling-routes.test.ts
  - gateway/packages/api/src/scheduling/shared-reminder-service.test.ts
---

# Shared-reminder create may retry on stale friend_id args and accept does not notify requester

## Problem

Production evidence from 2026-05-27 showed user A tried to invite user B to a
shared reminder twice before the corrected request succeeded. The first
visible failure after the corrected name was not a delivery problem; the
runtime called the scheduling domain with stale `friend_id`-shaped arguments
and the gateway returned `friend_not_found`.

The same shared reminder was later accepted by user B. The invitee received and
handled the invitation, but user A was not notified that B had accepted.

## Background

The successful production request was `cmpndkid70006ru1tkvj9xfju`.

- Requester A: `ck_SXk_J0U0V5JKcK09QHEuo`, display name `olivers`.
- Invitee B: `ck_CsFu-A91jbCSBwtizPx1K`, display name `李梓豪`.
- Title: `打篮球`.
- Final state: `accepted`.
- Request created at `2026-05-27 01:18:02.491 UTC`.
- Accept event recorded at `2026-05-27 01:18:17.972 UTC`.
- B's invite product notification was delivered.
- There was no product notification row for A after B accepted.
- A had an active delivery route around the accept time, so the absence is in
  the product notification workflow, not route delivery.

The first corrected create attempt used arguments where `friend_id` alternated
between a friendship id and an account id. Current runtime and gateway
contracts accept `invitee_name`, `invitee_account_id`, `friend_account_id`, or
`friendship_id` depending on layer, but `friend_id` is not a current contract
field.

## Initial Analysis

There are two separate defects.

1. Shared-reminder create still leaks the stale `friend_id` alias. The runtime
   forced-arg allowlist does not include `friend_id`, the execution-agent path
   recognizes `friend_account_id` rather than `friend_id`, and the gateway
   create route only resolves `invitee_account_id` or `invitee_name`. When the
   model produces `friend_id`, the create path can lose the usable target and
   ask the user to retry.
2. `acceptSharedReminder` records the accept event and creates the invitee
   projection, but it does not enqueue a product notification to the requester.
   The requester-facing success copy says the invite will synchronize after
   confirmation, but the durable workflow has no requester notification step.

## Current Contract Update

The requester acceptance notification portion is resolved by gateway commit
`fc1dfa26` and production compensation evidence below.

The earlier `friend_id` normalization direction in this issue is superseded by
the later product decision that the runtime does not need historical-system or
historical-data compatibility. Root commit `f28566b1` now enforces the current
contract instead: shared-reminder create uses `create_shared_reminder` with
canonical args such as `invitee_name` / `invitee_account_id` /
`friendship_id`, `title`, and `fire_at`; stale model-shaped aliases including
`friend_id`, `start_time`, `start_datetime`, and `date_time` fail closed
instead of being normalized.

## Cleanup Direction

`friend_id` should be treated as a legacy input alias only at ingestion
boundaries. It should not remain a durable or preferred scheduling contract.
Normalize it immediately:

- account-like values should become `invitee_account_id` or
  `friend_account_id`, depending on layer;
- friendship-like values should become `friendship_id`;
- new code and prompts should continue to prefer `invitee_name`,
  `invitee_account_id`, and `friendship_id`.

The accept path should add a requester notification instead of changing the
existing invitation notification. This keeps the invitation workflow and the
acceptance workflow separately idempotent.

## Proposed Fix

1. Add regression tests that reproduce both missing behaviors:
   - a shared-reminder create with legacy `friend_id` resolves to the invitee;
   - accepting a shared reminder enqueues a requester notification on initial
     accept and accepted retries.
2. Normalize legacy `friend_id` in runtime forced args for
   `create_shared_reminder`.
3. Allow the internal create route to resolve invitees from explicit
   `friendship_id` as well as `invitee_account_id` or `invitee_name`.
4. Add a requester acceptance notification with an idempotency key like
   `shared-reminder:{requestId}:shared_reminder_accepted`.
5. Keep the notification metadata structured with request id, request type,
   actor account id, invitee name, title, fire time, timezone, local date/time,
   and duration.

## Review Questions

- Is `friend_id` normalization safest in the runtime only, or should the
  gateway also tolerate it as a legacy API alias?
- Should acceptance notifications include `allowed_actions: []` so a short
  reply from the requester is not interpreted as another pending action?
- Should the accept path notify requester only on the first successful
  transition, or also when retrying an already accepted request?

## Review Synthesis

Codex xhigh reviewed the issue and code boundaries. The key accepted feedback
was:

- Requester acceptance notification must be an idempotent compensation on all
  successful accept paths, not only the first state transition. Otherwise a
  process exit or create failure after status becomes `accepted` can make later
  retries return early and permanently skip the requester notification.
- Do not encode informational acceptance notifications with
  `allowed_actions: []`. The focus layer treats empty allowed actions as
  missing and can fall back to accept/reject. Acceptance notifications should
  omit `allowed_actions` and carry `status: accepted` in metadata.
- `friend_id` should remain a legacy ingestion alias. Runtime and gateway
  should normalize it to `invitee_account_id` or `friendship_id`; durable
  shared-reminder service code should not accept or persist `friend_id`.
- Gateway should support `friendship_id` at the internal create route because
  the runtime may normalize friendship-shaped `friend_id` to `friendship_id`.

Claude Code was launched twice for the requested review, but both runs stayed
silent until manually stopped. No usable Claude Code findings were produced.

## Fix

- Runtime forced-arg normalization now maps legacy create
  `friend_account_id` and account-shaped `friend_id` to
  `invitee_account_id`, and friendship-shaped `friend_id` to `friendship_id`.
- The scheduling execution worker now accepts legacy `friend_id` from the
  inner tool call and immediately normalizes it before calling the scheduling
  port.
- The internal scheduling route now resolves shared-reminder create invitees
  from `friendship_id`, and tolerates legacy `friend_id` only as an ingestion
  alias. Conflicting explicit and legacy fields fail closed with
  `invalid_body`.
- `acceptSharedReminder` now ensures a requester-facing
  `shared_reminder_accepted` product notification for fresh accepts,
  accepted-race retries, and already-accepted retries. The notification uses
  idempotency key `shared-reminder:{requestId}:shared_reminder_accepted`.
- Acceptance notifications omit `allowed_actions` and include structured
  accepted metadata.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_normalizes_legacy_friend_id_aliases -q`
  failed before the runtime normalization and passed after the fix.
- `pnpm --dir gateway/packages/api test src/routes/internal-scheduling-routes.test.ts -- -t "resolves create_shared_reminder friendship_id"`
  failed before gateway friendship resolution and passed after the fix.
- `pnpm --dir gateway/packages/api test src/scheduling/shared-reminder-service.test.ts -- -t "accepts before fire time|accept loses a race|accept retry returns"`
  failed before requester accepted notification compensation and passed after
  the fix.
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_execution_agents.py -q`
  passed.
- `pnpm --dir gateway/packages/api test src/routes/internal-scheduling-routes.test.ts src/scheduling/shared-reminder-service.test.ts`
  passed.
- `pnpm --dir gateway/packages/api build` passed.
- `git diff --check` and `git -C gateway diff --check` passed.
- `zsh scripts/verify-surface repo-os-docs worker-runtime` passed.
- `pnpm --dir gateway/packages/api test` passed: 78 test files, 781 tests.
- `zsh scripts/review-trigger --base HEAD~1` reported no required human
  review. It flagged medium repo-OS/evidence reminders for the broader dirty
  tree.
- `./scripts/deploy-compose-to-gcp.sh --dry-run` completed.
- `./scripts/deploy-compose-to-gcp.sh --restart` rebuilt and restarted
  `coke-agent`, `coke-bridge`, and `gateway`; remote gateway/bridge health and
  public site checks passed.
- Post-deploy compose status showed `coke-agent`, `coke-bridge`, and
  `gateway` running, with gateway and bridge healthy.
- Post-deploy gateway/agent/bridge logs from the deploy window showed no
  matching `error`, `exception`, `traceback`, `invalid_body`,
  `friend_not_found`, or `product_notification_missing_delivery_route`.
- Production compensation: replaying `accept_shared_reminder` for already
  accepted request `cmpndkid70006ru1tkvj9xfju` returned accepted and created
  the missing requester notification
  `shared-reminder:cmpndkid70006ru1tkvj9xfju:shared_reminder_accepted`.
  The row status was `delivered` at `2026-05-27 02:22:02.175 UTC`.
