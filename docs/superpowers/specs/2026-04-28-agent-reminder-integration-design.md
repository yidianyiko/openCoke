# Agent Reminder Integration Design

**Status:** draft for review
**Date:** 2026-04-28
**Depends on:** `docs/superpowers/specs/2026-04-28-reminder-system-design.md`

## Summary

Agent Reminder Integration connects the existing two-stage agent flow to the
new Reminder System service. It keeps reminder product semantics in Reminder
System and keeps agent-specific intent detection, tool schema, prompt
behavior, and response translation in the agent integration layer.

The integration keeps the current high-level flow:

```text
PrepareWorkflow
  -> OrchestratorAgent
  -> ReminderDetectAgent, only when need_reminder_detect=true
  -> visible_reminder_tool wrapper
  -> ReminderService
  -> session_state.tool_results

ChatWorkflow
  -> reads tool_results and reports actual reminder outcomes

PostAnalyzeWorkflow
  -> skips or clears internal proactive follow-up when a timed reminder was created
```

The important boundary is that `visible_reminder_tool` is only an Agno-facing
wrapper. Reminder business rules live in `ReminderService`.

## Goals

- Preserve the existing two-stage agent flow: Orchestrator gates reminder
  detection, and ReminderDetectAgent performs reminder tool calls.
- Route all agent reminder operations through `ReminderService`.
- Keep Reminder System as the owner of reminder validation, lifecycle
  transitions, scheduler updates, and structured errors.
- Keep agent integration as the owner of LLM tool schema, prompt
  instructions, conversational clarification, tool result translation, and
  PostAnalyze coordination.
- Provide deterministic tool results that ChatWorkflow can use without
  hallucinating reminder success.
- Preserve and extend the reminder evaluation path around ReminderDetectAgent
  and a fake reminder tool recorder.

## Non-Goals

- No reminder domain model, scheduler, or delivery runtime redesign in this
  spec.
- No replacement of the two-stage agent flow in v1.
- No ChatResponseAgent direct reminder writes in v1.
- No OrchestratorAgent direct reminder creation in v1.
- No natural-language parsing inside Reminder System.
- No proactive follow-up redesign beyond preserving the existing
  `reminder_created_with_time` suppression behavior.
- No Google Calendar import path. Calendar import is out of scope for v1
  Reminder System and therefore not exposed through the agent tool.

## Ownership Boundary

Reminder System owns:

- `ReminderService` and its inputs and outputs
- core reminder validation and lifecycle behavior
- floating local-time schedule semantics and the supported RRULE subset
- chat delivery routing and post-delivery state advance
- structured error codes
- ordered partial batch result semantics

Agent Reminder Integration owns:

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
5. Before running ReminderDetectAgent, set the session-state context
   consumed by the Agno tool wrapper.
6. ReminderDetectAgent either calls `visible_reminder_tool` or stops.
7. Tool wrapper writes structured results to `session_state.tool_results`.

ReminderDetectAgent failure must not fail the main user turn. It should log
the failure and leave ChatWorkflow to continue. If the Orchestrator
requested reminder detection but no tool result exists, ChatWorkflow must
use the existing "reminder not executed" context so the assistant does not
claim success.

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

### visible_reminder_tool Wrapper

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

The LLM must not provide owner ids, source types, conversation ids,
character ids, route keys, or timezones. Those values come from trusted
runtime context.

## Tool Argument Contract

The v1 Agno wrapper keeps a compact LLM-facing schema.

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

Future UI and HTTP producers should prefer direct `reminder_id` selection
and should not depend on keyword resolution.

The wrapper does not accept `body`, `new_body`, `priority`, `sort_order`,
`list_id`, or `delivery_targets`. Those fields were removed from the v1
reminder model.

## Operation Mapping

### Create

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

### Update

Update requires `reminder_id` or successful keyword resolution. The wrapper
builds a `ReminderPatch`:

- `title` updated when `new_title` is provided.
- `schedule` updated when `new_trigger_at` or `rrule` is provided. The
  wrapper recomputes `local_date`, `local_time`, and `timezone` from the
  parsed datetime and the user's effective timezone. If only `rrule` is
  supplied, the wrapper reuses the existing anchor and local intent.

