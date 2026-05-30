# Reminder Domain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan Status:** complete

**Goal:** Build the clean-rebuild Reminder domain, scheduler facade, calendar read model, and thin Flask routes on the existing `coke/schema.py` tables.

**Architecture:** The Reminder domain owns reminder CRUD, batch itemized results, recurrence expansion, occurrence-grain fire lifecycle, undelivered resend selection, proactive discard, and calendar read-model action handles. It uses an injected detector port for structured field extraction and an injected delivery port for route resolution/send attempts, with no legacy imports, parser fallbacks, regex recovery, or schema forks. API routes stay thin and `coke/app.py` only gains an optional service kwarg plus blueprint registration block.

**Tech Stack:** Python dataclasses and Protocols, in-memory repository for unit tests, standard `zoneinfo`, Flask blueprints, pytest run from the worktree root with `/data/projects/coke/.venv/bin/python`.

---

## File Structure

- Create `coke/domains/reminder/__init__.py`: package exports for service, repository, scheduler, and read model.
- Create `coke/domains/reminder/models.py`: reminder dataclasses, command/result dataclasses, literal states, ports, and `ReminderError`.
- Create `coke/domains/reminder/repository.py`: repository Protocol and in-memory implementation that mirrors `reminder`, `reminder_fire`, `shared_reminder`, and `reminder_projection` schema constraints.
- Create `coke/domains/reminder/recurrence.py`: timezone-pinned recurrence expansion and next-trigger calculation.
- Create `coke/domains/reminder/service.py`: owner-scoped commands, detector boundary, validation, duplicate handling, conversions, fire lifecycle, proactive behavior, undelivered resend, and nightly summary facts.
- Create `coke/domains/reminder/scheduler.py`: singleton scheduler facade with memory jobstore support for tests, grouped due-fire collection, restart catch-up, and nightly summary scheduling facts.
- Create `coke/domains/reminder/calendar_read_model.py`: typed calendar entries and type-specific action handles.
- Create `coke/api/reminder_routes.py`: thin Reminder routes delegating to the service/read model.
- Modify `coke/app.py`: add `reminder_service=None` and register `create_reminder_blueprint(reminder_service)` when provided.
- Create tests under `tests/unit/coke/reminder/`: service, recurrence/scheduler, calendar read model, routes, and schema-contract tests.

---

## Task 1: Failing Contract Tests

**Files:**
- Create: `tests/unit/coke/reminder/test_reminder_service.py`
- Create: `tests/unit/coke/reminder/test_reminder_scheduler.py`
- Create: `tests/unit/coke/reminder/test_reminder_calendar_read_model.py`
- Create: `tests/unit/coke/reminder/test_reminder_routes.py`
- Create: `tests/unit/coke/reminder/test_reminder_schema_contract.py`

- [x] **Step 1: Write service contract tests**

Cover:
- timed and no-trigger-time create with owner, pinned timezone, and 15-minute default duration
- duplicate prevention by same owner/content/trigger or same owner/content/null trigger, ignoring duration and entry point
- itemized batch results: `succeeded`, `needs-follow-up`, and `failed` in one inbound
- past-time and incomplete-date validation states before commit
- explicit `schedule_unscheduled`, `clear_trigger_time`, and recurring clear-trigger confirmation facts
- occurrence-grain fire lifecycle, compare-and-set idempotency, recurring completion advance, undelivered resend, and proactive discard
- injected detector fake accepted as trusted-or-invalid with no regex recovery

Example assertion shape:

```python
result = service.execute_batch(
    owner_account_id="acct_1",
    items=[
        ReminderBatchItem(
            operation="create",
            content="pay rent",
            trigger_time=datetime(2026, 5, 30, 9, 0, tzinfo=UTC),
            captured_timezone="Asia/Tokyo",
        ),
        ReminderBatchItem(operation="create", content="missing", time_state="invalid"),
    ],
)
assert [item.state for item in result.items] == ["succeeded", "failed"]
```

- [x] **Step 2: Write recurrence and scheduler tests**

