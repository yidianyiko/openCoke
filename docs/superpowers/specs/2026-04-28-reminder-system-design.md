# Reminder System Design

**Status:** draft for review
**Date:** 2026-04-28
**Supersedes:** the Reminder System portions of the pre-split reminder core
redesign draft, plus the now-merged agent integration draft.

## Summary

Reminder System is the minimum durable reminder core for Coke Phase 1
personal supervision. It replaces the reminder portion of the current
`deferred_actions` runtime as a breaking redesign.

This spec treats **Reminder System** and **Agent System** as separate systems.
They interact only through structured protocols:

1. **Command protocol, Agent System -> Reminder System**
   - Agent System creates, updates, cancels, completes, and lists reminders
     through a structured command surface.
   - V1 exposes that surface through an MCP-compatible tool adapter used by
     the agent runtime.

2. **Fired-event protocol, Reminder System -> Agent System**
   - Reminder System emits a structured `ReminderFiredEvent` when a reminder is
     due.
   - Agent System consumes the event and owns all user-visible output.

Reminder System owns reminder state, schedule semantics, lifecycle, and the
durable next fire time. Agent System owns natural-language understanding,
target disambiguation, user-visible response wording, chat locks, and final
conversation output.

V1 is a clean replacement, not a compatibility migration. Existing reminder
rows in `deferred_actions` may be dropped during rollout because the system
has not been materially used in production. Proactive follow-up remains a
separate runtime concern until its own redesign replaces it.

## Goals

- Provide a minimum reminder system that powers assistant-created reminders
  for the current single-user supervision product.
- Make Reminder System independent from Agent System internals.
- Let Agent System write reminders through a structured command protocol.
- Let Reminder System fire reminders through a structured event protocol.
- Keep product semantics distinct from process-local scheduler state.
- Use Mongo as the durable source of truth for reminder aggregate state.
- Use APScheduler 3.x only as an in-process wake-up layer.
- Keep exactly one durable scheduler source: `Reminder.next_fire_at`.
- Preserve enough routing context for Agent System to render the future
  reminder in the intended conversation.
- Avoid reminder shadow copies in Agent System.

## Non-Goals

V1 explicitly defers everything below. Each item stays out of the model until
a real consumer exists; adding any of them later is a forward-only change on
schema-on-read storage.

Producers and surfaces:

- Public HTTP/API producer
- Web UI producer
- Google Calendar import
- Direct user access to Reminder System without Agent System mediation
- Multiple Agent System implementations

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
- External-source attribution (`external_id`, `external_key`, `snapshot`,
  `imported_at`)

Delivery and reliability:

- Email, push, webhook, or multi-target delivery
- Reminder System writing chat output directly
- Acknowledgement, dismissal, snooze
- Constant/repeat notifications
- Configurable retry policy
- Durable outbox implementation
- Per-occurrence history table or delivery-attempt table
- Multi-worker scheduler claiming
- Trigger leases (`lease_token`, `leased_at`, `lease_expires_at`)
- Optimistic concurrency (`revision`)
- Exactly-once output

Agent behavior:

- Replacement of the existing OrchestratorAgent -> ReminderDetectAgent flow
- ChatResponseAgent direct reminder writes
- OrchestratorAgent direct reminder creation
- Natural-language parsing inside Reminder System
- Proactive follow-up redesign beyond preserving the existing
  `reminder_created_with_time` suppression behavior

Migration:

- Reminder data migration from `deferred_actions`

## System Architecture

```text
+---------------------------+       command protocol        +---------------------------+
| Agent System             | ---------------------------> | Reminder System           |
|                           |                              |                           |
| - OrchestratorAgent       |                              | - Reminder command port   |
| - ReminderDetectAgent     |                              | - ReminderService         |
| - MCP/tool adapter        |                              | - ReminderScheduler       |
| - ChatResponseAgent       |                              | - Mongo reminders         |
| - conversation locks      |                              | - APScheduler wake-ups    |
| - final chat output       |                              |                           |
|                           | <--------------------------- |                           |
+---------------------------+       fired-event protocol    +---------------------------+
```

Expanded runtime view:

