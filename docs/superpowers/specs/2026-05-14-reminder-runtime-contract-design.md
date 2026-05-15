# Reminder Runtime Contract Design

**Status:** implemented as in-process contract facade
**Date:** 2026-05-14
**Owner:** Codex
**Reviewed against code:** 2026-05-15

## Summary

Define a stable Reminder Runtime Contract after internal follow-up is unified
into the Reminder System.

The first implementation keeps Reminder in-process and routes current Agno,
PostAnalyze, and bridge/web management adapters through
`agent/reminder/runtime_contract.py`.

The contract turns Reminder from a Coke-internal feature into an
agent-facing domain runtime:

```text
at a future time, bring something back into a context
```

This is the first concrete application of
`docs/design-docs/agent-capability-contract.md`. The goal is not to implement
MCP, CLI, a new scheduler, or an independent service yet. The goal is to make
the Reminder boundary clean enough that Agno tools, bridge HTTP routes, future
MCP tools, future CLI commands, and the web board can all call the same domain
contract instead of owning separate reminder behavior.

This spec depends on the implementation of
`docs/superpowers/specs/2026-05-13-internal-followup-reminder-unification-design.md`.
It has been rechecked against the post-unification code shape where internal
follow-up lives in `reminders`, but it still needs human review before an
execution plan is written.

## Problem

Reminder currently has multiple entrypoints:

- the single-Agent runtime calls the `reminder_intent` tool wrapper
- `ReminderIntentPort` uses reminder detection and then executes
  `visible_reminder_tool.entrypoint`
- the customer web board calls gateway `/api/customer/reminders`
- gateway calls bridge `/bridge/internal/reminders`
- bridge calls `ReminderManagementService`
- the scheduler fires reminders through `ReminderFireEventHandler`

These paths are close to a capability boundary, but the contract is still
implicit. Some behavior lives in adapters, some in `ReminderService`, and some
in the fire handler. Future MCP or CLI work would risk exposing this internal
shape unless the Reminder Runtime Contract is made explicit first.

The immediate prerequisite is now met in code: visible reminders and internal
agent follow-ups both live in `reminders`, distinguished by origin, visibility,
and fire mode. The old `deferred_actions.kind=proactive_followup` runtime path
has been retired. The remaining work is to make the runtime contract explicit
so future adapters do not reintroduce split behavior.

## Design Goal

Create a domain contract that can be used by all reminder producers and
consumers:

```text
Agent / Web / HTTP / MCP / CLI
  -> adapter
  -> Reminder Runtime Contract
  -> Reminder runtime core
  -> Mongo, scheduler, fire handler, delivery callback
```

The contract should be usable in-process first. It does not require extracting
Reminder into a separate process or service.

## Non-Goals

- Do not implement MCP, CLI, or new public APIs in this design.
- Do not introduce a generic `ScheduledAction`, `GenericAction`, or workflow
  engine abstraction.
- Do not redesign reminder intent detection.
- Do not add goal, task, milestone, blocker, or progress-tracking models.
- Do not replace APScheduler or implement multi-worker claiming in this step.
- Do not preserve long-lived compatibility for legacy reminder rows missing
  required post-unification fields.
- Do not expose internal follow-ups in user-facing reminder management.

## Approaches Considered

### A. Adapter-First

Expose MCP or CLI directly on top of the current ReminderService and bridge
routes.

Pros:

- fastest demo path
- proves external agent interest quickly

Cons:

- leaks Coke-specific conversation and route details
- duplicates behavior across adapters
- forces future cleanup through public surfaces
- risks preserving the current internal/proactive split

### B. Durable-Runtime-First

Start by replacing the scheduler with outbox, claim, retry, and fire-attempt
records.

Pros:

- addresses production reliability directly
- prepares for multiple workers and external customers

Cons:

- too much infrastructure before the contract is clear
- risks becoming a generic workflow engine
- delays the simpler boundary cleanup needed by MCP/CLI/API work

### C. Contract-First

Define the Reminder Runtime Contract in code and docs, keep the runtime
in-process, and migrate existing adapters to call it.

Pros:

- clarifies ownership before adding new surfaces
- keeps current Coke behavior stable
- makes MCP, CLI, HTTP, and web adapters straightforward later
- fits the agent capability contract rule

Cons:

- does not by itself improve scheduler durability
- still needs an execution plan before code changes start

Recommendation: use Contract-First.

## Contract Concepts

### Reminder

A reminder is a durable future re-entry into a context.

Required post-unification fields:

```text
id
owner_user_id
title
schedule
target
origin: user | agent | web
visibility: visible | internal
fire_mode: notify | followup
prompt: string | null
metadata: object
lifecycle_state: active | completed | cancelled | failed
next_fire_at
last_fired_at
last_event_ack_at
last_error
created_at
updated_at
completed_at
cancelled_at
failed_at
```