Cover:
- recurrence expansion uses `captured_timezone` even after the owner's display timezone changes
- same owner and same due time produces one grouped fire turn with ordered fire ids
- restart catch-up creates missed personal/shared fires and discards missed proactive reminders
- nightly summary uses 20:00 in the owner's current global timezone and returns no-trigger-time reminder ids

- [x] **Step 3: Write calendar read model tests**

Cover typed entries:
- one-time
- recurring occurrence in requested range
- shared projection with friend identifiers
- unscheduled
- undelivered
- merged groups

Cover action handles:
- personal reminder: `edit`, `complete`, `delete`
- recurring occurrence: `complete_occurrence`, `edit_series`, `delete_series`
- shared projection: `complete_own_projection`, `cancel_whole_shared_reminder`

- [x] **Step 4: Write route tests**

Cover:
- routes delegate to service/read model without owning domain decisions
- route errors map `ReminderError` to JSON error bodies
- `create_app(..., reminder_service=service)` registers the reminder blueprint without changing existing app blocks

- [x] **Step 5: Run the new tests and verify RED**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder -v
```

Expected before implementation: collection/import failures or assertion failures because `coke.domains.reminder` and `coke.api.reminder_routes` do not exist yet.

---

## Task 2: Domain Models, Repository, And Recurrence

**Files:**
- Create: `coke/domains/reminder/models.py`
- Create: `coke/domains/reminder/repository.py`
- Create: `coke/domains/reminder/recurrence.py`
- Create: `coke/domains/reminder/__init__.py`
- Test: `tests/unit/coke/reminder/test_reminder_service.py`
- Test: `tests/unit/coke/reminder/test_reminder_scheduler.py`

- [x] **Step 1: Implement dataclasses and ports**

Define current-contract literals:

```python
ReminderKind = Literal["timed", "no_trigger_time", "recurring", "proactive", "shared_projection"]
ReminderLifecycle = Literal["active", "completed", "deleted"]
ReminderFireState = Literal["pending", "claimed", "completed", "discarded"]
DeliveryResult = Literal["delivered", "undelivered"]
BatchItemState = Literal["succeeded", "needs-follow-up", "failed"]
TimeValidationState = Literal["valid_future", "needs_past_time_confirmation", "needs_incomplete_date_clarification", "invalid"]
```

Define `Reminder`, `ReminderFire`, `ReminderBatchItem`, `ReminderBatchResult`, `ReminderItemResult`, `ReminderFireGroup`, `NightlySummaryTurn`, `DetectedReminderFields`, `ReminderDetectorPort`, and `ReminderDeliveryPort`.

- [x] **Step 2: Implement in-memory repository**

The repository must reject duplicates with the same key shape as `coke/schema.py`: active reminders with same owner/content hash/`next_fire_at`, or active reminders with same owner/content hash and both no trigger time. It must store fires by `(reminder_id, occurrence_key)` and expose active owner-scoped list/query methods for service and read model.

- [x] **Step 3: Implement recurrence**

Support hourly/daily/weekly/monthly/yearly intervals, minimum hourly, default sub-daily window `08:00` to `23:00`, expansion in `captured_timezone`, and `next_after(rule, after)` returning UTC-aware datetimes.

- [x] **Step 4: Run focused tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py tests/unit/coke/reminder/test_reminder_scheduler.py -v
```

Expected after this task: model/repository/recurrence tests that do not require service methods pass; service behavior tests still fail until Task 3.

---

## Task 3: Reminder Service

**Files:**
- Create: `coke/domains/reminder/service.py`
- Modify: `coke/domains/reminder/__init__.py`
- Test: `tests/unit/coke/reminder/test_reminder_service.py`

- [x] **Step 1: Implement create/edit/complete/delete and batch execution**

Use `ReminderService(repository, detector=None, delivery=None, now=None, id_factory=None)`. Each batch item is validated and committed independently, returning itemized facts. Missing/wrong semantic fields from the detector return `failed` or `needs-follow-up`; the service must not recover detector output with keyword, regex, or template parsing.

- [x] **Step 2: Implement time validation and conversions**

`validate_trigger_time()` must return the four domain states before commit. `schedule_unscheduled()` and `clear_trigger_time()` must be explicit transitions; clearing a recurring series returns a follow-up choice fact rather than silently converting.

