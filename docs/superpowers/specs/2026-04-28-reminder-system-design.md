# Reminder System Design

**Status:** draft for review
**Date:** 2026-04-28
**Supersedes:** the Reminder System portions of the pre-split reminder core
redesign draft, plus the now-merged agent integration spec.

## Summary

Reminder System is the minimum reminder core that powers Coke Phase 1
personal supervision. It directly replaces the reminder portion of the current
`deferred_actions` runtime as a breaking redesign.

The system has two layers in this spec:

1. **Reminder Core** — data model, service, scheduler, chat delivery, and
   storage. Producer-neutral.
2. **Agent Integration** — the only producer in v1. Owns LLM tool schema,
   prompt instructions, and translation between LLM intent and core service
   calls.

HTTP/API, Web UI, and Google Calendar import are explicit non-goals and will
be added under their own future producer sections when each is built.

V1 is a clean replacement, not a compatibility migration. Existing reminder
rows in `deferred_actions` may be dropped during rollout because the system
has not been materially used in production. Proactive follow-up remains a
separate runtime concern until its own redesign replaces it.

## Goals

- Provide a minimum reminder core that powers assistant-created reminders for
  the current single-user supervision product.
- Keep product semantics distinct from process-local scheduler state.
- Use Mongo as the durable source of truth and APScheduler 3.x as the
  in-process timing layer.
- Keep exactly one durable scheduler source: `Reminder.next_fire_at`.
- Keep agent-specific intent detection, tool schema, prompt behavior, and
  response translation in the agent integration layer, so future producers
  (UI, HTTP, calendar import) can reuse the core service unchanged.

## Non-Goals

V1 explicitly defers everything below. Each item stays out of the model until
a real consumer exists; adding any of them later is a forward-only change on
schema-on-read storage.

Producers and surfaces:

- HTTP/API producer
- Web UI producer
- Google Calendar import (would need `time_policy=zoned`, external
  attribution, sanitized event snapshots)

Reminder shape:

- Reminder lists (`ReminderList`, `list_id`, default-list materialization)
- Multiple alert times per reminder (`triggers[]` array, relative/absolute/
  all-day trigger types)
- All-day reminders (`is_all_day`, `all_day_local_time`)
- Zoned schedules (`time_policy=zoned`)
- After-completion recurrence (`recurrence_policy=after_completion`)
- Internal reminders (`visibility=internal`); proactive follow-up is its own
  redesign
- `body`, `priority`, `sort_order`, `metadata` fields on reminders

Delivery and runtime:

- Multi-target delivery (`email`, `push`, `webhook`); v1 ships chat only
- Acknowledgement, dismissal, snooze
- Constant/repeat notifications
- Configurable retry policy
- Floating realignment on user timezone change
- Default reminder policy collection (timed-offset and all-day-local-time
  defaults; v1 always fires at the scheduled instant)
- Optimistic concurrency (`revision`)
- Trigger leases (`lease_token`, `leased_at`, `lease_expires_at`)
- Per-occurrence history table or delivery-attempt table

Migration:

- Reminder data migration from `deferred_actions`

Agent integration:

- Replacement of the two-stage agent flow
- ChatResponseAgent direct reminder writes
- OrchestratorAgent direct reminder creation
- Natural-language parsing inside Reminder System
- Proactive follow-up redesign beyond preserving the existing
  `reminder_created_with_time` suppression behavior

## Architecture Overview

```text
PrepareWorkflow
  -> OrchestratorAgent
  -> ReminderDetectAgent, only when need_reminder_detect=true
  -> visible_reminder_tool wrapper      ── agent integration layer
  -> ReminderService                    ── reminder core layer
       -> Mongo (durable state)
       -> APScheduler (in-process wake-ups)
       -> Chat delivery adapter
  -> session_state.tool_results

ChatWorkflow
  -> reads tool_results and reports actual reminder outcomes

PostAnalyzeWorkflow
  -> skips internal proactive follow-up when a timed reminder was created
```

The layering rule: the agent integration layer is the only producer in v1
and may not hold reminder business rules. The reminder core layer owns
validation, lifecycle, scheduling, and delivery; it does not know about LLM
tool schema or chat-response prose.

---

# Reminder Core

This part of the spec defines the producer-neutral reminder core.

## Domain Model

