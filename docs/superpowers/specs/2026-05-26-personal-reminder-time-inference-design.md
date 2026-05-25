---
status: active
created_at: 2026-05-26
owner: reminder-system
kind: smoke-fix-design
surface: worker-runtime
source_evidence: artifacts/evidence/shared-reminder-agent-smoke/personal-reminder-time-content-list-20260525t191524Z.json
---

# Personal Reminder Time-Inference Edge Fix

## Scope

This design covers PR-14, PR-15, PR-17, PR-18, and PR-19 from the Batch B
personal-reminder smoke. It is a worker-runtime design only. The implementation
target is the detector and deterministic normalization path around:

- `agent/agno_agent/capabilities/reminder_intent.py`
- `agent/agno_agent/adapters/reminder_command_executor.py`
- `agent/agno_agent/tools/reminder_protocol/tool.py`
- `agent/reminder/schedule.py` only if the precision contract needs it

The requested executor path is stale; the current executor is
`agent/agno_agent/adapters/reminder_command_executor.py`.

No gateway behavior is implicated by the captured agent smoke path. Gateway
customer reminder routes should only be touched if a later implementation
changes the public reminder API contract.

## Layer Trace Per Case

### PR-14 Past Time

Input: `提醒我昨天 10 点开会。`

Observed Batch B result: no Mongo write, generic fallback, and no
`reminder_domain` tool call.

Layer trace:

- Detector: primary failure. The request has reminder intent, title, and an
  explicit past trigger, but no structured reminder result reached execution.
- Schedule normalizer: not reached.
- Reminder runtime acceptance: not reached. If reached, one-shot
  `anchor_at <= now` is rejected as `past_one_shot`.
- Gateway acceptance: not reached.

Required behavior: no write plus a visible future-time prompt.

### PR-15 Just Past

Pattern: explicit same-day clock roughly five minutes before `current_time`.

Observed Batch B result: no Mongo write and an unsafe "processing" fallback.
The cluster also reports a created-past variant, not proven by this evidence,
which can happen if the model rewrites the day before schedule validation.

Layer trace:

- Detector: unstable; it may emit a past time, emit no usable decision, or
  rewrite the day.
- Schedule normalizer: bare-clock normalization skips explicit dates, so it
  does not convert `今天 HH:mm` to tomorrow.
- Reminder runtime acceptance: should reject explicit past one-shot schedules
  with `past_one_shot`.
- Gateway acceptance: not reached.

Required behavior: no write plus a clear invalid-past or future-time prompt.

### PR-17 Bare Clock

Inputs: `3 点提醒我喝水。` and `6 点 17 分提醒我拉伸。`

Observed Batch B result: both reminders were written as one-shots. Stored
times were mostly correct, but replies claimed daily recurrence or the wrong day.

Layer trace:

- Detector: partly correct, but visible text can hallucinate recurrence or day.
- Schedule normalizer: existing helpers implement next-occurrence logic when
  no explicit date is present.
- Reminder runtime acceptance: accepts the normalized future one-shots.
- Reply contract: weakly enforced. `ReminderCommandExecutor` exposes
  `local_date`, `local_time`, `rrule`, and `visible_summary`, but the final
  Interaction Agent can still contradict them.
- Gateway acceptance: not reached.

Required behavior: bare future clock resolves to today, bare past clock
resolves to tomorrow, and the final reply matches stored date/time/recurrence.

### PR-18 Relative Time And Relative Date

Inputs: `5 分钟后提醒我喝水。`, `明早提醒我喝水。`,
`下下周三提醒我喝水。`

Observed Batch B result: `5 分钟后` created from runtime current time; `明早`
invented 08:00 and wrote; `下下周三` asked for the missing time with no write.

Layer trace:

- Detector: mixed. Relative delays are mostly handled; vague date/day-period
  phrases can still get model-defaulted clocks.
- Schedule normalizer: relative delays are corrected from runtime
  `current_time`, but vague date/day-period phrases have no missing-clock guard.
- Reminder runtime acceptance: accepts invented `08:00` because it is a valid
  future datetime; this layer cannot infer that the time was not user supplied.
- Gateway acceptance: not reached.