- [x] **Step 3: Implement occurrence fire lifecycle**

`claim_due_fire()` must create or return the occurrence-grain fire idempotently. Fire completion updates per-fire delivery result and handled/completed state separately from the series lifecycle. Recurring occurrence completion keeps the series active and advances `next_fire_at`; deleting the recurring reminder deletes the whole series.

- [x] **Step 4: Implement delivery-specific behavior**

Due personal/shared reminders with no usable channel or failed send become `undelivered`. `undelivered_resend_turn()` selects only undelivered fires whose reminders are active and unhandled. Proactive reminders are hidden, user-immutable, and discarded on no channel/send failure instead of becoming undelivered.

- [x] **Step 5: Run service tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py -v
```

Expected: all service tests pass.

---

## Task 4: Scheduler And Calendar Read Model

**Files:**
- Create: `coke/domains/reminder/scheduler.py`
- Create: `coke/domains/reminder/calendar_read_model.py`
- Test: `tests/unit/coke/reminder/test_reminder_scheduler.py`
- Test: `tests/unit/coke/reminder/test_reminder_calendar_read_model.py`

- [x] **Step 1: Implement scheduler facade**

Create `ReminderScheduler` with a memory jobstore mode for tests. It must group fires by `(owner_account_id, due_at)`, preserve ordered fire ids, catch up missed personal/shared triggers, discard missed proactive triggers, and produce per-owner `NightlySummaryTurn` facts at 20:00 in the owner current timezone supplied by an injected `account_timezone` callable.

- [x] **Step 2: Implement calendar read model**

Create `ReminderCalendarReadModel(repository)` returning typed entries with display datetimes in the supplied owner current timezone. It must include hidden=false active reminders, active shared projections, undelivered fires, concrete recurring occurrences in range, unscheduled reminders, and merged groups while preserving per-entry action handles.

- [x] **Step 3: Run scheduler/read-model tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_scheduler.py tests/unit/coke/reminder/test_reminder_calendar_read_model.py -v
```

Expected: scheduler and read-model tests pass.

---

## Task 5: Routes, App Registration, Verification, And Commit

**Files:**
- Create: `coke/api/reminder_routes.py`
- Modify: `coke/app.py`
- Test: `tests/unit/coke/reminder/test_reminder_routes.py`
- Test: `tests/unit/coke/reminder/test_reminder_schema_contract.py`

- [x] **Step 1: Implement routes**

Expose thin JSON adapters for:
- `POST /api/reminders/batch`
- `GET /api/reminders/calendar`
- `POST /api/reminders/<reminder_id>/schedule-unscheduled`
- `POST /api/reminders/<reminder_id>/clear-trigger-time`
- `POST /api/reminders/<reminder_id>/complete`
- `POST /api/reminders/<reminder_id>/delete`

Routes must delegate to service/read-model methods and serialize facts; they must not reimplement business rules.

- [x] **Step 2: Register app blueprint**

Modify `create_app()` to accept `reminder_service=None` and register `create_reminder_blueprint(reminder_service)` in its own optional block.

- [x] **Step 3: Run full reminder tests**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder -v
```

Expected: all reminder tests pass.

- [x] **Step 4: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: commands complete and any suggested relevant test surface is either already covered or run before completion.

Result: `zsh scripts/suggest-verification --base HEAD~1` suggested
`zsh scripts/verify-surface clean-rebuild-backend repo-os-docs`.
`zsh scripts/verify-surface clean-rebuild-backend` passed with `251 passed`.
The combined `repo-os-docs` surface ran `zsh scripts/check` and failed on
pre-existing missing ownership-registry paths under `gateway` and `memo-runtime`,
which are outside Task 8's allowed file scope.

- [x] **Step 5: Commit with verification gap recorded**

If all verification passes, update this file to `**Plan Status:** complete`.
If an unrelated verification surface remains red, keep the status honest and
commit the implemented Task 8 files with the gap recorded:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-reminder-domain.md coke/domains/reminder coke/api/reminder_routes.py coke/app.py tests/unit/coke/reminder
git commit -m "feat: implement clean reminder domain"
```