V1 exposes three dataclasses: `Reminder`, `ReminderSchedule`, and
`ChatDeliveryTarget`. There is no `ReminderList`, `ReminderTrigger`,
`ReminderSource`, `DeliveryTarget`, `ReminderNotificationPolicy`,
`RetryPolicy`, or `DefaultReminderPolicy` in v1.

### Reminder

```python
@dataclass
class Reminder:
    id: str
    owner_user_id: str

    title: str
    schedule: ReminderSchedule
    chat_delivery: ChatDeliveryTarget
    source_type: Literal["user", "assistant", "system"]

    lifecycle_state: Literal["active", "completed", "cancelled", "failed"]

    next_fire_at: datetime | None
    last_fired_at: datetime | None
    last_delivered_at: datetime | None
    last_error: str | None

    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    failed_at: datetime | None
```

`title` is the only user-editable text field on a reminder in v1.
`next_fire_at` is the durable scheduler source. The scheduler runtime never
reads APScheduler state to decide what to fire; it always reads
`next_fire_at`.

### ReminderSchedule

```python
@dataclass
class ReminderSchedule:
    anchor_at: datetime
    local_date: date
    local_time: time
    timezone: str
    rrule: str | None
```

`anchor_at` is the schedule anchor. For one-shot reminders it is the
scheduled time; for recurring reminders it is the recurrence base and may be
in the past. It is timezone-aware at API boundaries and stored as UTC in
Mongo.

`local_date` and `local_time` are the durable wall-clock intent. `timezone`
is always an IANA timezone name. V1 always treats schedules as floating local
time: the scheduler interprets `local_time` in the user's effective timezone
when computing the next fire time.

### ChatDeliveryTarget

```python
@dataclass
class ChatDeliveryTarget:
    conversation_id: str
    character_id: str
    route_key: str | None
```

Chat is the only delivery channel in v1, and its routing parameters live
directly on the reminder. There is no `delivery_targets[]` array and no
opaque `config` dict.

If the chat route cannot be resolved at fire time, the reminder transitions
to `lifecycle_state="failed"` with `last_error` set. There is no retry in v1.

### Source Attribution

V1 stores only `source_type` as a string enum on the reminder. External-source
attribution (`external_id`, `external_key`, `snapshot`, `imported_at`) is
deferred until Google Calendar import or another external producer is built.

## Time And Recurrence Semantics

All API datetimes are timezone-aware. Naive datetimes are rejected.

One-shot schedules:

- `schedule.rrule is None`.
- `schedule.anchor_at` must be in the future for active reminders.
- The first scheduled instant is `schedule.anchor_at`.

Recurring schedules:

- `schedule.rrule` uses the supported RFC 5545 RRULE subset.
- `schedule.anchor_at` may be in the past because it is the recurrence
  anchor.
- The next scheduled instant is the first supported recurrence fire time
  after `now`.
- If there is no future fire time, creation fails with
  `InvalidSchedule(reason="no_future_fire_time")`.
- After successful delivery, the scheduler advances `next_fire_at` to the
  next recurrence fire time and the reminder remains `active`.
- If a recurring reminder has no remaining future fire time, it transitions
  to `lifecycle_state="completed"` and clears `next_fire_at`.

Floating local-time behavior:

- Schedules preserve `local_date` and `local_time` as durable intent.
- `next_fire_at` is computed by interpreting `local_time` on the next fire
  date in the user's effective timezone at compute time.
- V1 does not realign existing `next_fire_at` values when the user changes
  timezone. New reminders use the new timezone; existing recurring reminders
  pick up the new timezone whenever the scheduler next computes
  `next_fire_at` after a delivery.

Supported RRULE subset in v1:

- `FREQ=DAILY`
- `FREQ=WEEKLY` with optional `BYDAY=MO,TU,WE,TH,FR,SA,SU`
- `FREQ=MONTHLY`
- `FREQ=YEARLY`
- modifiers: `COUNT`, `UNTIL`, `INTERVAL`

Rejected in v1:

- `FREQ=HOURLY`, `FREQ=MINUTELY`, `FREQ=SECONDLY`
- `BYHOUR`, `BYMINUTE`, `BYMONTH`, `BYMONTHDAY`, `BYSETPOS`, `BYWEEKNO`,
  `BYYEARDAY`, `WKST`
- `EXDATE`, `RDATE`
- natural-language recurrence strings

## Service API

