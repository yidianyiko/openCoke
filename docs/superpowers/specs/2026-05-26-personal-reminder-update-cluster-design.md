---
status: active
created_at: 2026-05-26
owner: smoke-coverage
kind: smoke-followup-design
---

# Personal reminder update/delete cluster design

## Scope

This design covers Batch A findings PR-01 through PR-06 and PR-13 from
`artifacts/evidence/shared-reminder-agent-smoke/personal-reminder-crud-recurring-20260525t184640Z.json`.
It does not change product code. The surfaces implicated are:

- `worker-runtime`: reminder intent detection, domain tool wrapping, command
  execution, and Reminder Runtime target resolution.
- `gateway-api`: customer reminder route acceptance, especially ID-based
  update/cancel/complete and RRULE parity.
- `product-reminder`: the active `reminders` Mongo collection and lifecycle
  states.

## Current Path

The active agent path is not a direct gateway request. The Interaction Agent
calls `reminder_domain`; `agent_runtime.py` ignores model-supplied arguments
and runs `ReminderIntentPort` on the raw user message. `ReminderIntentPort`
calls ReminderDetectAgent, validates `ReminderDetectDecision`, then
`ReminderCommandExecutor` invokes `visible_reminder_tool.entrypoint`.
`visible_reminder_tool` builds the in-process `ReminderRuntimeContract` through
`CokeReminderAdapter`, resolves a target id, and calls
`update_visible_reminder`, `cancel_visible_reminder`, or
`complete_visible_reminder`.

The gateway customer routes are ID-based:

- `PATCH /:reminderId` updates title and/or schedule fields.
- `POST /:reminderId/complete` completes an existing reminder.
- `POST /:reminderId/cancel` cancels an existing reminder.

Therefore the gateway can only accept a write after an upstream layer has
resolved exactly one reminder id. For weekday recurrence, the gateway route is
also narrower than the runtime because it only accepts `FREQ=DAILY`,
`FREQ=WEEKLY`, or `null`, not `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR`.

## Evidence Notes

The Batch A JSON includes `mongo_delta.agent_sessions.added_rows` and
`agent_trace_excerpt` for these cases. A live Mongo lookup by the excerpted
session ids matched no current rows in this checkout, so this trace uses the
persisted evidence rows in the artifact as the stable source.

One important harness detail: Batch A used one account across cases and left
state behind. By PR-02, PR-05, and PR-06 there were multiple active reminders
with the same title family. A product fix must not silently pick one of those
reminders just to satisfy the smoke; ambiguous delete/update must fail closed
with a clarification.

## Layer Trace

| Case | Evidence trace | Dropping layer | Gateway acceptance |
| --- | --- | --- | --- |
| PR-01 snooze | Target turn repeatedly called `reminder_domain`; tool returned `ReminderDetectInvalidDecision` with missing `title` and `trigger_at`; final reply asked what to remind. | Intent inference lacks snooze/update semantics for "again/in 10 minutes" when the title must be inherited from the active reminder. No update reached the runtime. | Not reached. |
| PR-02 update time | Target turn called `reminder_domain`; tool returned failed `update` with `AmbiguousReminderKeyword`; the second `list` call returned the same cached failed result; final reply asked which water reminder. | Target resolution, plus same-turn tool-result caching. The resolver only has id or title keyword and found multiple active `喝水` reminders in the shared batch account. | Not reached. If routed through gateway after resolution, `PATCH /:id` can accept a full local date/time patch. |
| PR-03 update title | Tool returned failed `update` with "no reminder found"; evidence call carried an invalid model hint like `reminder_id: "8"`, but the real domain result had no usable target. | Target resolution cannot express "the 8 o'clock reminder" because the detector schema has only `reminder_id` and `keyword`; `_resolve_reminder_id` searches title text only. | Not reached. Gateway can accept title-only `PATCH /:id` once the id is resolved. |
| PR-04 update recurrence | Tool returned `ReminderDetectInvalidDecision` and asked for the reminder title. The seed reminder stayed `FREQ=DAILY`. | Two drops: detector validation rejects or fails to form a valid recurrence update, and executor `_build_patch` only carries `rrule` when a new trigger time is supplied. A recurrence-only update preserving the existing clock cannot be represented. | Not reached in agent path. Gateway would reject the expected weekday RRULE today because route validation only admits bare `FREQ=WEEKLY`. |
| PR-05 delete by fuzzy name | Tool result was failed `cancel` with `AmbiguousReminderKeyword`; final state remained active. | Target resolution failed closed because multiple active title matches existed in the batch account. That is safe behavior when ambiguity is real, but the smoke expected the case seed to be uniquely selectable. | Not reached. Gateway cancel accepts an id once resolved. |
| PR-06 complete vs delete | The complete turn produced failed `complete` with `AmbiguousReminderKeyword`; delete produced failed `cancel` with `AmbiguousReminderKeyword`; repeated `list` calls returned cached prior failures. Both seeded reminders stayed active. | Target resolution lacks selectors for local date, local time, and "remaining one"; same-turn caching hides attempts to inspect state after failure. The runtime does support distinct `complete` and `cancel` operations once an id is known. | Not reached. Gateway complete/cancel are distinct ID-based routes. |
| PR-13 end recurring | Tool result was failed `cancel` with "no reminder found"; evidence hint was `operation: cancel_recurring, frequency: daily`, which is not the current action contract. | Target resolution cannot select by recurrence cadence (`daily`) without title/id. The action must normalize to `cancel` plus a recurrence selector, then resolve exactly one active recurring source. | Not reached. Gateway cancel accepts an id after resolution. |

