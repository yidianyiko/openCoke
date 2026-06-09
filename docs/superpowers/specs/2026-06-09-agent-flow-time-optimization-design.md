# Agent Flow And Turn Latency Optimization Design

## Status

approved-for-implementation (2026-06-09)

## Problem

Clean Coke has stronger correctness boundaries than the legacy runtime, but the
interactive turn path is too heavy. Every ordinary turn pays a serial chain of
expensive model calls before the user sees any reply, and the user sees nothing
at all until the very last call returns.

## Evidence That Reframes The Problem

The 2026-06-09 real-user phase probe
(`docs/issues/2026-06-09-real-user-turn-latency-phase-probe.md`) plus three code
facts settle what is actually slow. This evidence corrects the original framing
of this spec.

Probe phase timing (production stack, six real-user turns):

| case | turn.total | semantic_interpreter | agent.primary | tools |
| --- | ---: | ---: | ---: | ---: |
| English greeting | 16.9s | 2.8s | 14.1s | 0 |
| English create reminder | 23.6s | 2.8s | 17.5s | 1 |
| English list reminders | 13.1s | 3.1s | 9.8s | 1 |
| Chinese greeting | 27.7s | 9.7s | 18.0s | 0 |
| Chinese create reminder | 21.2s | 3.2s | 13.2s | 1 |
| Chinese list reminders | 14.1s | 2.2s | 11.7s | 1 |

Aggregate: `turn.total` avg 19.4s; `agent.primary` avg 14.0s (~72%);
`semantic_interpreter` avg 4.0s. Reminder create also pays a separate detector
call (English 3.1s, Chinese 4.6s) inside the create tool path.

Three findings, each verified:

1. **`agent.primary` is a single fat generation, not a multi-call orchestration
   loop — for the dominant case.** The two greeting turns have `tool_count=0`:
   no tools, no detector, no orchestration. They still burn 14.1s and 18.0s. The
   cost is the generation itself (prompt size, model latency, output length),
   not the agent acting as a workflow orchestrator. Bypassing the agent for
   "explicit actions" does nothing for these turns.

2. **The reminder-list agent generation is wasted work.** Runtime code already
   re-renders the list deterministically:
   `_enforce_tool_reply_contracts` → `_render_reminder_list_reply`
   (`coke/llm/agno_interaction_agent.py:759,858`). When the reminder tool returns
   the `render_reminder_list` reply contract, the runtime **discards the agent's
   prose and substitutes a template**. The system pays ~9.8s for an agent
   generation whose output is then thrown away.

3. **Model roles are already separated.** `create_interaction_model`,
   `create_interpreter_model`, and `create_detector_model` are distinct
   (`coke/llm/config.py:72,81,92`). The interaction model is the heavy one. Every
   ordinary turn already pays `interpreter (~4s)` + `interaction generation
   (~14s)` ≈ 18s serial floor before any tool work.

The corrected framing: the problem is **not** that the agent orchestrates. It is
that the runtime pays for a **heavy generation that is sometimes discarded
(list) or could be templated/cheaper (confirmations)**, and that the user sees a
**black screen for the entire turn** because nothing streams.

## Flow Diagrams

### Clean current (measured)

```text
time   0s    4s        8s       12s      16s      20s     24s
       ├─────┼─────────┼────────┼────────┼────────┼───────┤

chat / greeting  (tool_count=0)
  interp ████ (4s)
  agent       ███████████████████████████ (14s single generation)
  visible ────────────────────────────────────────◀FIRST 18s

reminder create  (tool_count=1)
  interp ████ (4s)
  agent       ████████████████████████████████████ (17.5s)
              └ decide-gen + detector(3s) + finalize-gen
  visible ──────────────────────────────────────────────◀FIRST 21s

reminder list  (tool_count=1)
  interp ███ (3s)
  agent      ██████████████████████ (9.8s generation)
             └ runtime then DISCARDS agent prose, re-renders via template
  visible ────────────────────────────────────◀FIRST 13s
```

No streaming: every scenario is a full black screen until the last call returns.

### Legacy (architectural shape; no retained per-phase numbers)

