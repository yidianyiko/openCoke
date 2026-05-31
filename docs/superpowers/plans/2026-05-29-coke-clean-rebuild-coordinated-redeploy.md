# Coke Clean Rebuild Coordinated Redeploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use superpowers:systematic-debugging for live evidence gathering, superpowers:test-driven-development for code changes, and superpowers:verification-before-completion before reporting completion. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redeploy the live `gcp-coke` `coke-clean` stack to current `main` while preserving the two already-connected real personal-WeChat sessions.

**Architecture:** Keep the clean Python API as the only customer API authority: customer identity comes from `Authorization: Bearer <session_token>`, not from client-supplied account ids. Preserve product data and provider sessions in Postgres and the existing `wechat-personal-connector`; update only the clean application code, run Alembic in place, and mutate only the two existing credential rows for Argon2 login compatibility.

**Tech Stack:** Next.js 16, Vitest, Flask, SQLAlchemy 2.x, Alembic, Argon2, Docker Compose on `gcp-coke`, Postgres, Redis, and the existing personal-WeChat connector on port 8095.

---

**Plan Status:** in_progress
**Status Date:** 2026-05-31

### Task 1: Web Customer API Auth And Route Alignment

**Files:**
- Modify: `web/lib/customer-wechat-channel.ts`
- Modify: `web/lib/customer-wechat-channel.test.ts`
- Modify: `web/lib/customer-reminders.ts`
- Modify: `web/lib/customer-reminders.test.ts`
- Modify: `web/lib/customer-friends.ts`
- Modify: `web/lib/customer-friends.test.ts`
- Modify: `web/lib/customer-shared-reminders.ts`
- Modify: `web/lib/customer-shared-reminders.test.ts`
- Modify: `web/lib/customer-agent-instance.ts`
- Modify: `web/lib/customer-agent-instance.test.ts`
- Modify: `web/lib/customer-google-calendar-import.ts`

- [x] **Step 1: Write failing web tests for bearer-token customer helpers**

Update the Vitest expectations so clean customer helpers call `/api/channels`, `/api/reminders`, `/api/friends`, `/api/shared-reminders`, `/api/settings`, and `/api/calendar-import` paths, and the WeChat channel helper no longer sends `account_id` in query strings or request bodies.

Run:

```bash
cd web && pnpm test web/lib/customer-wechat-channel.test.ts web/lib/customer-reminders.test.ts web/lib/customer-friends.test.ts web/lib/customer-shared-reminders.test.ts web/lib/customer-agent-instance.test.ts
```

Expected before implementation: FAIL with stale `/api/customer/...` or `account_id` expectations not matching the current helper output.

- [x] **Step 2: Implement minimal web helper fixes**

Change the helpers so they use the clean Flask route families and rely on `customerApi` to attach the stored session token. Do not include account ids as authentication or owner fields in customer channel calls.

- [x] **Step 3: Verify focused web tests pass**

Run:

```bash
cd web && pnpm test web/lib/customer-wechat-channel.test.ts web/lib/customer-reminders.test.ts web/lib/customer-friends.test.ts web/lib/customer-shared-reminders.test.ts web/lib/customer-agent-instance.test.ts
```

Expected after implementation: all selected tests pass.

### Task 2: Idempotent Argon2 Credential Migration Script

**Files:**
- Create: `scripts/ops/migrate_coke_clean_credentials.py`
- Create: `scripts/ops/__init__.py`
- Create: `tests/unit/coke/deploy/test_migrate_coke_clean_credentials.py`

- [x] **Step 1: Write failing tests for in-place credential migration**

Create unit tests that build an in-memory SQLite database from `coke.schema.metadata`, seed only the two allowed credential rows, run the migration function with a fake deterministic hash factory, and assert:

- only `credential.password_hash` and `credential.updated_at` change
- `account`, `channel_identity`, and `channel` rows are not recreated or deleted
- a second run is idempotent when the verifier says the stored hash already matches

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/identity_access/test_live_credential_migration.py -v
```

Expected before implementation: FAIL because `scripts.ops.migrate_live_credentials_argon2` does not exist.

- [x] **Step 2: Implement the migration script**

Add a script with a `migrate_credentials(connection, targets, hash_password, verify_password, now)` function and a CLI that requires `DATABASE_URL`, hashes the two known passwords using `PasswordHasher`, verifies the current row by account id and email, updates the existing row in place, and prints only account/email/update status.

- [x] **Step 3: Verify focused Python migration tests pass**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/deploy/test_migrate_coke_clean_credentials.py -q
```

