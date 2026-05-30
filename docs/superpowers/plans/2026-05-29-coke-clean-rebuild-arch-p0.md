# Architecture P0 Invariants Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four P0 architecture-invariant gaps from `docs/issues/2026-05-31-implementation-conformance-audit.md` without touching the concurrent agent-prompt or settings work.

**Architecture:** Keep the clean-rebuild contracts in the existing bounded contexts. ConversationRuntime owns replay/freshness disposition, TurnRunner owns turn reconciliation and delivery callback dispatch, Reminder owns personal reminder facts/fire lifecycle/outbox, and SocialScheduling owns notification-recipient delivery lifecycle. No schema fork, legacy import, regex routing, compatibility shim, or fallback prose is introduced.

**Tech Stack:** Python 3.12, SQLAlchemy Core/ORM sessions, Flask blueprints for optional internal callbacks, in-memory repositories for pure unit tests, Postgres repositories for gated integration tests.

**Plan Status:** complete

---

## File Structure

- Modify: `coke/domains/conversation_runtime/models.py`
  - Add reconciliation metadata for replayed turns if needed.
- Modify: `coke/domains/conversation_runtime/repository.py`
  - Add read helpers for existing outbound messages/dispositions and atomic expected-version guard support.
- Modify: `coke/domains/conversation_runtime/service.py`
  - Add replay reconciliation and commit-time stale-state guard helpers that record `superseded`.
- Modify: `coke/turn/runner.py`
  - Skip/reconcile replayed terminal turns, avoid duplicate delivery, and send delivery outcomes to lifecycle callbacks.
- Modify: `coke/composition.py`
  - Return `DeliveryAttempt` from outbound delivery and register lifecycle callback services without editing agent prompt/settings files.
- Modify: `coke/domains/reminder/models.py`
  - Add command context and outbox event models needed by the existing `outbox` table.
- Modify: `coke/domains/reminder/repository.py`
  - Add same-transaction reminder write + outbox methods and in-memory parity.
- Modify: `coke/domains/reminder/service.py`
  - Make CRUD accept an optional expected-version guard and emit outbox rows in the same commit.
- Modify: `coke/domains/social_scheduling/service.py`
  - Make state-changing methods accept an optional expected-version guard and expose idempotent notification delivery writeback.
- No change: `coke/api/reminder_routes.py`, `coke/api/friend_routes.py`, `coke/api/shared_reminder_routes.py`
  - Direct web/API calls preserve the default `commit_guard=None` behavior.
- No change: `coke/app.py`
  - Delivery lifecycle writeback is wired in composition, so no internal callback route was needed.
- Create or modify tests under:
  - `tests/unit/coke/turn/test_turn_runner.py`
  - `tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py`
  - `tests/unit/coke/reminder/test_reminder_service.py`
  - `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`
  - `tests/integration/coke/repositories/test_reminder_atomic_outbox_contract.py`
  - `tests/integration/coke/test_runtime_wiring.py` if end-to-end Postgres wiring needs coverage.

## Task 1: Same-Trigger Replay Idempotency

**Files:**
- Modify: `tests/unit/coke/turn/test_turn_runner.py`
- Modify: `coke/domains/conversation_runtime/service.py`
- Modify: `coke/turn/runner.py`

- [x] **Step 1: Write failing replay tests**

Add tests proving replay of the same `trigger_id` does not invoke the agent, execute reminder tools, or deliver duplicate visible output after a terminal turn already has output. Also cover an existing `no_reply`, `failed`, or `superseded` disposition returning the existing state without re-running business logic.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_replayed_inbound_turn_with_existing_reply_reconciles_without_agent_or_delivery -v
```

Expected before implementation: FAIL because `TurnRunner.run_inbound_turn` ignores `start.replayed`.

- [x] **Step 2: Implement replay reconciliation**

Use existing `ConversationRuntimeService.start_turn(...).replayed`; when true, read the turn disposition and outbound messages. If a terminal disposition exists, return it with existing visible text and do not acquire the domain tool path or call `outbound_delivery.deliver`. If no terminal disposition exists, continue only for unfinished/pending reconciliation where no facts/output exist.

- [x] **Step 3: Run replay test green**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_replayed_inbound_turn_with_existing_reply_reconciles_without_agent_or_delivery -v
```

Expected after implementation: PASS.

## Task 2: Atomic Freshness Commit Guard

**Files:**
- Modify: `tests/unit/coke/turn/test_turn_runner.py`
- Modify: `tests/unit/coke/reminder/test_reminder_service.py`
- Modify: `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`
- Modify: `coke/domains/conversation_runtime/service.py`
- Modify: `coke/domains/reminder/service.py`
- Modify: `coke/domains/social_scheduling/service.py`
- Modify: `coke/composition.py`

- [x] **Step 1: Write failing stale-commit tests**