`ReminderService` is a plain Python service. It has no client runtime
dependency and no response-formatting behavior. It is the single domain
service for v1.

```python
@dataclass
class ReminderCreateInput:
    title: str
    schedule: ReminderSchedule
    chat_delivery: ChatDeliveryTarget
    source_type: Literal["user", "assistant", "system"]


@dataclass
class ReminderPatch:
    title: str | None = None
    schedule: ReminderSchedule | None = None


@dataclass
class ReminderQuery:
    lifecycle_states: list[str] | None = None


@dataclass
class ReminderBatchOperation:
    action: Literal["create", "update", "cancel", "complete", "list"]
    reminder_id: str | None = None
    create: ReminderCreateInput | None = None
    patch: ReminderPatch | None = None
    query: ReminderQuery | None = None


@dataclass
class ReminderBatchResult:
    ok: bool
    action: str
    reminder: Reminder | None
    reminders: list[Reminder] | None
    error: ReminderError | None


class ReminderService:
    def create(self, *, owner_user_id: str,
               input: ReminderCreateInput) -> Reminder: ...

    def update(self, *, reminder_id: str, owner_user_id: str,
               patch: ReminderPatch) -> Reminder: ...

    def cancel(self, *, reminder_id: str, owner_user_id: str) -> Reminder: ...
    def complete(self, *, reminder_id: str, owner_user_id: str) -> Reminder: ...

    def get(self, *, reminder_id: str, owner_user_id: str) -> Reminder: ...
    def list_for_user(self, *, owner_user_id: str,
                      query: ReminderQuery) -> list[Reminder]: ...

    def execute_batch(self, *, owner_user_id: str,
                      operations: list[ReminderBatchOperation]
                      ) -> list[ReminderBatchResult]: ...
```

Rules:

- Producers authenticate outside Reminder System and pass trusted
  `owner_user_id`.
- Producers pass structured schedule and chat delivery data. Reminder System
  rejects naive datetimes, natural-language times, and unsupported RRULE
  strings.
- Ownership is checked on every reminder operation.
- `execute_batch` preserves input order and returns one result per operation.
  A failed operation does not roll back prior successful operations. Later
  operations continue unless their own required selector is missing or
  invalid.
- Keyword resolution (mapping a user-supplied phrase to a reminder id) is a
  producer-side convenience and lives in the producer wrapper, not in
  Reminder System. The service identifies targets by `reminder_id`.

When a second producer is added (HTTP/API, UI, GCal), `ReminderService` may
be wrapped by a producer-facing command service or extended with an explicit
`ReminderCommandContext`. Until then, the agent integration calls
`ReminderService` directly.

## Scheduler Runtime

`ReminderScheduler` uses APScheduler 3.x.

Mongo is the durable source of truth. APScheduler is only an in-process
timing layer that wakes the scheduler loop.

Rules:

- On startup, `ReminderScheduler` scans active reminders with
  `next_fire_at != null` and registers an APScheduler job per reminder it has
  not already registered.
- Each APScheduler job id is `reminder:{reminder_id}`.
- Each job payload contains `reminder_id` and `next_fire_at` so stale
  wake-ups can be detected and rejected.
- When a job fires, the scheduler loop re-reads the reminder from Mongo,
  validates `lifecycle_state="active"` and the stored `next_fire_at` matches
  the wake-up payload, dispatches a chat delivery request, then updates
  `next_fire_at`, lifecycle, and timestamps.
- `create`, `update`, `cancel`, and `complete` ask the scheduler to register,
  replace, or remove its APScheduler job.
- On process restart, runtime jobs are reconstructed from Mongo by the
  startup scan above.
- No APScheduler job store is used.
- APScheduler 4.x is out of scope.

Concurrency and crash safety:

- A single Coke worker process runs `ReminderScheduler` at a time. The
  deployment guarantees this; v1 does not handle multi-worker schedulers.
- Within the process, the scheduler loop holds an asyncio lock keyed on
  `reminder_id` for the fetch → deliver → update sequence so a wake-up
  arriving during startup reconstruction cannot double-fire.
- The post-delivery update is gated by an atomic `findOneAndUpdate` predicate
  on `(_id, next_fire_at, lifecycle_state="active")`. If the predicate does
  not match, the wake-up is dropped without delivery.
- If a worker crashes between successful delivery and the post-delivery
  update, startup reconstruction may re-fire the same instant. The chat
  adapter must tolerate occasional duplicate delivery; v1 does not implement
  per-fire idempotency keys.

