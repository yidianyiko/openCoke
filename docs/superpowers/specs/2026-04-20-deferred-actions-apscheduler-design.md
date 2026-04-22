# Deferred Actions APScheduler Design

> Status note (2026-04-22): This design is now implemented. The live runtime
> uses `deferred_actions` for reminder and proactive follow-up scheduling, no
> active worker path reads or writes `conversation_info.future`, and
> `scripts/retire_legacy_reminder_compat.py` performs the remaining one-time
> data cleanup for retired compatibility fields and the legacy `reminders`
> collection.

## Summary

We will replace the current split `future` and `reminder` runtime with a new
clean-break `deferred_actions` system. The new system has one business model,
one scheduling path, one execution path, and no backward compatibility with
existing reminder or future data, prompts, or workflows.

The replacement design keeps MongoDB as the only source of truth and uses one
in-process APScheduler 3.x instance only to wake the worker at the next due
time for each action. Recurrence is stored directly as an `RRULE` string and
evaluated with `python-dateutil`. Internal proactive follow-up actions are
hidden from user-facing management; user reminders are visible and manageable.

## Decision

We will:

- add a new `deferred_actions` collection as the only future-action business
  model
- add a new `deferred_action_occurrences` collection for occurrence claiming,
  retry tracking, and execution audit
- remove `conversation_info.future` from scheduling responsibility
- remove the legacy reminder scheduler and reminder collection from the new
  runtime
- keep MongoDB as the source of truth for lifecycle state, recurrence, and next
  due time
- run exactly one APScheduler 3.x instance inside the single `coke-agent`
  process
- store recurrence directly as an `RRULE` string plus `dtstart` and `timezone`
- use APScheduler only for the next concrete trigger time, not as the business
  state store
- route all triggered actions through a single deferred-action execution
  handler, which must acquire the same conversation turn lock boundary used by
  other system-triggered turns before calling `handle_message()`

We will not:

- support old reminder or future data
- support old prompt schemas, tool contracts, or V1/V2 coexistence
- introduce Temporal
- design for multi-replica scheduler ownership in this version

## Rationale

The current split is a historical implementation artifact, not a valid domain
boundary. Both reminder and future/proactive paths ultimately represent the
same thing: a deferred outbound action targeted at a conversation. The correct
split is not `future` versus `reminder`; it is:

- business state versus runtime trigger state
- user-visible versus internal-only actions
- recurrence definition versus next-fire scheduling

APScheduler 3.x is sufficient because this runtime is explicitly single-process
and does not need multi-replica coordination. The design still avoids making
APScheduler the source of truth so the business model remains queryable,
editable, and auditable in MongoDB.

## Domain Model

### `deferred_actions`

Each document represents one scheduled future action.

```json
{
  "_id": "ObjectId",
  "conversation_id": "string",
  "user_id": "string",
  "character_id": "string",
  "kind": "user_reminder | proactive_followup",
  "source": "user_explicit | llm_inferred | system_policy",
  "visibility": "visible | internal",
  "lifecycle_state": "active | completed | cancelled | failed",
  "revision": 3,
  "title": "string",
  "payload": {
    "prompt": "string",
    "metadata": {}
  },
  "timezone": "Asia/Tokyo",
  "dtstart": "2026-04-20T09:00:00+09:00",
  "rrule": "FREQ=DAILY;BYHOUR=9",
  "next_run_at": "2026-04-21T09:00:00+09:00",
  "last_run_at": "2026-04-20T09:00:00+09:00",
  "run_count": 1,
  "max_runs": null,
  "expires_at": null,
  "retry_policy": {
    "max_attempts_per_occurrence": 3,
    "base_backoff_seconds": 60,
    "max_backoff_seconds": 900
  },
  "lease": {
    "token": null,
    "leased_at": null,
    "lease_expires_at": null
  },
  "last_error": null,
  "created_at": "2026-04-20T08:00:00+09:00",
  "updated_at": "2026-04-20T08:00:00+09:00"
}
```

Required behavior:

- `kind=user_reminder` is user-visible and user-manageable.
- `kind=proactive_followup` is internal-only and excluded from user-facing list,
  update, delete, and complete flows.
