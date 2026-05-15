# Reminder Python Plugin Boundary Design

**Status:** draft for review
**Date:** 2026-05-15
**Owner:** Codex

## Summary

Define the smallest next boundary that lets Reminder behave like an
in-process Python runtime plugin consumed by Coke.

This is a technical-product boundary, not a commercial product plan and not a
plugin framework. Reminder should be separable enough that Coke consumes it
through a small adapter and callback contract, while Reminder keeps its current
runtime behavior and user-visible semantics.

The target shape is:

```text
Coke caller
  -> CokeReminderAdapter
  -> ReminderRuntime
  -> ReminderRuntimeContract / ReminderService
  -> scheduler wake-up
  -> ReminderFireConsumer callback
  -> Coke agent continuation
```

The first phase should not rename every Coke-shaped field. The current
`conversation_id`, `character_id`, `route_key`, and `AgentOutputTarget`
language may remain while Coke is the only consumer. The real first boundary is
dependency direction: Reminder runtime should not own Coke agent continuation.

## Current State

The previous reminder work established an in-process contract:

- `agent/reminder/runtime_contract.py` exposes `ReminderRuntimeContract`
- Agno reminder tooling, PostAnalyze internal follow-up creation, and bridge
  reminder management call the contract instead of each owning reminder
  business behavior
- visible reminders and internal follow-ups share the `reminders` substrate
- future MCP, CLI, and HTTP adapters are intentionally deferred

That is a good contract boundary. It is not yet a plugin boundary:

- Coke callers still instantiate or call `ReminderRuntimeContract` directly
- fire handling is still centered on `ReminderFireEventHandler`, which knows
  Coke conversation locks, conversation lookup, character lookup, Agno runtime
  inputs, and output delivery
- Reminder's first target language is still Coke-shaped, which is acceptable
  for the first plugin phase but should stay out of future public adapters
- there is no single `ReminderRuntime` object that Coke can own and start as a
  capability/plugin

## Decision

Build a **Python object plugin boundary** first.

Do not build:

- a dynamic plugin manager
- a plugin registry
- marketplace-style install or unload behavior
- MCP, CLI, HTTP, or SDK adapters
- a separate repository
- a separate process or service
- a scheduler rewrite
- a neutral owner/context/target model as a phase-one requirement

The first implementation should introduce only the minimum runtime object and
Coke adapter seams needed to separate Reminder ownership from Coke
continuation.

## Why This Boundary Is Necessary

Reminder is a possible standalone technical product only if it can be reasoned
about as a runtime that Coke consumes.

The boundary is necessary because:

- future external adapters should not inherit Coke conversation and route
  internals as public API
- Reminder's core product is not only storing scheduled records; it is firing a
  future event and handing that event back to a consumer
- Coke should own how a fired reminder resumes an agent turn
- Reminder should own reminder lifecycle, scheduling, visibility, and fire
  event semantics

This is not for architectural neatness. It prevents Coke-specific continuation
logic from becoming part of Reminder's technical-product core.

## Non-Goals

- Do not change user-visible reminder behavior.
- Do not change reminder detection or natural-language time parsing.
- Do not replace `ReminderService` as the behavior owner for validation,
  persistence, and lifecycle.
- Do not remove APScheduler in this phase.
- Do not redesign Mongo reminder documents in this phase.
- Do not introduce a generic `ScheduledAction`, `GenericAction`, or
  `execute(payload)` abstraction.
- Do not force `AgentOutputTarget` out of the first phase if doing so only
  renames the current Coke-shaped data.

## Concepts

### ReminderRuntime

`ReminderRuntime` is the in-process object Coke owns as the Reminder plugin.

It should be explicit enough to answer:

- how Reminder starts
- how Reminder stops
- how active jobs are rebuilt
- which contract Coke calls for create/list/update/cancel/complete
- which consumer handles fired reminders

Initial shape:

```python
ReminderRuntime(
    contract: ReminderRuntimeContract,
    scheduler: ReminderScheduler,
    fire_consumer: ReminderFireConsumer,
)
```

The exact constructor may follow existing code structure, but the dependency
direction should be clear: Coke wires the runtime, Reminder does not import
Coke agent runtime modules.

### CokeReminderAdapter

`CokeReminderAdapter` is Coke's translation layer.

It should own Coke-specific concerns:

- extracting `owner_user_id`
- resolving `conversation_id`
- resolving `character_id`
- resolving `route_key`
- constructing the current `AgentOutputTarget`
- deciding which Reminder contract operation to call

Existing Agno tool code, PostAnalyze follow-up creation, and bridge management
may migrate to call this adapter instead of constructing Reminder runtime
dependencies independently.

This adapter can still pass `AgentOutputTarget` in phase one. The point is not
to hide that Coke is currently the only consumer. The point is to put Coke
translation in one place.

### ReminderFireConsumer

`ReminderFireConsumer` is the callback seam from Reminder back to the consumer.

Initial shape:

```python
class ReminderFireConsumer:
    async def handle_fire_event(self, event: ReminderFireEvent) -> ReminderFireResult:
        ...
```

Coke's implementation may delegate to the current `ReminderFireEventHandler`
at first. That keeps behavior stable while making the ownership explicit:

