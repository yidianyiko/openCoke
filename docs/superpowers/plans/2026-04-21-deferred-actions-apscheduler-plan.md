# Deferred Actions APScheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> Status note (2026-04-22): This historical plan has been completed on the
> `compat-retirement-reminders` branch. `deferred_actions` and
> `deferred_action_occurrences` are the live scheduling runtime, no active
> runtime path depends on `conversation_info.future`, and
> `scripts/retire_legacy_reminder_compat.py` is the cleanup entrypoint for
> retiring the legacy `reminders` collection and related compatibility fields.

**Goal:** Replace the split future/reminder runtime with a clean-break
deferred-actions system backed by MongoDB business state, RRULE recurrence, and
a single in-process APScheduler 3.x instance.

**Architecture:** MongoDB remains the only source of truth via `deferred_actions` and `deferred_action_occurrences`. APScheduler 3.x only schedules the next concrete fire time for each active action. Triggered actions enter through a single deferred-action executor that acquires the normal conversation turn lock before calling `handle_message()`.

**Tech Stack:** Python 3.12, APScheduler 3.11.x, python-dateutil, MongoDB, pytest, pytest-asyncio

---

## File Map

- Create: `dao/deferred_action_dao.py`
  Owns CRUD, indexes, revision fencing helpers, and active-action queries.
- Create: `dao/deferred_action_occurrence_dao.py`
  Owns occurrence claiming, attempt counting, and trigger-key idempotency.
- Create: `agent/runner/deferred_action_policy.py`
  Owns RRULE parsing, next occurrence calculation, expiry/max-runs handling, and retry backoff rules.
- Create: `agent/runner/deferred_action_scheduler.py`
  Owns APScheduler bootstrap, startup reconciliation, schedule/register/remove, and rebuild from Mongo.
- Create: `agent/runner/deferred_action_executor.py`
  Owns job fire handling, conversation lock acquisition, action lease claim, occurrence claim, retry handling, and success/failure transitions.
- Create: `agent/agno_agent/tools/deferred_action/service.py`
  Owns business-layer create/update/delete/list/complete for visible reminders plus internal follow-up create/replace/clear.
- Create: `agent/agno_agent/tools/deferred_action/time_parser.py`
  Owns explicit reminder time parsing into timezone-aware datetimes for `dtstart`.
- Create: `agent/agno_agent/tools/deferred_action/tool.py`
  Owns Agno tool wrappers for visible reminder management.
- Modify: `agent/runner/agent_runner.py`
  Boot the single scheduler instance and hand it to the worker runtime.
- Modify: `agent/runner/agent_handler.py`
  Introduce `message_source="deferred_action"` and branch templates/metadata by action kind.
- Modify: `agent/runner/agent_background_handler.py`
  Remove legacy future/reminder polling paths and leave only unrelated background work.
- Modify: `agent/agno_agent/workflows/prepare_workflow.py`
  Replace reminder-tool integration with the new deferred-action reminder path.
- Modify: `agent/agno_agent/workflows/post_analyze_workflow.py`
  Replace `conversation_info.future` writes with internal proactive follow-up create/replace/clear calls.
- Modify: `agent/agno_agent/schemas/post_analyze_schema.py`
  Replace `FutureResponse` with a new internal follow-up planning payload.
- Modify: `agent/agno_agent/workflows/chat_workflow_streaming.py`
  Route deferred-action message rendering through one source with kind-specific templates.
- Modify: `agent/prompt/chat_taskprompt.py`
  Remove old `FutureResponse` contract and add the new proactive follow-up planning contract.
- Modify: `agent/prompt/chat_contextprompt.py`
  Replace separate future/reminder templates with deferred-action templates keyed by kind.
- Modify: `agent/prompt/agent_instructions_prompt.py`
  Remove old reminder/future wording and document the new reminder-only visible tool surface.
- Modify: `agent/agno_agent/tools/context_retrieve_tool.py`
  Replace any direct future/reminder reads with visible reminder lookups from `deferred_actions`.
- Modify or delete legacy reminder modules under `agent/agno_agent/tools/reminder/`
  Remove or archive old service/validator/formatter/parser modules once callers are cut over.
- Modify or delete: `dao/reminder_dao.py`
  Remove old runtime use after cutover if no remaining references exist.
