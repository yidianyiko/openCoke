# Agent Flow And Turn Latency Optimization Design

## Status

draft-for-review

## Problem

Clean Coke has stronger correctness boundaries than the legacy runtime, but the
current interactive turn path is too heavy for high-frequency tool actions. A
normal inbound turn can serialize several expensive steps before the user sees a
final answer:

```text
SemanticInterpreter
→ context assembly
→ full Interaction Agent
→ tool call selected by the Interaction Agent
→ detector inside the tool/domain boundary
→ domain service
→ Interaction Agent structured output validation/retry
→ final reply
```

The real-user latency probe on 2026-06-09 showed `agent.primary` as the dominant
phase: 6 samples averaged 19.4s end-to-end, with `agent.primary` averaging 14.0s
and accounting for roughly 72% of total turn time. Reminder creation also paid a
detector call after the full Interaction Agent had already run.

The problem is architectural, not just provider latency. Provider improvements
can reduce individual model-call duration, but they do not remove unnecessary
serial model calls or the fact that the Interaction Agent currently acts as a
workflow orchestrator.

## Decision

Move the clean runtime closer to the legacy phase boundary while preserving clean
state guarantees:

```text
Semantic Prepare
→ Prepared Action Path when the action is explicit
→ constrained Short Render

or

Semantic Prepare
→ Full Interaction Agent for complex conversation
```

The Interaction Agent must stop being the normal orchestrator for clear domain
actions. It remains the complex-conversation fallback and a prose/rendering
owner, but high-frequency explicit actions should be prepared and executed by
runtime-owned orchestration.

This is not keyword routing and not confidence-threshold routing. Semantic
Prepare emits explicit structured yes/no decisions, like legacy Orchestrator
fields (`need_reminder_detect`, `need_context_retrieve`, `need_web_search`).

## Goals

- Prevent users from silently waiting for slow turns.
- Make 120s a rare emergency cutoff, not a normal response target.
- Keep most ordinary user-visible turns on the order of tens of seconds, not
  minutes.
- Reduce the serial LLM count for high-frequency tool actions.
- Keep staged commands, freshness checks, output dispositions, delivery audit,
  and domain boundaries from the clean architecture.
- Preserve the "no keyword router" and "no fake success prose" product
  contract.

## Non-Goals

- Do not reintroduce legacy Mongo state, bridge ownership, or session-state
  mutation patterns.
- Do not add keyword matching such as `if "reminder" in text`.
- Do not add numeric confidence thresholds as runtime policy.
- Do not blindly add more serial agents. More agents only help when they remove
  work from the critical path or narrow an LLM responsibility.
- Do not bypass staged command materialization or freshness guards for
  state-changing actions.
- Do not let runtime templates claim action success unless the canonical product
  contract explicitly allows that prose ownership.

## Legacy Lessons To Keep

Legacy was not faster because every model call was cheap. It was more responsive
because its runtime phases were clearer:

```text
PrepareWorkflow
→ ChatWorkflow streaming
→ PostAnalyzeWorkflow background
```

The useful lessons are:

- Prepare is a semantic orchestration phase, not keyword routing.
- Reminder detection can happen before the chat response phase when the
  orchestrator says it is needed.
- Chat response is primarily expression, and streaming can emit complete message
  segments before the whole workflow finishes.
- Post-analysis and memory-like work should not block the first user-visible
  reply.
- A sync-window receipt prevents the user from waiting silently while slower
  work continues.

The parts not to copy are equally important:

- Do not make placeholders indistinguishable from product replies.
- Do not mix turn outcome, delivery outcome, and late-promotion state in a way
  that requires inference from multiple legacy tables.
- Do not rely on broad mutable session state as the source of truth.
- Do not let old turns write state or send success after they have been
  superseded.

## Clean Guarantees To Preserve

The optimized flow must keep these clean advantages:

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

### 1. Semantic Prepare

Semantic Prepare is the clean counterpart to legacy Orchestrator. It is a
structured semantic decision layer, not a keyword router and not a full
Interaction Agent.

It emits mutually exclusive routing decisions:

```text
prepared_action
full_agent
clarification
no_reply
```

For `prepared_action`, it also emits an explicit action type:

```text
reminder_create
reminder_list
reminder_update
reminder_cancel
shared_reminder_create
none
```

It may also emit boolean preparation flags:

```text
need_detector
need_context_retrieve
need_web_search
need_full_agent
```

There is no `confidence` field. If the semantic decision is wrong, fix the
prompt, schema, examples, and eval corpus. Do not add runtime threshold tuning or
keyword patches.

### 2. Prepared Action Path

Prepared Action Path handles high-frequency, explicit domain actions without
first invoking the full Interaction Agent as a tool orchestrator.

Initial scope:

- explicit reminder create;
- explicit reminder list/search/count;
- explicit reminder update;
- explicit reminder cancel;
- later: explicit shared-reminder create after the reminder path is proven.

The path is:

```text
Semantic Prepare
→ ActionRunner
→ detector only when needed
→ domain service
→ staged command / trusted domain result
→ constrained Short Render
→ validated close decision
```

`ActionRunner` is runtime code, not an agent. It chooses the domain operation
from the structured Semantic Prepare result and calls existing domain services
through the same ports and guards used by tools.

### 3. Short Render

Short Render expresses a trusted domain result. It is not a new open-ended
workflow agent.

Constraints:

- no domain mutation tools;
- short trusted context;
- no business inference from chat history;
- only describe `trusted_facts.domain_result` and allowed claim facts;
- no retry loop beyond the existing output protocol recovery policy;
- state-changing success may only be claimed after the staged command is allowed
  to materialize.