```text
time   0s    4s        8s       12s      16s      ...background

any turn
  prepare ███ (semantic orchestration: need_detect / need_retrieve)
  detect      ██ (only when prepare says so, BEFORE chat)
  chat-stream    ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ (streaming generation)
  visible ──────────◀FIRST ~6-8s   ← first complete sentence emitted early
  post-analyze ........▓▓▓▓▓▓▓▓ (background: follow-up / memory, non-blocking)
```

Legacy's real advantage is not faster model calls. It is: prepare decides detect
before chat; chat **streams** so first-visible-token is small even when total
work is similar; post-analysis runs in the background. Clean currently fuses
`total` and `time-to-first-token` into one number.

### Proposed clean (projected, not yet measured)

```text
time   0s    4s        8s       12s      16s      20s
       ├─────┼─────────┼────────┼────────┼────────┤

chat / greeting  (cannot bypass the agent generation → cheaper + streamed)
  prepare ████ (4s, route=full_agent)
  agent-stream  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ (generation, streamed)
  visible ──────────────◀FIRST ~8s   ← 18s → ~8s via streaming

reminder list  (flagship: runtime template already exists)
  prepare ███ (3s, route=prepared_action / list)
  domain     ▪ (list query <1s, no LLM)
  render-tpl  ▪ (runtime template, 0 LLM)
  visible ──────◀FIRST ~4s    ← 13s → ~4s, entire 9.8s generation deleted

reminder create  (Prepare → detector → light render)
  prepare ████ (4s, route=prepared_action / create)
  detector    ███ (3s, the only required extraction LLM)
  render-tpl     ▪▪ (template / light LLM; success prose only after materialize)
  visible ──────────◀FIRST ~9s   ← 21s → ~9s, ~14s agent generation removed
```

### Side-by-side time-to-first-token

```text
scenario          Clean now (measured)   Legacy (shape)   Proposed (projected)
─────────────────────────────────────────────────────────────────────────────
chat / greeting   18s ████████           ~7s ◀ ███        ~8s ◀ ███  (streaming)
reminder list     13s ██████             ~7s ◀ ███        ~4s ◀ █▌   (delete+tpl)
reminder create   21s ██████████         ~7s ◀ ███        ~9s ◀ ████ (delete gen)
```

## Decision

Pursue three workstreams, ordered by proven value and risk. The original
"the Interaction Agent must stop being the orchestrator" framing is replaced:
the agent is not the problem for chat turns. The decisions are:

1. **Prepared Action Path for read-only and explicit reminder ops, list first.**
   Route explicit, unambiguous reminder list/count/cancel/update through runtime
   orchestration that reuses the existing domain ports and the existing runtime
   render template, skipping the heavy agent generation. List is the flagship:
   its agent generation is already discarded today, so the win is deleting wasted
   work and reusing an existing template, not building a new mechanism.

2. **Streaming first segment for the unavoidable agent generation.** Chat,
   greetings, empathy, and complex turns cannot bypass the agent — that
   generation *is* the product reply. The only lever is to stream the first
   complete safe segment so time-to-first-token drops from ~18s to single
   digits, plus reduce per-generation cost (prompt budget, render-only model
   role where applicable). This is a peer workstream, not a deferred extra.

3. **Prepared create path with a light/templated render.** Route explicit
   reminder create through detector then a runtime-owned or light render,
   removing the heavy agent generation from the common create path. Short Render
   defaults to a runtime template (zero or light LLM), not a render-mode
   Interaction Agent call, because render mode uses the same heavy model and
   would not move latency.

### Routing source

Routing is derived in **runtime code** from the existing `SemanticDecision`
structured fields (`intent_action`, `ambiguity`, `required_clarification`,
`reply_necessity`). No new model call is added, and no keyword matching is
introduced. The rule:

```text
route = prepared_action  if intent_action ∈ PREPARED_ACTIONS
                         and ambiguity == clear
                         and required_clarification == none
       clarification     if required_clarification != none
       no_reply          if reply_necessity == intentional_no_reply
       full_agent        otherwise
```

`PREPARED_ACTIONS` starts as `{list_reminders}`, then expands to
`{cancel, update}`, then `{create}`, then shared-reminder ops, per the migration
slices. This is semantic-field routing, not keyword routing: the route is read
from fields the interpreter already emits, and domain services remain the
authority for whether the action is valid and executable. There is no
`confidence` field and no numeric threshold. If routing is wrong, fix the
interpreter prompt, schema, examples, and eval corpus.