```text
User message
   |
   v
Agent System
   |
   | structured create/update/list/cancel/complete command
   v
Reminder Command Port
   |
   v
ReminderService  <---------->  Mongo.reminders
   |
   | register / replace / remove wake-up
   v
ReminderScheduler  <------->  APScheduler 3.x
   |
   | ReminderFiredEvent
   v
Agent Reminder Event Handler
   |
   | normal agent/chat output pipeline
   v
Conversation output
```

The architecture rule:

- Reminder System never writes chat output directly.
- Reminder System never calls an LLM.
- Agent System never writes Mongo reminder documents directly.
- Agent System does not maintain a separate durable reminder copy.
- Protocol payloads are the only contract between the systems.

## Ownership Boundary

Reminder System owns:

- `Reminder` aggregate state
- schedule validation
- recurrence computation
- lifecycle transitions
- durable `next_fire_at`
- Mongo persistence
- scheduler startup reconstruction
- stale wake-up rejection
- fired-event emission
- structured Reminder errors

Agent System owns:

- natural-language intent detection
- ambiguous user request clarification
- keyword or phrase based target resolution
- MCP/tool argument construction
- current user and conversation context
- final response wording
- conversation/output locking
- channel-specific output behavior
- rendering `ReminderFiredEvent` into a user-visible message
- PostAnalyze suppression after explicit timed reminder creation

Protocol owns:

- command shapes from Agent System to Reminder System
- result shapes from Reminder System to Agent System
- fired-event shape from Reminder System to Agent System
- fire result shape from Agent System back to Reminder System
- stable error codes

## User-Level Association Model

There is no separate "agent reminder" object in V1. The durable Reminder
record is the canonical reminder.

Agent-visible reminder identity is built from four pieces:

1. `owner_user_id`
   - The trusted principal shared by Agent System and Reminder System.
   - Every Reminder command is scoped by this id.
   - Agent System derives it from authenticated runtime context. The LLM never
     supplies it.

2. `reminder_id`
   - The canonical Reminder System id returned from create and list commands.
   - Update, cancel, and complete commands target this id.
   - Agent System may show it internally or keep it in tool result context,
     but ordinary chat output should usually refer to title and time.

3. `agent_output_target`
   - The future output routing hint stored on the reminder.
   - It captures where Agent System should render the fired reminder.
   - It is derived from the current conversation at creation time.

4. `title` and schedule summary
   - The human-facing description used for list results and keyword
     resolution.
   - Keyword resolution is always Agent System behavior. Reminder System only
     accepts canonical ids.

Common flows:

- Create:
  Agent System parses user intent, derives trusted owner/context, calls
  Reminder System, receives `reminder_id`, and uses the returned reminder in
  chat confirmation.

- List:
  Agent System calls Reminder System by `owner_user_id`, receives durable
  reminders, and presents them to the user. There is no local agent reminder
  cache.

- Update/cancel/complete by phrase:
  Agent System lists reminders for the owner, resolves the user phrase to one
  `reminder_id`, then sends a command using that id. If the phrase is
  ambiguous, Agent System asks the user to clarify. Reminder System has no
  search command in V1.

- Fire:
  Reminder System emits `ReminderFiredEvent` containing `reminder_id`,
  `owner_user_id`, title, fire time, and `agent_output_target`. Agent System
  uses that event to write the actual conversation output.

- User changes conversation:
  V1 keeps the original `agent_output_target`. Moving a reminder to another
  conversation is out of scope.

## Domain Model

V1 exposes three core dataclasses: `Reminder`, `ReminderSchedule`, and
`AgentOutputTarget`. There is no `ReminderList`, `ReminderTrigger`,
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
    agent_output_target: AgentOutputTarget
    created_by_system: Literal["agent"]

    lifecycle_state: Literal["active", "completed", "cancelled", "failed"]

    next_fire_at: datetime | None
    last_fired_at: datetime | None
    last_event_ack_at: datetime | None
    last_error: str | None

    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    failed_at: datetime | None
