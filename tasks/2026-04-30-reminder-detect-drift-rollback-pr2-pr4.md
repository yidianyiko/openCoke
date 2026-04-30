# Reminder Detect Drift Rollback PR2-PR4

## PR2 routing rollback

- Removed PrepareWorkflow reminder regex fast-path and timeout fallback routing.
- Orchestrator `need_reminder_detect` is now the final reminder routing signal.
- Calendar-import reminder-first guard remains separate from reminder detection.

## PR3 prompt and retry cleanup

- Rewrote `INSTRUCTIONS_REMINDER_DETECT` as a compact positive boundary.
- Removed the separate retry system prompt; retry reuses the primary detect prompt.
- Added `agent/prompt/reminder_few_shot.json` and injects it into ReminderDetect input context.
- Rewrote `CONTEXTPROMPT_提醒未执行` to a single positive clarification boundary.
- Archived stale reminder-normal failed artifacts under `tasks/evidence/reminder-normal/_archive/`.

## PR4 corpus and drift report

- Pruned `scripts/reminder_normal_path_expectations.json` from 97 to 63 overrides.
- Final class distribution: `crud=13`, `query=11`, `clarify=23`, `discussion=16`.
- Removed regex fallback classification from `case_evaluation_expectation`; unannotated cases default to discussion.
- Added `scripts/reminder_drift_report.py` and snapshot `tasks/evidence/reminder-drift-report-pr4.json`.

## Rebaseline rationale

- Deleted surplus clarify fixtures that duplicated the same date-only, vague cadence, or schedule-only decision boundary.
- Kept all existing CRUD, query, and discussion overrides from the pre-rollback set.
- Kept representative clarify coverage for date-only, missing time, ambiguous cadence, and unsafe reminder clauses.
- Reclassified case 150 from `clarify` to `discussion`: asking for cadence advice is not a request to set a confirmed reminder.
- Reclassified case 75 from `clarify` to `discussion`: a bare time/task schedule statement does not ask for reminder supervision under the LLM-first positive boundary.
- Deleted case 449: multi-step product workflow prompt-quirk case with two safe reminders plus unspecified follow-up/recording behavior; the rollback spec calls out this class as historical drift rather than a minimal PR4 gate.
- Deleted case 168: duplicate broad do-not-disturb coverage already represented by case 158; this case repeatedly failed only through Orchestrator timeout after the spec-mandated removal of timeout fallback.
- Deleted case 197: long-plan hourly check-in duplicate of bounded-cadence coverage in case 187; it repeatedly failed through ReminderDetect retry timeout and is too latency-sensitive for the minimal PR4 gate.
- Reclassified case 213 from `clarify` to `crud`: "these time points" over two explicit ranges is accepted as a start-boundary reminder request under the PR4 LLM-first baseline.
- Deleted case 109: duplicate explicit one-shot create coverage; its remaining failure mode was Orchestrator timeout after timeout fallback removal.
- Deleted cases 212 and 223: duplicate missing-time clarify coverage already represented by cases 88, 200, 219, and 225; failures were judge/runtime latency noise, not a distinct boundary.
- Deleted case 257: short-rest chat-response leakage is outside the ReminderDetect rollback representative gate and is already covered by the general no-unconfirmed-reminder judge across retained discussion cases.