## Root Cause

This is not one gateway propagation bug. The gateway is downstream of the
failures and usually never receives a request. The cluster is one root cause
class with several concrete gaps: the write path has no explicit target
resolution contract for update/delete/complete operations.

The current contract asks ReminderDetectAgent to return either an exact
`reminder_id` or a title `keyword`. That is too weak for real update/delete
language:

- "that 8 o'clock reminder" needs time-based target selection.
- "today's medicine reminder" needs date/time or occurrence selection.
- "the daily reminder" needs recurrence selection.
- "snooze it 10 minutes" needs recent active reminder inheritance.
- "drink water reminder" may match multiple active reminders and must clarify.

There are also two independent implementation bugs exposed by the same cases:

- `reminder_domain` caches the first domain result per turn and returns it for
  later calls, so a second call such as `list` after a failed update cannot
  actually inspect reminders.
- Recurrence-only update cannot propagate because `_build_patch` drops `rrule`
  unless a new trigger time is present.

## Proposed Fixes

### 1. Add a structured target selector

Replace the id-or-keyword-only targeting contract for write operations with a
small structured selector. Keep `reminder_id` as the strongest selector, but
add explicit fields the detector can populate:

- `target_title`: title or fuzzy title phrase.
- `target_local_date`: local date when the user says today/tomorrow/a date.
- `target_local_time`: local clock when the user says "8 o'clock" or similar.
- `target_rrule`: recurrence selector such as daily or weekdays.
- `target_scope`: `current_conversation`, `recent_active`, or `all_active`.

The detector should produce `clarify` when the user supplied no usable target
selector and state is ambiguous. It should not invent fake ids from clock
values, account suffixes, or phone-number-like text.

### 2. Resolve target before writing

Move target resolution into a domain helper used by update/cancel/complete:

1. List active visible reminders for the owner.
2. Apply selector filters in order: exact id, title, local date, local time,
   recurrence, and current/recent conversation when present.
3. If exactly one reminder remains, pass its id to the runtime write.
4. If zero or multiple remain, return a typed clarification result with compact
   candidate facts: title, local date, local time, and recurrence label.
5. Never fall back to "most recent" across all active reminders unless the
   selector explicitly says `recent_active` and only one recent active reminder
   is eligible.

This resolver is the central safety boundary. It should be tested independently
from ReminderDetectAgent so fuzzy matching does not become scattered across
prompt text, gateway routes, or UI code.

### 3. Support snooze as an update

For "再过 10 分钟提醒我" and similar relative-offset turns:

- If exactly one recent active visible reminder is tied to the current
  conversation or the immediately preceding reminder create/update turn,
  classify as `update` with that reminder as the target and
  `new_trigger_at = current_time + offset`.
- Preserve title and existing non-conflicting metadata.
- If no unique recent reminder exists, ask which reminder to snooze and make no
  write.

Do not create a generic "提醒" reminder as a fallback.

### 4. Preserve schedule on partial updates

Update patch construction must support:

- title-only update: preserve existing schedule.
- time-only update: preserve title, timezone, recurrence, and duration.
- recurrence-only update: preserve local date/time/timezone/duration and change
  `rrule`.
- title plus schedule update: apply both atomically.

This likely requires resolving the current reminder before building a schedule
patch. The patch builder should not need a new trigger time just to carry a new
RRULE.

### 5. Fix same-turn reminder-domain repeat behavior

