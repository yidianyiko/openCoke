# Worker Reminder Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan Status:** in_progress

**Goal:** Stop `reminder.lifecycle` outbox events from crash-looping the clean worker, make unknown worker topics non-fatal, and prove reminder duration edits still reply and emit consumable lifecycle evidence.

**Architecture:** `reminder.lifecycle` is durable evidence for an already-committed Reminder-domain write. The worker must consume and ACK it without creating a render turn or duplicate user-visible prose; scheduler/calendar state is already derived from Reminder-owned tables, so no extra projection write is needed in this repair. Unknown topics are treated as operationally visible skipped work, not loop-fatal exceptions.

**Tech Stack:** Python 3.11, Flask composition root, SQLAlchemy schema contracts, Redis Stream worker consumer, pytest, in-memory fakes, production compose on `gcp-coke` coke-clean.

---

## Source Context

- Master plan slice: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild.md` Task 6 worker/outbox runtime and Architecture Issues.
- Requirements slice: §5.8 personal reminders, especially duration edits and operation confirmation replies.
- Target architecture slice: §5 transactional outbox and §8 reminder execution.
- Schema source: `coke/schema.py`; use only existing `outbox`, `reminder`, `turn`, `message`, and related tables.

## Files

- Modify: `coke/worker/__main__.py`
- Modify: `coke/domains/reminder/service.py`
- Modify: `coke/domains/reminder/repository.py`
- Modify: `coke/domains/conversation_runtime/repository.py`
- Modify: `coke/composition.py`
- Modify: `coke/llm/agno_interaction_agent.py`
- Modify: `coke/llm/semantic_interpreter.py`
- Modify: `coke/turn/semantic_interpreter.py`
- Modify: `coke/turn/runner.py`
- Create: `tests/unit/coke/worker/test_worker_topic_resilience.py`
- Modify: `tests/unit/coke/reminder/test_reminder_service.py`
- Modify: `tests/unit/coke/turn/test_turn_runner.py`
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`
- Modify: `tests/unit/coke/llm/test_semantic_interpreter.py`
- Modify: `tests/integration/coke/test_composition_turn_integration.py`
- Modify: this plan file

## Tasks

### Task 1: Worker RED Tests

- [x] **Step 1: Add worker topic tests**

Create `tests/unit/coke/worker/test_worker_topic_resilience.py` with fakes for `runtime.session`, `runtime.turn_runner`, and `runtime.reply_pubsub`. Add tests that:

- publish `topic="reminder.lifecycle"` to `StreamConsumer`;
- call `_handle_event(runtime, event)`;
- assert the Redis message is ACKed by the consumer callback;
- assert neither `run_inbound_turn` nor `run_render_turn` was called;
- publish `topic="unexpected.topic"` followed by `topic="turn.inbound"`;
- assert the unknown topic logs a warning, is ACKed, and the following inbound event is processed.

- [x] **Step 2: Run worker tests and verify RED**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/worker/test_worker_topic_resilience.py -v
```

Expected before implementation: FAIL because `_handle_event` raises through `_turn_trigger_from_event()` for `reminder.lifecycle` and unknown topics.

### Task 2: Reminder Duration RED Tests

- [x] **Step 1: Add reminder service duration update test**

In `tests/unit/coke/reminder/test_reminder_service.py`, add a test that creates an existing timed reminder, calls `ReminderService.update_reminder(..., duration_minutes=60)`, and asserts:

- the same reminder row is updated, not duplicated;
- `duration_minutes == 60`;
- `next_fire_at` and `captured_timezone` are unchanged;
- a `reminder.lifecycle` outbox event with `operation == "update"` and `duration_minutes == 60` is emitted.

- [x] **Step 2: Add turn/tool duration confirmation test**

In `tests/unit/coke/turn/test_turn_runner.py`, add a test for the user text `把提醒改成60分钟` with an existing reminder and a real `ReminderToolAdapter`. The fake agent must call `operation="update_reminder"` with `duration_minutes=60`, return a JSON reply confirmation, and the assertions must prove:

- result disposition is `replied`;
- the persisted reminder duration is `60`;
- a confirmation outbound text is recorded;
- the emitted `reminder.lifecycle` event is consumable by worker evidence handling.

- [x] **Step 3: Add Agno tool normalization test**

In `tests/unit/coke/llm/test_interaction_agent.py`, add a test showing an Agno tool payload with `op="update"`, `reminder_id`, and `duration_minutes=60` normalizes to `operation="update_reminder"` instead of `reschedule_reminder`.

- [x] **Step 4: Run duration-focused tests and verify RED**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/coke/reminder/test_reminder_service.py::test_update_reminder_duration_updates_existing_row_and_writes_lifecycle_event \
  tests/unit/coke/turn/test_turn_runner.py::test_duration_update_turn_replies_and_lifecycle_event_is_worker_ackable \
  tests/unit/coke/llm/test_interaction_agent.py::test_reminder_tool_maps_agno_update_duration_op_to_update_operation \
  -v
```

