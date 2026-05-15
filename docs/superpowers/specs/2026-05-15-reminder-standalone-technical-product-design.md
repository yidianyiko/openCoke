# Reminder Standalone Technical Product Design

**Status:** draft for review
**Date:** 2026-05-15
**Owner:** Codex

## Summary

Define the next boundary for Reminder after the in-process
`ReminderRuntimeContract` implementation.

The goal is technical product independence, not commercial packaging. Reminder
should become a reusable runtime product that Coke consumes, while Coke remains
an IM agent product that happens to depend on Reminder.

```text
Coke
  -> Coke reminder adapter
  -> Reminder technical product contract
  -> Reminder runtime core
  -> Reminder storage, scheduler, fire attempts, and callback delivery
```

This design does not require splitting Reminder into a separate repository,
process, or deployable service immediately. It defines the boundary that makes
those moves possible later without rewriting Coke's reminder behavior again.

## Context

Reminder is no longer just scattered Coke behavior:

- visible user reminders and internal agent follow-ups both live in the
  Reminder System
- `agent/reminder/runtime_contract.py` is now the in-process contract called by
  Agno tools, PostAnalyze follow-up creation, and bridge reminder management
- Coke architecture documents describe Agno tools, HTTP routes, future MCP
  tools, future CLI commands, and web UI as adapters over a stable domain
  contract

That is the right first boundary. The next question is whether Reminder can be
treated as its own technical product. The answer should be yes, but only after
we remove Coke-specific assumptions from the Reminder-facing contract and give
Reminder its own runtime, storage, and callback seams.

## Product Definition

Reminder as a technical product means:

```text
At a future time, bring one thing back into a target context.
```

It is not:

- a commercial SaaS plan
- a billing or pricing surface
- a generic workflow engine
- a task database
- a goal, milestone, or blocker system
- an IM-agent-specific feature

It should be usable by Coke, another agent runtime, a local CLI, an MCP server,
or a backend application without those consumers learning Coke conversation
tables, route keys, character IDs, or scheduler internals.

## Design Goal

Move from "Coke has a Reminder capability" to "Coke consumes the Reminder
technical product."

The target shape is:

```text
Consumer application
  -> consumer adapter
  -> Reminder client or in-process contract
  -> Reminder runtime core
  -> Reminder repository
  -> wake-up engine
  -> fire event / callback contract
  -> consumer-owned continuation
```

The first consumer remains Coke. Future external surfaces should be adapters
over the same Reminder product contract, not parallel implementations.

## Non-Goals

- Do not implement MCP, CLI, HTTP, SDK, or a separate service in this design.
- Do not choose a repository split or packaging format in this design.
- Do not add billing, pricing, onboarding, marketing, or account-plan concepts.
- Do not turn Reminder into a generic `ScheduledAction` or `execute(payload)`
  engine.
- Do not move natural-language reminder intent detection into Reminder core.
- Do not replace Coke's user-visible reminder behavior in this design.
- Do not require multi-worker scheduling before the contract is separated.

## Approaches Considered

### A. Repo Or Service Split First

Extract `agent/reminder` into a package or service immediately.

Pros:

- creates a visible separation quickly
- forces missing dependencies to surface
- makes the product boundary feel concrete

Cons:

- high churn before the contract is stable
- risks moving Coke-specific concepts into a new package unchanged
- creates deployment and versioning questions before they are useful
- does not by itself improve the runtime contract

### B. External Adapter First

Add MCP, HTTP, or CLI directly on top of the current
`ReminderRuntimeContract`.

Pros:

- fastest way to prove external consumption
- useful for demos and manual testing
- keeps the current implementation mostly intact

Cons:

- exposes Coke-specific `conversation_id`, `character_id`, `route_key`, and
  `AgentOutputTarget` concepts too early
- public adapters become compatibility promises
- later cleanup becomes harder because external schemas have already leaked
  internal shape

### C. Boundary-First Technical Product

Define Reminder's product contract, context model, callback model, repository
seams, and reliability roadmap while keeping the implementation in the Coke
repo for now.

Pros:

- separates product ownership before physical extraction
- keeps Coke behavior stable
- makes future MCP, CLI, HTTP, SDK, package, or service adapters additive
- avoids turning this into a generic workflow platform