## Goals

- Cut time-to-first-token, not just total turn time. The user must stop staring
  at a black screen for tens of seconds.
- Delete wasted serial model work (the discarded list generation first).
- Keep most ordinary turns to single-digit time-to-first-token.
- Make 120s a rare emergency cutoff, not a normal response target.
- Keep staged commands, freshness checks, output dispositions, delivery audit,
  and domain boundaries from the clean architecture.
- Preserve the "no keyword router" and "no fake success prose" product contract.

## Non-Goals

- Do not reintroduce legacy Mongo state, bridge ownership, or session-state
  mutation patterns. Do not revive `StreamingChatWorkflow` as a code import; only
  its streaming-first-segment lesson.
- Do not add keyword matching such as `if "reminder" in text`.
- Do not add numeric confidence thresholds as runtime policy.
- Do not add a new serial LLM call for routing. Routing is derived from existing
  interpreter fields.
- Do not bypass staged command materialization or freshness guards for
  state-changing actions.
- Do not stream or template state-changing success before materialization.

## Clean Guarantees To Preserve

- input windows and `last_closed_inbound_seq`;
- `FreshnessGuard` before state changes and close decisions;
- staged commands for reminder and social scheduling mutations;
- explicit dispositions: `replied`, `no_reply`, `pending_async_reply`, `failed`,
  `recovered`, and `superseded`;
- separate turn outcome and delivery state;
- domain services as the source of product state changes;
- provider adapters behind canonical delivery contracts;
- telemetry and evidence that can explain where a turn spent time.

`pending_async_reply` remains an intermediate visibility disposition. It must not
materialize staged commands, set `completed_at`, or advance the input window.

## Target Flow

### 1. Routing (runtime, no new model call)

The existing `SemanticInterpreter` runs as today and emits `SemanticDecision`.
Runtime derives the route from its fields (see Routing source). No second
interpreter call, no separate "Semantic Prepare" model call.

### 2. Prepared Action Path

`ActionRunner` is runtime code, not an agent. For a `prepared_action` route it
selects the domain operation from the structured decision and calls existing
domain services through the same ports and guards used by tools.

```text
SemanticInterpreter
→ runtime route = prepared_action
→ ActionRunner
→ detector only when the action needs extraction (not for list/cancel)
→ domain service (same ports + FreshnessGuard + staged command as tools)
→ Short Render
→ validated close decision
```

Initial scope is `list_reminders` (read-only, no detector, no state change), then
`cancel`/`update`, then `create`.

### 3. Short Render

Short Render expresses a trusted domain result. It defaults to a **runtime-owned
template** (reusing the `_render_reminder_list_reply` pattern), zero or light
LLM. It does not reuse the render-mode Interaction Agent for the common case,
because that uses the heavy interaction model and would not improve latency.

Constraints:

- no domain mutation tools;
- only describe `trusted_facts.domain_result` and allowed claim facts;
- no business inference from chat history;
- state-changing success may only be claimed after the staged command is allowed
  to materialize.

### 4. Full Interaction Agent + Streaming

The full Interaction Agent remains the path for `full_agent` routes: open-ended
chat, personality, empathy, mixed intents, complex social scheduling, and any
action not yet covered by the Prepared Action Path. This generation cannot be
bypassed, so it must **stream the first complete safe segment** to cut
time-to-first-token. Streaming must not emit state-changing success before
materialization.

### 5. Background Work

Any analysis, memory update, summarization, or non-critical enrichment that is
not required for the first correct user-visible reply runs after the close
decision or through a recoverable background queue, with failures logged but not
turned into user-visible latency.

## Waiting And SLA Policy

1. Optimize the normal path so most turns never approach the emergency cutoff.
2. Keep a hard cutoff so pathological turns cannot leave users waiting silently.

- A visible waiting signal must be attempted after roughly 20-25s of active
  processing if no final reply has been recorded.
- Waiting text is a runtime-owned typed signal, not assistant prose about the
  user's request.
- The turn-level emergency deadline is in the 110-150s design range; the exact
  value is an implementation parameter after measuring complex cases. Hitting it
  is a reliability event, not a normal outcome.
