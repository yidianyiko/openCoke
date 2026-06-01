---
kind: active_issue
status: resolved
surface:
  - conversation-runtime
  - worker-runtime
  - notification-delivery
created_at: 2026-06-01
updated_at: 2026-06-01
---

# Pending Async Reply Closed A Stateful Turn

## What Happened

In production conversation `7fed5c7c-08f9-4778-bdcc-c14b7f2cf346`, the user
answered a shared-reminder clarification with `晚上十点半`. The runtime wrote a
waiting message after 20 seconds, but that message failed provider delivery with
`provider_network_error`. The Interaction Agent then continued running for
several minutes and repeatedly attempted `social_scheduling_tool` and
`reminder_tool`, but every tool call failed with `turn_superseded`.

The turn eventually replied with a failure message instead of creating the
shared reminder.

## Why It Matters

The waiting reply path exists to make slow turns visible while the original
worker continues. It must not close the original input window or remove the
turn's authority to stage and materialize its own business command. At the same
time, a newer inbound message after the waiting text must still supersede the
old turn so stale background work cannot create the wrong reminder.

## Affected Surfaces

- `conversation-runtime`
- `worker-runtime`
- `notification-delivery`

## Evidence

- Production `message` rows:
  - `2026-06-01 03:17:08Z` inbound seq `121`: `晚上十点半`
  - `2026-06-01 03:17:28Z` outbound segment `0`: `我还在处理，稍等一下。`
  - `2026-06-01 03:23:21Z` outbound segment `1`: `抱歉，创建提醒遇到了问题，稍后再试一下?`
- Production `delivery_attempt` rows for turn
  `b9cb4979-6099-441c-b180-1983d8fca9c2`:
  - waiting attempt failed with `provider_network_error`
  - final failure reply was sent
- Production worker logs repeatedly showed `turn_superseded` from
  `ConversationRuntimeService.stage_command()` after the waiting dispatcher
  persisted `pending_async_reply`.
- No `staged_command` row and no new `shared_reminder` row were created for the
  affected turn.

## Current Status

- Resolved and deployed to the clean production stack on 2026-06-01.
- Fix commit: `fb92c7f0d6a8448c8c4ae88b10e60c2ec64635ef`.
- The fix preserves real interruption safety and does not introduce blind
  WeChat retries that could duplicate visible messages.

## Resolution

`pending_async_reply` is now an intermediate visibility disposition instead of
a conversation close. Recording the waiting message still validates the turn is
fresh, but it no longer materializes staged commands, sets `turn.completed_at`,
or advances `conversation.last_closed_inbound_seq`.

Pending async turns remain active and interruptible. If the original worker
returns before any newer inbound, it can still stage/materialize the shared
reminder and commit the final reply. If a newer inbound arrives first, the
pending turn transitions to `superseded`, and stale state-changing commands are
rejected before mutation.

Waiting delivery failures are now logged as `waiting_reply_delivery_failed`
with the provider error code. This keeps the operational signal visible without
adding a retry loop that could duplicate WeChat messages.

## Verification

- `git diff --check` passed.
- `.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py tests/unit/coke/worker/test_waiting_reply.py -q`
  passed: 29 tests.
- `.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/conversation_runtime/test_outbox_relay.py -q`
  passed: 49 tests.
- `zsh scripts/suggest-verification --base HEAD~1` suggested
  `clean-rebuild-docs clean-rebuild-backend repo-os-docs`.
- `zsh scripts/review-trigger --base HEAD~1` reported
  `human_review_required: no`.
- `PATH="$PWD/.venv/bin:$PATH" zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs`
  passed, including 714 backend unit tests and repo-OS docs checks.
- `scripts/deploy-compose-to-gcp.sh` deployed backend tier to
  `/home/whoami/coke-clean`, ran Alembic upgrade/check, recreated `coke-api`,
  `coke-worker`, `coke-scheduler`, and `coke-outbox-relay`, and passed deploy
  health checks.
- Remote `.deployed-sha` is
  `fb92c7f0d6a8448c8c4ae88b10e60c2ec64635ef`; remote `docker compose ps`
  showed `coke-api` healthy and the worker, scheduler, relay, web, Postgres,
  and Redis running.