Cons:

- does not immediately create an external executable product
- requires disciplined follow-up work to avoid remaining only a document

Recommendation: use Boundary-First Technical Product.

## Ownership Boundary

Reminder owns:

- reminder identity and lifecycle
- schedule validation and normalization after adapters provide structured time
- visibility and fire-mode semantics
- durable wake-up state
- fired-event creation
- fire attempt state, retry policy, and terminal failure state
- callback or delivery event contract
- repository interfaces and storage-level invariants

Coke owns:

- natural-language intent detection
- Coke user, character, conversation, and route identity
- mapping Coke context into Reminder context
- final agent turn execution after a reminder fires
- user-visible Coke wording
- WeChat, gateway, and bridge delivery concerns
- Coke-specific reminder management UI

No Reminder core API should require a Coke conversation, character, route key,
or bridge request shape. Coke may carry those values in its own adapter payload
or callback metadata, but they should not be the Reminder product model.

## Core Product Concepts

### Owner

The owner is the authenticated subject that owns a reminder.

First independent shape:

```text
tenant_id: string | null
owner_id: string
owner_type: user | agent | system
```

Coke can map `owner_user_id` to `owner_id` and leave `tenant_id` unset until
multi-tenant product requirements exist.

### Context

The context is where the reminder should re-enter later.

First independent shape:

```text
context_id: string
context_type: conversation | thread | workflow | external
context_ref: object
```

For Coke, `context_ref` can contain conversation and character references, but
Reminder core treats it as opaque structured data with size and schema
constraints.

### Target

The target describes how a fired reminder is handed back to the consumer.

First independent shape:

```text
target_type: callback | webhook | queue | in_process
target_ref: object
```

Current Coke behavior maps to `target_type=in_process`. A future HTTP service
could use `webhook`, and a future local package could use an in-process
callback handler.

### Reminder

Reminder remains a durable future re-entry record:

```text
id
owner
context
target
title
prompt
schedule
origin
visibility
fire_mode
lifecycle_state
next_fire_at
last_fired_at
last_ack_at
last_error
metadata
created_at
updated_at
```

Domain behavior stays small:

- `visibility=visible` means consumers may expose the reminder to users
- `visibility=internal` means consumers must keep it out of user-management
  surfaces unless a later product decision changes that boundary
- `fire_mode=notify` means produce a reminder event
- `fire_mode=followup` means produce a continuation event using `prompt`

### Fire Event

Reminder firing should produce a durable event before consumer-specific work
runs:

```text
event_id
reminder_id
owner
context
target
fire_mode
scheduled_for
fired_at
attempt
trace_id
payload
```

Coke then consumes that event and decides how to re-enter the agent runtime.
Reminder should not directly own Coke's final message generation.

## Technical Interfaces

### Runtime Contract

The existing `ReminderRuntimeContract` is the first implementation surface. It
should evolve toward Coke-neutral inputs while preserving a Coke adapter that
keeps current behavior stable.

Target contract groups:

- visible reminder create, update, cancel, complete, list
- internal follow-up create, replace, clear
- fire-event claim, acknowledge, retry, fail
- due-reminder scanning or scheduler registration

The first implementation can keep method names close to the current contract,
but the data passed through those methods should move away from Coke-specific
target classes.

### Repository Interface

Reminder should define repository interfaces before physical extraction:

```text
ReminderRepository
FireEventRepository
FireAttemptRepository
```

Mongo can remain the first implementation. Coke DAOs should not be imported by
Reminder core once these interfaces exist.

### Scheduler Interface

APScheduler can remain the first wake-up engine, but Reminder should hide it
behind a runtime seam:

```text
ReminderWakeupEngine
  - schedule(reminder_id, fire_at)
  - unschedule(reminder_id)
  - rebuild_active_jobs()
  - shutdown()
```

The wake-up engine is not the source of truth. Durable reminder state is.

### Callback Interface

Reminder should call back through an explicit consumer-owned handler:

```text
ReminderFireConsumer.handle_fire_event(event) -> ack | retry | fail
```

For Coke, the consumer delegates to `ReminderFireEventHandler` and then the
normal agent runtime. For future adapters, the consumer could post to a webhook
or enqueue a message.