```

`title` is the only user-editable text field on a reminder in v1.
`next_fire_at` is the only durable scheduler source. The scheduler runtime
never reads APScheduler state to decide what to fire; it always reads
`Reminder.next_fire_at` from Mongo.

`last_event_ack_at` means Agent System acknowledged successful handling of a
fired event. Reminder System does not assert that a provider delivered a chat
message to an external app.

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
in the past. It is timezone-aware at protocol boundaries and stored as UTC in
Mongo.

`local_date` and `local_time` are the durable wall-clock intent. `timezone`
is always an IANA timezone name and is the schedule's calculation timezone.
V1 snapshots this value when the reminder is created or rescheduled. User
timezone changes do not affect existing reminders.

Schedule invariants:

- `schedule.anchor_at` is stored as UTC.
- `schedule.local_date` is the start local date. For recurring reminders it
  is the recurrence start date, not each future occurrence date.
- `schedule.anchor_at == schedule.local_date + schedule.local_time`
  interpreted in `schedule.timezone`, converted to UTC.
- `next_fire_at` is not stored inside `ReminderSchedule`. The reminder-level
  `next_fire_at` stores the next concrete UTC instant derived from this
  schedule.

### AgentOutputTarget

```python
@dataclass
class AgentOutputTarget:
    conversation_id: str
    character_id: str
    route_key: str | None
```

This is not a chat delivery adapter. It is protocol routing context telling
Agent System where to render a future `ReminderFiredEvent`.

Field rules:

- `conversation_id` is the Agent System conversation that should receive the
  fired reminder output. It is required.
- `character_id` is the assistant/persona identity that should speak in that
  conversation. It is required.
- `route_key` is an optional Agent System routing hint for the current
  conversation output route. It must be stable enough for Agent System to
  resolve after a worker restart, but Reminder System treats it as opaque.
- Agent System must derive all fields from trusted runtime context and must
  validate that the target belongs to `owner_user_id` before creating or
  rescheduling a reminder.
- The LLM must not provide these fields.
- If Agent System cannot resolve the target when a reminder fires, it returns
  a failed `ReminderFireResult`; Reminder System then marks the reminder
  failed in V1.

### Creation Attribution

V1 stores `created_by_system="agent"`. The field identifies which trusted
system created the reminder, not which human owns it.

External-source attribution is deferred until Google Calendar import or
another external producer is built.

## Command Protocol: Agent System -> Reminder System

Reminder System exposes a structured command port. V1 binds this port through
an MCP-compatible tool adapter in Agent System.

The protocol is structured and reminder-domain oriented. It does not accept
natural language.

```python
@dataclass
class ReminderCreateCommand:
    title: str
    schedule: ReminderSchedule
    agent_output_target: AgentOutputTarget
    created_by_system: Literal["agent"]


@dataclass
class ReminderPatch:
    title: str | None = None
    schedule: ReminderSchedule | None = None


@dataclass
class ReminderQuery:
    lifecycle_states: list[str] | None = None


@dataclass
class ReminderCommand:
    action: Literal["create", "update", "cancel", "complete", "list"]
    reminder_id: str | None = None
    create: ReminderCreateCommand | None = None
    patch: ReminderPatch | None = None
    query: ReminderQuery | None = None


@dataclass
class ReminderCommandEnvelope:
    owner_user_id: str
    command: ReminderCommand


@dataclass
class ReminderBatchCommandEnvelope:
    owner_user_id: str
    commands: list[ReminderCommand]


@dataclass
class ReminderCommandResult:
    ok: bool
    action: str
    reminder: Reminder | None
    reminders: list[Reminder] | None
    error: ReminderError | None
```

Service API:

```python
class ReminderService:
    def create(self, *, owner_user_id: str,
               command: ReminderCreateCommand) -> Reminder: ...

    def update(self, *, reminder_id: str, owner_user_id: str,
               patch: ReminderPatch) -> Reminder: ...

    def cancel(self, *, reminder_id: str, owner_user_id: str) -> Reminder: ...
    def complete(self, *, reminder_id: str, owner_user_id: str) -> Reminder: ...

    def get(self, *, reminder_id: str, owner_user_id: str) -> Reminder: ...
    def list_for_user(self, *, owner_user_id: str,
                      query: ReminderQuery) -> list[Reminder]: ...

    def execute_batch(self, *, owner_user_id: str,
                      commands: list[ReminderCommand]
                      ) -> list[ReminderCommandResult]: ...