- `rrule=null` means one-shot action.
- `next_run_at` is always materialized in MongoDB for `lifecycle_state=active`
  actions.
- every create, update, cancel, completion, retry reschedule, or recurrence
  advance increments `revision`
- `lease` is an execution claim and may never be used as the durable lifecycle
  state.
- `max_runs` ends a recurring action once `run_count` reaches the limit.
- `expires_at` ends a recurring action once the next computed occurrence would
  be later than that timestamp.
- `retry_policy` is filled by the service with kind-specific defaults when the
  caller does not specify one.

Indexes:

- `{lifecycle_state: 1, next_run_at: 1}`
- `{conversation_id: 1, kind: 1, lifecycle_state: 1}`
- `{user_id: 1, visibility: 1, lifecycle_state: 1, next_run_at: 1}`
- partial unique index for active internal follow-up per conversation:
  `{conversation_id: 1, kind: 1, lifecycle_state: 1}` where
  `kind=proactive_followup` and `lifecycle_state=active`

### `deferred_action_occurrences`

Each document records one scheduled occurrence, not one attempt.

```json
{
  "_id": "ObjectId",
  "action_id": "ObjectId",
  "scheduled_for": "2026-04-20T09:00:00+09:00",
  "trigger_key": "action:<id>:2026-04-20T09:00:00+09:00",
  "status": "claimed | succeeded | failed | skipped",
  "attempt_count": 1,
  "last_started_at": "2026-04-20T09:00:01+09:00",
  "last_finished_at": "2026-04-20T09:00:05+09:00",
  "last_error": null
}
```

Required behavior:

- unique index on `trigger_key`
- the execution path must create or claim the occurrence record before calling
  `handle_message()`
- repeated scheduler wakeups for the same action/time become no-ops
- retries for the same scheduled occurrence update `attempt_count` on the same
  occurrence record instead of creating a second record with the same
  `trigger_key`

## Runtime Topology

The single `coke-agent` process contains:

- message workers
- one deferred-action scheduler service
- one APScheduler 3.x instance

The APScheduler instance is process-local and created once during
`agent_runner.py` startup. The scheduler service performs:

1. reconcile stale execution leases from prior crashes
2. load all `active` actions with `next_run_at`
3. register one APScheduler job per action for the next due time
4. accept create/update/delete/reschedule events from the deferred action
   service
5. invoke the deferred-action executor when a job fires

MongoDB remains the only persistent state owner. APScheduler jobs are runtime
cache, not durable business records.

Every APScheduler job must carry:

- `action_id`
- `scheduled_for`
- `revision`

The executor may only claim an action when the fired job still matches the
current MongoDB row for all three values.

## Recurrence Rules

Recurrence is stored directly as an RFC 5545 `RRULE` string without a business
wrapper schema.

Rules:

- `dtstart` is mandatory when `rrule` is present
- recurrence evaluation uses `dateutil.rrule.rrulestr(rrule, dtstart=...)`
- timezone-aware datetimes are required for `dtstart`, `next_run_at`,
  `last_run_at`, and `expires_at`
- after a successful execution, the next run is computed as the first
  occurrence strictly after the effective trigger time
- `alarms` are out of scope in v1 of this reset; a reminder with multiple lead
  times becomes multiple `deferred_actions`

Misfire policy:

- one-shot overdue action: execute once immediately on startup recovery
- recurring overdue action: execute at most once immediately, then coalesce to
  the next occurrence after now
- we do not replay every missed interval after downtime

## Lifecycle

### Create

- explicit reminder parsing creates `kind=user_reminder`
- post-analyze follow-up planning creates or replaces
  `kind=proactive_followup`
- service computes initial `next_run_at`
- service writes Mongo document
- service registers APScheduler job for `next_run_at`
- service stores the job with the current `revision`

### Update

- user-facing update only applies to `visibility=visible`
- internal follow-up updates happen only through the planner
- service updates Mongo first, increments `revision`, then reschedules
  APScheduler

### Cancel / Complete

- user-facing delete/complete only applies to `visibility=visible`
- internal follow-up cancellation happens when planner outputs no follow-up or a
  replacement follow-up
- service updates Mongo state, increments `revision`, then removes scheduler job

### Trigger