Expected before implementation: FAIL because `ReminderService.update_reminder` and the `update_reminder` tool branch do not exist, and `op="update"` currently normalizes to `reschedule_reminder`.

### Task 3: Implement Worker Evidence Handling

- [x] **Step 1: Handle lifecycle evidence topics**

In `coke/worker/__main__.py`, add a small topic classifier before turn-trigger construction:

- `reminder.lifecycle` returns without running a turn;
- log an info record with event id, topic, operation, and reminder id;
- leave durable ACK to `StreamConsumer` after `_handle_event` returns.

- [x] **Step 2: Skip unknown topics**

In `coke/worker/__main__.py`, unknown topics must log a warning and return without raising so the consumer ACKs and continues.

- [x] **Step 3: Run worker tests and verify GREEN**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/worker/test_worker_topic_resilience.py -v
```

Expected after implementation: all worker topic resilience tests pass.

### Task 4: Implement Duration Update Path

- [x] **Step 1: Add ReminderService.update_reminder**

In `coke/domains/reminder/service.py`, implement duration/content/trigger update support without new tables:

- require an active owner-scoped reminder;
- reject proactive user edits;
- accept positive integer `duration_minutes`;
- keep `next_fire_at` unchanged for duration-only updates;
- validate trigger time if a trigger-time update is provided;
- write one reminder row update plus one `reminder.lifecycle` outbox event in the same repository method;
- return a `ReminderItemResult` with factual `duration_minutes`, content, and trigger time.

- [x] **Step 2: Expose operation through ReminderToolAdapter**

In `coke/composition.py`, add an `operation == "update_reminder"` branch that passes `content`, optional `trigger_time`, `captured_timezone`, and `duration_minutes` to the service.

- [x] **Step 3: Fix Agno reminder operation normalization and tool docs**

In `coke/llm/agno_interaction_agent.py`, normalize `op="update"` to `update_reminder`, map `new_duration_minutes` to `duration_minutes`, keep `modify_time` mapped to `reschedule_reminder`, and update the reminder tool doc/instructions to distinguish duration/content edits from time reschedules.

- [x] **Step 4: Run duration-focused tests and verify GREEN**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/coke/reminder/test_reminder_service.py::test_update_reminder_duration_updates_existing_row_and_writes_lifecycle_event \
  tests/unit/coke/turn/test_turn_runner.py::test_duration_update_turn_replies_and_lifecycle_event_is_worker_ackable \
  tests/unit/coke/llm/test_interaction_agent.py::test_reminder_tool_maps_agno_update_duration_op_to_update_operation \
  -v
```

Expected after implementation: all three focused tests pass.

### Task 5: Local Verification And Commit

- [x] **Step 1: Run focused worker/reminder/turn/LLM tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/coke/worker/test_worker_topic_resilience.py \
  tests/unit/coke/reminder/test_reminder_service.py \
  tests/unit/coke/turn/test_turn_runner.py \
  tests/unit/coke/llm/test_interaction_agent.py \
  -q
```

- [x] **Step 2: Run requested unit suite**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

- [x] **Step 3: Run requested integration command**

Run:

```bash
COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration -q
```

If `tests/integration` does not exist, record that exact pytest output as a verification gap.

- [x] **Step 4: Run diff-aware routing**

Run:

```bash
git diff --check
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

- [x] **Step 5: Commit local code/tests/plan progress**

Commit the coherent local repair before deploying:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-worker-reminder-lifecycle.md coke/worker/__main__.py coke/domains/reminder/models.py coke/domains/reminder/service.py coke/composition.py coke/llm/agno_interaction_agent.py tests/unit/coke/worker/test_worker_topic_resilience.py tests/unit/coke/reminder/test_reminder_service.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/llm/test_interaction_agent.py
git commit -m "fix: ack reminder lifecycle worker events"
```

### Task 5A: Follow-Up Reminder Focus Repair

First live smoke proved the worker no longer crashed on `reminder.lifecycle`, but
the exact user journey `把它改成60分钟` still produced a clarification because the
follow-up turn did not receive a trusted recent reminder focus.

- [x] **Step 1: Add focus RED tests**

Add tests proving:

- the Agno reminder tool defaults a missing `reminder_id` from a single trusted
  `focus_subject`;
- a second inbound turn after a reminder create receives the recently created
  reminder as focus and can update `duration_minutes` to `60`.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/coke/llm/test_interaction_agent.py::test_reminder_tool_defaults_update_reminder_id_from_single_focus_subject \
  tests/integration/coke/test_composition_turn_integration.py::test_followup_reminder_edit_receives_recent_created_reminder_focus \
  -v
```