## Reliability Model

The current in-process scheduler is acceptable for Coke's present stage, but a
standalone technical product needs a clearer reliability roadmap:

- idempotency key for externally repeatable writes
- trace id for every write and fire event
- fire attempt records
- claim and ack state for fired events
- bounded retry policy
- terminal failed state with durable error
- startup rebuild from durable state
- no claim that a reminder was delivered until the consumer acknowledges it

This does not require implementing a distributed scheduler immediately. It
does mean future external adapters must not claim stronger guarantees than the
runtime actually provides.

## Coke Adapter

Coke should become an adapter over Reminder:

```text
CokeReminderAdapter
  - maps owner_user_id to Reminder owner
  - maps conversation_id / character_id / route_key to context_ref
  - maps Coke output route to target_ref
  - calls Reminder product contract
  - consumes fire events and invokes Coke agent runtime
```

This adapter is the only place where Coke-specific identity and route semantics
should appear. Existing Agno tools, PostAnalyze follow-up creation, bridge HTTP
routes, and web management flows should depend on this adapter or the
underlying contract, not on Reminder storage internals.

## External Adapter Order

Do not start with every adapter.

Recommended order:

1. **Python in-process package/API shape**: proves Coke can consume Reminder as
   a technical module with a Coke adapter.
2. **HTTP API**: useful when another runtime or deployable service needs to
   call Reminder across process boundaries.
3. **MCP tool adapter**: useful when LLM agents outside Coke should create or
   manage reminders.
4. **CLI**: useful for operators, local testing, and "everything can be CLI"
   workflows, but it should wrap the same contract instead of becoming its own
   implementation.

MCP and CLI are adapters, not the core product.

## Migration Sequence

### Phase 1: Contract Neutralization

- introduce Coke-neutral owner/context/target data shapes
- add Coke adapter mapping current fields into those shapes
- keep existing behavior and storage unchanged where possible
- add contract tests proving current Coke paths use the neutral contract

### Phase 2: Runtime Seams

- define repository interfaces
- define wake-up engine interface
- define fire event and consumer callback interface
- move APScheduler and Mongo behind those seams

### Phase 3: Reliability

- add fire event records and attempts
- add claim, ack, retry, and fail behavior
- add trace and idempotency fields where external writes require them
- verify startup rebuild and failed-event behavior

### Phase 4: External Adapter

- choose one external adapter based on a real consumer
- prefer HTTP if another backend/runtime needs Reminder
- prefer MCP if external LLM agents are the main consumer
- prefer CLI if operator/local-product workflows are the main consumer

## Testing And Verification

Required evidence for implementation work:

- contract tests for Coke adapter mapping
- unit tests for Reminder core that do not import Coke agent runtime modules
- repository tests proving visibility and owner scoping
- scheduler tests proving rebuild from durable state
- fire-event tests proving ack, retry, and fail transitions
- existing Coke reminder tests proving user-visible behavior is unchanged
- bridge/web tests proving management surfaces still hide internal follow-ups
- diff-aware verification through `scripts/suggest-verification` and
  `scripts/review-trigger`

When the first external adapter is added, tests must prove the adapter calls
the Reminder product contract rather than duplicating business rules.

## Open Decisions

These should be answered before implementation planning:

- Is the first physical form still an in-repo module, or should it become an
  installable Python package inside the repo?
- Should the neutral owner model include `tenant_id` immediately, or should it
  remain optional until there is a second consumer?
- Which external adapter has a real first consumer: HTTP, MCP, or CLI?
- How much callback payload is allowed in `context_ref` and `target_ref`?
- Which reliability guarantee is required before exposing external writes?

## Success Criteria

Reminder is a standalone technical product when:

- Coke-specific identity appears only in Coke adapter code
- Reminder core can be understood without reading Coke agent runtime code
- Reminder contract tests run without Coke bridge or Agno dependencies
- scheduler and storage are behind Reminder-owned interfaces
- fired reminders produce a durable event or callback contract
- Coke remains a consumer and passes the same user-visible reminder tests
- a future HTTP, MCP, CLI, or SDK adapter can be added without changing
  Reminder business behavior