After successful delivery:

- One-shot reminders set `lifecycle_state="completed"`,
  `last_delivered_at=now`, and clear `next_fire_at`.
- Recurring reminders advance `next_fire_at` to the next recurrence instant,
  set `last_delivered_at=now`, and remain `active`.
- Recurring reminders with no remaining instant set
  `lifecycle_state="completed"` and clear `next_fire_at`.

After failed delivery:

- The reminder sets `lifecycle_state="failed"`, records `last_error`, and
  clears `next_fire_at`.

## Chat Delivery

The scheduler dispatches `ChatDeliveryRequest` to a single chat adapter:

```python
@dataclass
class ChatDeliveryRequest:
    reminder_id: str
    owner_user_id: str
    title: str
    fire_at: datetime
    chat_delivery: ChatDeliveryTarget
```

The chat adapter resolves the route, respects the conversation/output lock
boundary used by the selected chat route, and writes user-visible output. It
does not call the old deferred-action executor path. It returns success or a
structured failure; Reminder System updates lifecycle state from that result.

## Storage

Single collection: `reminders`.

```text
{
  _id: ObjectId,
  owner_user_id: str,
  title: str,

  schedule: {
    anchor_at: ts,
    local_date: date,
    local_time: time,
    timezone: str,
    rrule: str | null,
  },

  chat_delivery: {
    conversation_id: str,
    character_id: str,
    route_key: str | null,
  },

  source_type: "user" | "assistant" | "system",

  lifecycle_state: "active" | "completed" | "cancelled" | "failed",

  next_fire_at: ts | null,
  last_fired_at: ts | null,
  last_delivered_at: ts | null,
  last_error: str | null,

  created_at: ts,
  updated_at: ts,
  completed_at: ts | null,
  cancelled_at: ts | null,
  failed_at: ts | null,
}
```

Indexes:

- `{owner_user_id: 1, lifecycle_state: 1, created_at: -1}` for owner list views
- `{lifecycle_state: 1, next_fire_at: 1}` for scheduler scans

## Error Model

Core errors are structured and stable:

| error | when |
|---|---|
| `InvalidSchedule` | naive datetime, invalid timezone, past active one-shot, no future recurrence |
| `RRULENotSupported` | unsupported or malformed RRULE |
| `ReminderNotFound` | reminder id does not exist for owner |
| `OwnershipViolation` | owner mismatch |
| `InvalidChatDelivery` | required chat delivery fields missing |
| `InvalidArgument` | generic shape validation |

Each error exposes:

```python
class ReminderError(Exception):
    code: str
    user_message: str
    detail: dict[str, Any]
```

Producer wrappers translate these into surface-specific failures. Reminder
System does not know about client response phrasing or tool result
formatting.

---

# Agent Integration

This part of the spec defines the v1 producer that bridges the existing
two-stage agent flow to `ReminderService`. It is the only producer in v1.

## Ownership Boundary

Reminder Core (above) owns:

- `ReminderService` and its inputs and outputs
- core reminder validation and lifecycle behavior
- floating local-time schedule semantics and the supported RRULE subset
- chat delivery routing and post-delivery state advance
- structured error codes
- ordered partial batch result semantics

Agent Integration (below) owns:

- Orchestrator reminder gate rules
- ReminderDetectAgent instructions
- Agno `visible_reminder_tool` schema and wrapper behavior
- session-state extraction for owner and chat delivery context
- conversion from LLM tool arguments to `ReminderService` calls
- translation of `ReminderService` results into `session_state.tool_results`
- ChatWorkflow context that reports actual reminder tool outcomes
- PostAnalyze suppression of internal follow-up after timed reminder creation
- ReminderDetectAgent and tool-call evaluation corpus and runner

## Runtime Flow

### PrepareWorkflow

`PrepareWorkflow` keeps the existing sequencing:

1. Run OrchestratorAgent.
2. Read `orchestrator.need_reminder_detect`.
3. Run context retrieval, web search, timezone handling, calendar import
   entry surfacing, and URL extraction as today.
4. If `need_reminder_detect=true`, run ReminderDetectAgent.
5. Before running ReminderDetectAgent, set the session-state context consumed
   by the Agno tool wrapper.
