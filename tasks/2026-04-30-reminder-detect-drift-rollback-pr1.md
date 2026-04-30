# Reminder Detect Drift Rollback PR1

## Scope

Implement PR1 from `docs/superpowers/specs/2026-04-30-reminder-detect-drift-rollback-design.md`.

## Changes

- Remove post-LLM schedule-evidence and clock/time validators from `PrepareWorkflow`.
- Let schema-valid `ReminderDetectDecision` results execute through `visible_reminder_tool`.
- Keep retry for LLM timeout and structured schema failures only.
- Delete unit tests that pinned the removed Python semantic validator.

## Verification

- `pytest tests/unit/test_prepare_workflow_reminder_guard.py -q`
- `pytest tests/unit/test_reminder_detect_structured_output.py -q`
- `pytest tests/unit/prompt/test_agent_instructions_prompt.py -q`
- `pytest tests/evals/test_reminder_normal_path_eval.py -q`

## Notes

- `pytest tests/unit/ -q` currently reaches `624 passed` and fails one guardrail-script test because the local rollback diff is intentionally over the review-trigger oversized-change threshold.