- Update docs: `docs/architecture.md`, `docs/fitness/coke-verification-matrix.md`, and the task file
- Create tests:
  - `tests/unit/dao/test_deferred_action_dao.py`
  - `tests/unit/dao/test_deferred_action_occurrence_dao.py`
  - `tests/unit/agent/runner/test_deferred_action_policy.py`
  - `tests/unit/agent/runner/test_deferred_action_scheduler.py`
  - `tests/unit/agent/runner/test_deferred_action_executor.py`
  - `tests/unit/agent/agno_agent/tools/deferred_action/test_service.py`
  - `tests/unit/agent/agno_agent/workflows/test_post_analyze_deferred_actions.py`
  - `tests/unit/agent/runner/test_deferred_action_message_source.py`
  - `tests/e2e/test_deferred_actions_flow.py`

## Task 1: Add Dependencies And Core DAOs

**Files:**
- Modify: `requirements.txt`
- Create: `dao/deferred_action_dao.py`
- Create: `dao/deferred_action_occurrence_dao.py`
- Test: `tests/unit/dao/test_deferred_action_dao.py`
- Test: `tests/unit/dao/test_deferred_action_occurrence_dao.py`

- [ ] Add `APScheduler==3.11.2` and `python-dateutil>=2.9.0` to `requirements.txt`.
- [ ] Write DAO tests for:
  - collection names
  - index creation
  - create/get/update lifecycle transitions
  - active-action lookup by `next_run_at`
  - occurrence `trigger_key` uniqueness
- [ ] Implement `DeferredActionDAO` with helpers for:
  - `create_action()`
  - `get_action()`
  - `update_action()`
  - `claim_action_lease(action_id, revision, scheduled_for, lease_until)`
  - `release_action_lease()`
  - `list_active_actions()`
  - `reconcile_expired_leases()`
- [ ] Implement `DeferredActionOccurrenceDAO` with helpers for:
  - `claim_or_get_occurrence(trigger_key, scheduled_for)`
  - `mark_occurrence_succeeded()`
  - `mark_occurrence_failed()`
  - `increment_attempt_count()`
- [ ] Run:
  - `pytest tests/unit/dao/test_deferred_action_dao.py -v`
  - `pytest tests/unit/dao/test_deferred_action_occurrence_dao.py -v`
- [ ] Commit: `feat(deferred-actions): add core MongoDAOs`

## Task 2: Add RRULE And Retry Policy Engine

**Files:**
- Create: `agent/runner/deferred_action_policy.py`
- Test: `tests/unit/agent/runner/test_deferred_action_policy.py`

- [ ] Write policy tests for:
  - one-shot actions
  - recurring RRULE next occurrence calculation
  - `max_runs`
  - `expires_at`
  - startup coalescing of overdue recurring actions
  - capped exponential retry backoff
- [ ] Implement policy helpers:
  - `parse_rrule(dtstart, rrule)`
  - `compute_initial_next_run_at(action, now)`
  - `compute_next_run_after_success(action, scheduled_for, now)`
  - `compute_retry_at(action, attempt_count, now)`
  - `should_terminally_fail_occurrence(action, attempt_count)`
- [ ] Ensure policy always uses timezone-aware datetimes and advances recurring actions from the original occurrence, not from retry time.
- [ ] Run: `pytest tests/unit/agent/runner/test_deferred_action_policy.py -v`
- [ ] Commit: `feat(deferred-actions): add recurrence and retry policy engine`

## Task 3: Add Scheduler Runtime And Startup Reconciliation

**Files:**
- Create: `agent/runner/deferred_action_scheduler.py`
- Modify: `agent/runner/agent_runner.py`
- Test: `tests/unit/agent/runner/test_deferred_action_scheduler.py`

- [ ] Write scheduler tests for:
  - single APScheduler instance creation
  - startup lease reconciliation before schedule rebuild
  - registration payload includes `action_id`, `scheduled_for`, `revision`
  - reschedule/remove behavior
  - overdue-action immediate registration on startup
- [ ] Implement `DeferredActionScheduler` with:
  - `start()`
  - `shutdown()`
  - `load_from_storage()`
  - `register_action(action)`
  - `remove_action(action_id)`
  - `reschedule_action(action)`