Required behavior: concrete relative delays create; relative dates or day
periods without an exact clock ask for the missing time and make no write.

### PR-19 Sub-Minute Precision

Input: `6 点 18 分 45 秒提醒我喝水。`

Observed Batch B result: the trace included seconds, but Mongo stored
`06:18:00`, and the reply omitted seconds without saying it rounded.

Layer trace:

- Detector: not the main failure in the captured run; it recognized seconds.
- Tool/normalizer: precision is lost around reminder protocol batch dedupe and
  visible summaries, which use minute precision.
- Reminder runtime acceptance: can represent seconds because schedule building
  keeps the local anchor time.
- Gateway acceptance: not reached.

Required behavior: do not silently truncate. This design recommends preserving
explicit seconds end to end for one-shot reminders.

## Root Cause

This is not a single time-parser bug. The common missing invariant is:

> A reminder write must be authorized by concrete user time evidence, normalized
> against runtime `current_time` and user timezone, and echoed back from stored
> facts without silent precision loss.

Case grouping:

- PR-14 and PR-15 are past-time rejection and refusal-surface failures.
- PR-17 is bare-clock normalization plus reply-grounding. Some deterministic
  bare-clock code already exists and should be tightened, not replaced.
- PR-18 splits into covered relative delays and vague date/day-period phrases
  that need a missing-clock guard.
- PR-19 is a precision contract gap in the tool/summary path, not a detector
  parse failure.

Use one small deterministic `time_evidence` normalizer before command
execution, plus precision fixes in the reminder protocol adapter. Avoid
case-by-case prompt examples.

## Proposed Fixes

### 1. Add A Deterministic Time Evidence Normalizer

Add a helper in `reminder_intent.py` after detector output and before
`ReminderCommandExecutor.execute()`.

Responsibilities:

- Extract latest user turn, user timezone, and runtime `current_time`.
- Classify user time evidence:
  - `explicit_past`: explicit past date or same-day clock already past.
  - `bare_clock`: clock with no explicit date.
  - `relative_delay`: `N 分钟后`, `N 小时后`, timer wording.
  - `vague_date_without_clock`: `明早`, `明天`, `下下周三`, weekday/date words
    without exact hour/minute.
  - `explicit_seconds`: clock includes seconds.
- Return a normalized decision, a no-write invalid-schedule result, or a
  no-write missing-time clarification.

Cover top-level create/update and batch create/update. Do not parse unrelated
clocks that are not governed by a reminder verb.

### 2. Make Past-Time Refusal Deterministic

For PR-14 and PR-15:

- If original user wording proves an explicit past one-shot time, return a
  no-write domain result equivalent to: `这个提醒时间已经过去了，请告诉我一个未来的时间。`
- Keep `agent/reminder/schedule.py` `past_one_shot` rejection as the final
  acceptance boundary.
- Do not normalize explicit `昨天`, explicit past dates, or explicit
  `今天 HH:mm` into tomorrow.
- Only bare clocks may roll to the next occurrence.

### 3. Tighten Bare-Clock Semantics And Reply Grounding

For PR-17:

- Keep the current bare-clock rule: future today when still future, otherwise
  tomorrow.
- Keep `_EXPLICIT_DATE_PATTERN` as the boundary between explicit dates and
  bare clocks.
- Ensure `点 分` forms stay covered by
  `_SINGLE_BARE_CLOCK_EXTRACTION_PATTERN`.
- Ensure one-shot bare-clock wording does not gain `rrule` unless the user
  gave recurrence evidence.
- Strengthen final reply grounding so write confirmations must use
  `operations[*].facts.local_date`, `local_time`, and `rrule`. The reply must
  not say "daily" when `rrule` is empty or "tomorrow" when stored
  `local_date` is today.

### 4. Clarify Vague Relative Dates Without Clock

For PR-18:

- Keep relative-delay normalization based on runtime `current_time`.
- Add a no-write guard for date/day-period phrases that lack an exact clock:
  `明早`, `明天`, `下下周三`, `周三`, and equivalent date-only phrases.
- Return `date_only_missing_time` rather than accepting model-defaulted clocks
  such as 08:00 or 09:00.
