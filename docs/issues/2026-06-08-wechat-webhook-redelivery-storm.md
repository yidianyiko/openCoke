---
kind: active_issue
status: resolved
surface:
  - clean-rebuild-backend
created_at: 2026-06-08
updated_at: 2026-06-08
---

# 2026-06-08 WeChat Inbound Webhook Re-delivery Storm + Turn Latency

## What Happened

Two distinct production problems were found while investigating a user report
that creating a shared reminder took over a minute.

1. **Re-delivery storm.** A single `wechat_personal` inbound message
   (`inbound:AARzJWAF…`) was re-delivered ~436 times in 24h, each returning
   HTTP 500 with `duplicate_outbox_idempotency_key`.
2. **Slow shared-reminder turns.** A shared-reminder turn fired ~13 sequential
   GLM-5.1 calls and took 60-85s (first reply ~46s).

## Why It Matters

The storm spammed `coke-api` error logs and kept the connector spinning. The
latency is a direct, user-visible degradation on the core shared-reminder path.

## Root Cause

**Storm (two layers):**
- `coke-api`: a re-delivered inbound event that was already recorded and
  enqueued collides on the `inbound:<event_id>` outbox idempotency key.
  `record_inbound` raised `ConversationRuntimeError`, which surfaced as HTTP
  500. The connector treats non-2xx as failure and re-delivers, so the success
  ack never arrives and the message loops forever.
- Connector `_poll_session_once`: the ilink cursor is advanced only after the
  whole batch delivers, and it re-raised on any webhook non-2xx. One rejected
  ("poison") message blocked the session cursor indefinitely with no
  per-message attempt cap (the exponential backoff only throttled the loop).

**Latency:** the interaction agent and semantic interpreter ran GLM-5.1 with
thinking mode enabled (only the detector had it disabled). Thinking mode leaks
reasoning into the final message and frequently breaks the JSON output
protocol, forcing a full agent re-run (doubling per-turn LLM calls), and
inflates per-call latency (3-18s observed) across the agent's tool loop.

## Fix

- `1a41ee48` `fix(webhook): idempotent inbound replay + bounded connector retries`
  - Webhook acknowledges `duplicate_outbox_idempotency_key` as an idempotent
    replay (202), still committing; other runtime errors still surface.
  - Connector caps per-message webhook delivery at
    `MAX_WEBHOOK_DELIVERY_ATTEMPTS = 5`, persisting attempt counts in session
    state; under the cap it keeps the cursor and backs off, at the cap it drops
    the poison message and advances the cursor.
- `19a1f017` `perf(llm): disable thinking on interaction + interpreter models`
  - `enable_thinking: False` on all turn-path GLM-5.1 models for parity with
    the detector.

## Verification

- `.venv/bin/python -m pytest tests/unit/coke` → 840 passed (both commits).
- Deployed `coke-api` + `coke-worker` (backend compose) and the
  `wechat-personal-connector` container (separate compose, state volume
  preserved) on 2026-06-08 ~15:06-15:09 UTC.
- Post-deploy window 15:06-15:12 UTC: `duplicate_outbox_idempotency_key` = 0,
  webhook 500 exceptions = 0, connector tracebacks = 0 (≈6-9 storm events
  expected at the prior ~39-60s cadence; observed 0).

## Follow-up (open)

- **Thinking-off quality regression check is still pending.** The thinking
  disable was shipped directly (user-approved) to recover latency/stability
  first; a shared-reminder + normal-reply subset eval (30-50 cases) should
  confirm no quality regression before treating the choice as locked.