```

Rules:

- Agent System authenticates outside Reminder System and sends trusted
  `owner_user_id` in the command envelope.
- `owner_user_id` applies to every operation in a batch envelope. V1 does not
  allow cross-owner batch commands.
- Agent System passes structured schedule and output target data.
- Reminder System rejects naive datetimes, natural-language times, invalid
  timezones, and unsupported RRULE strings.
- Ownership is checked on every reminder operation.
- `execute_batch` preserves input order and returns one result per operation.
- A failed batch operation does not roll back prior successful operations.
- Later batch operations continue unless their own required selector is
  missing or invalid.
- Keyword resolution lives in Agent System. Reminder System identifies update,
  cancel, and complete targets by `reminder_id`.
- `get` is a service helper for trusted code paths and is not a command
  protocol action in V1.
- `search` is not a Reminder System command in V1. Agent System implements
  phrase matching by listing owner-scoped reminders and resolving locally.

## MCP Tool Adapter

The V1 Agent System exposes the command protocol to ReminderDetectAgent
through one MCP-compatible tool adapter.

The LLM-facing schema may stay compact:

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

The adapter derives trusted context:

- `owner_user_id` from authenticated runtime context
- `created_by_system="agent"`
- `agent_output_target` from the current conversation, character, and route
- `schedule.timezone` from the user's then-effective timezone

The LLM must not provide owner ids, creator system, conversation ids,
character ids, route keys, or timezones.

Mapping rules:

- `create` requires `title` and aware ISO 8601 `trigger_at`.
- `trigger_at` and `new_trigger_at` must be aware ISO 8601 datetimes.
- `rrule`, when present, must be an RFC 5545 RRULE string supported by
  Reminder System.
- `delete` is an LLM/tool adapter alias for the canonical `cancel` command
  and maps to `ReminderService.cancel`.
- `complete` maps to `ReminderService.complete`.
- `list` maps to `ReminderService.list_for_user`.
- `batch` maps to `ReminderService.execute_batch` and preserves operation
  order.

Keyword resolution:

- If the LLM supplies only `keyword` for update, cancel, or complete, the tool
  adapter may resolve it against visible reminders for the owner.
- Ambiguous or missing matches become structured tool failures.
- Reminder System never guesses a target from natural language.
- Future UI and HTTP producers should prefer direct `reminder_id` selection.

Tool results written for ChatWorkflow:

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

For batch, the adapter must preserve partial success visibility. ChatWorkflow
must be able to distinguish full success, partial success, and full failure.

Timed create and timed update successes set:

```python
session_state["reminder_created_with_time"] = True
```

List, cancel, complete, failed create, and title-only updates do not set this
flag.

## Fired-Event Protocol: Reminder System -> Agent System

When a reminder reaches `next_fire_at`, Reminder System emits a structured
event to Agent System.

```python
@dataclass
class ReminderFiredEvent:
    event_type: Literal["reminder.fired"]
    event_id: str
    fire_id: str
    reminder_id: str
    owner_user_id: str
    title: str
    fire_at: datetime
    scheduled_for: datetime
    agent_output_target: AgentOutputTarget
```

Field rules:

- `event_id` is unique per emission attempt.
- `fire_id` is deterministic for one scheduled fire, for example
  `{reminder_id}:{scheduled_for.isoformat()}`.
- `scheduled_for` is the stored `next_fire_at` that caused the wake-up.
- `fire_at` is the time Reminder System emitted the event.
- `agent_output_target` is the stored target from the reminder.

Agent System returns:

```python
@dataclass
class ReminderFireResult:
    ok: bool
    fire_id: str
    output_reference: str | None
    error_code: str | None
    error_message: str | None