- Preserve valid inputs that include exact time evidence, such as `明早 8 点`,
  `下下周三 14:00`, and `5 分钟后`.

### 5. Preserve Explicit Seconds Or Make Precision Explicit

For PR-19:

- Recommended contract: preserve explicit seconds for one-shot reminders.
- Remove or narrow adapter truncation where it changes stored schedule facts.
- Display seconds when nonzero in visible summaries and required reply facts.
- If product later chooses minute precision, switch to an explicit policy:
  no-write confirmation request, or write rounded time with a required reply
  fact that says it rounded.
- Never floor seconds silently.

## Risk Analysis

- Valid future explicit times must not be rejected. Refuse only when original
  user wording proves a one-shot past time.
- Bare-clock rollover must not apply to explicit dates. `今天 04:10` when it is
  already 04:15 is invalid; `4 点提醒我` at 04:15 means the next 04:00.
- Vague day-period handling must not reject exact clocks. `明早 8 点` is valid;
  bare `明早` asks for a time.
- Recurrence inference must stay evidence-based. Do not create daily reminders
  from one-shot bare-clock wording.
- Precision changes affect scheduler and display. Preserving seconds is safer
  than silent rounding because the schedule model already stores second-level
  `time` values. If minute precision is chosen later, require visible policy
  before writing.
- Reply grounding is part of the user-visible contract. A correct Mongo row is
  still a finding if the reply contradicts date, recurrence, or precision.

## Verification Plan

Unit tests:

- `tests/unit/agent/test_reminder_intent_capability.py`
  - PR-14: `昨天 10 点` returns no-write invalid-schedule/future-time prompt.
  - PR-15: explicit `今天 HH:mm` just before `current_time` returns no write.
  - PR-17: bare past clock rolls to tomorrow; bare future clock stays today.
  - PR-17: bare one-shot wording does not add `rrule`.
  - PR-18: `5 分钟后` uses runtime `current_time`; `明早` and `下下周三`
    return `date_only_missing_time`.
  - PR-19: seconds are preserved in the decision passed to the executor, or
    explicit minute-precision clarification is returned if product changes.
- `tests/unit/agent/test_reminder_command_executor.py`
  - executor forwards second-bearing `trigger_at`;
  - reply facts include stored `local_date`, `local_time`, and `rrule`.
- `tests/unit/agent/test_visible_reminder_protocol_tool.py`
  - one-shot past create returns user-safe `past_one_shot` failure;
  - second-bearing one-shot create stores/displays seconds when nonzero;
  - batch dedupe does not collapse distinct second-level times unless product
    explicitly chooses minute precision.

Smoke/eval:

- Re-run Batch B with GLM-5.1 thinking-off after unit tests pass.
- Minimum targeted rerun: PR-14, PR-15, PR-17, PR-18, PR-19 on a fresh account.
- Preferred rerun: full Batch B, because PR-23/PR-24 depend on earlier created
  reminder state and can expose reply-grounding regressions.
- Save evidence under `artifacts/evidence/shared-reminder-agent-smoke/`.

Expected smoke outcomes:

- PR-14: no write; visible invalid-past reply.
- PR-15: no write; visible invalid-past or future-time prompt.
- PR-17: correct today/tomorrow schedule; reply matches stored date/time and
  recurrence.
- PR-18: one write for `5 分钟后`; no writes for `明早` and `下下周三` without
  clock.
- PR-19: seconds preserved and visible, or explicit precision handling with no
  silent truncation.

## Reviewable Summary

- The cluster is a shared time-evidence invariant failure, not one parser bug.
- PR-14/15 need deterministic past-time refusal before or at the reminder
  runtime boundary.
- PR-17 needs bare-clock normalization coverage plus reply grounding from
  stored operation facts.
- PR-18 needs a missing-clock guard for vague relative dates/day periods while
  preserving relative-delay creation.
- PR-19 should preserve explicit seconds end to end; any minute-precision
  policy must be visible, never silent.
- The fix belongs in worker-runtime detector/normalizer and reminder protocol
  layers, not gateway, compatibility shims, or case-injected prompt examples.