- [ ] Modify `agent_runner.py` to boot one scheduler instance before worker/background loops and share it with the deferred-action service/runtime.
- [ ] Run: `pytest tests/unit/agent/runner/test_deferred_action_scheduler.py -v`
- [ ] Commit: `feat(deferred-actions): add in-process APScheduler runtime`

## Task 4: Add Deferred Action Executor

**Files:**
- Create: `agent/runner/deferred_action_executor.py`
- Modify: `agent/runner/agent_handler.py`
- Test: `tests/unit/agent/runner/test_deferred_action_executor.py`
- Test: `tests/unit/agent/runner/test_deferred_action_message_source.py`

- [ ] Write executor tests for:
  - stale job payload rejected by revision or `scheduled_for` mismatch
  - conversation lock acquired before `handle_message()`
  - duplicate wakeup becomes no-op via occurrence claim
  - success path updates lifecycle and reschedules recurring actions
  - failure path retries one-shot actions
  - terminal failure marks one-shot `failed`
- [ ] Implement executor flow:
  - acquire conversation lock
  - claim action lease with revision fence
  - claim occurrence
  - build deferred-action metadata
  - call `handle_message()`
  - update success/failure state
- [ ] Modify `agent_handler.py` to support `message_source="deferred_action"` plus kind-aware rendering hooks.
- [ ] Run:
  - `pytest tests/unit/agent/runner/test_deferred_action_executor.py -v`
  - `pytest tests/unit/agent/runner/test_deferred_action_message_source.py -v`
- [ ] Commit: `feat(deferred-actions): add executor and unified message source`

## Task 5: Add Visible Reminder Service And Tool Surface

**Files:**
- Create: `agent/agno_agent/tools/deferred_action/service.py`
- Create: `agent/agno_agent/tools/deferred_action/time_parser.py`
- Create: `agent/agno_agent/tools/deferred_action/tool.py`
- Modify: `agent/agno_agent/workflows/prepare_workflow.py`
- Modify: `agent/prompt/agent_instructions_prompt.py`
- Test: `tests/unit/agent/agno_agent/tools/deferred_action/test_service.py`

- [ ] Write service tests for:
  - create visible one-shot reminder
  - create recurring RRULE reminder
  - list only visible reminders
  - update visible reminder and increment revision
  - delete/complete visible reminder and unschedule it
  - reject management of internal proactive follow-ups
- [ ] Implement the service methods:
  - `create_visible_reminder()`
  - `list_visible_reminders()`
  - `update_visible_reminder()`
  - `delete_visible_reminder()`
  - `complete_visible_reminder()`
- [ ] Implement time parsing into timezone-aware `dtstart` plus direct RRULE acceptance.
- [ ] Replace old reminder-tool wiring in `PrepareWorkflow` with the new tool module.
- [ ] Update instructions prompt so the visible tool surface only exposes reminder management and does not mention old future behavior.
- [ ] Run: `pytest tests/unit/agent/agno_agent/tools/deferred_action/test_service.py -v`
- [ ] Commit: `feat(deferred-actions): add visible reminder service and tool surface`

## Task 6: Rewrite Post-Analyze Follow-Up Planning

**Files:**
- Modify: `agent/agno_agent/schemas/post_analyze_schema.py`
- Modify: `agent/agno_agent/workflows/post_analyze_workflow.py`
- Modify: `agent/prompt/chat_taskprompt.py`
- Modify: `agent/prompt/chat_contextprompt.py`
- Test: `tests/unit/agent/agno_agent/workflows/test_post_analyze_deferred_actions.py`

- [ ] Replace `FutureResponse` with a new internal follow-up planning payload that contains:
  - `FollowupTime`
  - `FollowupPrompt`
  - `FollowupAction` (`create | replace | clear`)
- [ ] Write workflow tests for:
  - create internal proactive follow-up
  - replace existing internal proactive follow-up
  - clear internal proactive follow-up
  - skip proactive follow-up when a timed visible reminder was created in the same turn
- [ ] Implement post-analyze write path to call the new deferred-action service instead of mutating `conversation_info.future`.
- [ ] Rewrite task/context prompts so they refer to internal follow-up planning instead of legacy `FutureResponse`.
- [ ] Run: `pytest tests/unit/agent/agno_agent/workflows/test_post_analyze_deferred_actions.py -v`
- [ ] Commit: `feat(deferred-actions): rewrite proactive follow-up planning`

