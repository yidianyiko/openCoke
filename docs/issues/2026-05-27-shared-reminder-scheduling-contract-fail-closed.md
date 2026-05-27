---
title: Shared-reminder scheduling contract accepts model-shaped payloads and can report false success
kind: incident
date: 2026-05-27
status: resolved
resolved_at: 2026-05-27T03:38:21Z
fix_commit: pending
affected_surfaces:
  - agent/agno_agent/runtime/agent_runtime.py
  - agent/agno_agent/runtime/execution_agents.py
  - agent/agno_agent/runtime/scheduling_types.py
  - tests/unit/agent/test_agent_runtime_construction.py
  - tests/unit/agent/test_agent_runtime_output_rules.py
  - tests/unit/agent/test_execution_agents.py
---

# Shared-reminder scheduling contract accepts model-shaped payloads and can report false success

## Problem

Production evidence from 2026-05-27 showed two shared-reminder invite attempts
that did not create `shared_reminder_requests` rows.

One turn asked to create an invite for `eva` at 11:00. The interaction agent
first called `scheduling_domain` with `list_friends`, then called
`create_shared_reminder`. The runtime returned the cached `list_friends` result
for the second call instead of executing the write. The assistant then replied
that the invite had been sent, but no row was created.

A later turn asked to create an invite for `olivers` at 14:00. The interaction
agent called `scheduling_domain` with model-shaped payload
`create_shared_reminder_request` and argument `start_time`. The runtime failed
inside scheduling intent normalization with `scheduling intent could not be
resolved`, so the request never reached gateway or Postgres.

## Background

Current active contract for shared-reminder create is:

- intent: `create_shared_reminder`
- canonical time field: `fire_at`
- gateway row: `shared_reminder_requests` with
  `status=pending_invitee_confirmation`

The repository no longer needs to preserve historical system or historical
data compatibility for stale tool payload names. Compatibility aliases should
not be added simply because the model emitted an old or invented shape. Stale
references in tests, prompts, or issue history should be migrated to the
current contract or deleted.

## Initial Analysis

There are three coupled defects.

1. The public agent-facing scheduling entrypoint is too loose. A generic
   `scheduling_domain(intent: Any)` lets the model invent shapes such as
   `create_shared_reminder_request` and `start_time`.
2. `scheduling_domain` caches the first result for the whole turn. A read
   followed by a write can return stale read output instead of executing the
   write, creating a false success path.
3. The unconfirmed durable-write guard does not cover invite wording such as
   "the invite has been sent" or "wait for them to confirm". A successful read
   can therefore be described as a successful write.

## Proposed Fix

Fix the current contract rather than expanding compatibility.

1. Keep `create_shared_reminder` and `fire_at` as the only create contract in
   code, prompts, and tests. Remove tests that require stale aliases such as
   `friend_id`, `start_datetime`, `date_time`, or broad "common create alias"
   normalization unless a current canonical spec names them as active.
2. Fail closed for non-canonical create intent names or create time fields.
   `create_shared_reminder_request` and `start_time` should not be silently
   normalized.
3. Replace whole-turn scheduling result caching with per-call semantics:
   - exact same normalized scheduling call may reuse the first result;
   - read then write must execute both calls;
   - different write then write must fail closed with a duplicate/multiple
     write error;
   - no call may reuse a read result as proof of a write.
4. Strengthen output grounding. Claims that an invitation/request was sent,
   submitted, created, or is waiting for the invitee to confirm must require a
   successful scheduling write operation.
5. Prefer a follow-up refactor to expose typed scheduling tools directly
   (`list_friends`, `create_shared_reminder`, `accept_shared_reminder`, and so
   on) instead of relying on `scheduling_domain(intent: Any)`. For this incident,
   keep the change small enough to deploy safely, but clean stale alias support
   in the touched path.

## Review Questions

- Should the immediate repair keep the generic `scheduling_domain` wrapper but
  make it strict, or should this incident switch the outer interaction agent to
  typed scheduling tools immediately?
- Should read after write be allowed in the same turn, or should any different
  call after a write fail closed?
- Which alias tests are current contract tests and which should be deleted as
  stale compatibility tests?

## Review Synthesis

Codex xhigh and Claude Code both reviewed the proposal. The accepted direction
is:

- Use a strict `scheduling_domain` wrapper for this production repair. Switching
  the outer interaction agent to typed scheduling tools is a larger prompt,
  trace, tool-list, and eval migration and should be a follow-up refactor.
- Strict rejection must return a typed failed scheduling
  `DomainExecutionResult` and must append it to `domain_results`. A
  normalization `ValueError` escaping into the model is not fail-closed.