Expected before implementation: FAIL because no focus subject is resolved from
recent reminder lifecycle evidence and the tool default does not fill
`reminder_id`.

- [x] **Step 2: Implement recent reminder focus**

Use existing `turn` and `outbox` tables only:

- add repository reads for latest conversation turn ids and reminder lifecycle
  events by `payload.turn_id`;
- resolve the latest active reminder from create/update/reschedule lifecycle
  evidence as a `MessageSubject`;
- pass that focus resolver through the composition root;
- default missing reminder ids for update/reschedule/clear/complete/delete
  operations from one trusted reminder focus.

- [x] **Step 3: Verify focus GREEN**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/coke/llm/test_interaction_agent.py::test_reminder_tool_defaults_update_reminder_id_from_single_focus_subject \
  tests/integration/coke/test_composition_turn_integration.py::test_followup_reminder_edit_receives_recent_created_reminder_focus \
  -v
```

Observed after implementation: `2 passed in 2.49s`.

### Task 5B: Follow-Up Semantic Focus Repair

Second live smoke proved the worker and repository focus were clean, but the
semantic decision layer still treated `把它改成60分钟` as reference-ambiguous
before the interaction agent could invoke the reminder tool.

- [x] **Step 1: Add semantic focus RED tests**

Add tests proving:

- `SemanticInterpreterRequest` carries trusted `focus_subject` to the LLM
  payload and prompt;
- a single trusted reminder focus clears only reference clarification for
  reminder edit actions, enabling tools while preserving missing-field
  clarifications.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/coke/turn/test_turn_runner.py::test_single_reminder_focus_clears_reference_clarification_for_update \
  tests/unit/coke/llm/test_semantic_interpreter.py::test_interpret_request_includes_trusted_focus_subject \
  -v
```

Observed before implementation: FAIL because `SemanticInterpreterRequest` had
no `focus_subject`, and the runner left `ask_reference_choice` as a tool-blocking
clarification.

- [x] **Step 2: Implement semantic focus handling**

Use trusted focus from `FocusResolver` before semantic interpretation, pass it
into the semantic request and LLM payload, and deterministically clear only
reference-based clarification for single-reminder edit/completion/deletion
actions.

- [x] **Step 3: Verify semantic focus GREEN**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/coke/turn/test_turn_runner.py::test_single_reminder_focus_clears_reference_clarification_for_update \
  tests/unit/coke/llm/test_semantic_interpreter.py::test_interpret_request_includes_trusted_focus_subject \
  -v
```

Observed after implementation: `2 passed in 2.38s`.

### Task 6: Redeploy And Live Verify

- [ ] **Step 1: Read deploy/coke-clean runtime commands**

Read `docs/deploy.md` and the recent coke-clean redeploy plan only for concrete compose paths, project names, snapshot commands, and service names.

- [ ] **Step 2: Capture rollback snapshot**

On `gcp-coke`, capture the current `coke-clean` git SHA, compose image/container state, `.env` checksum without printing secrets, and a Postgres dump or timestamped dump path before recreating services.

- [ ] **Step 3: Deploy current main non-disruptively**

Rsync/checkout current committed `main`, preserve `/home/whoami/coke-clean/.env`, run Alembic `upgrade head`, and recreate only clean Coke services needed for this code path: `coke-api`, `coke-worker`, `coke-scheduler`, `coke-outbox-relay`, and web only if compose dependency requires it. Do not touch `evolution-*`, `wechat-personal-connector`, accounts, channels, or connector sessions.

- [ ] **Step 4: Verify service health and sessions**

On `gcp-coke`, verify:

- clean API health/logins return `200`;
- both channels remain `connected`;
- connector `session_count=2`;
- `coke-clean-coke-worker-1` restart count is stable;
- recent worker logs have no `unsupported_worker_topic:reminder.lifecycle`.

- [ ] **Step 5: Live reminder duration smoke**

Through the connected account path, create a marked reminder, then send `把它改成60分钟`. Query clean Postgres to prove:

- the target reminder row has `duration_minutes = 60`;
- the user turn disposition is `replied`;
- an outbound confirmation message exists and is not system fallback;
- the corresponding `reminder.lifecycle` outbox event is `processed`/`acked`;
- worker logs remain clean.

- [ ] **Step 6: Final plan closeout**

Only after local verification and live verification pass, set `Plan Status: complete`, check all boxes, append concise verification evidence, and commit the plan closeout if it changed after deployment.