```

Semantics:

- `ok=True` means Agent System accepted and handled the event through its
  output pipeline.
- `ok=False` means Agent System could not render the reminder. V1 treats this
  as terminal reminder failure.
- Reminder System does not inspect or generate final chat prose.
- Reminder System may store `output_reference` in logs, but V1 does not store
  it on the reminder model.

V1 transport:

- The event may be delivered through an in-process function call from
  `ReminderScheduler` to an Agent event handler.
- The function call is still treated as a protocol boundary.
- Future transports may be webhook, queue, durable outbox, or another MCP-like
  event channel without changing the Reminder domain model.

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
- When a job fires, the scheduler re-reads the reminder from Mongo and
  validates `lifecycle_state="active"` and stored `next_fire_at` matching the
  wake-up payload.
- The scheduler emits `ReminderFiredEvent` to Agent System.
- The scheduler updates `next_fire_at`, lifecycle, and timestamps based on
  `ReminderFireResult`.
- `create`, `update`, `cancel`, and `complete` ask the scheduler to register,
  replace, or remove its APScheduler job.
- On process restart, runtime jobs are reconstructed from Mongo by the
  startup scan.
- No APScheduler job store is used.
- APScheduler 4.x is out of scope.

Concurrency and crash safety:

- A single Coke worker process runs `ReminderScheduler` at a time. Deployment
  guarantees this; v1 does not handle multi-worker schedulers.
- Within the process, the scheduler loop holds an asyncio lock keyed on
  `reminder_id` for the fetch -> emit -> update sequence.
- The post-event update is gated by an atomic `findOneAndUpdate` predicate on
  `(_id, next_fire_at, lifecycle_state="active")`.
- If the predicate does not match, the wake-up is dropped without emitting a
  new event.
- If a worker crashes after Agent System outputs the reminder but before
  Reminder System persists the post-event update, startup reconstruction may
  re-emit the same `fire_id`.
- Agent System should treat `fire_id` as the idempotency key when it has a
  local output ledger. V1 does not require a durable idempotency ledger.

After successful event handling:

- One-shot reminders set `lifecycle_state="completed"`,
  `last_fired_at=scheduled_for`, `last_event_ack_at=now`,
  `completed_at=now`, and clear `next_fire_at`.
- Recurring reminders advance `next_fire_at` to the next recurrence instant,
  set `last_fired_at=scheduled_for` and `last_event_ack_at=now`, and remain
  `active`.
- Recurring reminders with no remaining instant set
  `lifecycle_state="completed"`, `last_fired_at=scheduled_for`,
  `last_event_ack_at=now`, `completed_at=now`, and clear `next_fire_at`.

After failed event handling:

- The reminder sets `lifecycle_state="failed"`,
  `last_fired_at=scheduled_for`, `failed_at=now`, records `last_error`, and
  clears `next_fire_at`.

Lifecycle transitions:

| event | from | to | timestamp updates | scheduler effect |
|---|---|---|---|---|
| create one-shot | none | `active` | `created_at=updated_at=now`; terminal timestamps null | set `next_fire_at=anchor_at` |
| create recurring | none | `active` | `created_at=updated_at=now`; terminal timestamps null | set `next_fire_at` to first future recurrence |
| reschedule active | `active` | `active` | `updated_at=now`; preserve fire history | replace `next_fire_at` |
| cancel | `active` | `cancelled` | `updated_at=cancelled_at=now` | clear `next_fire_at` |
| manual complete | `active` | `completed` | `updated_at=completed_at=now` | clear `next_fire_at` |
| one-shot event acked | `active` | `completed` | `updated_at=completed_at=last_event_ack_at=now`; `last_fired_at=scheduled_for` | clear `next_fire_at` |
| recurring event acked with next instant | `active` | `active` | `updated_at=last_event_ack_at=now`; `last_fired_at=scheduled_for` | replace `next_fire_at` |
| recurring event acked with no next instant | `active` | `completed` | `updated_at=completed_at=last_event_ack_at=now`; `last_fired_at=scheduled_for` | clear `next_fire_at` |
| event failed | `active` | `failed` | `updated_at=failed_at=now`; `last_fired_at=scheduled_for`; set `last_error` | clear `next_fire_at` |

## Time And Recurrence Semantics

All protocol datetimes are timezone-aware. Naive datetimes are rejected.

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
- After successful event handling, the scheduler advances `next_fire_at` to
  the next recurrence fire time and the reminder remains `active`.
- If a recurring reminder has no remaining future fire time, it transitions
  to `lifecycle_state="completed"` and clears `next_fire_at`.

Floating local-time behavior:

- Schedules preserve `local_date` and `local_time` as durable intent.
- `next_fire_at` is computed by interpreting `local_time` on the next fire
  date in `schedule.timezone`.
- V1 does not realign existing `next_fire_at` values when the user changes
  timezone.
- New reminders snapshot the user's then-effective timezone into
  `schedule.timezone`.
- Existing reminders continue using their stored `schedule.timezone`.

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

## Agent System Runtime Flow

### User Turn

Agent System keeps the existing sequencing:

1. Run OrchestratorAgent.
2. Read `orchestrator.need_reminder_detect`.
3. Run context retrieval, web search, timezone handling, calendar import
   entry surfacing, and URL extraction as today.
4. If `need_reminder_detect=true`, run ReminderDetectAgent.
5. Before running ReminderDetectAgent, set the trusted session-state context
   consumed by the MCP/tool adapter.
6. ReminderDetectAgent either calls `visible_reminder_tool` or stops.
7. The tool adapter sends structured commands to Reminder System.
8. The tool adapter writes structured results to `session_state.tool_results`.
9. ChatWorkflow reads tool results and reports what actually happened.

ReminderDetectAgent failure must not fail the main user turn. It should log
the failure and leave ChatWorkflow to continue. If Orchestrator requested
reminder detection but no tool result exists, ChatWorkflow must use the
existing "reminder not executed" context so the assistant does not claim
success.

### ReminderDetectAgent

ReminderDetectAgent remains the only agent-facing reminder write path in v1.

Rules:

- It may call `visible_reminder_tool`.
- It must not call `ReminderService` directly.
- It must not generate final user-facing prose.
- It must output aware ISO 8601 datetimes for time-bearing create/update
  operations.
- It must output RFC 5545 RRULE strings for recurrence.
- It must use batch when a single user message contains multiple reminder
  operations.
- It must preserve user operation order in batch.
- It should stop without calling the tool when time or target selection is too
  ambiguous to form a structured command.

`tool_call_limit=1` and `stop_after_tool_call=True` remain required.
Multi-step user operations are represented as one `batch` tool call, not
multiple tool calls.

### Fired Reminder Output

When Agent System receives `ReminderFiredEvent`, it owns the final output
flow:

1. Resolve `agent_output_target`.
2. Acquire the normal conversation/output lock boundary.
3. Construct a user-visible reminder message from the event.
4. Write output through the existing agent/chat output pipeline.
5. Return `ReminderFireResult`.

Agent System may use a deterministic, template-like output for V1. It does
not need to run a general LLM turn unless product behavior requires it.

The fired reminder path should not call the old deferred-action executor path.
It should enter the same output safety boundary used by normal agent output.

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

  agent_output_target: {
    conversation_id: str,
    character_id: str,
    route_key: str | null,
  },

  created_by_system: "agent",

  lifecycle_state: "active" | "completed" | "cancelled" | "failed",

  next_fire_at: ts | null,
  last_fired_at: ts | null,
  last_event_ack_at: ts | null,
  last_error: str | null,

  created_at: ts,
  updated_at: ts,
  completed_at: ts | null,
  cancelled_at: ts | null,
  failed_at: ts | null,
}
```

