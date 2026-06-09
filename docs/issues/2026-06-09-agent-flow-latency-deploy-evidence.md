---
kind: verification_report
status: complete
surface:
  - conversation-runtime
  - worker-runtime
  - llm-runtime
  - production-smoke
severity: P1
created_at: 2026-06-09
updated_at: 2026-06-09
---

# 2026-06-09 Agent Flow Latency Optimization — Deploy Evidence

## What Shipped

Two optimizations from
`docs/superpowers/specs/2026-06-09-agent-flow-time-optimization-design.md`,
deployed to clean production (`coke-server`, gcp-coke), final SHA
`46d76896`:

1. **Plain reminder list prepared action** — explicit, unambiguous list/count
   requests route through runtime `ActionRunner` + the existing list template,
   skipping the discarded interaction-agent generation. Filtered list requests
   stay on the full agent. Read-only; never stages or mutates.
2. **Streaming first segment for chat turns** — pure `full_agent` chit-chat turns
   stream the first validated segment early to cut time-to-first-token. Scoped to
   non-mutating turns; fails safe to non-streaming.

Routing is derived from existing interpreter fields (no new model call, no
keyword routing).

## Bugs Found By Real-Account Smoke (not caught by unit tests)

Both features shipped green (891 unit tests) but were **inert in production**
until two bugs found by live smoke were fixed:

1. **`ambiguity == "clear"` gate.** The deployed interpreter emits
   `ambiguity="none"` for unambiguous plain-list and chit-chat turns; only
   filtered/specific turns return `"clear"`. Both `derive_route` and
   `is_streaming_eligible` gated on `== "clear"`, so every clean turn fell
   through. Fixed to accept `{"clear", "none"}`. Stubbed unit tests used
   `"clear"` and never exercised the production value.
2. **Awaiting Agno streaming.** `Agent.arun(stream=True)` returns an
   `AsyncIterator` directly (not a coroutine); the code awaited it, throwing
   `agno_streaming_start_failed` and falling back every time. Fixed by not
   awaiting. Verified end-to-end against real Agno 2.5.9 (RunContentEvent deltas,
   parser extracts complete segments). The stub fake used an `async def arun`
   and hid the contract.

## Production Telemetry Evidence

Synthetic Evolution webhook probes to `127.0.0.1:8000/webhooks/whatsapp/evolution`
on the deployed stack (`COKE_WEBHOOK_INBOUND_SECRET` unset):

Plain list query "我有哪些提醒" (account `61f1064c…`):

```text
turn.semantic_interpreter  3101ms
turn.context_assembly         0ms
turn.prepared_action          7ms   route=prepared_list action=list_reminders
turn.total                 3460ms
# no agent.primary — heavy generation removed
```

Before this change, an equivalent list turn spent ~9.8s in `agent.primary`
(total ~13s). After: **~3.5s total, prepared action 7ms, zero LLM in the action
path.**

Chit-chat greeting "你好呀今天怎么样" (account `af24c9a6…`):

```text
agent.primary  duration=4072ms  streamed=true  first_segment_ms=3214  tool_count=0
```

The first reply segment is delivered ~3.2s into the agent phase instead of after
the full generation, cutting the black-screen wait.

## Interpreter Probe (deployed model)

Direct in-container interpreter calls confirmed correct classification:

```text
"我有哪些提醒"     -> list_reminders, amb=none, clar=none, list_is_plain=True
"列一下我的提醒"   -> list_reminders, amb=none, clar=none, list_is_plain=True
"我有几个提醒"     -> list_reminders, amb=none, clar=none, list_is_plain=True
"我周五有什么提醒" -> list_reminders, amb=clear, clar=none, list_is_plain=False  # filtered -> full agent
greetings          -> chit_chat, amb=none, clar=none, reply_needed
```

## Safety Notes

- Probes used synthetic accounts (`999999999999998/9`); no reminders created, no
  state mutated (list is read-only, greetings are chit-chat).
- Both features fail safe: when not eligible or on any streaming error, the turn
  uses the unchanged non-streaming / full-agent path.
- Filtered list requests continue to route to the full agent
  (`list_is_plain=False`).

## Verification

- `.venv/bin/python -m pytest tests/unit/coke` → 891 passed.
- `zsh scripts/check`, `clean-rebuild-backend` + `repo-os-docs` surfaces → pass.
- Production smoke telemetry above.

## Follow-ups

- The two prior slices not yet implemented: emergency-deadline safety guard and
  reminder cancel/update/create prepared actions (see spec migration slices).
- Streaming rare case: if a chit-chat full reply fails final validation after the
  first segment streamed, the user could see segment + recovery; low risk for
  chit-chat, monitor.
