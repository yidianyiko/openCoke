# Turn Path Unification: Plan → Execute → Express

## Status

implemented-cutover (2026-06-11). Originally design-ready on 2026-06-10 through
**two** dual-review rounds (correctness-regression + architecture-purity lenses)
and a decision pass with the user. The Plan→Execute→Express spine is endorsed;
the second round's concrete findings — typed outcomes too coarse,
partial-overstate false-success, history-only recovery not durable, partial-close
transaction, streaming classification, inbound/render split, concrete data
contracts — are all incorporated (see "Resolved Design Decisions"). The inbound
pipeline is the only interactive inbound path.

Amended on 2026-06-12 by
`docs/superpowers/specs/2026-06-12-turn-eager-execute-abolish-staging-design.md`.
The Plan / PlanCompile / Execute / Express bounded split remains current, but
this document's staging, selected-command materialization, and mutating streaming
sub-design is historical only. Current runtime truth: Execute calls real domain
services inside the shared turn transaction, `ActionOutcome` carries only the
real typed outcome data, Close commits domain writes + outbound rows +
disposition atomically, and there is no staged-command storage layer.

Supersedes the fast-path direction in
`docs/superpowers/specs/2026-06-09-agent-flow-time-optimization-design.md`. Clean
slate, no compatibility shims. Render-mode Interaction Agent remains for
non-inbound structured turns.

## Scope

This design replaces the **inbound interactive turn** path only. Notification and
render turns (non-inbound, with their own segment-merge behavior) are out of
scope and unchanged. Concretely: the **render-mode agent code and the
notification/render output path stay**. Where this spec deletes Interaction-Agent
or output-protocol pieces, the deletion is scoped to the inbound interactive
path; any piece shared with render/notification turns is split (a narrowed inbound
Express vs the retained render-mode agent), never removed out from under the
non-inbound surfaces. The implementation plan must carry an explicit inbound-only
boundary so notification/render turns are provably untouched.

## Problem

The current clean turn path feels contorted and the feeling points at real debt:

1. **Duplicate LLM reasoning** — a classifier-only pass, a tool-calling
   Interaction Agent, and the reminder detector all reason over the same turn;
   understanding happens more than once.
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
one overloaded agent" is rejected. The goal: keep bounded expression while removing
the duplication, the parallel path, and the bolted-on streaming.

## Decision

Rebuild the inbound interactive turn as **one uniform pipeline**:

```text
Plan        propose intent + a flat list of requested actions (natural-language
   →        / keyword params, NOT resolved IDs). The only reasoning brain.
PlanCompile  deterministic validation of action enums, required params, and
   →        whether a missing-param clarification is required before execution.
Execute     runtime runs each action through domain services, which OWN
   →        reference resolution and return typed outcomes; Execute assembles
            them into settled_outcome (the per-action typed outcomes).
Express     bounded streaming agent renders settled_outcome. It only describes
   →        settled_outcome, so no-false-success is structural.
Close/Deliver  materialize, set disposition, advance close state, deliver.
Background   post-analysis / memory, off the critical path.
```

**Complexity is data, not a branch.** No `simple`/`complex` marking and no
routing to different handlers. A greeting is zero actions; a reminder is one;
"move the meeting, remind me to bring the contract, add 老王" is three.
Clarification is not a separate path — it is a typed outcome (`needs_input` from
PlanCompile, or `needs_choice`/`not_possible` from a service). The same machine
runs all of them.

### The key correction from review: response is derived, not pre-decided

The earlier draft had Plan decide the response up front. Both reviews showed this
is unsafe: many turns cannot know the right user-visible response until **after**
a service result. The corrected contract:

- **Plan proposes**; it does not decide success vs clarification vs blocked.
- **Domain services resolve and judge** (see "Service-side resolution" below) and
  return typed outcomes.
- **Execute assembles** the per-action typed outcomes into `settled_outcome`.
- **Express renders** `settled_outcome`; because it can only describe it,
  no-false-success is structural and needs no downstream verifier (see Express
  role).

The result-conditioned branching the old ReAct loop did becomes the **typed
outcome a domain service deterministically returns** — not an LLM re-reasoning
loop and not a second code path. Expressing that outcome is rendering, not a
decision.

