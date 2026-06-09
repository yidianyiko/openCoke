# Turn Path Unification: Plan → Execute → Express

## Status

approved-design (2026-06-10). Supersedes the fast-path direction in
`docs/superpowers/specs/2026-06-09-agent-flow-time-optimization-design.md`.
This is a clean-slate rebuild of the interactive turn path with **no migration,
no compatibility shims, and no historical remnants**. Current production keeps
running the existing path until this rebuild reaches correctness and latency
parity, then it is replaced wholesale.

## Problem

The current clean turn path feels contorted, and the feeling points at real
architectural debt:

1. **Three LLM brains that duplicate each other.** A `SemanticInterpreter`
   classifies intent, the `Interaction Agent` then re-decides which tools to call
   (re-judging intent), and a separate `reminder_detector` extracts fields. The
   same understanding work happens more than once.
2. **The Interaction Agent is both orchestrator and expresser.** It carries tool
   schemas, runs a tool-calling loop, accumulates tool results, and then
   generates prose — all in one growing context. This is the real
   context-growth source.
3. **Performance was patched by adding parallel paths.** A reminder-list "fast
   path" (`ActionRunner` + `routing.derive_route` + `is_streaming_eligible`)
   bypasses the agent for some turns and re-implements the correctness guards on
   a second path. Two ways to handle a turn, each needing independent
   verification.
4. **Two renderers for the same output.** For reminder lists the agent generates
   prose and then `_enforce_tool_reply_contracts` discards it and substitutes a
   runtime template. The agent's generation is wasted.
5. **Streaming was bolted onto a validate-then-send core.** The agent both acts
   and expresses, so streaming risked claiming success before materialization,
   forcing awkward suppression logic.

The constraint that justifies keeping a dedicated expression agent is real:
**expression must run on a bounded context to avoid context explosion.** A single
legacy-style agent that reasons, orchestrates tools, and expresses in one context
grows without bound on long conversations. So "collapse back to one agent" is not
acceptable. The goal is to keep bounded expression while removing the duplication,
the parallel paths, and the bolted-on streaming.

## Decision

Rebuild the interactive turn as **one uniform shape**:

```text
Plan      reason over the conversation, emit a declarative plan
   →      (0..N domain actions + how to respond). The only reasoning brain.
Execute   runtime runs the plan's domain actions behind correctness guards.
   →      No LLM. Produces a settled, trusted outcome.
Express   bounded streaming agent renders the settled outcome, or converses
   →      for action-free turns. No tools, no orchestration.
Background  post-analysis / memory, off the critical path.
```

**Complexity is data, not a branch.** There is no `simple` vs `complex` marking
and no routing to different handlers. A greeting is a plan with zero actions; a
single reminder is a plan with one action; "move the meeting, remind me to bring
the contract, and add 老王" is a plan with three actions. The same machine runs
all of them. Clarification is a plan with zero actions whose response directive
is "ask one question." This is the legacy reality (one path absorbs the
difficulty) without legacy's context explosion (expression is split out and
bounded).

This collapses three brains into two clean roles — **Plan** and **Express** —
each doing its job exactly once.

## Roles

### Plan (the single reasoning layer)

- **Input:** windowed conversation, trusted facts, focus/reference context.
  Bounded by conversation length, which is windowed and summarized — it does NOT
  carry tool schemas, tool-call results, or a multi-step orchestration loop.
- **Output:** a declarative `TurnPlan`:
  - `actions`: ordered list of domain actions. Each action has a `domain`
    (reminder, social_scheduling, settings, friendship, calendar_import, …), an
    `operation` (create, update, cancel, list, schedule, add_via_code, …), and
    typed `params` already extracted from the message (e.g. reminder
    `trigger_time`, `content`). The list may be empty.
  - `response_directive`: how Express should respond — `render_outcome`,
    `converse`, `ask_clarification` (with the clarification subject), or
    `acknowledge`.
  - `reply_necessity`: `reply_needed` or `intentional_no_reply`.
- **Discipline:** no `confidence` field, no numeric thresholds, no keyword/regex
  routing. If Plan is wrong, fix its prompt, schema, examples, and eval corpus.
- Plan replaces the current `SemanticInterpreter`. Field extraction that the
  `reminder_detector` does today is **folded into Plan's action params** — there
  is no separate extraction brain. (See Risks for the eval gate on this.)

### Execute (runtime, no LLM)

- Runs each action in `TurnPlan.actions` in order through existing domain
  services and ports.
- All correctness guards live here, as runtime gates around execution:
  - `FreshnessGuard` before any state change and before close;
  - staged commands for every mutation; nothing materializes until the staged
    command is allowed to commit;
  - supersede / input-window / `last_closed_inbound_seq` handling;
  - dispositions: `replied`, `no_reply`, `pending_async_reply`, `failed`,
    `recovered`, `superseded`;
  - separate turn outcome and delivery state; delivery audit; provider adapters
    behind canonical delivery contracts.
- Produces a `settled_outcome`: trusted facts describing exactly what happened
  (created/updated/listed/failed), suitable for Express to describe truthfully.

### Express (bounded streaming expression)

- **Input:** `settled_outcome` + `response_directive` + (for `converse`) windowed
  conversation history + persona. Nothing else. No tool schemas, no tool loop.
- **Output:** user-facing segments, **streamed** as each segment completes.
- **Has no tools and performs no domain mutation.** It can only describe a
  settled outcome or converse.
- Express is the single renderer. The runtime list template and the agent's
  prose generation collapse into this one owner; the discard-and-substitute step
  is deleted.

## Why Streaming Becomes Unconditionally Safe

In the current path the agent acts and expresses together, so a streamed segment
could claim success before the action materialized. In the new shape **Execute
fully completes — including the staging/materialization decision — before Express
starts.** Express only ever describes an already-settled outcome. Therefore:

