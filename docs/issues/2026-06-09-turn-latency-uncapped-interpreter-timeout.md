---
kind: active_issue
status: open
surface:
  - conversation-runtime
  - llm-config
  - production-smoke
severity: P0
created_at: 2026-06-09
updated_at: 2026-06-09
---

# 2026-06-09 P0: Turn Stalled ~11min On Uncapped Interpreter/Detector LLM Timeout

## What Happened

Eva sent `olivers明天什么时候有空` at 2026-06-09 12:43:50 Asia/Shanghai
(04:43:50 UTC). The turn (`50ff596b-042c-4d09-bfde-1c9edf617f30`) delivered the
"still processing" placeholder at 12:44:12 but did not deliver the real answer
(`olivers明天基本全天有空，只有12:00-12:15忙` / `午饭约12:15以后可以吗？`) until
12:55:12 — a ~11 minute user-visible delay.

The turn row confirms processing, not delivery, was slow:
`started_at 04:43:51`, `completed_at 04:55:12`; the `waiting:1`, `reply:1`,
`reply:2` delivery attempts were all fast (959/943/409 ms).

Worker logs (timestamped) show a single ~8m51s stall on one Z.AI call:

```
04:46:05.717  POST api.z.ai/.../chat/completions -> 500, retry in 0.464s
   <gap: ~8m51s, no log lines>
04:54:56.652  POST api.z.ai/.../chat/completions -> 500, retry in 0.798s
04:54:59.234  -> 200 OK
04:55:03..11  follow-up agent/tool calls -> 200
04:55:13      POST :8095/send (delivery)
```

Z.AI (GLM official endpoint) was returning intermittent HTTP 500s, and one
request hung for ~531s before resolving.

## Why It Matters

P0 user-facing latency: an 11-minute wait for a routine friend-availability
question. The placeholder masks it as "still processing" but the real answer is
catastrophically late, and any provider stall can reproduce it on any turn.

## Root Cause

`coke/llm/config.py` set a bounded per-request timeout only on the interaction
model (`create_interaction_model` → `timeout=interaction_timeout_s`, 45s).
`create_interpreter_model` and `create_detector_model` passed **no** timeout, so
the OpenAI client fell back to its ~600s default. The stalled call was therefore
the interpreter or detector (the interaction model is capped at 45s and could
not produce a ~531s gap). All three are on the same user-reply critical path;
the semantic interpreter runs on every turn (intent classification is LLM-only,
not keyword routing), so an uncapped interpreter timeout stalls the whole turn.

A prior test (`test_openai_like_model_uses_zai_settings_and_interaction_timeout`)
had codified the defect by asserting `interpreter_model.timeout is None` and
`detector_model.timeout is None`.

## Affected Surfaces

- `conversation-runtime`
- `llm-config`
- `production-smoke`

## Evidence

Production reads on `gcp-coke` (2026-06-09):

- `message` / `turn` rows for `50ff596b-...` (placeholder 12:44:11, real reply
  12:55:12; turn started 04:43:51, completed 04:55:12).
- `delivery_attempt` for the turn: `waiting:1` sent, `reply:1`/`reply:2` sent,
  all sub-second latency.
- `docker logs -t coke-clean-coke-worker-1` window 04:43–04:56: ~8m51s gap
  between two Z.AI 500 responses on a single hung request.

## Current Status

- Resolved and deployed to production (`gcp-coke` / `coke-clean`).
- Mechanism (QZS call, no further approval per user): bound interpreter and
  detector per-request timeout to the same `interaction_timeout_s` so every
  turn-path text model fails fast and retries instead of blocking on a ~600s
  default.

## Resolution

Fix: `coke/llm/config.py` passes `timeout=self.interaction_timeout_s` to
`create_interpreter_model` and `create_detector_model`. All three turn-path text
models now share the same bounded per-request timeout (default 45s, tunable via
`COKE_INTERACTION_TIMEOUT_S`).

- RED→GREEN test:
  `tests/unit/coke/llm/test_config.py::test_openai_like_model_uses_zai_settings_and_interaction_timeout`
  now asserts interpreter and detector models carry the bounded timeout.
- Full backend unit suite: `.venv/bin/python -m pytest tests/unit/coke -q` →
  844 passed.

Fix commit: `a515bae1` `fix(llm): bound interpreter and detector per-request
timeout`.

Production deploy (2026-06-09, `scripts/deploy-compose-to-gcp.sh`, backend
tier):

- First attempt dropped on an SSH network timeout during image build; it had
  already rebuilt and recreated services with the new code, but did not write
  the deployed-sha marker or run the final health check. Re-ran the idempotent
  deploy to complete cleanly: `clean deploy health checks passed`.
- `gcp-coke:/home/whoami/coke-clean/.deployed-sha` = `a515bae1...` (matches fix
  commit).
- Backend containers recreated; `coke-api` `healthy`.
- Fix confirmed live: `create_interpreter_model` carries
  `timeout=self.interaction_timeout_s` in the running `coke-api`, `coke-worker`,
  and `coke-scheduler` containers.

Production user-path confirmation: the next turn that stalls a turn-path text
model should now bound that single request at 45s instead of ~600s. Watch
worker logs for the absence of multi-minute gaps between Z.AI calls.

## Follow-Ups

Two further hardening ideas were investigated on 2026-06-09 and **rejected as
net-negative**:

1. **A 90s turn-total deadline — rejected.** Normal multi-step turns (e.g.
   friend-availability and shared-scheduling) legitimately run ~60-85s because a
   turn chains several LLM calls (interpreter → interaction agent tool loop →
   render). A 90s total cap sits barely above that envelope and would clip
   legitimate slow-but-valid turns under any provider slowness, and a hard
   mid-turn abort risks inconsistent state. Product-distorting, not shipped.
2. **Reducing `max_retries` below 2 — rejected.** `agno.OpenAIChat`
   forwards `timeout` and `max_retries` to the OpenAI client (`_get_client_params`).
   In this very incident the stalled call recovered only on the third attempt
   (`max_retries=2`): attempt1 500, attempt2 stalled/500, attempt3 200. Cutting
   to `max_retries=1` would have failed that call during exactly the Z.AI
   500-storm the retries exist to absorb. The per-request timeout (now 45s)
   already bounds the amplification at ~3×45s=135s/call, which is acceptable.

Recommended future work (separate, designed change — not a P0 hotfix):

- **Generous turn-total wall-clock budget (~150s) in `InteractiveTurnSupervisor`.**
  The supervisor already runs each turn as an asyncio task with cancellation
  (`task.cancel` + `interaction_agent.cancel(run_id)`) and session rollback on
  `BaseException`, and tracks `close_committed`, so a deadline can fire cleanly
  only on turns still in processing. ~150s is ~1.8× the normal worst case, so it
  catches pathological accumulation without clipping legitimate turns. Design
  decisions to settle first: the graceful timeout reply to the user (today they
  get only the "processing" placeholder, so a hard abort would be placeholder →
  silence), the budget value, and whether to lean on idempotent inbound replay
  to re-run the aborted turn.
- Z.AI (official GLM) returned intermittent 500s in this window; track provider
  stability (and a possible provider fallback / circuit breaker) separately from
  the client-timeout fix.