- Remove stale create alias behavior from code and tests. This includes
  `friend_id`, `friend_name`, `reminder_title`, `reminder_time`, `time`,
  `scheduled_time`, `start_datetime`, `date_time`, `duration`, and
  `activity/location` normalization in the shared-reminder create path.
- The scheduling call ledger must use normalized tool plus normalized args.
  Exact duplicate calls may reuse the first result; read before write may
  execute; a different call after a write must fail closed.
- Preloaded/preselected scheduling results must not be silently reused for a
  different model-initiated scheduling call.
- Invite-sent grounding must be claim-specific. Invitation/request sent,
  submitted, or waiting-for-confirmation wording requires a successful
  `create_shared_reminder` write, not merely any durable write.
- Scheduling write results should also satisfy the durable-write visible-summary
  contract; otherwise the model can invent final wording after a real but
  unsummarized write.

## Verification Plan

- Add failing unit tests for non-canonical create payload rejection.
- Add failing unit tests for `list_friends` followed by
  `create_shared_reminder` executing both calls.
- Add failing unit tests for different write calls failing closed.
- Add failing output-rule tests for invitation-sent wording without a
  confirmed scheduling write.
- Add regression tests for preloaded scheduling result misuse and scheduling
  writes without visible summaries.
- Run worker-runtime verification and production deployment smoke before
  closing this issue.

## Fix Summary

Implemented the strict current-contract repair.

- The outer runtime now accepts only canonical
  `create_shared_reminder` forced arguments for shared-reminder create:
  counterparty, `title`, `fire_at`, optional `duration_minutes`, `timezone`,
  and `idempotency_key`.
- Non-canonical create intent or argument shapes now return typed failed
  scheduling `DomainExecutionResult` values instead of raising
  `ValueError` into model free text.
- Same-turn scheduling calls are keyed by normalized intent and normalized
  forced args. Exact duplicates may reuse the first result; read before write
  executes both calls; any different call after a successful write fails closed.
- Preloaded scheduling results are no longer silently reused for a later
  model-initiated `scheduling_domain` call.
- The inner scheduling worker rejects stale forced create fields instead of
  normalizing aliases.
- Invite/request sent or waiting-for-confirmation wording now requires a
  successful scheduling write whose operation action is
  `create_shared_reminder`.
- Scheduling writes must carry visible summary facts, matching the durable
  write contract expected by user-visible replies.

## Verification Evidence

Local verification:

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/agent/test_execution_agents.py -q`
  - `121 passed in 3.46s`
- `zsh scripts/suggest-verification --base HEAD~1`
  - suggested `zsh scripts/verify-surface repo-os-docs worker-runtime`
- `zsh scripts/review-trigger --base HEAD~1`
  - `human_review_required: no`
  - risk triggers recorded: repo-OS docs touched, oversized diff, evidence gap
- `git diff --check`
  - passed with no output
- `zsh scripts/verify-surface repo-os-docs worker-runtime`
  - `scripts/check` passed
  - `tests/unit/runner/ -v`: `67 passed`
  - `tests/unit/agent/ -v`: `522 passed`
  - `tests/unit/test_clawscale_only_topology.py -v`: `7 passed`

Production deployment and smoke:

- `./scripts/deploy-compose-to-gcp.sh --restart`
  - completed successfully
  - verified remote health endpoints
  - verified public site at `https://coke.keep4oforever.com`
- `ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml ps'`
  - `coke-agent`, `coke-bridge`, `gateway`, `mongo`, `postgres`, and `redis`
    running; bridge and gateway healthy
- Internal health:
  - agent `{"ok":true,"version":"0.1.0"}`
  - bridge `{"ok":true}`
- Public health:
  - `https://coke.keep4oforever.com/health` returned
    `{"ok":true,"version":"0.1.0"}`
  - `https://coke.keep4oforever.com/bridge/healthz` returned `{"ok":true}`
- Recent production logs after restart were checked for
  `scheduling intent could not be resolved`, `invalid_scheduling`,
  `invalid_body`, `traceback`, `exception`, and `error`; grep returned no
  matches.
- Remote source was checked for the deployed strict-contract markers:
  `invalid_scheduling_args`, `multiple_scheduling_calls_after_write`, and
  `_SHARED_REMINDER_INVITE_WRITE_CLAIM_PATTERNS`.

Additional evidence artifact:

- `artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-scheduling-contract-fail-closed-20260527t033821Z.md`

No artificial live shared-reminder invite was created during production smoke,
to avoid sending a real user notification. The canonical create, invalid
payload, read-before-write, duplicate write, output-grounding, and
visible-summary behaviors are covered by runtime unit tests.

## Follow-Up

The larger typed-tool refactor remains intentionally out of scope for this
incident. A future change can replace the generic `scheduling_domain(intent=...)`
surface with directly exposed typed scheduling tools once prompt traces, evals,
and tool-list expectations are migrated together.