Add tests proving a superseded interactive turn commits no reminder, no friendship, no shared reminder, no notification facts, and records `superseded`. The test guard must supersede after the adapter pre-check but before the domain write to prove commit-time enforcement.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_superseded_after_tool_entry_commits_no_domain_facts -v
```

Expected before implementation: FAIL because the domain service writes after the adapter's earlier guard.

- [x] **Step 2: Add domain command guard context**

Thread an optional callable guard or command context from tool adapters into state-changing Reminder and SocialScheduling methods. The guard is checked inside the same method immediately before mutation/outbox production. Direct API calls pass `None`.

- [x] **Step 3: Preserve `superseded` disposition**

When the guard raises `ConversationRuntimeError("turn_superseded")`, let TurnRunner map it to the existing `superseded` disposition and avoid output delivery.

- [x] **Step 4: Run stale-commit tests green**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_superseded_after_tool_entry_commits_no_domain_facts -v
```

Expected after implementation: PASS.

## Task 3: Delivery-Lifecycle Writeback

**Files:**
- Modify: `tests/unit/coke/turn/test_turn_runner.py`
- Modify: `tests/unit/coke/reminder/test_reminder_service.py`
- Modify: `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`
- Modify: `coke/turn/runner.py`
- Modify: `coke/composition.py`
- Modify: `coke/domains/reminder/service.py`
- Modify: `coke/domains/social_scheduling/service.py`
- Modify: `coke/app.py` only if an internal callback route is needed.

- [x] **Step 1: Write failing delivery writeback tests**

Add tests proving failed `ReminderFireTurn` delivery sets personal fires to `undelivered`, failed `ProactiveFireTurn` delivery discards proactive fires, and failed `NotificationTurn` delivery marks affected `notification_recipient` rows `failed` with user-safe error facts. Add delivered variants where needed.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_render_delivery_failure_updates_output_class_lifecycle -v
```

Expected before implementation: FAIL because `OutboundDeliveryPort.deliver` returns `None` and TurnRunner discards the persisted `delivery_attempt`.

- [x] **Step 2: Return delivery attempts from outbound delivery**

Change `OutboundDeliveryPort.deliver` and `ChannelReachabilityOutboundDelivery.deliver` to return the persisted attempt object from `ChannelReachabilityService.send_text`.

- [x] **Step 3: Add lifecycle callback dispatcher**

After render delivery, dispatch by `trigger_type`: reminder fire ids from payload update `ReminderService.record_fire_delivery`; proactive fire id updates `ReminderService.record_proactive_delivery`; notification payload updates `SocialSchedulingService.record_notification_delivery` for each target recipient. Keep the operation idempotent.

- [x] **Step 4: Run delivery tests green**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_render_delivery_failure_updates_output_class_lifecycle -v
```

Expected after implementation: PASS.

## Task 4: Atomic Reminder Write Plus Outbox

**Files:**
- Modify: `tests/unit/coke/reminder/test_reminder_service.py`
- Create: `tests/integration/coke/repositories/test_reminder_atomic_outbox_contract.py`
- Modify: `coke/domains/reminder/models.py`
- Modify: `coke/domains/reminder/repository.py`
- Modify: `coke/domains/reminder/service.py`

- [x] **Step 1: Write failing outbox tests**

Add an in-memory service test proving reminder create/edit/complete/delete creates a durable outbox event with deterministic idempotency. Add a Postgres integration test gated on `COKE_TEST_DATABASE_URL` proving a simulated outbox insert failure rolls back the reminder row and a successful create commits both.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py::test_personal_reminder_create_writes_outbox_event -v
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/repositories/test_reminder_atomic_outbox_contract.py -v
```

Expected before implementation: FAIL because personal reminder lifecycle writes only `reminder` / `reminder_fire` rows.

- [x] **Step 2: Add repository transaction methods**

Add methods that persist reminder changes and outbox records together for Postgres and in-memory repos. Use the existing `schema.outbox` columns and deterministic idempotency keys such as `reminder:<operation>:<reminder_id>` or `reminder:<turn_id>:<item_index>` when turn context is present.

- [x] **Step 3: Update service CRUD**

Route `execute_batch` create, `schedule_unscheduled`, `reschedule_reminder`, `clear_trigger_time`, `complete_reminder`, and `delete_reminder` through the same-transaction outbox path. Do not emit outbox for validation/follow-up/duplicate failures.

- [x] **Step 4: Run outbox tests green**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py::test_personal_reminder_create_writes_outbox_event -v
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/repositories/test_reminder_atomic_outbox_contract.py -v
```

Expected after implementation: PASS, or SKIP for the Postgres test only when `COKE_TEST_DATABASE_URL` is unavailable.

## Task 5: Final Verification And Commit

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-arch-p0.md`

- [x] **Step 1: Run targeted suites**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn tests/unit/coke/conversation_runtime tests/unit/coke/reminder tests/unit/coke/social_scheduling -q
```

Expected: all selected unit tests pass.

- [x] **Step 2: Run full unit suite**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: all unit tests pass.

- [x] **Step 3: Run gated integration suite**

Run:

```bash
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke -q
```

Expected: all integration tests pass, or only environment-dependent tests skip when the database is unavailable.

- [x] **Step 4: Run diff-aware verification routing**

Run:

```bash
git diff --check
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: no whitespace errors; suggested verification reviewed; review-trigger reported but does not block commit.

- [x] **Step 5: Mark plan complete and commit**

After verification passes, set `Plan Status: complete`, mark every checkbox done, commit coherent changes on `fix/arch-p0`, then report `git log --oneline main..HEAD`.