Do not return the first `reminder_domain` result for every later call in the
same turn. Choose one of these behaviors:

- Preferred: allow one call only and return an explicit duplicate-call domain
  error on the second call, with instructions that the Interaction Agent must
  answer from the first domain result.
- Acceptable for debugging: allow a second read-only `list` after a failed
  write, but never allow a second write in the same turn.

The preferred option is safer and matches the current design where
ReminderDetectAgent owns the single structured decision.

### 6. Align gateway RRULE validation

If implementation routes any personal reminder writes through gateway, update
`customer-reminder-routes.ts` so create/update RRULE validation follows the
Reminder Runtime subset instead of the current hard-coded literals. At minimum,
weekday recurrence must accept `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR`.

Gateway update/cancel/complete should stay ID-based. Do not add fuzzy target
resolution to gateway routes; target resolution belongs in the agent/reminder
domain layer before gateway or runtime writes.

## Risk Analysis

- Mis-targeted writes are the highest risk. A broad fuzzy match could update,
  cancel, or complete the wrong reminder. The resolver must fail closed on
  zero or multiple matches.
- Batch A state contamination can make safe clarification look like a product
  failure. Verification should distinguish "correct clarification due to real
  ambiguity" from "failed to update a unique target".
- Recurring changes can accidentally cancel or mutate a whole series when the
  user meant one occurrence. PR-13 is a series cancel; PR-12 remains unsupported
  occurrence skip and must keep no-write behavior.
- Same-turn repeat-call changes can reintroduce duplicate writes if the wrapper
  permits multiple writes. Prefer duplicate-call error over permissive retry.
- Gateway RRULE widening can accept schedules the runtime cannot fire if the
  validator is not shared with `ReminderRuntimeContract`.
- Prompt-only fixes are fragile. The durable fix is a typed selector plus
  deterministic resolver, with prompt/schema changes only to fill that selector.

## Verification Plan

### Unit and contract tests

- Reminder detector/schema tests:
  - update time produces `action=update`, `target_title=喝水`, and
    `new_trigger_at`.
  - update title by "8 o'clock" produces `target_local_time=08:00` and
    `new_title=吃药`.
  - daily stop produces `action=cancel` and `target_rrule=FREQ=DAILY`.
  - snooze with recent active context produces update, not create.
  - ambiguous target produces `clarify` with no executable write fields.
- Target resolver tests:
  - unique title match resolves one id.
  - duplicate title match returns clarification and no write.
  - local-time selector resolves the 08:00 reminder.
  - recurrence selector resolves a single daily source and rejects multiple
    daily sources.
  - current/recent conversation selector does not select unrelated active
    reminders.
- Command executor/tool tests:
  - title-only, time-only, and recurrence-only update preserve untouched fields.
  - delete normalizes to cancel and writes `cancelled_at`.
  - complete writes `completed_at` and does not cancel.
  - second `reminder_domain` call in one turn returns explicit duplicate-call
    behavior or the documented safe read-only behavior.
- Gateway API tests if gateway validation changes:
  - `PATCH /:id` accepts weekday RRULE supported by runtime.
  - invalid RRULE remains a 400.
  - cancel/complete remain ID-only and do not accept fuzzy selectors.

### Smoke/eval

- Run focused reminder eval tests required by the reminder CRUD skill:
  `pytest tests/evals/test_reminder_eval_*.py -v`.
- Run focused agent handler/runtime tests covering domain tool single-call
  behavior.
- Rerun Batch A for PR-01..06 and PR-13 first, one case at a time when
  diagnosing failures.
- Then rerun the full Batch A smoke and save a new evidence JSON under
  `artifacts/evidence/shared-reminder-agent-smoke/`.
- If Batch A keeps one shared account, expected outcomes for PR-02, PR-05, and
  PR-06 must be interpreted with actual active reminder cardinality. A case
  that has multiple matching active reminders should pass by asking a
  clarification and making no write, not by guessing.

## Reviewable summary

- The cluster is not one gateway propagation failure; most writes never reach
  gateway or runtime because target resolution fails first.
- The central design fix is a typed target selector plus a deterministic,
  fail-closed resolver for update/cancel/complete.
- Two concrete code gaps must also be fixed: recurrence-only update patching and
  repeated `reminder_domain` calls returning the first cached result.
- Gateway should remain ID-based, but RRULE validation must match the runtime if
  weekday recurrence is exposed through customer routes.
- Verification must rerun Batch A with attention to real ambiguity; a safe
  clarification is the correct outcome when multiple reminders match.
