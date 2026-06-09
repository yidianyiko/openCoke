---
kind: active_issue
status: open
surface:
  - conversation-runtime
  - worker-runtime
  - production-smoke
severity: P0
created_at: 2026-06-09
updated_at: 2026-06-09
---

# 2026-06-09 P0: Interrupted Turn Pinned DB Transaction Across Agent Work

## What Happened

The clean production smoke `latency_20260609T064334Z` drove two marked webhook
first-contact messages and then a marked personal reminder through the real
clean stack. The personal reminder step timed out waiting for exactly one active
owner-scoped reminder.

The affected account conversation had this sequence:

- First-contact inbound at `2026-06-09 06:46:30Z`, turn
  `5d690528-283b-4421-a216-5b9d5abc3a6d`.
- Personal-reminder inbound at `2026-06-09 06:46:44Z`, turn
  `b05164b8-dcbb-4b07-afa0-9865fe76fd04`.
- The first turn was marked `superseded` with reason
  `interrupted_by_newer_inbound`.
- The personal reminder turn remained `pending_async_reply` after the waiting
  message and never created a matching `reminder` row.

## Why It Matters

This is a user-visible stuck-turn failure on the reminder creation path. The
user receives the waiting message, but the state-changing tool work never
starts because the newer turn blocks behind an old, interrupted turn's open
transaction.

It also confirms that turn latency is not only provider latency. Long or
cancelled LLM/agent work can hold database transaction state and block later
work in the same conversation/account.

## Root Cause

`TurnRunner` committed the start-turn claim boundary, but did not commit
side-effects from the pre-LLM gate before entering semantic interpreter and
Interaction Agent work.

The pre-LLM gate calls account/settings paths that can lazily create
`agent_settings` and `user_profile` rows. In production, the interrupted first
turn kept the SQLAlchemy transaction open while the agent path continued or was
cancelled. That uncommitted transaction held unique-key locks on account-scoped
settings/profile rows. The personal reminder turn then blocked trying to
insert/read the same default rows, so it never reached the reminder tool.

## Affected Surfaces

- `conversation-runtime`
- `worker-runtime`
- `production-smoke`

## Evidence

- Smoke command: `python -m scripts.smoke.clean_smoke --mode webhook --run-id
  latency_20260609T064334Z` inside the production `coke-api` container.
- Local evidence copy:
  `artifacts/evidence/clean-smoke/latency_20260609T064334Z.json`.
- Smoke result: `personal_reminder: timed out waiting for exactly one active
  owner-scoped personal reminder`.
- Reminder check: no `reminder` row matched the smoke marker.
- `turn` rows showed the first-contact turn superseded and the reminder turn
  stuck in `pending_async_reply`.
- `pg_stat_activity` showed a worker backend blocked on
  `INSERT INTO agent_settings (...)` behind another worker backend that was
  `idle in transaction` from the first-contact turn and held locks on
  `agent_settings` and `user_profile`.
- Turn latency telemetry for concurrent first-contact turns showed
  `turn.semantic_interpreter` taking several seconds before agent work; no
  completion telemetry was emitted for the blocked personal reminder turn.

## Current Status

- Open while the fix is verified and deployed.
- Proposed fix: commit the claim boundary again immediately after the pre-LLM
  gate, before access-denied handling, semantic interpretation, or agent work.

## Resolution

Pending production deploy and repeated smoke verification.

Local verification before deploy:

- RED regression: the synchronous claim-boundary test failed until the second
  post-gate commit was added.
- `.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py -k
  'claim_boundary_commits' -v` passed: 2 tests.
- `.venv/bin/python -m pytest tests/unit/coke/test_turn_latency_telemetry.py
  tests/unit/coke/turn/test_turn_runner.py
  tests/unit/coke/llm/test_semantic_interpreter.py
  tests/unit/coke/llm/test_reminder_detector.py
  tests/unit/coke/smoke/test_clean_smoke.py -v` passed: 120 tests.
- `zsh scripts/suggest-verification --base HEAD` suggested
  `clean-rebuild-backend repo-os-docs`.
- `zsh scripts/review-trigger --base HEAD` reported
  `human_review_required: no`.
- `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed:
  backend unit suite 853 tests plus `scripts/check`.
- `git diff --check` passed.