`origin`, `visibility`, and `fire_mode` are contract fields, not adapter-local
metadata. They determine which callers may see or mutate a reminder and how a
fire event is handled.

Current implementation note: visible reminder creation writes `origin=user`
even when the adapter is the customer web board. `origin=web` exists in the
model type but should not be treated as an implemented product distinction
until a dedicated command or origin-selection rule exists.

`origin=api` is reserved for a future external API decision. It is not part of
the first contract while external APIs do not exist.

### Target

The first contract target should keep the current Coke conversation target:

```text
conversation_id
character_id
route_key
```

This is enough for Coke and should remain the only target required in the
first contract. Future target types, such as webhook callback or external
agent callback, should be added only after the Coke contract is stable.

### Schedule

The contract accepts structured schedule data only:

```text
anchor_at
local_date
local_time
timezone
rrule
```

Natural language time parsing stays outside the Reminder Runtime Contract.
Agent-facing adapters may resolve natural language into a structured schedule,
but the runtime contract does not parse vague time strings.

### Visibility

`visible` reminders are user-facing. They can be listed and mutated by the
visible reminder tool and customer reminder management API.

`internal` reminders are agent/runtime-facing. They are not shown in
`/account/reminders`, not returned by visible reminder list operations, and not
mutable by user-facing reminder CRUD unless a future product decision changes
that boundary.

### Fire Mode

`notify` means the reminder should produce normal visible reminder wording.

`followup` means the reminder should re-enter the normal agent turn using the
stored `prompt`. The user sees only the final generated Coke message, not
technical reminder wording.

## Contract Operations

### Create Visible Reminder

Creates a durable user-visible reminder.

Inputs:

```text
owner_user_id
title
schedule
target
idempotency_key optional
trace_id optional
```

Rules:

- first-contract visible creation sets `origin=user`, `visibility=visible`,
  `fire_mode=notify`, `prompt=null`, and `metadata={}`
- one-shot active reminders must schedule a future `next_fire_at`
- RRULE is allowed only through the existing visible reminder schedule subset
- repeated create with the same idempotency key should return the same durable
  result once idempotency storage exists; before that storage exists, adapters
  must not claim idempotent external writes

### Create Or Replace Internal Follow-Up

Creates or replaces the one active internal follow-up for an owner and
conversation.

Inputs:

```text
owner_user_id
conversation_id
character_id
route_key
title
prompt
schedule
metadata
trace_id optional
```

Rules:

- at most one active internal follow-up exists per owner and conversation
- created reminders use `origin=agent`, `visibility=internal`, and
  `fire_mode=followup`
- `prompt` must be non-empty
- RRULE is rejected in the first internal follow-up contract
- replacement updates title, prompt, schedule, `next_fire_at`, metadata, and
  timestamps
- replacement must not create a parallel deferred-action row
- clearing a timed user reminder in the same turn should cancel the active
  internal follow-up through this contract

### Update Reminder

Updates a visible reminder by id.

Inputs:

```text
owner_user_id
reminder_id
patch.title optional
patch.schedule optional
trace_id optional
```

Rules:

- default user-facing update scope is `visibility=visible`
- internal reminders are not mutated through visible update paths
- schedule updates recompute `next_fire_at` and reschedule the job

### Cancel Reminder

Cancels an active reminder.

Inputs:

```text
owner_user_id
reminder_id
visibility_scope
trace_id optional
```

Rules:

- visible cancel paths use `visibility_scope=visible`
- internal clear paths use `visibility_scope=internal`
- cancel sets `lifecycle_state=cancelled`, clears `next_fire_at`, and removes
  the scheduler job

### Complete Reminder

Completes an active visible reminder.

Inputs:

```text
owner_user_id
reminder_id
trace_id optional
```

Rules:

- user-facing complete paths use `visibility=visible`
- completing internal follow-ups manually is out of scope for the first
  contract

### List Reminders

Lists reminders for an owner.

Inputs:

```text
owner_user_id
visibility
lifecycle_states
date_range optional
trace_id optional
```

Rules:

- user-facing list operations request `visibility=visible`
- internal follow-up lookup requests `visibility=internal` and
  `fire_mode=followup`
- missing `visibility` rows are legacy data and are not treated as visible by
  this contract

### Fire Reminder

Handles a scheduler fire event for an active reminder and expected
`next_fire_at`.

Inputs:

```text
reminder_id
expected_next_fire_at
fire_id
trace_id optional
```

Rules:

- re-read the reminder from storage before firing
- drop stale fire attempts when stored `next_fire_at` no longer matches
- branch by `fire_mode`
- `notify` uses existing visible reminder output behavior
- `followup` re-enters the normal agent turn with `prompt`
- successful one-shot fires complete the reminder
- successful recurring visible reminder fires advance `next_fire_at`
- failed fires mark the reminder failed and do not fall back to
  `deferred_actions`