- streaming a success statement can never precede materialization (it already
  happened);
- there is no eligibility predicate and no per-action streaming gate — streaming
  is a universal property of Express;
- a superseded turn is stopped in Execute/close handling before Express delivers,
  with the same supersede rules as any reply.

The entire "no streamed success before materialization" hazard dissolves
structurally rather than being defended with suppression logic.

## What Gets Deleted (no remnants)

- the standalone fast path: `coke/turn/action_runner.py` as a *bypass*,
  `coke/turn/routing.py` as a bypass gate, `coke/turn/streaming.py`
  (`is_streaming_eligible`) — the runtime-execution idea survives as Execute, but
  the "second path" framing is gone;
- `list_is_plain` and any field that existed only to gate the bypass;
- `_enforce_tool_reply_contracts` template substitution and the dual renderer;
- the Interaction Agent's tool profile, tool-calling loop, and orchestration
  responsibilities;
- the separate `SemanticInterpreter` classify step (promoted into Plan) and the
  separate `reminder_detector` brain (folded into Plan's extraction);
- the bolted-on streaming consumption / eligibility wiring in `runner.py`.

## What Is Kept (as Execute guards, not separate brains)

`FreshnessGuard`, staged commands, dispositions, supersede / input-window,
separate turn-vs-delivery state, delivery audit, provider adapters, and the
no-false-success contract. These move from "phases and parallel paths in front of
the agent" to "runtime gates wrapping Execute." `pending_async_reply` remains a
visibility-only disposition that does not materialize staged commands, set
`completed_at`, or advance the input window.

## Expected Shape Per Turn

```text
greeting:      Plan(actions=[], converse) → Express(stream)
list:          Plan(actions=[list {filter}], render) → Execute(query) → Express(stream)
create:        Plan(actions=[create {time, content}], render) → Execute(stage+materialize) → Express(stream)
multi-action:  Plan(actions=[update…, create…, add_participant…], render) → Execute(run all) → Express(stream)
clarification: Plan(actions=[], ask_clarification) → Express(stream one question)
```

One capable bounded Plan call plus one bounded streaming Express call per turn,
with a guarded no-LLM Execute in between — fewer serial LLM hops than the current
interpreter + orchestrating agent + detector + protocol retry chain.

## Risks And How They Are Handled

- **Plan must be a capable planner and extractor.** Folding multi-action planning
  and field extraction into one structured call raises the bar on that call.
  Mitigation: this is the same "hard turns are hard" problem every architecture
  has; a plan it cannot complete becomes `actions=[]` +
  `ask_clarification`, which is the same shape, not a second path. The
  extraction-into-Plan decision is gated on an eval comparing Plan-extracted
  reminder fields against the current detector on a representative corpus before
  the detector is deleted.
- **No complexity branch means Plan owns all difficulty.** Accepted on purpose:
  branching on difficulty is exactly the smell being removed. Difficulty is
  expressed as plan size and as clarification, never as a routing decision.
- **Express must never exceed the settled outcome.** Express is constrained to
  describe `settled_outcome` and allowed conversational content only; the
  no-false-success contract is enforced at the Execute/close boundary, not by
  trusting Express prose.

## Migration

Clean-slate, no compatibility:

1. Production stays on the current path (it works) for the duration of the
   rebuild. Do not degrade production to chase cleanliness mid-flight.
2. Build Plan / Execute / Express as new, focused units. Delete the superseded
   constructs listed above in the same change that replaces them — no aliases, no
   dual code paths kept "just in case".
3. Replace the production turn path wholesale only after correctness-boundary
   parity (staged commands, freshness, dispositions, supersede, no-false-success)
   and latency/time-to-first-token parity-or-better are demonstrated on the real
   user path.

## Verification Strategy

- **Plan eval** on a representative corpus (30–50 cases per the project's
  eval-subset norm): intent + action set + extracted params + response directive,
  including multi-action and clarification cases. Gate the detector deletion on
  extraction parity.
- **Execute correctness tests**: every guard (freshness, staged-command commit,
  supersede non-delivery, disposition correctness, `pending_async_reply`
  non-closing) holds under the new shape.
- **Express contract tests**: describes only the settled outcome; no domain
  mutation; streaming delivers complete segments and never a success claim absent
  a settled outcome.
- **Real-account smoke** on the deployed rebuild for greeting, list, create,
  update, cancel, multi-action, and clarification, reading the new telemetry
  phases (`turn.plan`, `turn.execute`, `turn.express` with first-segment timing).
  Per project rule: green unit tests with stubbed models are necessary but not
  sufficient — probe the real model and the real user path before claiming the
  rebuild is at parity.
- **Latency evidence**: before/after turn total and time-to-first-token.

## Open Implementation Parameters

- whether reminder field extraction lives fully inside Plan or as a typed
  Execute-step validator after Plan proposes params (decided by the extraction
  eval, default: inside Plan);
- the Express model role (small/fast streaming model vs the current interaction
  model) — decided by render-quality and latency measurement;
- exact `TurnPlan` schema field names and the domain/operation enum surface
  (implementation plan);
- waiting-signal threshold and emergency-deadline value remain guardrails from
  the prior design and are unchanged by this restructure.

## Summary

Keep legacy's clean linear reality — one path that absorbs difficulty — and keep
clean Coke's bounded-context protection, by splitting the old single agent into
**Plan (reason → declarative plan) → Execute (runtime, guarded, no LLM) →
Express (bounded streaming render/converse)**. Complexity is plan size, not a
branch. Each job is done once. Streaming is structurally safe. The fast path, the
dual renderer, the duplicate brains, and the bolted-on streaming do not exist in
the new architecture — not as migrated code, but as deleted concepts.
```