## Service-Side Resolution

Resolution belongs in the tool/service side: actions operate on **keywords and
natural references, not pre-resolved IDs**. The service resolves the reference
and returns a typed result; ambiguity is a service outcome, not an agent guess.
The clean domain services already work this way — e.g. reminder
`update_by_keyword`/delete/complete resolve a match and return
`no_matching_reminder` or `ambiguous_reminder_reference` with candidates.

This design adopts that contract uniformly:

- Plan emits actions with **keyword / natural-reference params**, never invented
  IDs. ("delete my gym reminder" → `reminder.delete {match: "gym"}`.)
- The **domain service owns resolution** and returns a **typed outcome**. Each
  outcome has a universal `category` AND a **mandatory domain `status`** (the
  fine-grained truth Express must not lose), plus a domain data payload:

  | category | meaning | required domain `status` examples |
  | --- | --- | --- |
  | `done` | the action settled with effect | `created`, `updated`, `cancelled`, `listed`, `partial{succeeded, failed}`, `already_done`/`duplicate_active`, `imported{imported, skipped, downgraded, failed}` |
  | `needs_choice` | ambiguous; the user must pick | candidates + which field is ambiguous |
  | `needs_input` | a required field is missing | which field (`trigger_time`, `content`, …) |
  | `needs_confirmation` | resolvable but risky (past/incomplete date, etc.) | what to confirm |
  | `not_possible` | cannot be done | `not_a_friend`, `unreachable`, `unsupported`, `already_cancelled`, … |
  | `nothing` | no-op | — |

  The universal `category` keeps Express's rendering uniform; the mandatory
  `status` carries the domain truth (partial counts, duplicate-vs-created,
  already-cancelled) so Express **cannot lose it to a coarse "done"**. The
  per-domain `ActionHandler` produces the correct `status` — this is the
  deterministic, exhaustively-tested surface.

- When the category is `needs_choice` / `needs_input` / `needs_confirmation`,
  **interact with the user** — asking is a first-class, expected outcome.

There is **no separate `response_obligation` concept and no `ObligationResolver`
unit.** The typed outcome IS the deterministic, testable contract, and it is
produced where the decision is actually made — the **domain service** (the
reminder service already returns ambiguous/not-found today). Execute assembles
the per-action typed outcomes into `settled_outcome`; Express renders them. The
"how to respond" is not a decision layer: the decision (which outcome) is the
service's deterministic result; turning it into prose (confirm / ask which /
explain) is Express's rendering job.

Within-turn reference resolution that is DB-backed (resolving a friend name or a
focus/reference to a concrete row) stays **runtime-owned inside the domain
services / Execute**, not folded into Plan's prompt.

### Lightweight Pending-Clarification Record (not command recovery)

We delete the **recoverable-*command* subsystem** — there is no half-done mutation
to recover, because a blocked/ambiguous action never mutates. The
`RecoverableSchedulingIntent` model with its open/consumed/expired/superseded
command lifecycle, the `follow_up_action` interpreter field, and the
mutation-recovery semantics all go.

But review showed that relying on conversation history alone to recover "which
one?" is **not** safe: the next inbound carries only the new message, and the
prior assistant clarification + its candidates live in Agno/window-dependent
history, which is not a durable product invariant. So we **keep one narrow,
non-mutating record**: a `PendingClarification` capturing the unresolved action,
its **structured candidates**, the source input window, an action fingerprint,
an expiry, and consume-on-resolve. It is **not** a staged command and mutates
nothing.

Next turn: Execute reads any open `PendingClarification` for the conversation;
Plan proposes the resolving action (e.g. picks a candidate or supplies the
correction); Execute matches it to the record by fingerprint, completes the
deferred action, and consumes the record. Lapses on expiry or supersede;
double-completion is additionally guarded by inbound idempotency + domain
duplicate-active checks; no durable alias is learned (the record is one-shot).

This is far smaller than the old subsystem (no command state, no materialization
recovery) but keeps the **structured candidates** that "which one?" genuinely
needs — the part that cannot be reconstructed from prose.

## Multi-Action Turns: Flat List, No Conditional Plan

`TurnPlan.actions` is a **flat ordered list with no `depends_on` / `on_result`
conditionals.** Service-side resolution removes the need for conditional plans:

- An apparent "B depends on A's result" almost always collapses into a **richer
  single-action selector resolved by the service** — e.g. "move my earliest
  reminder an hour later" is one `update {select: "earliest", shift: "+1h"}`, not
  a query-then-update chain. The ReAct "list friends first, then create with the
  ID" pattern is exactly the chaining that service-side resolution deletes.
- Where the service cannot resolve a single target, the outcome is `ambiguous` or
  `not_found` → a **`needs_choice`/`needs_input` outcome (clarification)**, never a
  cross-action dependency.

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
  combined reply (e.g. "moved the meeting to 10:00; you have two reminders
  matching 'gym' — which one?").
- An unresolved action records a non-mutating `PendingClarification` with its
  **structured candidates** (see "Lightweight Pending-Clarification Record"); the
  next turn resolves it deterministically. No staged command, no mutation
  recovery.
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
- Plan owns language-level action proposal. It does **not** own precise field
  extraction (trigger time, durations, IDs) — that stays with the detector as an
  Execute step (see "Detector").

### PlanCompile (deterministic, no LLM)

- Validates action enums, required-param presence, and reference-candidate
  shape. If a required param is structurally missing, it sets a
  `needs_input` outcome **before** execution (no LLM needed to know
  a create has no content).
- Keeps Plan narrow: Plan proposes language-level actions; PlanCompile turns them
  into executable, validated action specs or a clarification.

### Execute (runtime, no LLM, internally structured)

Execute is **not** a monolith. It is composed of small units so the runner stays
as the orchestration boundary:

- `ActionExecutor` drives the ordered actions;
- per-domain `ActionHandler`s call the domain service (which owns resolution and
  returns typed outcomes);
- a detector extraction step supplies precise fields where needed (reminder time,
  etc.) before a mutating handler runs;
- `ExecutionOutcomeBuilder` assembles the per-action typed outcomes into
  `settled_outcome` (preserving the staged-vs-materialized and
  model-visible-vs-internal distinctions that exist today, e.g. pruned staged
  shared-reminder facts);
- `Freshness/StagingGuard`, `CloseCoordinator`, `DeliveryCoordinator` own the
  transaction boundary.

Execute touches **no** LLM, streaming, prompt rules, or provider payload
formatting.

### Express (bounded streaming, one model, no downstream verifier)

- **What it is:** the current Interaction Agent with orchestration removed — same
  user-facing-prose job, but no tools, no tool loop, bounded context. (Names are
  cosmetic; "Express" just marks the narrowed role.)
- **Input:** `settled_outcome` (the per-action typed outcomes) + (for `converse`,
  i.e. a no-action turn) windowed history + persona. No tool schemas.
- **Output:** user-facing segments, streamed. One capable model for both render
  and converse; lists are rendered by the same model from the prompt ("list every
  item with its time"), **not** a deterministic template — the template was a
  crutch for the overloaded agent and the focused Express does not need it.
- **Must render the domain `status`, including partials.** Express is told to
  state the mandatory `status` faithfully: a `done.partial{succeeded, failed}`
  must be reported as partial (state the failures), a `duplicate_active` must not
  be reported as a fresh create, an `already_cancelled` must not be reported as a
  cancel. The explicit `status` (not coarse `done`) is what makes this possible.
- **No downstream claim/coverage verifier.** The no-false-success guarantee is
  **structural, not a second-layer check**: Express only ever describes a
  `settled_outcome` produced by Execute, so it cannot claim a state change Execute
  did not perform short of hallucinating its own input. The overloaded agent
  claimed success *as it decided to act*; the Plan/Execute/Express split
  removes that root cause. If smoke ever shows Express asserting an outcome not in
  `settled_outcome` (e.g. overstating a `partial` as full), the fix is **upstream**
  (sharper `status`, Express prompt), not a downstream verifier.

> Deliberate override (2026-06-10): both design reviews recommended a
> settled-outcome-bound Express verifier, and the re-review specifically warned
> that the structural argument does not cover **partial** overstatement. We
> consciously rely on the mandatory explicit `status` + Express prompt + smoke
> instead of a verifier, and fix upstream if violated. Residual risk (Express
> softening a partial) is watched in smoke; revisit a minimal partial-claim guard
> only if production shows it.

## Data Contracts

> Historical after 2026-06-12: this section records the implemented 2026-06-10
> contract before the eager-execute amendment. The current `ActionOutcome` has no
> staged id field, and the materialization-plan concept is retired.

The implementation plan defines exact fields; the spine is these typed units (so
no boundary is "guessed"):

- `TurnPlan` — `{ actions: list[ProposedAction], reply_necessity }`. Plan output.
- `ProposedAction` — `{ domain, operation, params (keyword/natural refs) }`.
- `CompiledAction` — PlanCompile output: a validated `ProposedAction` or a
  `needs_input` mark. No resolution yet (resolution is the service's job).
- `ActionOutcome` — per action: `{ category, status (mandatory domain status),
  data, staged_command_id? }`. Produced by the per-domain `ActionHandler`.
- `SettledOutcome` — `{ outcomes: list[ActionOutcome] }` for the turn. Express
  input.
- `PendingClarification` — `{ unresolved_action_fingerprint, candidates,
  source_input_window, expires_at, status }`. Non-mutating; not a staged command.
- `MaterializationPlan` — the selected staged-command ids `CloseCoordinator.commit`
  materializes atomically.

Each per-domain `ActionHandler` owns its domain operation/param schema, its
resolution (keyword/selector → row), its detector use for extraction, and
producing the normalized `ActionOutcome` (`category` + mandatory `status`).
PlanCompile stays generic (enum/required-param validation only).

## Close Boundary And Streaming (made explicit)

> Historical after 2026-06-12: current mutating inbound turns buffer Express
> segments, commit real Execute-time domain writes at Close, then deliver from
> committed outbound rows. There is no close-time command materialization step.

The close/materialization order must be exact, and the streaming rule must be
mechanical (no "classify the prose as descriptive vs success"). The contract:

1. **Resolve then stage.** Each `ActionHandler` resolves its action against the
   domain service (keyword/selector → concrete target) and stages **only the
   concrete, materializable command** with stable facts (`resolve_and_stage`, not
   the current stage-then-resolve order). Ambiguous/blocked actions produce a
   typed outcome and stage nothing.
2. `ExecutionOutcomeBuilder` assembles `settled_outcome`; Express generates
   segments from it.
3. **CloseCoordinator.commit** takes the plan, the rendered segments, and the
   **selected staged-command ids** (only the resolved actions), rechecks freshness
   / supersede, **materializes those commands atomically**, sets the disposition,
   advances `last_closed_inbound_seq`, and records the non-mutating
   `PendingClarification` for any unresolved action. Materialization failure of
   one command fails that command's outcome (reported as `not_possible`/error),
   without falsely reporting it as done. Nothing about an ambiguous action is
   committed.
4. **Streaming rule (mechanical, not prose classification):**
   - A **no-action / read-only / converse** turn (no staged command) may stream
     segments before close — these cannot assert a state change.
   - A **mutating** turn (any staged command) **buffers all segments until after
     step 3 commit**, then delivers. No state-change segment is ever delivered
     before its materialization. This trades the streaming latency win on
     mutating turns for a guarantee that needs no prose inspection; the latency
     win remains on chat and list/read turns (the high-frequency cases).
   - A newer inbound or freshness failure before step 3 supersedes the turn:
     nothing materializes and nothing buffered is delivered.

`pending_async_reply` remains visibility-only: it does not materialize, set
`completed_at`, or advance the close sequence.

## Detector

The detector is **not a brain and not duplication** — it is a specialized
extraction step that turns a natural time phrase ("明天9点") into a concrete
datetime in the user's timezone. Plan proposes the natural phrase; the detector
resolves it; their jobs do not overlap, so keeping it does not reintroduce the
duplication smell. Natural-language time parsing (Chinese relative/vague/recurring
time) is genuinely hard and brittle as deterministic code, which is why it is an
LLM step rather than runtime code.

**End-state: the detector stays long-term as an Execute extraction step.** It is
the one remaining extra serial LLM hop on the create/update path. Folding it into
Plan (extract during planning, removing the hop) is an **optional, measured
latency optimization — not a goal** — pursued only if the serial hop proves a
meaningful latency cost AND a strong live-model parity eval passes (timezone,
relative/vague time, recurrence, duration, missing-time follow-up, "do not
guess"; false concrete time and missed clarification are zero-tolerance). If the
eval does not pass, the detector simply stays.

## What Gets Deleted (no remnants)

- the reminder-list **fast path as a parallel bypass**: `action_runner` as a
  bypass, `routing.derive_route` as a gate, `streaming.is_streaming_eligible`,
  `list_is_plain` — the runtime-execution idea survives inside Execute, the
  "second path" framing is gone;
- `_enforce_tool_reply_contracts` and the **output-protocol claim-validation
  layer** (`validate_social_scheduling_claim` and the list-substitution /
  post-hoc claim checks) — no-false-success is now structural (Express only
  describes `settled_outcome`), not a downstream verifier;
- the Interaction Agent's tool profile, tool-calling loop, and orchestration;
- the standalone classifier-only step (promoted into Plan);
- the bolted-on streaming consumption / eligibility wiring in `runner.py`;
- the recoverable-*command* part of the `RecoverableSchedulingIntent` subsystem
  (the staged-command/materialization-recovery lifecycle) and the interpreter
  `follow_up_action` field — replaced by a much smaller non-mutating
  `PendingClarification` record (see "Lightweight Pending-Clarification Record").

The detector is **not** deleted — it is relocated into Execute as an extraction
step (see Detector).

## What Is Kept (as Execute-owned guards)

`FreshnessGuard`, staged commands, dispositions, supersede / input-window /
`last_closed_inbound_seq`, separate turn-vs-delivery state, delivery audit, and
provider adapters. The **no-false-success contract is kept but enforced
structurally** (Execute decides+performs; Express only describes the result),
not by a downstream claim verifier.

## Expected Shape Per Turn

```text
greeting:     Plan([]) → Execute(none) → Express(converse, stream)
list:         Plan([list {filter}]) → Execute(query → counts) → Express(render list, stream)
create:       Plan([create {content, time-phrase}]) → detector extract → Execute(stage) → Express(confirm) → materialize@close
delete vague: Plan([delete {match:"gym"}]) → Execute(service → needs_choice{c}) → Express(ask which)
multi-action: Plan([update…, create…, add_participant…]) → Execute(run all, typed outcomes) → Express(summary, stream)
```

One bounded Plan call + a no-LLM Execute + one bounded streaming Express call
(plus the detector only where extraction is needed) — fewer serial LLM hops than
the current interpreter + orchestrating agent + detector + protocol-retry chain.

## Risks

- **Plan extraction parity** if/when the detector is folded in — gated on eval,
  not assumed.
- **Typed-outcome coverage** — every domain action must return a `category` +
  mandatory `status`; an edge case must return `not_possible` (fail closed),
  never a `done` it did not achieve, and a partial must be `done.partial`, never
  bare `done`. This contract is the deterministic, exhaustively-tested surface.
- **Partial overstatement** — the residual false-success class (Express softening
  a `partial`). Mitigated by the explicit `status` + prompt; watched in smoke;
  fixed upstream. No downstream verifier by decision (recorded override).
- **settled_outcome fidelity** — must preserve model-visible-vs-internal pruning
  (shared reminders) and full counts (calendar import) or Express will
  under-report.
- **PendingClarification correctness** — the structured record must resolve the
  right deferred action (fingerprint), expire/lapse cleanly, and never
  double-complete.
- **Plan must propose correct multi-action sets**; a set it cannot form becomes a
  clarification (`needs_input`), the same shape — never a second path.

## Verification Strategy

- **Plan eval** (intent + proposed action set + reply necessity) on the
  representative corpus; multi-action and clarification cases included.
- **Detector parity eval** before any detector deletion: live-model paired
  against current behavior across Chinese/English, timezone boundaries,
  midnight/DST, vague/incomplete/past times, recurrence, duration, batch,
  no-trigger, missing-time follow-up, new-topic, and shared-reminder extraction;
  false concrete time and missed clarification are zero-tolerance.
- **Typed-outcome tests** (at the service boundary): each domain action returns
  the right `category` + `status`, including ambiguous/not_found/duplicate_active/
  already_cancelled/unreachable/partial/needs_confirmation; edge → `not_possible`,
  partial → `done.partial`, never a false bare `done`.
- **Close-boundary tests**: resolve_and_stage → render → selective materialize →
  disposition → close-advance; multi-action partial close materializes only the
  resolved commands; supersede before materialize delivers/mutates nothing;
  `pending_async_reply` non-closing.
- **Streaming tests**: mutating turns buffer until after commit; non-mutating
  (chat/list/read) turns stream; no state-change segment delivered before its
  materialization.
- **PendingClarification tests**: structured candidates persist; next-turn
  resolution by fingerprint; expiry/lapse; no double-complete.
- **Express tests**: renders `category` + `status` from `settled_outcome` only,
  including partial-as-partial; streaming delivers complete segments.
- **Real-account smoke** on the deployed rebuild for greeting, list, create,
  update, cancel, ambiguous-delete, shared-reminder, calendar-import,
  multi-action, clarification — reading new telemetry phases (`turn.plan`,
  `turn.execute`, `turn.express` first-segment timing). Green stubbed unit tests
  are necessary but not sufficient; probe the real model and user path.
- **Latency evidence**: turn total and time-to-first-token, before/after.

## Resolved Design Decisions (2026-06-10)

> Historical amendment: the bounded spine, typed outcomes, and inbound/render
> split remain. The 2026-06-12 eager-execute spec replaces the selected-command
> materialization and mutating streaming decisions below.

Decided across two dual-review rounds and a decision pass with the user.

- **Flat action list, no `depends_on`** — dependencies collapse into
  service-resolved selectors or clarification; multi-action turns use
  **run-all + aggregate** with per-action staging (see "Multi-Action Turns").
- **Lightweight `PendingClarification`, not command recovery** — the
  recoverable-*command* subsystem and `follow_up_action` are deleted, but a small
  non-mutating record keeps the **structured candidates** "which one?" needs
  (history is not a durable invariant). See "Lightweight Pending-Clarification
  Record".
- **One Express model, no downstream verifier — but explicit `status`** — one
  capable model renders list and converse from the prompt; no list template;
  no-false-success is structural, and the **mandatory domain `status`** (incl.
  `partial`) lets Express report partials faithfully. Residual partial-overstate
  risk is watched in smoke, fixed upstream (see Express role; deliberate override
  recorded).
- **Universal `category` + mandatory domain `status`, no `response_obligation`/
  ObligationResolver** — services return a `category`
  (done/needs_choice/needs_input/needs_confirmation/not_possible/nothing) plus a
  fine-grained `status`; `settled_outcome` is the per-action list; Express renders
  it (see Service-Side Resolution).
- **Streaming only on non-mutating turns** — mutating turns buffer until close
  commit; chat/list/read turns stream. Mechanical, no prose classification (see
  Close Boundary).
- **resolve_and_stage + selective partial close** — resolve before staging;
  `CloseCoordinator.commit` materializes only the selected resolved commands
  atomically (see Close Boundary, Data Contracts).
- **Inbound-only scope, render-mode agent retained** — shared pieces are split,
  not removed from under notification/render turns (see Scope).
- **Detector stays long-term as an Execute extraction step** — folding into Plan
  is an optional measured latency optimization gated on a parity eval, not a goal
  (see Detector).

## Summary

Keep one clean linear reality — one path that absorbs difficulty, with
resolution pushed into the services — and keep bounded-context protection, by
splitting the old single agent into **Plan (propose) → PlanCompile
(validate) → Execute (resolve via services, assemble settled_outcome, guarded, no
LLM) →
Express (bounded streaming render, one model, no downstream verifier)**. The
response is derived from real outcomes, not pre-decided. Complexity is plan size;
result-conditioned branching is a deterministic Execute-owned outcome policy.
Streaming cuts time-to-first-token for descriptive content while materialization
stays atomic at close. No-false-success is structural — Execute decides and
performs, Express only describes the result — so the fast path, the dual
renderer, the duplicate reasoning, the persisted recovery subsystem, and the
downstream claim-validation layer are all deleted as concepts. Only the detector
is relocated (into Execute), pending an eval to fold it into Plan.
```
