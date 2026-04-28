# Reminder Tool Contract Refactor Design

**Status:** superseded by `2026-04-28-reminder-core-redesign-design.md`
**Date:** 2026-04-28

> This spec scoped only the LLM↔tool argument contract. Review concluded the
> reminder system needs a structural redesign (independent ReminderCore +
> non-agent ingress + unified actor model). See the redesign spec for the
> current direction. The contract decisions in this document are folded into
> the redesign as the LLM adapter section.

---
**Surfaces:** `agent/agno_agent/tools/deferred_action/tool.py`,
`agent/agno_agent/agents`, `agent/prompt/agent_instructions_prompt.py`,
`agent/agno_agent/workflows/prepare_workflow.py`,
`agent/runner/deferred_action_policy.py`,
`scripts/reminder_test_cases.json`

## Goal

Redesign the visible reminder system around a simple contract:

- the LLM understands user intent and resolves user time into absolute aware
  ISO 8601 datetimes
- the reminder tool validates structured arguments and executes CRUD
- batch operations cover multi-reminder and mixed CRUD requests in one user
  message
- real user reminder inputs are the acceptance benchmark

The system should optimize for correctness on real messaging-style user input,
not for backward compatibility with older tool parameters.

## Non-Goals

- No compatibility with `trigger_time` or `new_trigger_time`.
- No tool-side natural-language time parser for phrases like `3分钟后`,
  `明天`, or `tomorrow at 3pm`.
- No full iCalendar object model such as `VCALENDAR`, `VEVENT`, `VTODO`, or
  `.ics` import/export as part of this refactor.
- No evaluation through ChatResponse, Interact, PostAnalyze, outbound delivery,
  or Mongo persistence when testing tool-call accuracy.
- No long-term storage of raw user time text or LLM reasoning traces.

## Core Decision

Use:

```text
ISO 8601 aware trigger_at + RFC 5545 RRULE subset
```

Do not use:

```text
natural-language trigger_time + tool parser
```

The reminder tool is an executor, not a natural-language time interpreter.

## Why Timezone Belongs In This Design

User timezone is already injected into runtime context, but the important
question is ownership of the final scheduled instant.

The LLM must see enough context to resolve a local user phrase:

```text
Current time: 2026年04月28日11时30分
User timezone: Asia/Tokyo
User message: 今天17:58提醒我锻炼
```

It should then call the tool with:

```json
{
  "action": "create",
  "title": "锻炼",
  "trigger_at": "2026-04-28T17:58:00+09:00"
}
```

The tool must not receive `今天17:58`. If the LLM lacks enough information to
produce an aware ISO datetime, it should not call the tool and the user-facing
flow should ask for clarification.

## Responsibility Split

### LLM Responsibilities

The LLM is responsible for:

- detecting reminder intent
- deciding which CRUD operation or operations are requested
- splitting one message into ordered operations
- resolving relative, local, and named time expressions into `trigger_at`
- using the user timezone from input context unless the user explicitly names a
  different timezone for that reminder
- generating RFC 5545 `RRULE` strings for recurrence
- refusing to call the tool when time or target identity is ambiguous

Examples:

- `5分钟后提醒我关火` -> `trigger_at` based on message timestamp
- `今天17:57提醒我喝水` -> local date/time using user timezone
- `纽约时间明早9点提醒我联系客户` -> aware datetime using the explicit task timezone
- `每天17:58提醒我锻炼` -> `trigger_at` plus `rrule="FREQ=DAILY"`
- `晚上提醒我复盘` -> no tool call; needs clarification

### Tool Responsibilities

The visible reminder tool is responsible for:

- validating tool arguments
- rejecting malformed or timezone-less datetimes
- rejecting unsupported or malformed `RRULE`
- resolving reminder targets by id or keyword
- executing create, list, update, delete, complete, and batch
- preserving batch operation order
- returning only actual execution results

The tool must not:

- parse natural-language time phrases
- infer timezone from raw text
- silently skip failed batch operations
- confirm operations that were not executed

## Tool Schema

### Create

```json
{
  "action": "create",
  "title": "喝水",
  "trigger_at": "2026-04-28T17:57:00+09:00",
  "rrule": null
}
```

Required:

- `action="create"`
- `title`
- `trigger_at`

Optional:

- `rrule`

### Update

```json
{
  "action": "update",
  "keyword": "项目周报",
  "new_title": "提交周报",
  "new_trigger_at": "2026-04-29T15:00:00+09:00",
  "rrule": null
}
```

Required:

- `action="update"`
- one target: `reminder_id` or `keyword`
- at least one changed field: `new_title`, `new_trigger_at`, or `rrule`

### Delete

```json
{
  "action": "delete",
  "keyword": "买牛奶"
}
```

Required:

- `action="delete"`
- one target: `reminder_id` or `keyword`

### Complete

```json
{
  "action": "complete",
  "keyword": "吃药"
}
```

Required:

- `action="complete"`
- one target: `reminder_id` or `keyword`

### List

```json
{
  "action": "list"
}
```

### Batch

```json
{
  "action": "batch",
  "operations": [
    {
      "action": "create",
      "title": "喝水",
      "trigger_at": "2026-04-28T17:57:00+09:00"
    },
    {
      "action": "create",
      "title": "锻炼",
      "trigger_at": "2026-04-28T17:58:00+09:00",
      "rrule": "FREQ=DAILY"
    },
    {
      "action": "delete",
      "keyword": "买牛奶"
    }
  ]
}
```

