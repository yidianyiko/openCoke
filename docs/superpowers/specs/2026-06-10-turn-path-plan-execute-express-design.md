# Turn Path Unification: Plan → Execute → Express

## Status

design-in-review (2026-06-10). Revised after two independent design reviews
(correctness-regression lens and architecture-purity lens) that both returned
"not ready for an implementation plan" with strongly convergent findings. This
revision applies the clear, agreed corrections; remaining open questions are in
"Still To Discuss".

Supersedes the fast-path direction in
`docs/superpowers/specs/2026-06-09-agent-flow-time-optimization-design.md`. Clean
slate, no compatibility shims. Production keeps running the existing path until
this rebuild reaches correctness-boundary and latency parity, then is replaced
wholesale.

## Scope

This design replaces the **inbound interactive turn** path only. Notification and
render turns (non-inbound, with their own segment-merge behavior) are out of
scope here and are not changed by this work.

## Problem

The current clean turn path feels contorted and the feeling points at real debt:

1. **Three LLM brains that duplicate each other** — `SemanticInterpreter`
   classifies intent, the `Interaction Agent` re-decides which tools to call, and
   `reminder_detector` extracts fields; understanding happens more than once.
2. **The Interaction Agent is both orchestrator and expresser** — it carries tool
   schemas, runs a tool loop, accumulates results, then generates prose in one
   growing context. This is the real context-growth source.
3. **Performance was patched by adding a parallel path** — the reminder-list fast
   path bypasses the agent and re-implements the guards on a second path.
4. **Two renderers for one output** — the agent renders a list, then
   `_enforce_tool_reply_contracts` discards it and substitutes a template.
5. **Streaming was bolted onto a validate-then-send core**, forcing awkward
   eligibility/suppression logic.

The constraint that justifies a dedicated expression agent is real: **expression
must run on a bounded context to avoid context explosion.** So "collapse back to
one legacy agent" is rejected. The goal: keep bounded expression while removing
the duplication, the parallel path, and the bolted-on streaming.

## Decision

Rebuild the inbound interactive turn as **one uniform pipeline**:

```text
Plan        propose intent + a flat list of requested actions (natural-language
   →        / keyword params, NOT resolved IDs). The only reasoning brain.
PlanCompile  deterministic validation of action enums, required params, and
   →        whether a missing-param clarification is required before execution.
Execute     runtime runs each action through domain services, which OWN
   →        reference resolution and return typed outcomes; Execute derives a
            settled_outcome + a response_obligation from the real results.
Express     bounded streaming agent renders the response_obligation; a
   →        deterministic post-verifier binds its claims to settled_outcome.
Close/Deliver  materialize, set disposition, advance close state, deliver.
Background   post-analysis / memory, off the critical path.
```

**Complexity is data, not a branch.** No `simple`/`complex` marking and no
routing to different handlers. A greeting is zero actions; a reminder is one;
"move the meeting, remind me to bring the contract, add 老王" is three.
Clarification is not a separate path — it is a `response_obligation` value
produced either by PlanCompile (missing param) or by Execute (ambiguous/blocked
outcome). The same machine runs all of them.

### The key correction from review: response is derived, not pre-decided

The earlier draft had Plan decide the response up front. Both reviews showed this
is unsafe: many turns cannot know the right user-visible response until **after**
a service result. The corrected contract:

- **Plan proposes**; it does not decide success vs clarification vs blocked.
- **Domain services resolve and judge** (see "Service-side resolution" below) and
  return typed outcomes.
- **Execute derives** `settled_outcome` + `response_obligation` from those real
  results.
- **Express renders** the obligation and is **verified** against settled facts.

The result-conditioned branching the old ReAct loop did becomes an explicit,
deterministic **outcome → obligation policy owned by Execute** — not an LLM
re-reasoning loop and not a second code path.

## Service-Side Resolution (the legacy lesson)

Legacy pushed resolution down into the tool/service side: it operated on
**keywords and natural references, not pre-resolved IDs**. The service resolved
the reference and returned a typed result; ambiguity was a service outcome, not
an agent guess. The clean domain services already work this way — e.g.
reminder `update_by_keyword`/delete/complete resolve a match and return
`no_matching_reminder` or `ambiguous_reminder_reference` with candidates.

This design adopts that contract uniformly:

- Plan emits actions with **keyword / natural-reference params**, never invented
  IDs. ("delete my gym reminder" → `reminder.delete {match: "gym"}`.)
- The **domain service owns resolution** and returns a typed outcome:
  `done`, `ambiguous{candidates}`, `not_found`, `blocked{reason}`, or
  `counts{...}`.
