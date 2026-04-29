# Reminder Real Corpus Class-E2E Eval

## Goal

Build a class-E2E reminder eval runner for `scripts/reminder_test_cases.json`.
The runner simulates user input through the agent message path, captures
user-visible output, observes reminder CRUD, and virtually validates created
reminders can fire without waiting for wall-clock time.

## Current Scope

- Each case uses the corpus `metadata.from_user` and `metadata.source_id` as the
  simulated terminal-style user and conversation.
- Reminder persistence, scheduler jobs, and outbound messages are isolated per
  case in memory.
- CLI defaults to 16-way concurrency and process isolation so a blocked model
  call becomes `case_timeout` instead of hanging the whole run.
- Real external-model smoke requires explicit approval because it exports
  corpus user messages and identifiers to the configured model provider.

## Verification

- `pytest tests/evals/test_reminder_tool_eval.py tests/evals/test_reminder_e2e_eval.py -q`
- `python -m py_compile scripts/eval_reminder_e2e_cases.py`
- `python scripts/eval_reminder_e2e_cases.py --limit 0 --concurrency 2 --case-timeout-seconds 1`
- Sandbox smoke:
  `python scripts/eval_reminder_e2e_cases.py --limit 1 --concurrency 1 --case-timeout-seconds 5 --output /tmp/reminder-e2e-smoke-1.json`
  returns `case_timeout` and does not hang.

## 2026-04-29 Normal-Path Reminder Loop Status

- One-case normal-path evidence is saved through `case394`.
- The next case is `case395`; with `1892` total corpus cases, `1497` offsets
  remain from `395` through `1891`.
- `case287` fixed a detector/chat handoff bug: when ReminderDetect completes
  with a structured non-executable query/discussion decision, ChatWorkflow should
  not inject the pending-reminder setup notice.
- `case288` added a fixture clarification expectation for a "later today"
  reminder request with no concrete clock time.
- `case292` fixed a no-action ReminderDetect chat boundary: when reminder terms
  are only the discussion topic, chat may ask whether a reminder is wanted but
  should not promise an unscheduled reminder.
- `case293` fixed shared expected-title extraction for
  `<time>的提醒，<title>` phrasing.
- `case294` fixed list-query direct replies so ReminderDetect `query/list`
  results return the tool summary instead of going through ChatWorkflow.
- `case295` fixed shared expected-title normalization for nominal `的提醒`
  suffixes, and tightened ReminderDetectRetry guidance so single create retries
  use top-level `title`/`trigger_at` instead of update-only fields.
- `case297` fixed reminder-status complaint routing so messages like
  "为什么刚刚没有叫我" go through ReminderDetect without waiting on Orchestrator.
- `case300` added a clarification expectation for a bare future plan with time
  and task, and routes time-plus-task schedule statements through ReminderDetect
  without waiting on Orchestrator.
- `case304` added a clarification expectation for finish-trigger reminder
  requests like "看完" that lack a concrete trigger time or cadence.
- `case305` added a clarification expectation for explicit reminder requests
  that provide content but no concrete trigger time.
- `case306` added a clarification expectation for explicit reminder requests
  that provide a time but no reminder content; the passing live run was slow
  after detector and retry timeouts but ended in a safe clarification.
- `case307` and `case308` passed without code or fixture changes.
- `case309` added a clarification expectation for vague "after a while"
  reminder requests that lack a concrete trigger.
- `case310` through `case312` passed without code or fixture changes.
- `case313` fixed nightly cadence schema validation so `每晚`/`每夜` count as
  concrete recurring cadence evidence, and added a recurring expected-create
  fixture for the nightly 22:30 wash-up reminder.
- `case314` tightened no-action reminder chat context so follow-up reminder
  questions are phrased as optional confirmation, and added a discussion
  expectation for a tentative exercise plan without reminder intent.
- `case315` passed without code or fixture changes.
- `case316` added a discussion expectation for a wake-up status statement
  without reminder intent; first run hit the chat timeout fallback, rerun passed
  with a normal discussion reply but remained slow.