6. ReminderDetectAgent either calls `visible_reminder_tool` or stops.
7. Tool wrapper writes structured results to `session_state.tool_results`.

ReminderDetectAgent failure must not fail the main user turn. It should log
the failure and leave ChatWorkflow to continue. If the Orchestrator requested
reminder detection but no tool result exists, ChatWorkflow must use the
existing "reminder not executed" context so the assistant does not claim
success.

### ReminderDetectAgent

ReminderDetectAgent remains the only agent-facing reminder write path in v1.

Rules:

- It may call `visible_reminder_tool`.
- It must not call `ReminderService` or any lower-level reminder service
  directly.
- It must not generate final user-facing prose.
- It must output aware ISO 8601 datetimes for time-bearing create/update
  operations.
- It must output RFC 5545 RRULE strings for recurrence.
- It must use batch when a single user message contains multiple reminder
  operations.
- It must preserve user operation order in batch.
- It should stop without calling the tool when time or target selection is
  too ambiguous to form a structured command.

`tool_call_limit=1` and `stop_after_tool_call=True` remain required.
Multi-step user operations are represented as one `batch` tool call, not
multiple tool calls.

## visible_reminder_tool Wrapper

`visible_reminder_tool` is an Agno wrapper around `ReminderService`.

It accepts LLM-facing arguments for:

- `create`
- `list`
- `update`
- `delete`
- `complete`
- `batch`

The wrapper derives the trusted runtime context from `session_state`:

- `owner_user_id` from the trusted runtime user
- `source_type="assistant"`
- `chat_delivery` from the current chat conversation, character, and route
- the user's effective timezone, used to interpret tool-supplied datetimes

The LLM must not provide owner ids, source types, conversation ids, character
ids, route keys, or timezones. Those values come from trusted runtime
context.

### Tool Argument Contract

```python
def visible_reminder_tool(
    action: str,
    title: str | None = None,
    trigger_at: str | None = None,
    reminder_id: str | None = None,
    keyword: str | None = None,
    new_title: str | None = None,
    new_trigger_at: str | None = None,
    rrule: str | None = None,
    operations: list[dict[str, Any]] | None = None,
) -> str: ...
```

Mapping rules:

- `create` requires `title` and `trigger_at`.
- `trigger_at` and `new_trigger_at` must be aware ISO 8601 datetimes.
- `rrule`, when present, must be an RFC 5545 RRULE string supported by
  Reminder System.
- `delete` maps to `ReminderService.cancel`.
- `complete` maps to `ReminderService.complete`.
- `list` maps to `ReminderService.list_for_user` filtered to active and
  recently completed reminders.
- `batch` maps to `ReminderService.execute_batch` and preserves operation
  order.

Keyword resolution is an agent-integration convenience only. If a user asks
to update, delete, or complete a reminder and the LLM supplies only
`keyword`, the wrapper may resolve it against visible reminders for the
owner. Ambiguous or missing matches become structured tool failures and must
not be guessed by Reminder System.

The wrapper does not accept `body`, `new_body`, `priority`, `sort_order`,
`list_id`, or `delivery_targets`. Those fields were removed from the v1
reminder model.

### Operation Mapping

#### Create

The wrapper builds a `ReminderCreateInput` from tool arguments and runtime
context, then calls `ReminderService.create`.

Fields:

- `title` from the LLM
- `schedule.anchor_at` from the parsed `trigger_at`
- `schedule.local_date`, `schedule.local_time`, `schedule.timezone` derived
  from `trigger_at` interpreted in the user's effective timezone
- `schedule.rrule` from the LLM when provided
- `chat_delivery` from `session_state`
- `source_type="assistant"`

On success, if the created reminder has a future `next_fire_at`, the wrapper
sets:

```python
session_state["reminder_created_with_time"] = True
```

#### Update

Update requires `reminder_id` or successful keyword resolution. The wrapper
builds a `ReminderPatch`:

- `title` updated when `new_title` is provided.
- `schedule` updated when `new_trigger_at` or `rrule` is provided. The
  wrapper recomputes `local_date`, `local_time`, and `timezone` from the
  parsed datetime and the user's effective timezone. If only `rrule` is
  supplied, the wrapper reuses the existing anchor and local intent.

If an update changes the scheduled time and the call succeeds, the wrapper
sets `reminder_created_with_time=True` so PostAnalyze does not also create an
internal proactive follow-up for the same user intent.

#### List