- **Execute maps the typed outcome to a `response_obligation`**:
  `report_success`, `ask_clarification{candidates|missing}`,
  `explain_blocked{reason}`, `report_counts{...}`, or `converse`.
- When the obligation is `ask_clarification`, **interact with the user** — that is
  a first-class, expected outcome, rendered by Express like any other.

Within-turn reference resolution that is DB-backed (resolving a friend name or a
focus/reference to a concrete row) stays **runtime-owned inside the domain
services / Execute**, not folded into Plan's prompt.

### No Persisted Recovery State

Cross-turn correction ("I meant 老王张", or answering "which gym reminder?") needs
**no persisted recoverable-intent record, no facts hash, and no `follow_up_action`
signal.** A blocked or ambiguous action never mutates, so there is no half-done
state to recover — only an unresolved conversational thread, which is already in
Plan's windowed history. Plan reconstructs the deferred or remaining action from
that history and re-proposes it as a normal action; Execute runs it normally.

This deletes a whole subsystem that existed only to compensate for the narrow
classifier: the `RecoverableSchedulingIntent` model and its open/consumed/
expired/superseded lifecycle, its 15-minute expiry, the repository/service
methods, and the interpreter `follow_up_action` field. The guarantees they
provided are covered elsewhere: double-completion by inbound idempotency + domain
duplicate-active guards + Plan reading "already done" from history; staleness by
history windowing + turn supersede; and "no durable alias learning" is automatic
because nothing is persisted. The only requirement is that the unresolved turn is
within Plan's history window, which always holds for an immediate clarification.

## Multi-Action Turns: Flat List, No Conditional Plan

`TurnPlan.actions` is a **flat ordered list with no `depends_on` / `on_result`
conditionals.** Service-side resolution removes the need for conditional plans:

- An apparent "B depends on A's result" almost always collapses into a **richer
  single-action selector resolved by the service** — e.g. "move my earliest
  reminder an hour later" is one `update {select: "earliest", shift: "+1h"}`, not
  a query-then-update chain. The ReAct "list friends first, then create with the
  ID" pattern is exactly the chaining that service-side resolution deletes.
- Where the service cannot resolve a single target, the outcome is `ambiguous` or
  `not_found` → a **clarification obligation**, never a cross-action dependency.

**Precondition (a real requirement on domains):** each domain service owns
resolution and selectors (keyword, ordering like "earliest", "if absent", …) and
returns a typed outcome. A reference it cannot resolve to a single target is a
clarification, not a guess.

### Aggregation policy: run-all + aggregate

When a turn has multiple actions and they settle to mixed outcomes (some `done`,
some `ambiguous`/`blocked`), Execute **runs every action independently and
aggregates**:

- Cleanly resolved actions are staged and **materialize at close** as usual.
- Ambiguous/blocked actions do **not** mutate; each contributes its outcome to a
  combined `response_obligation` (e.g. "moved the meeting to 10:00; you have two
  reminders matching 'gym' — which one?").
- An unresolved action is simply asked about. The user's next-turn answer is
  reconstructed by **Plan from windowed conversation history** — there is no
  persisted "recoverable intent". Because a blocked action never mutated, there
  is no state to recover; only the conversational thread, which Plan already
  reads. (See "No Persisted Recovery State".)
- Disposition is `replied` (the turn did reply); the resolved actions' staged
  commands materialize, the unresolved one's do not. Close materialization stays
  atomic **per resolved action set**; nothing about an ambiguous action is
  committed.

Rejected alternatives: short-circuit on first block (more round-trips), and
two-phase all-or-nothing (atomic but does zero of three when one is unclear —
too harsh for the reminder product).

## Roles

### Plan (single reasoning brain, narrow)

- **Input:** windowed conversation, trusted facts, focus/reference context.
  Bounded by conversation, windowed/summarized. No tool-call loop, no tool
  results.
- **Output `TurnPlan`:** linguistic understanding + an ordered list of *requested*
  actions, each `{domain, operation, keyword/natural params}`, plus
  `reply_necessity`. It does **not** emit a final response decision.
- **Discipline:** no `confidence`, no thresholds, no keyword/regex routing in
  runtime. Fix errors via prompt/schema/examples/eval.
- Plan replaces `SemanticInterpreter`. Plan does **not** yet own precise field
  extraction (trigger time, durations, IDs) — that stays with the detector as an
  Execute step (see "Detector").

### PlanCompile (deterministic, no LLM)

- Validates action enums, required-param presence, and reference-candidate
  shape. If a required param is structurally missing, it sets a
  `clarification_required` obligation **before** execution (no LLM needed to know
  a create has no content).
- Keeps Plan narrow: Plan proposes language-level actions; PlanCompile turns them
  into executable, validated action specs or a clarification.

### Execute (runtime, no LLM, internally structured)

Execute is **not** a monolith. It is composed of small units so it does not
become "TurnRunner v2":

- `ActionExecutor` drives the ordered actions;
- per-domain `ActionHandler`s call the domain service (which owns resolution and
  returns typed outcomes);
- a detector extraction step supplies precise fields where needed (reminder time,
  etc.) before a mutating handler runs;
- `ExecutionOutcomeBuilder` assembles `settled_outcome` (preserving the
  staged-vs-materialized and model-visible-vs-internal distinctions that exist
  today, e.g. pruned staged shared-reminder facts);
- an `ObligationResolver` maps typed outcomes → `response_obligation`;
- `Freshness/StagingGuard`, `CloseCoordinator`, `DeliveryCoordinator` own the
  transaction boundary.

Execute touches **no** LLM, streaming, prompt rules, or provider payload
formatting.

### Express (bounded streaming, verified)

- **Input:** `response_obligation` + `settled_outcome` + (for `converse`) windowed
  history + persona. No tool schemas, no tool loop.
- **Output:** user-facing segments, streamed, **plus structured claim/coverage
  references** against `settled_outcome` so the output is verifiable.
- **Post-verifier (deterministic):** rejects false success, staged-success
  wording, missing counts (e.g. calendar import imported/skipped/downgraded/
  failed), incomplete reminder lists, and unsupported no-reply. "Bounded prompt"
  is **not** the safety boundary — the verifier is. This is the focused successor
  to today's social-claim validator and list-substitution, not their deletion.
- Exact list rendering may use a deterministic renderer inside the Express layer
  rather than free prose, to guarantee coverage.

## Close Boundary And Streaming (made explicit)

The earlier claim "streaming is structurally safe because Execute settles first"
was over-stated; the close/materialization order must be exact. The contract:

1. Actions run; domain services resolve and produce typed outcomes; staged
   commands are staged under `Freshness/StagingGuard`.
2. `ObligationResolver` produces the `response_obligation`; Express generates
   segments; the post-verifier validates them against `settled_outcome`.
3. **Only after** verified segments exist and a final freshness/supersede check
   passes does `CloseCoordinator` **materialize** staged commands, set the
   disposition, and advance `last_closed_inbound_seq` — atomically, as today.
4. **Streaming rule:** Express may stream **descriptive** segments derived from a
   settled-or-staged outcome, but a **success claim for a state change** must use
   wording valid at staging time and is only delivered as final after
   materialization in step 3. A newer inbound or freshness failure before step 3
   supersedes the turn: nothing materializes and no success is delivered. This
   preserves the clean invariant (no materialization before close) while still
   cutting time-to-first-token for the descriptive/conversational portion.

`pending_async_reply` remains visibility-only: it does not materialize, set
`completed_at`, or advance the close sequence.

## Detector

Do **not** fold `reminder_detector` into Plan yet. Field extraction (timezone,
relative/vague time, recurrence, duration, missing-time follow-up, "do not
guess") is a deliberate, specialized responsibility today and the GLM
thinking-off path is tuned for it. Keep the detector as an **Execute extraction
step**. Deleting it later is gated on a strong live-model paired eval (see
Verification); until that passes, the detector stays.

## What Gets Deleted (no remnants)

- the reminder-list **fast path as a parallel bypass**: `action_runner` as a
  bypass, `routing.derive_route` as a gate, `streaming.is_streaming_eligible`,
  `list_is_plain` — the runtime-execution idea survives inside Execute, the
  "second path" framing is gone;
- `_enforce_tool_reply_contracts` as a *post-hoc substitution* (replaced by the
  Express deterministic renderer + verifier);
- the Interaction Agent's tool profile, tool-calling loop, and orchestration;
- the standalone `SemanticInterpreter` classify step (promoted into Plan);
- the bolted-on streaming consumption / eligibility wiring in `runner.py`;
- the **persisted recoverable-scheduling-intent subsystem** (model + lifecycle +
  expiry + repository/service methods) and the interpreter `follow_up_action`
  field — cross-turn correction is reconstructed by Plan from history (see "No
  Persisted Recovery State").

The detector and the no-false-success verification are **not** deleted — they are
relocated into Execute / the Express verifier respectively.

## What Is Kept (as Execute-owned guards)

`FreshnessGuard`, staged commands, dispositions, supersede / input-window /
`last_closed_inbound_seq`, separate turn-vs-delivery state, delivery audit,
provider adapters, and the no-false-success contract.

## Expected Shape Per Turn

```text
greeting:     Plan([]) → Execute(none) → Express(converse, stream)
list:         Plan([list {filter}]) → Execute(query → counts) → Express(render list, verified)
create:       Plan([create {content, time-phrase}]) → detector extract → Execute(stage) → Express(confirm) → materialize@close
delete vague: Plan([delete {match:"gym"}]) → Execute(service → ambiguous{c}) → obligation=ask → Express(ask which)
multi-action: Plan([update…, create…, add_participant…]) → Execute(run all, typed outcomes) → Express(summary, verified)
```

One bounded Plan call + a no-LLM Execute + one bounded streaming Express call
(plus the detector only where extraction is needed) — fewer serial LLM hops than
the current interpreter + orchestrating agent + detector + protocol-retry chain.

## Risks

- **Plan extraction parity** if/when the detector is folded in — gated on eval,
  not assumed.
- **ObligationResolver completeness** — every domain's typed outcomes must map to
  an obligation; an unmapped outcome must fail closed (block + explain), never a
  false success. This table is the new home of result-conditioned logic and must
  be exhaustively tested.
- **settled_outcome fidelity** — must preserve model-visible-vs-internal pruning
  (shared reminders) and full counts (calendar import) or Express will
  under-report.
- **Plan must propose correct multi-action sets**; a set it cannot form becomes a
  clarification obligation, the same shape — never a second path.

## Verification Strategy

- **Plan eval** (intent + proposed action set + reply necessity) on the
  representative corpus; multi-action and clarification cases included.
- **Detector parity eval** before any detector deletion: live-model paired
  against current behavior across Chinese/English, timezone boundaries,
  midnight/DST, vague/incomplete/past times, recurrence, duration, batch,
  no-trigger, missing-time follow-up, new-topic, and shared-reminder extraction;
  false concrete time and missed clarification are zero-tolerance.
- **ObligationResolver tests**: every typed domain outcome → correct obligation,
  including ambiguous/not_found/blocked/counts; unmapped → fail closed.
- **Close-boundary tests**: stage → verify → materialize → disposition →
  close-advance ordering; supersede before materialize delivers nothing and
  mutates nothing; `pending_async_reply` non-closing.
- **Express verifier tests**: reject false/staged success, missing counts,
  incomplete lists, unsupported no-reply; streaming delivers complete segments.
- **Real-account smoke** on the deployed rebuild for greeting, list, create,
  update, cancel, ambiguous-delete, shared-reminder, calendar-import,
  multi-action, clarification — reading new telemetry phases (`turn.plan`,
  `turn.execute`, `turn.express` first-segment timing). Green stubbed unit tests
  are necessary but not sufficient; probe the real model and user path.
- **Latency evidence**: turn total and time-to-first-token, before/after.

## Still To Discuss (not yet decided)

1. **Express model role** — reuse the interaction model vs a smaller/faster
   render model; decided by render-quality + latency measurement.
2. **Exact `response_obligation` taxonomy** and the per-domain typed-outcome
   surface (implementation-plan detail, but the taxonomy shape affects testing).
3. **Detector end-state** — stays as an Execute step now; the bar and corpus to
   ever fold it into Plan.

Resolved (2026-06-10):
- **Flat action list, no `depends_on`** — dependencies collapse into
  service-resolved selectors or clarification; multi-action turns use
  **run-all + aggregate** with per-action staging (see "Multi-Action Turns").
- **No persisted cross-turn recovery state** — the recoverable-scheduling-intent
  subsystem, facts hash, and `follow_up_action` are deleted; Plan reconstructs a
  deferred/remaining action from windowed history (see "No Persisted Recovery
  State").

## Summary

Keep legacy's clean linear reality — one path that absorbs difficulty, with
resolution pushed into the services — and keep clean Coke's bounded-context
protection, by splitting the old single agent into **Plan (propose) → PlanCompile
(validate) → Execute (resolve via services, derive obligation, guarded, no LLM) →
Express (bounded streaming render, verified)**. The response is derived from real
outcomes, not pre-decided. Complexity is plan size; result-conditioned branching
is a deterministic Execute-owned outcome policy. Streaming cuts time-to-first
token for descriptive content while materialization stays atomic at close. The
fast path, the dual renderer, and the duplicate reasoning are deleted as
concepts; the detector and the no-false-success verifier are relocated, not
removed.
```
