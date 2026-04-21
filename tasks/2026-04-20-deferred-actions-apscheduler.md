# Task: Deferred Actions APScheduler Reset

- Status: Completed
- Owner: Codex
- Date: 2026-04-20

## Goal

Replace the split `future` and `reminder` runtime with a clean-break deferred
actions system backed by MongoDB business state and a single in-process
APScheduler 3.x instance.

## Scope

- In scope:
  - unified `deferred_actions` domain model
  - APScheduler 3.x in-process trigger runtime
  - RRULE-based recurrence storage and next-run calculation
  - internal-only proactive follow-up actions
  - user-visible reminder management on top of the same substrate
- Out of scope:
  - backward compatibility with existing reminder/future data or prompts
  - old-data migration
  - Temporal adoption
  - multi-replica scheduler deployment

## Touched Surfaces

- worker-runtime
- repo-os

## Acceptance Criteria

- A written design defines the replacement runtime, data model, lifecycle, and
  reliability rules.
- The design explicitly removes `conversation_info.future` and the legacy
  reminder runtime from the new architecture.
- The design keeps MongoDB as source of truth and limits APScheduler to
  next-fire triggering.
- A follow-up execution plan breaks the work into reviewable implementation
  steps.

## Verification

- Command: `test -f tasks/2026-04-20-deferred-actions-apscheduler.md && test -f docs/superpowers/specs/2026-04-20-deferred-actions-apscheduler-design.md && test -f docs/exec-plans/2026-04-21-deferred-actions-apscheduler-plan.md`
- Command: `pytest tests/unit/dao/test_deferred_action_dao.py tests/unit/dao/test_deferred_action_occurrence_dao.py -v`
- Command: `pytest tests/unit/runner/test_deferred_action_policy.py tests/unit/runner/test_deferred_action_scheduler.py tests/unit/runner/test_agent_runner_deferred_actions.py tests/unit/runner/test_deferred_action_executor.py tests/unit/runner/test_deferred_action_message_source.py tests/unit/runner/test_background_handler_deferred_only.py tests/unit/runner/test_background_conversation_participants.py -v`
- Command: `pytest tests/unit/agent/test_deferred_action_service.py tests/unit/agent/test_post_analyze_deferred_actions.py tests/unit/test_context_retrieve_deferred_reminders.py tests/unit/agent/test_agent_handler.py tests/unit/test_clawscale_only_topology.py tests/unit/test_repo_os_structure.py -v`
- Command: `pytest tests/e2e/test_deferred_actions_flow.py -v`
- Command: `zsh scripts/verify-surface worker-runtime`
- Command: `zsh scripts/check`
- Expected evidence: deferred-action worker runtime, repo-os checks, and deferred-actions e2e flow all pass with the final clean-break architecture.

## Notes

The user explicitly requested a clean break: no migration, no compatibility
layer, and internal proactive follow-up actions remain hidden from user-facing
query/update/delete flows.

Plan: `docs/exec-plans/2026-04-21-deferred-actions-apscheduler-plan.md`

Result:

- Deferred reminders and internal follow-ups now share the `deferred_actions`
  substrate plus `deferred_action_occurrences`.
- The worker boots one in-process APScheduler runtime and executes due actions
  through the normal conversation lock boundary.
- Legacy reminder/future runtime paths, DAO, tools, tests, and e2e cases were
  removed from this branch.
