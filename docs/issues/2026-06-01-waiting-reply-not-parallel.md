---
title: Waiting reply did not run in parallel with slow Interaction Agent turns
kind: incident
status: resolved
area: conversation-runtime, worker-runtime
created: 2026-06-01
updated: 2026-06-01
---

# Waiting Reply Not Parallel

## What Happened

A production inbound reminder-list question spent more than two minutes inside
the interactive turn before the final reply was delivered. The user saw no
intermediate feedback even though the runtime had a `pending_async_reply`
disposition and waiting-message path.

## Root Cause

The existing waiting path was reachable only when the Interaction Agent returned
`AgentResult.timeout`. The production Agno call was synchronous and did not emit
that timeout while it was still blocked in the model call, so the code could not
send a 20-second "still working" message. Waiting was therefore serialized after
the slow path instead of being supervised in parallel.

## Fix

`coke-outbox-relay` now owns a lightweight parallel waiting dispatcher. On every
relay loop it scans active inbound turns whose `started_at` is older than
`COKE_WAITING_REPLY_AFTER_SECONDS` (default 20 seconds), persists
`pending_async_reply`, records segment `0` runtime-owned waiting text, and
delivers it through the same channel route. The original worker turn keeps
running and may later transition from `pending_async_reply` to `replied`.

This does not complete full pre-reply input-window coalescing or Agno async
cancellation. Those remain the larger P1 path in
`docs/superpowers/specs/2026-05-31-coke-pre-reply-interrupt-coalescing-design.md`.

## Evidence

- `.venv/bin/python -m pytest tests/unit/coke/worker/test_waiting_reply.py tests/unit/coke/turn/test_turn_runner.py::test_timeout_yields_waiting_text_pending_async_then_transitions_to_replied tests/unit/coke/test_backend_foundation.py::test_settings_from_env_reads_runtime_entrypoint_configuration -q`
  passed with 4 tests.
- `.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_outbox_relay.py tests/unit/coke/worker/test_waiting_reply.py -q`
  passed with 6 tests.
- `zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs`
  passed, including 601 backend unit tests.
- Evidence files:
  `artifacts/evidence/2026-06-01-waiting-reply/focused-pytest.txt`,
  `artifacts/evidence/2026-06-01-waiting-reply/scripts-check.txt`,
  `artifacts/evidence/2026-06-01-waiting-reply/black-check.txt`,
  `artifacts/evidence/2026-06-01-waiting-reply/verify-surface.txt`.