- After a timeout or cancellation, stale work must not materialize staged
  commands or send success prose.

## Correctness Rules

- Routing may select an explicit action, but domain services remain the
  authority for whether the action is valid and executable.
- Detector output remains trusted-or-invalid. Runtime must not patch detector
  errors with regex fallbacks.
- Prepared Action Path must use the same freshness and staged-command commit
  guard as tool execution.
- `pending_async_reply` is visibility only and does not close the input window.
- New inbound messages before close supersede stale work; stale work may not
  deliver a normal final answer.
- Delivery failures are recorded as delivery evidence, not confused with turn
  outcome.
- Streamed segments are subject to the same supersede and materialization rules:
  no streamed success before materialization, no streamed segment from
  superseded work.

## Telemetry Required Before And During Implementation

Add or preserve timing for:

- routing decision (derived, no model call) and chosen route;
- ActionRunner;
- detector calls by action type;
- domain service execution;
- Short Render (template vs light LLM);
- Full Interaction Agent primary, protocol retry, and first-segment-stream
  latency;
- waiting-dispatch latency and delivery result;
- emergency deadline/cancellation events.

Every event must avoid user content, raw prompts, raw tool arguments, and raw
model output.

## Migration Slices

### Slice 1: Measurement And Safety

- Keep current behavior.
- Split `agent.primary` telemetry into model, tool, and render sub-phases with
  `turn_id`, agent role, tool count, and attempt count.
- Add the turn-level emergency deadline as a safety guard, with tests proving it
  does not close or materialize stale state incorrectly.

### Slice 2 (flagship): Reminder List Prepared Action

Route explicit, unambiguous `list_reminders` through `ActionRunner` → list domain
service → runtime list template. This deletes the ~9.8s discarded agent
generation and reuses the existing `_render_reminder_list_reply` template. Highest
proven value, lowest risk (read-only, no detector, no state change).

### Slice 3 (peer track): Streaming First Segment

Stream the first complete safe segment for `full_agent` turns. This is the only
lever for the dominant no-tool chat case. Do not stream state-changing success
before materialization. Can proceed in parallel with Slice 2.

### Slice 4: Reminder Cancel / Update Prepared Actions

Route explicit cancel/update through `ActionRunner` with freshness and
staged-command guards, then Short Render. Requires deterministic clarification
handling for ambiguous targets.

### Slice 5: Reminder Create Prepared Action

Route explicit create through detector then domain service then Short Render,
removing the heavy agent generation from the common create path.

### Slice 6: Shared Reminder Prepared Actions

Extend only after reminder paths prove the boundary. Shared reminders have
participant, privacy, and partial-delivery complexity.

## Verification Strategy

- unit tests for runtime route derivation: exclusivity, no confidence field,
  no keyword matching, correct `PREPARED_ACTIONS` gating;
- unit tests for `ActionRunner` calling existing domain ports with freshness
  guards;
- unit tests that `pending_async_reply` remains non-closing;
- contract tests for Short Render template output against trusted domain results;
- streaming tests proving no success segment before materialization and no
  segment from superseded work;
- real-user or production-like smoke for reminder list/create/update/cancel;
- latency evidence comparing before/after turn phase timings and
  time-to-first-token;
- interruption tests proving stale prepared actions cannot materialize or send
  success after a newer inbound supersedes them.

## Open Implementation Parameters

- exact emergency deadline value in the 110-150s range;
- exact waiting threshold if 20s vs 25s differs by channel;
- whether reminder cancel/update need deterministic clarification before the
  Prepared Action Path can own them;
- whether a render-only smaller model role is worth adding for the cases Short
  Render cannot template purely.

## Summary

The evidence corrected the framing. The agent is not slow because it
orchestrates; it is slow because each heavy generation costs ~14s, the list
generation is discarded, and nothing streams. The decision:

```text
clean target:
  flagship   reminder list → ActionRunner → runtime template (delete wasted gen)
  peer       full_agent chat → stream first segment (cut time-to-first-token)
  then       create → detector → light render (delete heavy gen)
  routing    derived from existing interpreter fields, no new model call
```

This reduces latency by deleting discarded work and streaming the unavoidable
work, not by hiding slow work behind a later timeout message. Waiting and hard
deadlines remain guardrails.