Indexes:

- `{owner_user_id: 1, lifecycle_state: 1, created_at: -1}` for owner list
  views
- `{lifecycle_state: 1, next_fire_at: 1}` for scheduler scans

Storage rules:

- Reminder System is the only writer of `reminders`.
- Agent System must not write reminder documents directly.
- All schedule invariants are enforced before persistence and on update.
- Mongo stores aggregate state, not a durable queue or scheduler job store.

## Error Model

Core Reminder errors are structured and stable:

| error | when |
|---|---|
| `InvalidSchedule` | naive datetime, invalid timezone, past active one-shot, no future recurrence |
| `RRULENotSupported` | unsupported or malformed RRULE |
| `ReminderNotFound` | reminder id does not exist for owner |
| `OwnershipViolation` | owner mismatch |
| `InvalidOutputTarget` | required agent output target fields missing |
| `InvalidArgument` | generic shape validation |
| `ReminderFireFailed` | Agent System returned failed fire result |

`ReminderFireFailed` is emitted from the fired-event path, not from the
LLM-facing command tool path.

Each error exposes:

```python
class ReminderError(Exception):
    code: str
    user_message: str
    detail: dict[str, Any]
```

Agent System translates Reminder errors into surface-specific tool failures
and final user-facing wording. Reminder System does not know about client
response phrasing.

Required tool error mapping:

| Reminder error | Agent tool behavior |
|---|---|
| `InvalidSchedule` | no write; tell ChatWorkflow the time was invalid or missing |
| `RRULENotSupported` | no write; report unsupported recurrence |
| `ReminderNotFound` | no write; ask user to clarify target |
| `OwnershipViolation` | no write; generic not-found style result |
| `InvalidOutputTarget` | no write; report reminder could not be routed |
| `InvalidArgument` | no write; report malformed request |

The tool adapter must not swallow failures as success. ChatWorkflow must be
able to see `ok=false`.

## Operational Behavior

Startup:

- Reminder System reconstructs APScheduler jobs from active Mongo reminders.
- Agent System does not need to replay reminder state on startup.
- If Agent System is unavailable, fired events fail in V1 and reminders become
  failed.

Restart:

- APScheduler jobs are disposable.
- Mongo `next_fire_at` reconstructs runtime state.
- A crash after Agent output but before Reminder state update may cause
  duplicate event emission for the same `fire_id`.

Observability:

- Log command attempts and results by `owner_user_id`, `reminder_id`, and
  action.
- Log fired-event attempts by `fire_id`, `reminder_id`, `scheduled_for`, and
  result.
- Do not log raw user secrets or provider credentials.

Security:

- The LLM cannot choose `owner_user_id`.
- The LLM cannot choose `agent_output_target`.
- Reminder commands are scoped to the authenticated owner.
- Ownership mismatch should return not-found style behavior to Agent System.

## Acceptance Criteria

### System Boundary

- The spec describes Reminder System and Agent System as separate systems.
- Reminder System exposes a structured command protocol to Agent System.
- Reminder System emits structured `ReminderFiredEvent` objects to Agent
  System.
- Reminder System never writes chat output directly.
- Agent System owns all user-visible chat output.
- Agent System never writes Mongo reminder documents directly.
- Protocol payloads define the boundary between systems.

### Reminder Core

- The redesigned `Reminder` no longer has top-level `actor`, `upsert_key`,
  `delivery_channel`, `conversation_id`, `character_id`, `dtstart`,
  `timezone`, `rrule`, `expires_at`, `next_run_at`, `last_run_at`,
  `run_count`, or generated-text fields.
- The new shape uses `schedule`, `agent_output_target`, `created_by_system`,
  `lifecycle_state`, `next_fire_at`, `last_fired_at`,
  `last_event_ack_at`, and `last_error`.
- Core model exposes only `Reminder`, `ReminderSchedule`, and
  `AgentOutputTarget`.
- `Reminder.next_fire_at` is the only durable scheduler source.
- The system supports a single floating local-time schedule with optional
  RRULE recurrence and no all-day or zoned variants.
- `ReminderService` is the only domain service.
- `execute_batch` preserves order and returns ordered partial results without
  rolling back prior successes.
- V1 does not migrate existing reminder rows from `deferred_actions`.

### Agent Integration

- Agent flow remains OrchestratorAgent gate followed by ReminderDetectAgent.
- ReminderDetectAgent remains the only agent-facing reminder write path.
- OrchestratorAgent does not call `ReminderService` or
  `visible_reminder_tool` in v1.
- ChatResponseAgent does not directly write reminders.
- `visible_reminder_tool` is an MCP-compatible adapter over the Reminder
  command protocol, not a holder of reminder business rules.
- The adapter derives owner, creator system, output target, and schedule
  timezone from trusted runtime context, not from LLM arguments.
- The adapter does not accept `body`, `new_body`, `priority`, `sort_order`,
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
- Fired reminders are rendered by Agent System from `ReminderFiredEvent`.

## Test Matrix

### Reminder System

| layer | covers |
|---|---|
| model | field validation, schedule invariant, lifecycle timestamps |
| schedule | timezone validation, floating local-time computation, supported RRULE subset, rejected RRULE features |
| command protocol | create, list, update, cancel, complete, ownership checks, ordered batch with partial failure |
| scheduler | startup reconstruction, stale wake-up rejection, atomic post-event update, one-shot and recurring state advance |
| fired-event protocol | event payload shape, deterministic `fire_id`, success and failure result handling |
| storage | collection schema, index coverage, no Agent direct writes |

### Agent System

| layer | covers |
|---|---|
| prompt | Orchestrator gate rules, ReminderDetectAgent ISO/RRULE/batch instructions |
| MCP/tool adapter | argument parsing, trusted context derivation, command mapping, error mapping |
| association | owner-scoped list, keyword-to-id resolution, ambiguous target failure |
| batch | ordered results, partial failure, timed-success flag behavior |
| ChatWorkflow | tool result context, no-success-claim guard when no tool result exists |
| fired output | event target resolution, output lock usage, `ReminderFireResult` success/failure |
| PostAnalyze | timed create/update suppresses internal proactive follow-up |
| eval | fake tool or fake Reminder command port, no Mongo/scheduler/outbound dependency |