Short Render can initially reuse render-mode Interaction Agent infrastructure
with a constrained tool profile. If that still proves too slow for simple
confirmations, a later product decision can consider runtime-owned typed
confirmation messages. That is a separate prose-ownership decision.

### 4. Full Interaction Agent

The full Interaction Agent remains the fallback for:

- semantic prepare decisions explicitly routed as `full_agent` because the turn
  is complex, mixed, unsupported by Prepared Action Path, or not an explicit
  domain action;
- mixed intents where the user asks for conversation and action together;
- complex social scheduling or friendship flows not yet covered by Prepared
  Action Path;
- open-ended chat, personality, empathy, and reasoning;
- cases where the prepared action result needs a clarification not covered by a
  deterministic path.

This keeps the agent valuable where an agent is needed, while removing routine
domain orchestration from its normal hot path.

### 5. Background Work

Any analysis, memory update, summarization, or non-critical enrichment that is
not required for the first correct user-visible reply belongs outside the
critical path. It may run after the close decision or through a recoverable
background queue, with failures logged but not turned into user-visible latency.

## Waiting And SLA Policy

The latency strategy has two layers:

1. Optimize the normal path so most turns never approach the emergency cutoff.
2. Keep a hard cutoff so pathological turns cannot leave users waiting
   indefinitely.

Policy:

- A visible waiting signal must be attempted after roughly 20-25s of active
  processing if no final reply has been recorded.
- Waiting text is a runtime-owned typed signal, not assistant prose about the
  user's request.
- The turn-level emergency deadline should be generous enough not to clip normal
  complex turns, but it must terminate silent waiting. A value around 110-150s is
  the design range; the exact value is an implementation parameter after
  measuring current complex cases.
- Hitting the emergency deadline is a reliability event, not an acceptable
  normal outcome.
- After a timeout or cancellation, stale work must not materialize staged
  commands or send success prose.

## Expected Latency Shape

The desired direction is:

```text
ordinary chat:
  Semantic Prepare → Full Interaction Agent

explicit reminder create:
  Semantic Prepare → detector/domain → Short Render

explicit reminder list/cancel/update:
  Semantic Prepare → domain → Short Render

slow or complex turn:
  waiting signal by 20-25s → final reply or controlled failure later
```

Prepared reminder actions should remove one full Interaction Agent orchestration
call from the common action path. The detector may still be necessary, but it
should not be nested behind an earlier full agent call whose main job was to
decide to call the detector.

## Correctness Rules

- Semantic Prepare may route an explicit action, but domain services remain the
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

## Telemetry Required Before And During Implementation

The existing phase telemetry is enough to prove the current bottleneck is
architectural, but not enough to safely optimize every sub-path. Add or preserve
timing for:

- Semantic Prepare;
- ActionRunner;
- detector calls by action type;
- domain service execution;
- Short Render;
- Full Interaction Agent primary and protocol retry;
- waiting-dispatch latency and delivery result;
- emergency deadline/cancellation events.

Every event must avoid user content, raw prompts, raw tool arguments, and raw
model output.

## Migration Slices

### Slice 1: Measurement And Safety

- Keep current behavior.
- Add any missing timing needed to split `agent.primary` into model, tool, and
  render sub-phases.
- Add a turn-level emergency deadline design only as a safety guard, with tests
  proving it does not close or materialize stale state incorrectly.

### Slice 2: Reminder List/Cancel/Update Prepared Actions

Start with lower-risk actions that usually do not need detector extraction or
complex state mutation. Route explicit list/cancel/update decisions through
ActionRunner and Short Render.

### Slice 3: Reminder Create Prepared Action

Route explicit reminder creation through detector and domain service before
Short Render. This is the highest-value latency win because it removes the full
agent-as-tool-orchestrator step from the common create path.

### Slice 4: Streaming Or Early Segment Delivery

Evaluate whether constrained render output can stream safe segments. Do not
stream state-changing success before materialization.

### Slice 5: Shared Reminder Prepared Actions

Extend only after reminder paths prove the boundary. Shared reminders have
participant, privacy, and partial-delivery complexity and should not be the
first migration target.

## Verification Strategy

Use evidence that exercises user-visible paths, not only unit tests:

- unit tests for Semantic Prepare routing exclusivity and no confidence fields;
- unit tests for ActionRunner calling existing domain ports with freshness
  guards;
- unit tests that `pending_async_reply` remains non-closing;
- contract tests for Short Render with trusted domain results;
- real-user or production-like smoke cases for reminder create/list/update/cancel;
- latency evidence comparing before and after turn phase timings;
- interruption tests proving stale prepared actions cannot materialize or send
  success after a newer inbound supersedes them.

## Open Implementation Parameters

These are implementation parameters, not architecture alternatives:

- exact emergency deadline value in the 110-150s range;
- exact waiting threshold if 20s vs 25s differs by channel;
- whether Short Render first reuses existing render-mode Interaction Agent or a
  smaller render-only model role;
- which reminder update/cancel cases require deterministic clarification before
  Prepared Action Path can own them.

## Summary

The design decision is to make clean Coke keep its correctness model while
recovering legacy's clearer runtime phases:

```text
legacy lesson:
  prepare action before chat expression

clean target:
  Semantic Prepare → ActionRunner → Short Render
  with Full Interaction Agent only when a full agent is actually needed
```

This reduces latency by deleting unnecessary serial orchestration, not by hiding
slow work behind a later timeout message. Waiting and hard deadlines remain
guardrails; the normal path should be faster enough that they rarely decide the
user experience.
