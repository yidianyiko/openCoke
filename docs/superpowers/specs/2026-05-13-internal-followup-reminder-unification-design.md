# Internal Follow-up Reminder Unification Design

**Status:** draft for review
**Date:** 2026-05-13
**Owner:** Codex

## Summary

Unify Coke's internal proactive follow-up with the Reminder System by treating
agent-created follow-up as an internal reminder.

This is not a new generic scheduler or task platform. The product concept stays
small:

```text
reminder = at a future time, bring one thing back into the conversation
```

User-created reminders and agent-created follow-ups differ by origin,
visibility, and fire behavior, not by runtime substrate. The current
`deferred_actions.kind=proactive_followup` path should stop receiving new
writes. After the new internal-reminder path is verified, proactive follow-up
support in `deferred_actions` should be deleted instead of kept as a
compatibility fallback.

## Problem

Coke currently has two scheduling mechanisms for closely related product
behavior:

- visible user reminders live in MongoDB `reminders` and are fired by
  `ReminderScheduler`
- internal proactive follow-ups live in MongoDB `deferred_actions` and are
  fired by the deferred-action runtime

That split is no longer a good domain boundary. A proactive follow-up is still
a reminder: it was created by the agent rather than by explicit user intent,
and it is normally hidden from the user's reminder-management UI.

Keeping two mechanisms creates avoidable problems:

- lifecycle and scheduling behavior are duplicated across two services
- reminder creation has to suppress or clear a separate follow-up subsystem
- future agent behavior has to reason about two kinds of scheduled
  conversation re-entry
- tests can pass for one scheduling path while the other path drifts
- old proactive follow-up code can survive as a hidden compatibility branch
  after the Reminder System is already the better owner

## Decision

Represent proactive follow-up as an internal reminder in the existing
`reminders` collection.

Add the minimum fields needed to distinguish follow-ups from ordinary visible
reminders:

```text
origin: user | agent | web
visibility: visible | internal
fire_mode: notify | followup
prompt: optional string
metadata: optional object
```

Default existing documents on read:

```text
origin = user
visibility = visible
fire_mode = notify
prompt = null
metadata = {}
```

Do not introduce `ScheduledAction`, generalized future-action types, task
tables, or a second abstraction layer. The existing `ReminderService`,
`ReminderDAO`, `ReminderScheduler`, and `ReminderFireEventHandler` remain the
runtime owners.

## Product Semantics

### Visible User Reminder

Created when the user explicitly asks for a reminder or creates one from the
web UI.

```text
origin=user | web
visibility=visible
fire_mode=notify
title="写论文"
prompt=null
```

It appears in `/account/reminders`, can be listed or modified by the user, and
fires as a user-visible reminder.

### Internal Agent Follow-up

Created by `PostAnalyzeWorkflow` when the agent decides a later check-in is
useful if the user does not reply.

```text
origin=agent
visibility=internal
fire_mode=followup
title="检查用户是否开始写论文"
prompt="问用户有没有开始。如果没有，把任务压缩到 5 分钟第一步。"
```

It does not appear in `/account/reminders` and is not listable through the
visible reminder tool. When it fires, it re-enters the normal agent turn as an
internal follow-up trigger. The user sees only the final Coke message, not
technical reminder wording.

## Data Model

Extend `agent.reminder.models.Reminder` with:

```python
origin: Literal["user", "agent", "web"]
visibility: Literal["visible", "internal"]
fire_mode: Literal["notify", "followup"]
prompt: str | None
metadata: dict | None
```

Persist the same fields on `reminders` documents.

Validation rules:

- `visibility="visible"` reminders may use `fire_mode="notify"` only.
- `visibility="internal"` reminders must use `origin="agent"`.
- `origin="agent"` with `visibility="visible"` is invalid in this change.
- `fire_mode="followup"` requires a non-empty `prompt`.
- `fire_mode="followup"` with `visibility="visible"` is invalid.
- `fire_mode="notify"` must store `prompt=None`.
- User-facing list, update, cancel, and complete operations default to
  `visibility="visible"` and must not expose internal reminders.
- Internal follow-up helpers may mutate only `origin="agent"` and
  `visibility="internal"` reminders.
- `metadata` is for runtime bookkeeping only, such as no-reply follow-up
  counters. The only initially expected key is `proactive_times`; do not put
  user-facing task fields, goal fields, or arbitrary product state in it.

Schema-on-read defaults are enough for existing reminder rows. No mandatory
Mongo migration is required before deployment.

Query rules must also preserve legacy visible reminders. Any DAO or service
query for visible reminders must treat missing `visibility` as visible:

```text
visibility selector = {"$or": [{"visibility": "visible"}, {"visibility": {"$exists": false}}]}
```

Do not implement visible-reminder queries as `{"visibility": "visible"}` only,
because pre-change reminder documents do not have this field and would
disappear from user-facing lists.

## Service API

Keep ordinary reminder APIs unchanged for visible reminders.

Add two narrow service methods:

```python
ReminderService.create_or_replace_internal_followup(
    *,
    owner_user_id: str,
    conversation_id: str,
    character_id: str,
    route_key: str | None,
    title: str,
    prompt: str,
    schedule: ReminderSchedule,
    metadata: dict | None = None,
) -> Reminder

ReminderService.clear_internal_followup(
    *,
    conversation_id: str,
    owner_user_id: str,
) -> Reminder | None
```

Replacement rule:

- At most one active internal follow-up per conversation.
- Creating a new internal follow-up for the same conversation replaces the
  prior active one by updating its title, prompt, schedule, `next_fire_at`,
  and timestamps.
- Clearing marks the active internal follow-up `cancelled` and removes its
  scheduler job.
- The clear path must always include `owner_user_id`; it must not clear by
  conversation id alone.
- Add an index that supports the active internal follow-up lookup, preferably
  a partial unique index over `(owner_user_id, agent_output_target.conversation_id)`
  for documents with `visibility="internal"`, `fire_mode="followup"`, and
  `lifecycle_state="active"`.
- Replacement during a fire race follows the existing Reminder System
  `next_fire_at` compare-and-update behavior. If the old wake-up has not yet
  emitted, the replacement's new `next_fire_at` wins and the stale wake-up is
  dropped. If the old wake-up already emitted into Agent System, that event is
  allowed to complete; do not add cross-runtime rollback logic.

This mirrors the current `DeferredActionService.create_or_replace_internal_followup`
behavior without keeping a second scheduler path.

## Runtime Flow

### PostAnalyze Creation

`PostAnalyzeWorkflow._handle_followup_plan()` should stop constructing
`DeferredActionService`.

Instead:

```text
FollowupPlan create/replace
  -> ReminderService.create_or_replace_internal_followup(...)

FollowupPlan clear
  -> ReminderService.clear_internal_followup(...)

session_state["reminder_created_with_time"]
  -> ReminderService.clear_internal_followup(...)
```

The existing "timed visible reminder suppresses follow-up" behavior remains,
but it now clears an internal reminder rather than a deferred action.

### Fire Handling

`ReminderScheduler` continues to emit `ReminderFiredEvent`.

`ReminderFireEventHandler` branches by `fire_mode`:

- `notify`: existing visible-reminder behavior.
- `followup`: create a system/deferred input into the normal agent turn using
  `prompt` as the instruction payload and metadata marking
  `kind=internal_followup`.

The fired follow-up should still use the stored `agent_output_target` for
conversation, character, and route resolution. `agent_output_target` already
exists on current `Reminder` records and continues to hold `conversation_id`,
`character_id`, and optional `route_key`; this spec does not replace that
target model.

Internal follow-up fire handling must not emit the normal visible-reminder
notification text or any management-surface event that would make the internal
follow-up appear as a user-created reminder. Only the final generated Coke
message should be user-visible.

Lifecycle after successful follow-up fire:

- one-shot internal follow-up completes after a successful agent output
- recurring internal follow-up is out of scope; internal follow-up creation
  must reject RRULE for this change

Lifecycle after failed follow-up fire:

- use the existing Reminder System fire failure behavior: mark the reminder
  `failed`, record `last_error`, and clear `next_fire_at`
- do not silently retry through `deferred_actions`

## Web And Visible Tool Behavior

Internal follow-ups must not appear in user-facing reminder management:

- `/account/reminders` lists `visibility=visible` only.
- `/api/customer/reminders` lists and mutates `visibility=visible` only.
- `visible_reminder_tool` list/update/cancel/complete operates on
  `visibility=visible` only.

This prevents agent-created check-ins from feeling like user-authorized
reminders while still using the same scheduling substrate.

## Migration And Deletion

This change should be forward-only and avoid long-lived dual runtime paths.

Implementation phases:

1. Add reminder fields with schema-on-read defaults.
2. Add internal follow-up service helpers and DAO query/update support.
3. Switch `PostAnalyzeWorkflow` to write internal reminders.
4. Switch reminder fire handling to support `fire_mode=followup`.
5. Verify the new path.
6. Delete the old proactive follow-up runtime path.

Deletion requirement after verification:

- Remove `DeferredActionService.create_or_replace_internal_followup`.
- Remove `DeferredActionService.clear_internal_followup` if no non-test caller
  remains.
- Remove `DeferredActionDAO.find_active_internal_followup` if no non-test
  caller remains.
- Remove tests that exist only to prove `deferred_actions.kind=proactive_followup`.
- Update architecture docs so proactive follow-up is no longer described as
  living in `deferred_actions`.
- Keep unrelated `deferred_actions` behavior only if it is still used by other
  product surfaces such as imported calendar reminders or historical deferred
  action flows.

Do not keep fallback behavior that writes proactive follow-up to
`deferred_actions` when internal reminder creation fails. A failure should be
visible in logs/tests and should not silently reintroduce the old mechanism.

Before deleting the old proactive follow-up handler, inspect local and
production data for active `deferred_actions.kind=proactive_followup` rows.
If any active rows exist, clear or migrate them before deleting the handler.
The final state must be: no active proactive rows, no scanner branch that tries
to execute that kind, and no unknown-kind log noise from historical rows.

## Validation

Focused verification must prove both the new path and the removal of old
proactive writes.

Minimum tests:

- `ReminderService` can create, replace, and clear one internal follow-up per
  conversation.
- the active internal follow-up lookup uses the new index/selector shape and
  enforces one active follow-up per owner+conversation.
- visible reminder list/update/cancel/complete excludes internal reminders.
- visible reminder list/query still includes legacy reminder rows where
  `visibility` is missing.
- `PostAnalyzeWorkflow` writes internal reminders for follow-up create/replace
  and clears them for clear or `reminder_created_with_time`.
- no `deferred_actions.kind=proactive_followup` write happens from
  `PostAnalyzeWorkflow`.
- `ReminderFireEventHandler` routes `fire_mode=followup` through the normal
  agent/output path using the stored prompt.
- failed internal follow-up fire uses Reminder System failure semantics and
  does not fall back to `deferred_actions`.
- internal follow-up creation rejects RRULE in this change.
- ordinary visible reminder creation and firing remain unchanged.
- `/api/customer/reminders` and `/account/reminders` do not expose internal
  follow-ups.
- before deleting old proactive code, data inspection proves there are no
  active `deferred_actions.kind=proactive_followup` rows left to execute.

Recommended commands after implementation:

```bash
.venv/bin/python -m pytest \
  tests/unit/reminder/test_service.py \
  tests/unit/agent/test_post_analyze_workflow.py \
  tests/e2e/test_reminder_system_flow.py \
  -k "reminder or followup" -v
```

```bash
.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/test_reminder_management_service.py \
  tests/unit/connector/clawscale_bridge/test_bridge_app.py \
  -k "reminder or reminders" -v
```

```bash
cd gateway/packages/api && npm test -- src/routes/customer-reminder-routes.test.ts
```

```bash
cd gateway/packages/web && npm test -- app/'(customer)'/account/reminders/page.test.tsx
```

Run diff-aware routing before final closeout:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

If the implementation deletes deferred-action proactive code, run the
deferred-action tests that still cover non-proactive behavior to prove no
unrelated surface was broken.

## Acceptance Criteria

- New proactive follow-ups are stored in `reminders`, not `deferred_actions`.
- User-created visible reminders keep their current behavior and API shape.
- Internal follow-ups are hidden from customer reminder management.
- A fired internal follow-up produces a normal Coke message through the
  existing conversation/output path.
- Creating a timed visible reminder clears any active internal follow-up for
  the conversation.
- After verification, old proactive follow-up code in `deferred_actions` is
  removed or explicitly proven to have no remaining non-test callers before
  deletion.
- Architecture docs and tests no longer describe proactive follow-up as a live
  `deferred_actions` responsibility.

## Out Of Scope

- A generic scheduled-action platform.
- Calendar-import origin changes.
- Goal, task, milestone, blocker, or progress-tracking tables.
- User-visible management of internal follow-ups.
- Snooze, dismissal, retry policy, durable outbox, or exactly-once delivery.
- Multi-worker scheduler claiming.
- Recurring proactive follow-up redesign.
- Changing reminder intent detection behavior.
- Changing pending-workflow flags.

## Review Questions

Reviewers should focus on these points:

- Is `origin/visibility/fire_mode/prompt` enough, or is any field unnecessary?
- Does the deletion requirement remove the old proactive path without breaking
  other `deferred_actions` consumers?
- Does `ReminderFireEventHandler` have enough context to run an internal
  follow-up as a normal agent turn without leaking technical wording?
- Are the validation commands strong enough to prove both unification and
  non-regression?