```text
Reminder scheduler
  -> Reminder runtime fire event
  -> CokeReminderFireConsumer
  -> current ReminderFireEventHandler
  -> Coke agent runtime
```

Over time, Coke-specific conversation locking and agent continuation can move
behind the Coke consumer instead of remaining the apparent owner of Reminder
runtime firing.

### ReminderFireEvent

Phase one can reuse the existing event payload shape and `AgentOutputTarget`
fields. A neutral target model is not required yet.

The event boundary should still be explicit:

```text
reminder_id
owner_user_id
title
schedule
agent_output_target
fire_mode
prompt
metadata
scheduled_for
fired_at
```

The event means "Reminder fired." It does not mean "Coke has completed the
agent continuation." Completion still depends on the consumer result.

## Dependency Rule

After the first plugin-boundary implementation:

- `agent/reminder/*` should not import `agent.agno_agent.*`
- `agent/reminder/*` should not import `connector.clawscale_bridge.*`
- Reminder runtime code should not perform Coke conversation lookup
- Reminder runtime code should not acquire Coke conversation locks directly
- Reminder runtime code should not construct Agno `AgentInput`
- Coke-specific continuation should live in a Coke consumer/adapter

The current target fields may remain, but the code that interprets them as
Coke conversation state belongs to Coke.

## Phased Design

### Phase 1: Adapter And Fire Callback Boundary

Goal: create the smallest plugin-shaped boundary without changing product
behavior.

Work:

- introduce `CokeReminderAdapter`
- introduce `ReminderRuntime` as an in-process object
- introduce `ReminderFireConsumer`
- wire the scheduler fire path through the consumer seam
- allow the Coke consumer to delegate to the current `ReminderFireEventHandler`
- keep current `AgentOutputTarget` and reminder document shape
- keep current Agno, PostAnalyze, bridge, and web behavior

Expected result:

```text
Coke code owns Coke context mapping.
Reminder owns reminder runtime lifecycle and fire event production.
Coke consumer owns agent continuation after a reminder fires.
```

### Phase 2: Runtime Seams

Goal: make Reminder easier to package as a reusable runtime module.

Work:

- make scheduler lifecycle explicit on `ReminderRuntime`
- isolate repository construction behind Reminder-owned factories or
  interfaces
- keep Mongo as the first repository implementation
- add tests that import Reminder runtime without importing Agno or bridge code

This phase still does not require external protocols.

### Phase 3: Target Neutralization Only When Needed

Goal: avoid premature renaming while preserving future independence.

Do not rename `AgentOutputTarget` just because the name is Coke-shaped. Rename
or generalize it only when one of these becomes true:

- a second real consumer needs a different target shape
- an MCP, CLI, HTTP, or SDK adapter would otherwise expose Coke internals
- tests prove Reminder core has to understand Coke conversation behavior
- the current name blocks packaging Reminder as a module

When that happens, introduce a neutral target/context model and keep a Coke
mapping adapter. Until then, centralizing Coke mapping is more valuable than
broad model churn.

### Phase 4: External Adapter

Only after the plugin boundary is stable, choose one external adapter based on
a real consumer:

- HTTP if another backend or runtime needs cross-process Reminder calls
- MCP if external LLM agents need Reminder as a tool
- CLI if local/operator workflows are the first independent consumer

Each external adapter must call the same runtime contract. None should own
Reminder business behavior.

## Testing And Verification

Implementation should prove the boundary rather than only proving green tests.

Required evidence:

- unit tests for `CokeReminderAdapter` mapping current Coke context into the
  current Reminder contract
- tests proving Agno reminder creation still calls the same user-visible path
- tests proving PostAnalyze internal follow-up still creates/clears internal
  reminders
- bridge reminder management tests proving visible reminder management is
  unchanged and internal follow-ups stay hidden
- scheduler/fire tests proving fired reminders are handed to a
  `ReminderFireConsumer`
- import-boundary tests or focused assertions proving Reminder core does not
  import Agno or bridge modules
- diff-aware verification with `scripts/suggest-verification` and
  `scripts/review-trigger`

Runtime or user-visible claims still need the appropriate worker, bridge, or
E2E evidence. Structure checks alone are not enough for behavior claims.

## Success Criteria

The first plugin boundary is complete when:

- Coke callers route reminder operations through a Coke-owned adapter or a
  single runtime object
- Reminder firing goes through an explicit consumer seam
- Coke agent continuation is implemented by a Coke consumer, not by Reminder
  core
- current user-visible reminder behavior is unchanged
- current internal follow-up behavior is unchanged
- no MCP, CLI, HTTP, repo split, or plugin framework was introduced
- the remaining Coke-shaped target language is documented as a first-consumer
  compatibility choice, not as the final public contract

## Review Questions

- Is `CokeReminderAdapter` the right name, or should it be scoped to the Agno
  runtime and bridge separately?
- Should `ReminderRuntime` own scheduler boot immediately, or only wrap the
  contract and fire consumer in phase one?
- Should the first fire consumer delegate to `ReminderFireEventHandler`, or
  should `ReminderFireEventHandler` itself become Coke's consumer
  implementation?