Batch operation objects must be flat and must include `action`.

Invalid:

```json
{
  "action": "batch",
  "operations": [
    {
      "create": {
        "title": "喝水",
        "trigger_at": "2026-04-28T17:57:00+09:00"
      }
    }
  ]
}
```

## Time Contract

`trigger_at` and `new_trigger_at` must be ISO 8601 aware datetimes:

- valid: `2026-04-28T17:58:00+09:00`
- valid: `2026-04-28T08:58:00Z`
- invalid: `2026-04-28T17:58:00`
- invalid: `今天17:58`
- invalid: `5分钟后`

For user-local phrases, use the user's effective timezone from input context.

For explicitly named task timezones, use the timezone the user named for that
task only. This must not change the user's global timezone.

If the user asks for a past one-shot reminder, the LLM should not call the tool
unless the user's wording clearly implies the next future occurrence.

## Recurrence Contract

Use RFC 5545 `RRULE` strings for recurring reminders.

Initial supported subset:

- `FREQ=DAILY`
- `FREQ=WEEKLY`
- `FREQ=MONTHLY`
- `FREQ=YEARLY`
- optional `COUNT`
- optional `UNTIL`
- optional `INTERVAL`
- optional `BYDAY` for weekly recurrence

Examples:

```json
{
  "trigger_at": "2026-04-28T17:58:00+09:00",
  "rrule": "FREQ=DAILY"
}
```

```json
{
  "trigger_at": "2026-04-29T09:00:00+09:00",
  "rrule": "FREQ=WEEKLY;BYDAY=MO,WE,FR"
}
```

The tool should reject:

- `daily`
- `every day`
- malformed RRULE strings
- RRULE features outside the supported subset

## Storage Model

Storage should stay minimal.

For one-shot reminders, durable state only needs the final scheduled instant:

```json
{
  "title": "喝水",
  "next_run_at": "2026-04-28T08:57:00Z"
}
```

The existing deferred-action substrate may still store implementation fields
such as `dtstart`, `timezone`, lifecycle state, ownership fields, retry policy,
and scheduler metadata. This design does not require storing raw user text,
LLM-normalized candidates, or audit copies of time expressions.

For recurring reminders, durable state must preserve recurrence semantics:

```json
{
  "title": "锻炼",
  "dtstart": "2026-04-28T08:58:00Z",
  "timezone": "Asia/Tokyo",
  "rrule": "FREQ=DAILY",
  "next_run_at": "2026-04-28T08:58:00Z"
}
```

`timezone` matters for recurrence because `每天17:58` is a local-time semantic,
not just a single UTC instant.

## Batch Semantics

Batch is the primary path for:

- multiple creates in one user message
- mixed create/update/delete/list/complete in one user message
- high-volume creation after the product has accepted the requested volume

Rules:

- execute operations in user order
- each operation produces its own result entry
- if an operation fails, return a structured failure identifying that operation
- do not silently continue and then claim the whole batch succeeded
- do not create only the first operation because of tool-call limits

The preferred model is one batch tool call for one user message that contains
multiple reminder operations.

## Evaluation Strategy

Use `scripts/reminder_test_cases.json` as the real user input corpus.

The evaluation runner must exercise only:

```text
ReminderDetectAgent -> fake visible_reminder_tool recorder
```

It must not exercise:

- ChatResponseAgent
- InteractAgent or character response generation
- PostAnalyze
- Mongo persistence
- outbound delivery

For each case, capture:

- whether the tool was called
- action name
- flat argument shape
- number and order of operations
- whether create/update calls contain aware ISO datetimes
- whether recurrence uses supported `RRULE`

The first acceptance smoke should include the known real case:

```text
今天有这么两个事情提醒我 一个是17：57喝水，一个是每天17：58锻炼
```

Expected tool call:

```json
{
  "action": "batch",
  "operations": [
    {
      "action": "create",
      "title": "喝水",
      "trigger_at": "2026-04-28T17:57:00+09:00"
    },
    {
      "action": "create",
      "title": "锻炼",
      "trigger_at": "2026-04-28T17:58:00+09:00",
      "rrule": "FREQ=DAILY"
    }
  ]
}
```

## Acceptance Criteria

- The tool schema no longer exposes `trigger_time` or `new_trigger_time`.
- ReminderDetectAgent instructions require `trigger_at` / `new_trigger_at`.
- ReminderDetectAgent input includes the user's effective timezone.
- Real reminder eval uses the restored `scripts/reminder_test_cases.json`.
- The eval runner validates tool-call schema, not just whether a tool was
  called.
- A three-case real MiniMax smoke passes with `+09:00` for `Asia/Tokyo`.
- Unit tests cover aware datetime validation, RRULE validation, and batch
  execution order.

## Open Questions

- What is the maximum number of operations allowed in one batch before product
  confirmation is required?
- Should batch be atomic, or should partial success be allowed with explicit
  per-operation failure reporting?
- Which RRULE features beyond the initial subset should be supported in v1?
- Should `EXDATE` and `RDATE` be added after the first recurring-reminder pass?

