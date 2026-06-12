# Reminder Temporal Contract Design

Status: approved for implementation
Date: 2026-06-12

## Goal

Make reminder creation use one temporal contract across detector, domain
service, recurrence, and tests: the model supplies semantic temporal decisions;
the domain validates and stores only canonical temporal data.

## Root Cause

The current code mixes three jobs:

1. The prompt tells the detector what the model should decide.
2. Detector parsing accepts and repairs non-canonical output such as
   `freq`, `byday`, `hour`, and `minute`.
3. Reminder creation still applies a storage fallback for some missing
   durations.

This creates special-case behavior in the wrong layer. Prompt text alone cannot
enforce the contract, but runtime code also must not guess semantic content
from raw user text. The missing boundary is a small domain-level temporal helper
that validates canonical fields without adding new natural-language heuristics.

## Contract

For conversation-created reminders:

- Timed, recurring, and shared-projection reminders are calendar-visible.
- Calendar-visible create operations must carry a positive `duration_minutes`.
  The value may come from an explicit duration, a time range, or an LLM task
  duration estimate, but it must not be silently defaulted to 15 minutes.
- A recurring reminder must carry a canonical recurrence rule:
  `{"frequency": "hourly|daily|weekly|monthly|yearly", "interval": positive_int}`.
  Hourly rules may also carry canonical `window_start` and `window_end`.
- A recurring reminder must carry the first concrete `trigger_time`. For
  phrases such as "every Monday at 9 AM", the detector must choose the next
  matching future occurrence from the authoritative local `now`; the domain
  must not ask "which week" once the model supplied a concrete time.
- Direct malformed recurrence shape is a producer error, not a user question.
  The runtime rejects it instead of repairing it.

For non-calendar-visible or non-conversation boundaries:

- No-trigger-time personal reminders may keep an internal storage duration so
  existing storage and projections have a positive integer, but this value is
  not a calendar-visible task estimate.
- Proactive reminders may keep the same internal storage fallback because they
  are hidden from the calendar and are not directly user-editable.
- Calendar import keeps its own event boundary: when a third-party imported
  event has no duration, the import service may use the product-approved
  15-minute event fallback.

## Architecture

Add a focused `coke.domains.reminder.temporal` module that owns:

- canonical recurrence validation and normalization;
- positive duration parsing;
- create-time temporal field normalization;
- trigger-time conversion from detector-local time to UTC.

`ReminderService` consumes that helper before duplicate checks, conflict checks,
or persistence. `recurrence.py` also validates through the same helper before
advancing occurrences. `SiliconFlowReminderDetector` stops repairing RRULE-style
or legacy recurrence output and accepts only the canonical shape its prompt and
schema request.

This is not "three layers of prompt". The prompt is an instruction to the LLM;
the detector schema is the model-output boundary; the domain helper is the
business invariant. Each layer has a different responsibility.

## Error Handling

- Missing duration for calendar-visible create returns
  `missing_duration_minutes`.
- Missing first trigger for a recurring rule returns
  `missing_recurring_trigger_time`.
- Non-canonical recurrence shape returns `invalid_recurrence_rule`.
- `kind="recurring"` without a recurrence rule returns
  `missing_recurrence_rule`.

## Testing

Unit tests must cover:

- conversation-created timed reminders without `duration_minutes` no longer
  persist with 15 minutes;
- no-trigger-time reminders still store an internal 15-minute value;
- recurring creates without first trigger do not persist;
- non-canonical recurrence output from the detector is rejected instead of
  repaired;
- valid recurring detector output still persists the next concrete trigger.

## Out Of Scope

- Adding keyword or regex weekday parsers.
- Adding a new duration-estimation service.
- Changing calendar import's third-party event fallback.
- Changing shared-reminder participant, conflict, or delivery behavior.
