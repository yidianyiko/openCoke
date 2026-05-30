# RR1 Postgres Repositories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Plan Status:** complete

**Goal:** Add SQLAlchemy-backed repository implementations for the six clean Coke domains, with contract tests proving parity with the existing in-memory repositories.

**Architecture:** Keep domain service APIs and repository Protocols unchanged. Each Postgres repository maps the existing domain dataclasses to the existing SQLAlchemy Core tables in `coke/schema.py`, uses an injected SQLAlchemy `Session`, and translates DB uniqueness conflicts into the same domain errors raised by the in-memory implementation. The only shared production helper is `coke/domains/_pg.py` for row conversion, savepoint-protected writes, and JSON normalization.

**Tech Stack:** Python 3.12, SQLAlchemy Core/ORM `Session`, Postgres 18.1 via psycopg, pytest.

---

## File Structure

- Create `coke/domains/_pg.py`: shared SQLAlchemy helpers for row mappings, JSON conversion, savepoint-wrapped writes, and generic update/insert helpers.
- Modify `coke/domains/identity_access/repository.py`: add `PostgresIdentityAccessRepository`.
- Modify `coke/domains/channel_reachability/repository.py`: add `PostgresChannelReachabilityRepository`.
- Modify `coke/domains/conversation_runtime/repository.py`: add `PostgresConversationRuntimeRepository`.
- Modify `coke/domains/reminder/repository.py`: add `PostgresReminderRepository`.
- Modify `coke/domains/social_scheduling/repository.py`: add `PostgresSocialSchedulingRepository`.
- Modify `coke/domains/calendar_import/service.py`: add `PostgresCalendarImportRepository` beside the existing protocol and in-memory implementation because this domain does not have a separate `repository.py`.
- Create `tests/integration/coke/repositories/conftest.py`: Postgres session fixture, skip gate for `COKE_TEST_DATABASE_URL`, transaction rollback, and parent-row seed helpers.
- Create `tests/integration/coke/repositories/test_*_repository_contract.py`: contract tests parametrized across in-memory and Postgres repositories.

## Tasks

### Task 1: Contract Test Harness And Identity Repository

**Files:**
- Create: `tests/integration/coke/repositories/conftest.py`
- Create: `tests/integration/coke/repositories/test_identity_access_repository_contract.py`
- Create: `coke/domains/_pg.py`
- Modify: `coke/domains/identity_access/repository.py`

- [x] **Step 1: Write failing identity contract tests**

Add tests that create account, activation, access, credential, session, channel identity, and auth artifact records; assert round-trip equality; assert duplicate credential email, session token, channel provider tuple, and artifact code raise `ValueError` with the in-memory error strings.

- [x] **Step 2: Run identity contract tests and observe RED**

Run: `COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/repositories/test_identity_access_repository_contract.py -q`

Expected: fail because `PostgresIdentityAccessRepository` is missing.

- [x] **Step 3: Implement shared helper and Postgres identity repository**

Add dataclass row builders, `session.begin_nested()`-protected writes, `IntegrityError` translation, lower-case credential email lookup, token/code-to-`token_hash` mapping, and usable-channel lookup via the existing `channel` table.

- [x] **Step 4: Run identity contract tests and commit**

Run the same command. Expected: all tests in the file pass. Commit the helper, identity repository, and tests.

### Task 2: Channel Reachability Repository

**Files:**
- Create: `tests/integration/coke/repositories/test_channel_reachability_repository_contract.py`
- Modify: `coke/domains/channel_reachability/repository.py`

- [x] **Step 1: Write failing channel contract tests**

Add tests for channel add/save/list/get-active, route upsert and retirement, delivery attempt save/get, duplicate active channel, duplicate route key mismatch, and duplicate provider idempotency.

- [x] **Step 2: Run channel contract tests and observe RED**

Run: `COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/repositories/test_channel_reachability_repository_contract.py -q`

Expected: fail because `PostgresChannelReachabilityRepository` is missing.

- [x] **Step 3: Implement Postgres channel repository**

Map `channel`, `delivery_route`, and `delivery_attempt`; preserve active-channel and route invariants; translate unique conflicts to the same `ValueError` codes.

- [x] **Step 4: Run channel contract tests and commit**

Run the same command. Expected: all tests in the file pass. Commit the domain repository and tests.

### Task 3: Conversation Runtime Repository

**Files:**
- Create: `tests/integration/coke/repositories/test_conversation_runtime_repository_contract.py`
- Modify: `coke/domains/conversation_runtime/repository.py`

- [x] **Step 1: Write failing conversation contract tests**

Add tests for conversation add/save, atomic inbound message + media + outbox write, turn replay lookup, outbound segment uniqueness, disposition upsert, and outbox publish/process transitions.

- [x] **Step 2: Run conversation contract tests and observe RED**

Run: `COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/repositories/test_conversation_runtime_repository_contract.py -q`