- `case317` through `case330` passed without code or fixture changes.
- `case331` added a clarification expectation for a date-only reminder request
  with content but no clock time; the runtime correctly asks what time next
  Monday instead of inventing a default.
- `case332` passed without code or fixture changes.
- `case333` tightened ReminderDetect structured schema validation so executable
  datetime fields require an explicit timezone, and added an expected-create
  fixture for the corpus-anchored late-afternoon interpretation of `4:37`.
- `case334` passed without code or fixture changes.
- `case335` added a discussion expectation for a question about how the agent
  knew a prior schedule, and clarified the unconfirmed-reminder judge rubric so
  memory/reference replies are not treated as future reminder promises.
- `case336` through `case342` passed without code or fixture changes.
- `case343` through `case348` passed without code or fixture changes.
- `case349` first hit a provider/runtime timeout in ReminderDetect and retry;
  rerun passed without code changes.
- `case350` through `case358` passed without code or fixture changes.
- `case359` exposed a time-bounded study-plan boundary: the chat reply promised
  an uncreated reminder after ReminderDetect returned discussion. The detector
  prompt now classifies future plan-with-time statements as clarification, the
  local routing guard sends `学到/做到/写到 <time>` study/work plans through
  ReminderDetect, and the case fixture expects clarification.
- `case360` through `case363` passed without code or fixture changes.
- `case364` added a discussion expectation for a past status report with a
  clock time (`刚刚16:58...开始学习了`) that should not create a reminder.
- `case365` and `case366` passed without code or fixture changes.
- `case367` added `FREQ=MINUTELY;INTERVAL=n` support for explicit unbounded
  minute-interval reminders such as `每隔10min提醒我...`.
- `case368` and `case369` passed without code or fixture changes.
- `case370` passed without code or fixture changes.
- `case371` added a clarification expectation for a date-only next-Monday
  reminder request with content but no clock time, and shortened the
  clarification-output LLM judge prompt after repeated judge timeouts on clear
  time-clarification replies.
- `case372` and `case373` passed without code or fixture changes.
- `case374` added a clarification expectation for a broad request to end
  today's reminders without identifying the target reminder.
- `case375` and `case376` passed without code or fixture changes.
- `case377` added a clarification expectation for a detailed daily plan with
  vague "occasionally remind me" supervision scope, raised ReminderDetectRetry
  output capacity for long structured decisions, tightened retry datetime/action
  field constraints, and fixed the primary-timeout retry path so invalid
  schedule evidence returns a clarification tool result instead of falling
  through to chat.
- `case378` and `case379` passed without code or fixture changes.
- `case380` added a query expectation for asking whether an alarm/reminder is
  set (`有定闹钟`), which should list reminder status instead of creating one.
- `case381` through `case387` passed without code or fixture changes.
- `case388` added a clarification expectation for a meeting reminder that says
  to remind "in advance" but omits the lead time; the first rerun hit a
  clarification-judge timeout, and the next rerun passed.
- `case389` added a clarification expectation for advance-reminder lead times
  with no base event or event time; one rerun hit a clarification-judge timeout,
  and the next rerun passed.
- `case390` added a clarification expectation for a detailed time-blocked task
  list without explicit reminder intent; the runtime asked which tasks should be
  reminded instead of creating reminders for the whole list.
- `case391` added a clarification expectation for an isolated follow-up-style
  request to remind about study-related tasks without the referenced schedule in
  the current turn; one rerun timed out and later wrote the generic timeout
  fallback, and the next rerun passed.
- `case392` and `case393` passed without code or fixture changes; `case393`
  was slow and returned the generic timeout fallback for a no-reminder status
  update.
- `case394` added a clarification expectation for a clock-time study statement
  without explicit reminder intent; one rerun hit a clarification-judge timeout,
  and the next rerun passed.
- Continue with one case at a time, saving evidence and clearing logs after each
  case.
- Future failures must be handled in this priority order: schema field
  constraints, fixture counterexamples/classification, then LLM judge rubric.
  Do not append prohibition phrases to `CONTEXTPROMPT_提醒未执行` or expand
  regex blacklists to pass a case.