## Adapter Mapping

### Agno Tool Adapter

Current path:

```text
reminder_intent tool wrapper
  -> ReminderIntentPort
  -> reminder detector
  -> ReminderCommandExecutor
  -> visible reminder adapter
  -> Reminder Runtime Contract
```

The model-facing tool remains small. It should not expose scheduler, Mongo,
visibility-internal, or fire-handler details. It should receive structured
success and error results.

Current implementation note: the Agno path still uses `ReminderIntentPort` and
`ReminderCommandExecutor` as the adapter boundary. Contract work should avoid
changing reminder intent detection behavior unless a separate spec requires it.

### PostAnalyze Follow-Up Adapter

PostAnalyze now calls internal follow-up methods on the Reminder runtime:

```text
FollowupPlan
  -> create_or_replace_internal_followup
  -> clear_internal_followup
```

It must not construct `DeferredActionService` for proactive follow-up.

### Bridge HTTP Adapter

Bridge `/bridge/internal/reminders` should authenticate trusted gateway calls,
validate request shape, and call the contract. It should not contain reminder
business behavior beyond transport validation and error mapping.

### Gateway Customer API Adapter

Gateway `/api/customer/reminders` should authenticate the customer, derive the
customer id from the session, validate request JSON, and call the bridge or
runtime contract. It must not trust caller-supplied owner ids.

### Web Board Adapter

`/account/reminders` should render and mutate visible reminders only. It is a
human management surface over the visible subset of the contract.

### Future MCP Adapter

A future MCP server may expose tool schemas for create, list, cancel, and
update, but it must call the same contract. It should not expose internal
follow-up operations until there is a product decision about agent-authored
hidden follow-ups outside Coke.

### Future CLI Adapter

A future CLI may parse flags and print structured output, but it must call the
same contract. CLI output should support JSON mode before it is treated as
agent-friendly.

## Error Taxonomy

The contract should return structured errors. Suggested first set:

```text
InvalidArgument
InvalidSchedule
InvalidOutputTarget
PermissionDenied
ReminderNotFound
Conflict
SchedulerHookFailed
ReminderFireFailed
```

Adapters may translate these to surface-specific HTTP status codes, tool
messages, CLI exit codes, or MCP tool errors. The domain error code should
remain stable.

## Idempotency And Trace

The contract should accept `trace_id` before all adapters are ready to use it.
It should appear in logs and fire attempts where practical.

External idempotency is desirable but should be staged:

1. define `idempotency_key` in contract request shapes
2. ensure adapters can pass it through
3. add storage-backed idempotency records before claiming external retry-safe
   writes

Until step 3 exists, HTTP, MCP, and CLI adapters must not advertise exactly-once
or retry-safe create semantics.

## Sequencing

This design should be implemented only after internal follow-up unification is
complete and verified.

Recommended sequence after unification:

1. Review the unification diff against this spec.
2. Rename or introduce a contract-facing service boundary without changing
   user-visible behavior.
3. Move adapter-owned business rules into the contract layer where needed.
4. Add focused contract tests for visible and internal reminder operations.
5. Update bridge and Agno adapters to call the contract explicitly.
6. Only then design MCP or CLI adapters.

## Validation Expectations

Minimum design-time checks before implementation planning:

- current visible reminder create/list/update/cancel/complete maps cleanly to
  the contract
- internal follow-up create/replace/clear maps cleanly to the contract
- fire handling can branch by `fire_mode`
- customer management cannot see internal reminders
- no contract operation depends on `deferred_actions.kind=proactive_followup`
- no adapter owns reminder behavior that should be contract-owned

Minimum implementation-time tests should include:

- contract tests for visible reminder CRUD
- contract tests for internal follow-up create/replace/clear
- contract tests proving missing-visibility legacy rows are excluded
- fire handler tests for `notify` and `followup`
- bridge tests proving owner scope is derived from trusted auth
- gateway tests proving caller-supplied owner ids are ignored
- web tests proving internal reminders are not rendered

Run diff-aware verification after implementation planning:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

## Open Questions

- Should visible web-created reminders continue to store `origin=user`, or
  should a later contract revision introduce a real `origin=web` distinction?
- Should `origin=api` be allowed in a later external API contract, or should
  API-created reminders use one of the existing origins until external APIs
  exist?
- Should the first contract expose internal follow-up operations only to
  in-process Coke code, or also to trusted bridge routes?
- Should `trace_id` be required for fire handling even if it is optional for
  user-facing CRUD?
- Is `target` intentionally Coke-conversation-only for the first contract, or
  should the contract reserve a target `kind` field now?
- Should idempotency storage be included in the first implementation plan, or
  deferred until MCP/CLI/API external writes exist?

## Review Gate

Before this design becomes an implementation plan, review the open questions
and decide whether the first implementation should only rename/extract the
current service boundary or also introduce request/response envelope types for
the contract.