List calls `ReminderService.list_for_user` and returns enough structured data
for ChatWorkflow to answer the user, including title, schedule summary,
lifecycle state, and reminder id when appropriate for follow-up operations.

#### Cancel And Complete

Delete maps to `ReminderService.cancel` because cancellation preserves domain
lifecycle state. Complete maps to `ReminderService.complete`. Both require
`reminder_id` or successful keyword resolution.

#### Batch

Batch preserves the user's requested operation order. The wrapper converts
each flat operation object into a `ReminderBatchOperation` and calls
`ReminderService.execute_batch`.

Rules:

- The wrapper returns one result per operation, in input order.
- Earlier successes remain successful if a later operation fails.
- A failed operation does not make the whole batch look successful.
- If any timed create/update succeeds, set `reminder_created_with_time=True`.

### Tool Results

The wrapper appends normalized tool result records to
`session_state.tool_results`.

Each result should include:

```text
{
  tool_name: "提醒操作",
  ok: bool,
  action: str,
  reminder_id: str | null,
  result_summary: str,
  error_code: str | null,
}
```

`result_summary` is a concise factual summary for ChatWorkflow context. It
may be localized for the current runtime, but it must not include unsupported
claims or generated apologies. ChatResponseAgent owns final user-facing
wording.

For batch, the wrapper may append one aggregate result plus per-operation
details, or append one result per operation. In both cases ChatWorkflow must
be able to distinguish full success, partial success, and full failure.

### Error Translation

The wrapper translates `ReminderError` into stable tool failures.

| Reminder error | Tool behavior |
|---|---|
| `InvalidSchedule` | no write; tell ChatWorkflow the time was invalid or missing |
| `RRULENotSupported` | no write; report unsupported recurrence |
| `ReminderNotFound` | no write; ask user to clarify target |
| `OwnershipViolation` | no write; generic not-found style result |
| `InvalidChatDelivery` | no write; report reminder could not be routed |
| `InvalidArgument` | no write; report malformed request |

The wrapper must not swallow failures as success. ChatWorkflow must be able
to see `ok=false`.

## ChatWorkflow Integration

ChatWorkflow reads `session_state.tool_results` and tells the user what
actually happened.

Rules:

- If a reminder operation succeeded, ChatResponse may confirm the concrete
  operation.
- If a reminder operation failed, ChatResponse should explain the failure and
  ask for the missing clarification when useful.
- If Orchestrator set `need_reminder_detect=true` but no reminder tool result
  is present, ChatWorkflow must include the reminder-not-executed context and
  must not claim a reminder was set.
- ChatResponseAgent must not independently create, update, cancel, or
  complete reminders.

## PostAnalyze Integration

`PostAnalyzeWorkflow` keeps the existing suppression contract:

- If `session_state["reminder_created_with_time"]` is true, skip or clear
  internal proactive follow-up planning for the turn.
- Pure list/delete/complete operations do not set this flag.
- Title-only updates do not set this flag unless they also change a
  scheduled time.
- Partial batch sets this flag when at least one timed create/update
  succeeds.

This contract prevents duplicate follow-up scheduling when the user already
asked for an explicit reminder.

## Prompt Requirements

ReminderDetectAgent instructions must say:

- Use the visible reminder tool only for user-visible reminder operations.
- Do not plan internal proactive follow-ups.
- Resolve local and relative user times into aware ISO 8601 datetimes before
  calling the tool.
- Do not pass natural-language time strings to the tool.
- Use RRULE strings for recurrence.
- Use batch for multiple operations in one user message.
- Preserve operation order in batch.
- Prefer concise titles.
- Stop without tool call when the user intent is too ambiguous to form a
  structured command.

Orchestrator instructions must preserve the current gate:

- Set `need_reminder_detect=true` for reminder/task/alarm/timer intent, user
  personal reminder queries, and context continuation.
- Set it false for unrelated small talk, external-world search, and pure past
  facts.
- Orchestrator must not call `ReminderService` or `visible_reminder_tool` in
  v1.

## Evaluation

The existing reminder operation corpus remains the primary agent-facing
evaluation input. The evaluation path should isolate:

- Orchestrator gate accuracy
- ReminderDetectAgent tool-call accuracy
- operation classification accuracy
- timed create/update accuracy
- batch operation shape and ordering
- false-positive rate on negative cases