- APScheduler fires the process-local job
- executor acquires the conversation turn lock before entering the message
  execution path; if the lock is unavailable, it reschedules a short retry
- executor atomically claims the action lease only if `_id`, `revision`, and
  `next_run_at == scheduled_for` still match the fired job payload
- executor sets `lease.token`, `lease.leased_at`, and `lease.lease_expires_at`
- executor creates or claims the `deferred_action_occurrences` row using the
  `trigger_key`
- executor increments `attempt_count` when retrying an existing failed
  occurrence
- executor builds the system input and calls `handle_message()`
- success path updates `last_run_at`, increments `run_count`, computes the next
  occurrence, and either:
  - sets `lifecycle_state=completed` for one-shot actions
  - sets `lifecycle_state=completed` when `max_runs` or `expires_at` ends the
    recurrence
  - keeps `lifecycle_state=active` and updates `next_run_at` for recurring
    actions that continue
- failure path records `last_error`, clears the action lease, and applies the
  retry policy for the same scheduled occurrence

Retry policy rules:

- retries are occurrence-scoped, not recurrence-scoped
- the original occurrence time remains in
  `deferred_action_occurrences.scheduled_for`
- retry wakeups use the same occurrence record and only increment
  `attempt_count`
- retry backoff is capped exponential backoff based on `retry_policy`
- on retry, the action updates `next_run_at` to the retry time and increments
  `revision`
- once the occurrence reaches its retry ceiling:
  - one-shot actions become `lifecycle_state=failed`
  - recurring actions mark the occurrence failed, clear the lease, and advance
    to the next recurrence after the original `scheduled_for`

## Execution Semantics

Triggered actions use a single message source: `deferred_action`.

Templates and behavior branch on `kind`, not on separate reminder/future
message sources.

Required execution rules:

- `user_reminder` renders as a system-triggered reminder
- `proactive_followup` renders as an internal planned follow-up
- reminder creation and proactive planning may not create duplicate actions for
  the same user intent in the same turn
- if a user turn creates any timed `user_reminder`, the post-analyze planner
  skips proactive follow-up creation for that turn

Internal-only behavior:

- at most one active `proactive_followup` per conversation
- proactive follow-up remains hidden from user query/update/delete flows
- planners may replace the active internal follow-up in place

## Reliability Rules

- MongoDB is the only source of truth
- startup reconciliation must reset any expired action lease before rebuilding
  APScheduler jobs
- APScheduler jobs are rebuilt from MongoDB at process startup
- a stale action lease older than the configured timeout is recoverable
- execution idempotency is enforced by
  `deferred_action_occurrences.trigger_key`
- stale APScheduler jobs may never claim an action after a revision or due-time
  change
- scheduler restart must not require manual repair
- no branch of the system may mutate scheduling state inside
  `conversation_info.future`

## Replacement Scope

The new runtime replaces all of these responsibilities:

- current `conversation_info.future` planning and triggering
- current reminder collection and reminder polling loop
- current split `message_source="future"` and `message_source="reminder"`
  execution paths

The new runtime introduces these replacement units:

- `DeferredActionDAO`
- `DeferredActionService`
- `DeferredActionScheduler`
- `DeferredActionExecutor`
- new prompt/planner contracts for explicit reminders and internal follow-up

## Affected Components

- `agent/runner/agent_runner.py`
- `agent/runner/agent_background_handler.py`
- `agent/runner/agent_handler.py`
- `agent/agno_agent/workflows/prepare_workflow.py`
- `agent/agno_agent/workflows/post_analyze_workflow.py`
- `agent/agno_agent/workflows/chat_workflow_streaming.py`
- `agent/agno_agent/tools/`
- `agent/prompt/`
- `dao/`
- tests covering worker-runtime scheduling and execution

## Verification Strategy

The implementation must prove:

- one-shot reminder create / trigger / complete
- recurring RRULE reminder create / trigger / reschedule
- startup recovery of overdue and future actions
- hidden proactive follow-up creation, replacement, and trigger
- user-facing reminder list/update/delete excludes internal follow-up
- duplicate scheduler wakeup does not produce duplicate outbound execution
- no runtime path reads or writes `conversation_info.future` for scheduling
