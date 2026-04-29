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

- One-case normal-path evidence is saved through `case292`.
- The next case is `case293`; with `1892` total corpus cases, `1599` offsets
  remain from `293` through `1891`.
- `case287` fixed a detector/chat handoff bug: when ReminderDetect completes
  with a structured non-executable query/discussion decision, ChatWorkflow should
  not inject the pending-reminder setup notice.
- `case288` added a fixture clarification expectation for a "later today"
  reminder request with no concrete clock time.
- `case292` fixed a no-action ReminderDetect chat boundary: when reminder terms
  are only the discussion topic, chat may ask whether a reminder is wanted but
  should not promise an unscheduled reminder.
- Continue with one case at a time, saving evidence and clearing logs after each
  case.
- Future failures must be handled in this priority order: schema field
  constraints, fixture counterexamples/classification, then LLM judge rubric.
  Do not append prohibition phrases to `CONTEXTPROMPT_提醒未执行` or expand
  regex blacklists to pass a case.