The evaluation runner should use a fake `visible_reminder_tool` recorder or a
fake `ReminderService`, not Mongo, scheduler, ChatResponse, PostAnalyze, or
outbound delivery.

The corpus should include:

- explicit timed create
- vague create that should ask for clarification rather than create
- list
- update title
- update time
- cancel/delete
- complete
- recurrence
- batch with all success
- batch with partial failure
- negative non-reminder cases

---

# Acceptance Criteria

## Reminder Core

- The redesigned `Reminder` no longer has top-level `actor`, `upsert_key`,
  `delivery_channel`, `conversation_id`, `character_id`, `dtstart`,
  `timezone`, `rrule`, `expires_at`, `next_run_at`, `last_run_at`,
  `run_count`, or generated-text fields. The new shape uses `schedule`,
  `chat_delivery`, `source_type`, `lifecycle_state`, `next_fire_at`,
  `last_fired_at`, `last_delivered_at`, and `last_error`.
- Core model exposes only `Reminder`, `ReminderSchedule`, and
  `ChatDeliveryTarget`. No `ReminderList`, `ReminderTrigger`,
  `ReminderSource` object, `DeliveryTarget`, `ReminderNotificationPolicy`,
  `RetryPolicy`, or `DefaultReminderPolicy` exists in v1.
- `Reminder.next_fire_at` is the only durable scheduler source.
- The system supports a single floating local-time schedule with optional
  RRULE recurrence and no all-day or zoned variants.
- Chat is the only delivery channel; routing fields live directly on the
  reminder.
- `ReminderService` is the only service; there is no separate
  `ReminderCommandService` in v1.
- `execute_batch` preserves order and returns ordered partial results without
  rolling back prior successes.
- V1 does not migrate existing reminder rows from `deferred_actions`.

## Agent Integration

- Agent flow remains OrchestratorAgent gate followed by ReminderDetectAgent.
- ReminderDetectAgent remains the only agent-facing reminder write path.
- OrchestratorAgent does not call `ReminderService` or
  `visible_reminder_tool` in v1.
- ChatResponseAgent does not directly write reminders.
- `visible_reminder_tool` is an Agno wrapper around `ReminderService`, not a
  holder of reminder business rules.
- `visible_reminder_tool` no longer depends on `DeferredActionService`.
- The wrapper derives owner, source type, and chat delivery context from
  trusted `session_state`, not from LLM arguments.
- The wrapper does not accept `body`, `new_body`, `priority`, `sort_order`,
  `list_id`, or `delivery_targets` arguments.
- Timed create and timed update successes set
  `session_state["reminder_created_with_time"] = True`.
- List, cancel, complete, failed create, and non-time updates do not set
  `reminder_created_with_time`.
- Batch returns ordered partial results and preserves prior successes when
  later operations fail.
- Tool failures are visible to ChatWorkflow as `ok=false`.
- ChatWorkflow must not claim reminder success when
  `need_reminder_detect=true` and no tool result exists.
- PostAnalyze skips or clears internal proactive follow-up when a timed
  reminder was successfully created or rescheduled in the turn.
- ReminderDetectAgent evaluation covers create, list, update, cancel,
  complete, recurrence, batch, ambiguous cases, and negative cases.

# Test Matrix

## Reminder Core

| layer | covers |
|---|---|
| model | default values, field validation, lifecycle timestamps |
| schedule | timezone validation, floating local-time computation, supported RRULE subset, rejected RRULE features |
| service | create, list, update, cancel, complete, ownership checks, ordered batch with partial failure |
| scheduler | startup reconstruction, atomic claim race, post-delivery state advance for one-shot and recurring reminders |
| storage | collection schema, index coverage |
| delivery | chat success path, chat failure marks reminder failed |

## Agent Integration

| layer | covers |
|---|---|
| prompt | Orchestrator gate rules, ReminderDetectAgent ISO/RRULE/batch instructions |
| tool wrapper | argument parsing, session context derivation, service call mapping, error mapping |
| service integration | calls `ReminderService.create/update/cancel/complete/list_for_user/execute_batch` with correct context |
| batch | ordered results, partial failure, timed-success flag behavior |
| ChatWorkflow | tool result context, no-success-claim guard when no tool result exists |
| PostAnalyze | timed create/update suppresses internal proactive follow-up |
| eval | fake tool or fake service, no Mongo/scheduler/outbound dependency |