Expected after implementation: all tests pass.

### Task 3: Schema And Deployment Readiness Checks

**Files:**
- Read: `coke/schema.py`
- Read: `migrations/versions/`
- Remote read: `/home/whoami/coke-clean/.env`
- Remote read: `/home/whoami/coke-clean/docker-compose.prod.yml`

- [ ] **Step 1: Compare local Alembic head to metadata**

Run local schema/autogenerate checks without modifying the live database. If Alembic reports missing schema changes, add a deterministic revision before deployment; otherwise record that no new revision is needed.

- [ ] **Step 2: Inspect live stack and capture rollback state**

On `gcp-coke`, record current `coke-clean` git commit/image ids, service list, API health, connector health, and the two connected account/channel rows before deployment.

- [x] **Step 3: Run local full verification for touched surfaces**

Run:

```bash
cd web && pnpm test
cd web && pnpm build
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q
```

Expected: all three commands pass before committing deployable code.

Evidence:
- `cd web && pnpm test` -> 210 passed.
- `cd web && pnpm build` -> production build completed successfully.
- `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q` -> 453 passed.
- `zsh scripts/check` -> check passed.

### Task 4: Commit Local Changes

**Files:**
- Modified and created files from Tasks 1-2
- Modified: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-coordinated-redeploy.md`

- [x] **Step 1: Mark completed plan checkboxes for verified local work**

Update this plan incrementally as each verified task completes.

- [ ] **Step 2: Commit coherent local changes on current branch**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-coordinated-redeploy.md web/lib scripts/ops tests/unit/coke/identity_access
git commit -m "fix: align customer web auth for clean redeploy"
```

Expected: one local commit containing the web adapter fixes, migration script, tests, and plan progress.

### Task 5: In-Place Live Credential Migration

**Files:**
- Remote run: `/home/whoami/coke-clean/scripts/ops/migrate_live_credentials_argon2.py`

- [ ] **Step 1: Copy/deploy current code to `gcp-coke` without touching connector**

Update `/home/whoami/coke-clean` to the current branch commit while preserving `/home/whoami/coke-clean/.env` and leaving `evolution-*` and `wechat-personal-connector` untouched.

- [ ] **Step 2: Run Alembic upgrade head against live Postgres**

Run the live equivalent of:

```bash
DATABASE_URL=<from preserved env> /data/projects/coke/.venv/bin/python -m alembic upgrade head
```

Expected: live DB reaches Alembic head without dropping/recreating product data.

- [ ] **Step 3: Run credential migration against live Postgres**

Run the migration script against live `DATABASE_URL`. Expected: both `olivers@coke.keep4oforever.com` and `lizihao@coke.keep4oforever.com` report `updated` or `already_current`; no account/channel/channel_identity rows are recreated.

### Task 6: Non-Disruptive Clean Stack Redeploy

**Files:**
- Remote modify: `/home/whoami/coke-clean`

- [ ] **Step 1: Build/recreate clean app services only**

Recreate `coke-api`, `coke-worker`, `coke-scheduler`, `coke-outbox-relay`, and `coke-web`. Do not restart or reconfigure `evolution-*` or `wechat-personal-connector`.

- [ ] **Step 2: Verify restart stability**

Verify `docker compose ps`, `/healthz`, and recent logs for restart loops or tracebacks.

### Task 7: Live Post-Deploy Verification

**Files:**
- Remote read only plus authenticated API calls

- [ ] **Step 1: Login both real accounts through live API**

POST to live `/api/auth/login` for olivers and lizihao with the web password field. Expected: HTTP 200 with a session token for each account.

- [ ] **Step 2: Prove bearer auth is enforced and accepted**

For at least one customer route, verify HTTP 401 without `Authorization` and HTTP 200 with the new bearer token.

- [ ] **Step 3: Prove both personal-WeChat sessions survived**

GET channel status for both accounts with bearer tokens. Expected: `connection_state=connected`. Also verify connector `/healthz` reports `connected_session_count=2`.

- [ ] **Step 4: Spot-check settings persistence**

Use authenticated `/api/settings` calls to update and re-read a low-risk timezone/settings field, then restore the original value if changed.

- [ ] **Step 5: Close the plan**

When all verification passes, set `Plan Status` to `complete` and record the final evidence in this file before the final report.