## Task 7: Cut Over Runtime Reads And Delete Legacy Trigger Paths

**Files:**
- Modify: `agent/runner/agent_background_handler.py`
- Modify: `agent/agno_agent/tools/context_retrieve_tool.py`
- Delete or modify: `dao/reminder_dao.py`
- Delete or modify legacy modules under `agent/agno_agent/tools/reminder/`

- [ ] Remove legacy reminder polling from `agent_background_handler.py`.
- [ ] Remove legacy future polling from `agent_background_handler.py`.
- [ ] Replace context retrieval of future/reminder state with visible reminder reads from `deferred_actions`.
- [ ] Remove dead references to `conversation_info.future`, legacy reminder IDs, and old reminder collections.
- [ ] Run focused searches and ensure there are no runtime reads/writes left:
  - `rg -n "conversation_info\\.future|message_source=\\\"future\\\"|message_source=\\\"reminder\\\"|reminder_dao|handle_pending_future_message|handle_pending_reminders" agent dao tests`
- [ ] Commit: `refactor(deferred-actions): remove legacy future and reminder runtime`

## Task 8: Add Integration And End-To-End Coverage

**Files:**
- Create: `tests/e2e/test_deferred_actions_flow.py`
- Modify/create any shared fixtures needed under `tests/`

- [ ] Add integration coverage for:
  - startup recovery of active future-dated actions
  - startup recovery of expired leases
  - duplicate scheduler fire blocked by occurrence claim
  - one-shot reminder success path
  - recurring reminder success and reschedule path
  - proactive follow-up hidden from visible management APIs
- [ ] Add one e2e flow that covers:
  - user creates a recurring reminder
  - worker restarts
  - reminder fires once
  - next occurrence is rescheduled
  - post-analyze writes an internal follow-up that remains invisible to user list/delete flows
- [ ] Run:
  - `pytest tests/unit/agent/runner/test_deferred_action_scheduler.py tests/unit/agent/runner/test_deferred_action_executor.py -v`
  - `pytest tests/unit/agent/agno_agent/workflows/test_post_analyze_deferred_actions.py tests/unit/agent/agno_agent/tools/deferred_action/test_service.py -v`
  - `pytest tests/e2e/test_deferred_actions_flow.py -v`
- [ ] Commit: `test(deferred-actions): add integration and e2e coverage`

## Task 9: Update Docs And Verification Surface

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/fitness/coke-verification-matrix.md`
- Modify: `tasks/2026-04-20-deferred-actions-apscheduler.md`

- [ ] Update `docs/architecture.md` so the current runtime topology describes:
  - `deferred_actions`
  - `deferred_action_occurrences`
  - in-process APScheduler 3.x
  - unified deferred-action execution path
- [ ] Update `docs/fitness/coke-verification-matrix.md` with the focused worker-runtime commands for the new scheduler/executor/tests.
- [ ] Update the task file status and notes to reflect the final approved architecture and plan location.
- [ ] Run:
  - `zsh scripts/verify-surface worker-runtime`
  - `test -f docs/superpowers/specs/2026-04-20-deferred-actions-apscheduler-design.md`
  - `test -f docs/exec-plans/2026-04-21-deferred-actions-apscheduler-plan.md`
- [ ] Commit: `docs(deferred-actions): update runtime architecture and verification docs`

## Verification

- Unit:
  - `pytest tests/unit/dao/test_deferred_action_dao.py tests/unit/dao/test_deferred_action_occurrence_dao.py -v`
  - `pytest tests/unit/agent/runner/test_deferred_action_policy.py tests/unit/agent/runner/test_deferred_action_scheduler.py tests/unit/agent/runner/test_deferred_action_executor.py -v`
  - `pytest tests/unit/agent/agno_agent/tools/deferred_action/test_service.py tests/unit/agent/agno_agent/workflows/test_post_analyze_deferred_actions.py -v`
- Integration:
  - `pytest tests/e2e/test_deferred_actions_flow.py -v`
- Repo surface:
  - `zsh scripts/verify-surface worker-runtime`

## Notes

- This plan intentionally contains no migration tasks and no compatibility work.
- The implementation must treat MongoDB as the only source of truth; APScheduler jobs are cache.
- Hidden proactive follow-ups are part of the same substrate but never appear in user-facing reminder management.
