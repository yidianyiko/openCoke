# Reminder Overlap And Shared Reschedule — Design

Status: ACCEPTED. Scope: clean inbound turn path, personal reminders used as self
schedule entries, and social shared reminders.

## Problem

The v6 WeChat real-account smoke exposed two product gaps:

1. Personal self-schedule entries do not reject overlapping time ranges. A user
   can have an active `团队会议` from 08:30 to 09:30 and still create `运动` from
   08:00 to 09:00. The database already rejects completely identical active
   personal reminders, but overlap is a separate interval rule.
2. Shared reminders do not support normal update/reschedule CRUD. The current
   social scheduling surface exposes create, cancel, list, and availability
   only. A request such as `和张三的 openCoke 预约改到明天下午 4 点` cannot update
   the active shared reminder in place.

## Product Decisions

- Time overlap is a hard pre-write constraint. If a personal reminder or self
  schedule overlaps an existing active calendar-visible reminder, the system
  refuses the create/update/reschedule and asks the user to choose another time.
- A shared reminder reschedule is an update of the existing shared reminder and
  its participant projections. It must not be implemented as a cancel plus a new
  shared reminder because that changes identity, notification semantics, and
  user-visible history.
- Shared reminder update starts with time and duration. Title/content update is
  deliberately deferred; time reschedule is the required behavior for the v6
  E5/E6 cases.
- Conflict checks must be truthful. The system may ask the user to choose another
  time, but it must not suggest a concrete alternate time unless that slot has
  been checked.

## Current Code Boundaries

- `ReminderService._create`, `reschedule_reminder`, and `update_reminder` validate
  time and duplicates, then write reminders. They do not check interval overlap.
- `ReminderCalendarReadModel` already treats reminder duration as the display
  interval, so the overlap rule should use the same `next_fire_at +
  duration_minutes` model.
- `SocialSchedulingService.create_shared_reminder` already runs duplicate,
  reachability, and receiver conflict preflight before writing.
- `SocialSchedulingRepository.shared_busy_intervals` returns active shared
  intervals for a participant, but does not yet support excluding the reminder
  currently being updated.
- `SocialSchedulingActionHandler`, `PARAM_KEY_SCHEMA`, the planner action set,
  and the Agno tool instructions currently do not expose shared reminder update.

## Personal Overlap Design

Add a repository query for active calendar-visible busy intervals owned by an
account:

- one-shot reminders: `[next_fire_at, next_fire_at + duration_minutes)`;
- shared projections: included because they are active reminders on the user's
  calendar;
- proactive and hidden reminders: excluded;
- no-trigger reminders: excluded;
- recurring reminders: expand occurrences that intersect the proposed interval
  using existing recurrence utilities.

Before writing a personal reminder create, update, or reschedule:

1. Normalize the proposed trigger time and duration.
2. Build the proposed interval.
3. Query active intervals for the owner, excluding the reminder being updated.
4. If any interval overlaps, return a non-success result such as
   `time_conflict` with privacy-safe facts: conflicting reminder id, content,
   start, end, and timezone.
5. Do not write the new or updated reminder.

The user-visible reply should say the requested time conflicts with an existing
schedule/reminder and ask for another time. It should not claim the reminder was
created or updated.

## Shared Reschedule Design

Add `update_shared_reminder` to the social scheduling domain.

Inputs:

- `account_id`: the participant making the change;
- `shared_reminder_id`, or the same participant + match resolution used by
  cancel;
- optional `local_trigger_at` / `time_phrase`;
- optional `duration_minutes`;
Title/content editing is out of scope for the first implementation.

Service behavior:

1. Load the shared reminder and require that `account_id` is a participant.
2. Require the shared reminder to be active.
3. Resolve the new time/duration from inputs. If no update field is
   present, return `needs_update_fields`.
4. Validate the new time as future when time changes.
5. Re-run duplicate detection for the proposed updated identity, excluding the
   current shared reminder.
6. Re-run reachability and conflict checks for all participants. Conflict checks
   must exclude this shared reminder's current interval, otherwise every
   reschedule would conflict with itself.
7. If checks fail, return a blocked result and leave the existing shared reminder
   and projections unchanged.
8. If checks pass, atomically update:
   - `shared_reminder.local_trigger_at`, `duration_minutes`, and `updated_at`;
   - all active projection reminder rows' `next_fire_at`, `duration_minutes`,
     `content`, and `updated_at`.
9. Emit a `shared_reminder_updated` or `shared_reminder_rescheduled`
   notification fact to the other participants.

Inbound turn behavior:

- Add `social_scheduling.update_shared_reminder` to `PARAM_KEY_SCHEMA`, planner
  allowed actions, and handler dispatch.
- Reuse the existing `_resolve_shared_reminder` logic so vague references with
  multiple candidates ask the user to choose instead of mutating state.
- Stage the update only after service preflight succeeds. For blocked conflicts,
  no staged command should be created.

Agno/tool behavior:

- Expose `update_shared_reminder` in the social scheduling tool docs.
- Instruct the model to call it for shared reminder time/duration changes, and to
  keep using `cancel_shared_reminder` only for explicit cancellation.
- Replies must be grounded in the tool result: success means the shared reminder
  was updated and remains active; blocked conflict means the old time remains.

## Tests And Smoke Changes

Unit coverage:

- personal create refuses overlap with an existing timed reminder;
- personal create refuses overlap with an existing shared projection;
- personal update/reschedule excludes the target reminder itself but refuses
  overlap with another reminder;
- shared reschedule updates the existing shared reminder id and all projections;
- shared reschedule into receiver conflict leaves old shared reminder/projections
  unchanged;
- shared reschedule with ambiguous reference asks for a choice and stages no
  command;
- duplicate updated shared reminder is rejected without mutation.

v6 smoke changes:

- `calendar_self_create_002` stops being `expected_gap`; expected outcome becomes
  conflict/no write.
- `scheduling_reschedule_001` stops being `expected_gap`; expected outcome becomes
  update existing shared reminder to the new time.
- `scheduling_reschedule_002` stops being `expected_gap`; expected outcome becomes
  conflict/no write and old shared reminder remains active at the old time.

## Non-Goals

- No automatic alternate-time recommendation in this pass.
- No cancel-plus-create fallback for shared reschedule.
- No change to the default 15-minute duration.
- No schema migration unless the implementation proves an efficient interval
  query needs an index. The initial implementation can use existing active
  reminder queries because current scale is small.

## Verification

- Targeted unit tests for reminder and social scheduling services and inbound social
  handler.
- Planner/semantic tests showing shared reschedule maps to
  `update_shared_reminder`.
- `zsh scripts/suggest-verification --base HEAD~1`.
- Suggested backend surface verification.
- Real GCP WeChat smoke for D3, E5, and E6 after deployment, one message at a
  time, with DB row-effect assertions and cleanup.