Expected: fail because `PostgresConversationRuntimeRepository` is missing.

- [x] **Step 3: Implement Postgres conversation repository**

Map `conversation`, `message`, `inbound_media`, `turn`, `output_disposition`, and `outbox`; write inbound message/media/outbox in one repository call; translate duplicate IDs, turn trigger IDs, outbox idempotency keys, and outbound segment conflicts.

- [x] **Step 4: Run conversation contract tests and commit**

Run the same command. Expected: all tests in the file pass. Commit the domain repository and tests.

### Task 4: Reminder Repository

**Files:**
- Create: `tests/integration/coke/repositories/test_reminder_repository_contract.py`
- Modify: `coke/domains/reminder/repository.py`

- [x] **Step 1: Write failing reminder contract tests**

Add tests for active reminder listing, due reminder ordering, timed/no-trigger duplicate prevention, save lifecycle updates, fire occurrence uniqueness, fire updates, owner fire listing, and future proactive discard.

- [x] **Step 2: Run reminder contract tests and observe RED**

Run: `COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/repositories/test_reminder_repository_contract.py -q`

Expected: fail because `PostgresReminderRepository` is missing.

- [x] **Step 3: Implement Postgres reminder repository**

Map `reminder` and `reminder_fire`; rely on partial unique indexes for duplicate active reminders; update proactive rows with SQL; translate unique conflicts to the same `ValueError` codes.

- [x] **Step 4: Run reminder contract tests and commit**

Run the same command. Expected: all tests in the file pass. Commit the domain repository and tests.

### Task 5: Social Scheduling Repository

**Files:**
- Create: `tests/integration/coke/repositories/test_social_scheduling_repository_contract.py`
- Modify: `coke/domains/social_scheduling/repository.py`

- [x] **Step 1: Write failing social scheduling contract tests**

Add tests for friend link token/code storage through the existing `auth_artifact` table, active friendship uniqueness, shared reminder duplicate lookup, participant projection uniqueness, busy intervals, notification fact idempotency, and recipient uniqueness.

- [x] **Step 2: Run social scheduling contract tests and observe RED**

Run: `COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/repositories/test_social_scheduling_repository_contract.py -q`

Expected: fail because `PostgresSocialSchedulingRepository` is missing.

- [x] **Step 3: Implement Postgres social scheduling repository**

Map `friend_link`, `friendship`, `shared_reminder`, `reminder_projection`, `notification_fact`, and `notification_recipient`; store public friend tokens and link codes as `auth_artifact` rows bound to the friend link ID in `continuation`; translate uniqueness conflicts.

- [x] **Step 4: Run social scheduling contract tests and commit**

Run the same command. Expected: all tests in the file pass. Commit the domain repository and tests.

### Task 6: Calendar Import Repository

**Files:**
- Create: `tests/integration/coke/repositories/test_calendar_import_repository_contract.py`
- Modify: `coke/domains/calendar_import/service.py`

- [x] **Step 1: Write failing calendar import contract tests**

Add tests for run add/save/get, item source-occurrence dedupe, list items for run, and authorization stop/revoke state round-trip.

- [x] **Step 2: Run calendar import contract tests and observe RED**

Run: `COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/repositories/test_calendar_import_repository_contract.py -q`

Expected: fail because `PostgresCalendarImportRepository` is missing.

- [x] **Step 3: Implement Postgres calendar import repository**

Map `calendar_import_run` and `calendar_import_item`; store authorization state in `auth_artifact` rows using `type='calendar_authorization'`, `purpose='google_calendar'`, `delivery='oauth'`, `token_hash=auth_handle`, and `delivery_state=state`, because the clean schema intentionally has no separate calendar authorization table.

- [x] **Step 4: Run calendar import contract tests and commit**

Run the same command. Expected: all tests in the file pass. Commit the domain repository and tests.

### Task 7: Full Verification And Plan Closeout

**Files:**
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-rr1-postgres-repositories.md`

- [x] **Step 1: Run Alembic consistency check**

Run: `DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m alembic upgrade head`

Expected: exit 0.

- [x] **Step 2: Run in-memory unit suite**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q`

Expected: all tests pass.

- [x] **Step 3: Run Postgres repository contract suite**

Run: `COKE_TEST_DATABASE_URL=postgresql+psycopg://ydyk@/coke_rr_test?host=/var/run/postgresql /data/projects/coke/.venv/bin/python -m pytest tests/integration/coke/repositories -q`

Expected: all tests pass.

- [x] **Step 4: Run diff-aware verification routing**

Run: `zsh scripts/suggest-verification --base HEAD~1` and `zsh scripts/review-trigger --base HEAD~1`.

Expected: commands exit 0 or produce a non-blocking risk report.

- [x] **Step 5: Mark plan complete and commit closeout**

Set `Plan Status` to `complete` only after verification passes. Commit the plan status update.