If an update changes the scheduled time and the call succeeds, the wrapper
sets `reminder_created_with_time=True` so PostAnalyze does not also create
an internal proactive follow-up for the same user intent.

### List

List calls `ReminderService.list_for_user` and returns enough structured
data for ChatWorkflow to answer the user, including title, schedule
summary, lifecycle state, and reminder id when appropriate for follow-up
operations.

### Cancel And Complete

Delete maps to `ReminderService.cancel` because cancellation preserves
domain lifecycle state. Complete maps to `ReminderService.complete`. Both
require `reminder_id` or successful keyword resolution.

### Batch

Batch preserves the user's requested operation order. The wrapper converts
each flat operation object into a `ReminderBatchOperation` and calls
`ReminderService.execute_batch`.

Rules:

- The wrapper returns one result per operation, in input order.
- Earlier successes remain successful if a later operation fails.
- A failed operation does not make the whole batch look successful.
- If any timed create/update succeeds, set `reminder_created_with_time=True`.

## Tool Results

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
may be localized for the current runtime, but it must not include
unsupported claims or generated apologies. ChatResponseAgent owns final
user-facing wording.

For batch, the wrapper may append one aggregate result plus per-operation
details, or append one result per operation. In both cases ChatWorkflow
must be able to distinguish full success, partial success, and full
failure.

## Error Translation

The wrapper translates `ReminderError` into stable tool failures.

Required mappings:

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
- If a reminder operation failed, ChatResponse should explain the failure
  and ask for the missing clarification when useful.
- If Orchestrator set `need_reminder_detect=true` but no reminder tool
  result is present, ChatWorkflow must include the reminder-not-executed
  context and must not claim a reminder was set.
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

This contract prevents duplicate follow-up scheduling when the user
already asked for an explicit reminder.

## Prompt Requirements

ReminderDetectAgent instructions must say:

- Use the visible reminder tool only for user-visible reminder operations.
- Do not plan internal proactive follow-ups.
- Resolve local and relative user times into aware ISO 8601 datetimes
  before calling the tool.
- Do not pass natural-language time strings to the tool.
- Use RRULE strings for recurrence.
- Use batch for multiple operations in one user message.
- Preserve operation order in batch.
- Prefer concise titles.
- Stop without tool call when the user intent is too ambiguous to form a
  structured command.

Orchestrator instructions must preserve the current gate:

- Set `need_reminder_detect=true` for reminder/task/alarm/timer intent,
  user personal reminder queries, and context continuation.
- Set it false for unrelated small talk, external-world search, and pure
  past facts.
- Orchestrator must not call `ReminderService` or `visible_reminder_tool`
  in v1.

## Evaluation

The existing reminder operation corpus remains the primary agent-facing
evaluation input. The evaluation path should isolate:

- Orchestrator gate accuracy
- ReminderDetectAgent tool-call accuracy
- operation classification accuracy
- timed create/update accuracy
- batch operation shape and ordering
- false-positive rate on negative cases

The evaluation runner should use a fake `visible_reminder_tool` recorder or
a fake `ReminderService`, not Mongo, scheduler, ChatResponse, PostAnalyze,
or outbound delivery.

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

## Acceptance Criteria

- Agent flow remains OrchestratorAgent gate followed by ReminderDetectAgent.
- ReminderDetectAgent remains the only agent-facing reminder write path.
- OrchestratorAgent does not call `ReminderService` or
  `visible_reminder_tool` in v1.
- ChatResponseAgent does not directly write reminders.
- `visible_reminder_tool` is an Agno wrapper around `ReminderService`, not
  a holder of reminder business rules.
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

## Test Matrix

| layer | covers |
|---|---|
| prompt | Orchestrator gate rules, ReminderDetectAgent ISO/RRULE/batch instructions |
| tool wrapper | argument parsing, session context derivation, service call mapping, error mapping |
| service integration | calls `ReminderService.create/update/cancel/complete/list_for_user/execute_batch` with correct context |
| batch | ordered results, partial failure, timed-success flag behavior |
| ChatWorkflow | tool result context, no-success-claim guard when no tool result exists |
| PostAnalyze | timed create/update suppresses internal proactive follow-up |
| eval | fake tool or fake service, no Mongo/scheduler/outbound dependency |
