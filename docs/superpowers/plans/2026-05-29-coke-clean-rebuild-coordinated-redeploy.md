# Coke Clean Rebuild Coordinated Redeploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use superpowers:systematic-debugging for live evidence gathering, superpowers:test-driven-development for code changes, and superpowers:verification-before-completion before reporting completion. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redeploy the live `gcp-coke` `coke-clean` stack to current `main` while preserving the two already-connected real personal-WeChat sessions.

**Architecture:** Keep the clean Python API as the only customer API authority: customer identity comes from `Authorization: Bearer <session_token>`, not from client-supplied account ids. Preserve product data and provider sessions in Postgres and the existing `wechat-personal-connector`; update only the clean application code, run Alembic in place, and mutate only scoped auth/profile rows for the two preserved live accounts.

**Tech Stack:** Next.js 16, Vitest, Flask, SQLAlchemy 2.x, Alembic, Argon2, Docker Compose on `gcp-coke`, Postgres, Redis, and the existing personal-WeChat connector on port 8095.

---

**Plan Status:** complete
**Status Date:** 2026-05-31

**Resume Note:** Prior deployment stopped on live `alembic check` because
APScheduler jobstore objects were visible to Alembic. Current `main` includes
`coke/alembic_filters.py`, and this final attempt must prove both live
`alembic upgrade head` and live `alembic check` before recreating app services.
Tasks 5-7 below preserve that stopped attempt as historical evidence. Task 8
is the completed final coordinated deploy path.

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

- [x] **Step 1: Compare local Alembic head to metadata**

Run local schema/autogenerate checks without modifying the live database. If Alembic reports missing schema changes, add a deterministic revision before deployment; otherwise record that no new revision is needed.

- [x] **Step 2: Inspect live stack and capture rollback state**

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
- Live `alembic upgrade head` ran through `coke-migrate` before service restart.
- Live `alembic check` then failed with schema drift: `apscheduler_jobs` table and
  `ix_apscheduler_jobs_next_run_time` index exist in live runtime use but are not
  defined in `coke/schema.py`.
- Current scheduler code imports `SQLAlchemyJobStore` and configures the Postgres
  job store, so this is a real schema gap under the "build only on coke/schema.py"
  constraint, not a harmless stale table assumption.

### Task 4: Commit Local Changes

**Files:**
- Modified and created files from Tasks 1-2
- Modified: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-coordinated-redeploy.md`

- [x] **Step 1: Mark completed plan checkboxes for verified local work**

Update this plan incrementally as each verified task completes.

- [x] **Step 2: Commit coherent local changes on current branch**

Run:

```bash
git add docs/superpowers/plans/2026-05-29-coke-clean-rebuild-coordinated-redeploy.md web/lib scripts/ops tests/unit/coke/identity_access
git commit -m "fix: align customer web auth for clean redeploy"
```

Expected: one local commit containing the web adapter fixes, migration script, tests, and plan progress.

Evidence:
- Commit: `dcbb74ed fix: align customer web auth for clean redeploy`.

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

Blocked evidence:
- `alembic upgrade head` completed with no application service restart.
- `alembic check` failed because live/current scheduler behavior depends on
  `apscheduler_jobs`, which is not present in `coke/schema.py`.
- Per the task hard constraint, deployment stopped before credential migration
  and before recreating `coke-api`, `coke-worker`, `coke-scheduler`,
  `coke-outbox-relay`, or `coke-web`.
- Remote rollback bundle: `/home/whoami/coke-clean-rollback-20260531T033638Z.tgz`.
- Remote source was restored from that bundle with `.env` preserved, and app
  image tags were rebuilt from the restored source after the blocked build.
- Post-stop health: `/healthz` returned `{"ok":true}` and connector `/healthz`
  returned `connected_session_count=2`.
- Session preservation proof after stop: both real provider subjects remained
  `connection_state=connected` with active delivery routes.

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

### Task 8: Final Coordinated Deploy After Alembic Filter Fix

**Files:**
- Modify: `scripts/deploy-compose-to-gcp.sh`
- Modify: `scripts/ops/migrate_coke_clean_credentials.py`
- Modify: `tests/unit/coke/deploy/test_clean_compose_deploy_contract.py`
- Modify: `tests/unit/coke/deploy/test_migrate_coke_clean_credentials.py`
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-coordinated-redeploy.md`
- Remote read/write: `/home/whoami/coke-clean`

- [x] **Step 1: Write failing deploy-script test for Alembic check**

Add a focused assertion to `tests/unit/coke/deploy/test_clean_compose_deploy_contract.py` proving the clean deploy script runs `alembic check` through the same `coke-migrate` Docker Compose path after `alembic upgrade head`.

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/deploy/test_clean_compose_deploy_contract.py::test_deploy_script_targets_clean_project_without_legacy_gateway_logic -v
```

Expected before implementation: FAIL because `scripts/deploy-compose-to-gcp.sh` runs `alembic upgrade head` but does not run `alembic check`.

- [x] **Step 2: Implement minimal deploy-script check**

Update the dry-run text and real remote deploy block so the script runs:

```bash
docker compose -p "$PROJECT_NAME" -f docker-compose.prod.yml -f docker-compose.clean.yml run --rm coke-migrate alembic upgrade head
docker compose -p "$PROJECT_NAME" -f docker-compose.prod.yml -f docker-compose.clean.yml run --rm coke-migrate alembic check
```

Do not add legacy stack, connector, or Evolution service control.

- [x] **Step 3: Verify deploy-script tests pass**

Run:

```bash
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/deploy -v
```

Expected after implementation: all deploy unit tests pass.

- [x] **Step 4: Commit local deploy-script and plan work**

Run:

```bash
git add scripts/deploy-compose-to-gcp.sh tests/unit/coke/deploy/test_clean_compose_deploy_contract.py docs/superpowers/plans/2026-05-29-coke-clean-rebuild-coordinated-redeploy.md
git commit -m "fix: require alembic check in clean deploy"
```

- [x] **Step 5: Capture fresh rollback snapshot and predeploy state**

On `gcp-coke`, create `/home/whoami/coke-clean-rollback-<UTC>.tgz` from
`/home/whoami/coke-clean` while preserving `.env`, and record current source
commit/image ids, `docker ps`, clean compose `ps`, API health, connector
`/healthz`, and the two real account channel/delivery-route rows.

- [x] **Step 6: Sync current main to remote without touching secrets**

Sync current `main` sources to `/home/whoami/coke-clean`, excluding `.git`,
`.venv`, `.env`, `node_modules`, `.next`, and `__pycache__`. Preserve the remote
`/home/whoami/coke-clean/.env`.

- [x] **Step 7: Run live Alembic upgrade and check**

Run both commands via the clean compose `coke-migrate` service against live
Postgres:

```bash
docker compose -p coke-clean -f docker-compose.prod.yml -f docker-compose.clean.yml run --rm coke-migrate alembic upgrade head
docker compose -p coke-clean -f docker-compose.prod.yml -f docker-compose.clean.yml run --rm coke-migrate alembic check
```

Expected: both exit 0. If either fails, classify with `systematic-debugging`,
stop before service recreation, and preserve product data.

- [x] **Step 8: Migrate only the two live credentials in place**

Run:

```bash
docker compose -p coke-clean -f docker-compose.prod.yml -f docker-compose.clean.yml run --rm -e PYTHONPATH=/app coke-migrate python scripts/ops/migrate_coke_clean_credentials.py
```

Expected: `credential_migration updated=2 skipped=0 missing=-` or an
idempotent `updated=0 skipped=2 missing=-` if already migrated. The script also
ensures missing `user_profile` rows for only these two preserved accounts,
because live `/api/friends` and notification rendering require the clean
identity profile contract. Verify no account/channel/channel_identity rows were
recreated.

- [x] **Step 9: Recreate only clean app services**

Recreate `coke-api`, `coke-worker`, `coke-scheduler`, `coke-outbox-relay`, and
`coke-web` from the new image/source. Do not restart or reconfigure
`evolution-*` or `wechat-personal-connector`.

- [x] **Step 10: Verify service health and restart stability**

Confirm `/healthz=200`, clean compose service health, restart counts are zero,
and recent logs do not show crash loops or connector disconnects.

- [x] **Step 11: Live login and bearer-auth verification**

Login `olivers@coke.keep4oforever.com` and
`lizihao@coke.keep4oforever.com` through `/api/auth/login` using the web
`password` field. Verify a customer route returns 401 without bearer token and
200 with bearer token.

- [x] **Step 12: Verify both real WeChat sessions are preserved**

Use the two session tokens to call channel status and verify
`connection_state=connected` for both account ids. Also verify connector
`/healthz` still reports `connected_session_count=2`. If any status is not
connected, stop and report that a human WeChat re-scan is required.

- [x] **Step 13: Live behavior spot-checks**

Drive authenticated/live-safe checks for:

1. A `明天中午` personal reminder stores a future local time and does not fire immediately.
2. A shared-reminder create reply does not say `等确认` and the DB row is `active`.
3. A notification fact renders from creator/title/time facts if a fresh notification is produced.
4. New delivery-attempt rows carry `message_id`.

Clean up marked future reminders/shared reminders through product APIs or domain
commands; do not delete unmarked user data.

- [x] **Step 14: Close plan**

After local pytest and live verification pass, set `Plan Status` to `complete`,
mark completed checkboxes, record final evidence, and commit the plan closeout if
it changed after the deploy-script commit.

Evidence:
- Fresh rollback snapshot: `/home/whoami/coke-clean-rollback-20260531T051954Z.tgz`
  (`snapshot_bytes=138069477`). Predeploy API `/healthz` returned `{"ok":true}`;
  connector `/healthz` returned `connected_session_count=2`; both real channel
  rows were `connection_state=connected` with active delivery routes.
- Source sync preserved `/home/whoami/coke-clean/.env` and excluded `.git`,
  `.venv`, `.env`, `node_modules`, `.next`, `__pycache__`, and root-owned web
  package-cache content.
- Live Alembic through `coke-migrate`: `alembic upgrade head` exited 0 and
  `alembic check` exited 0 with `No new upgrade operations detected.` after
  rebuilding the migration image containing `coke/alembic_filters.py`.
- Credential/profile migration: first scoped credential run updated the two
  preserved rows in place; after the clean API exposed missing profile rows,
  the idempotent rerun reported `credential_migration updated=0 skipped=2
  profiles_created=2 profiles_skipped=0 missing=-`. No account, channel, or
  channel-identity rows were recreated.
- Recreated only clean app services: `coke-api`, `coke-worker`,
  `coke-scheduler`, `coke-outbox-relay`, and `coke-web`. Final service state:
  API health 200; all five clean app services `status=running`; API health
  `healthy`; restart counts 0.
- Final API/auth verification: both olivers and lizihao login calls returned
  HTTP 200 with session tokens; `/api/channels/status` returned HTTP 401 without
  bearer and HTTP 200 with bearer; both channel statuses remained
  `connection_state=connected`; connector `/healthz` remained
  `connected_session_count=2`.
- Live behavior smoke marker `final-deploy-actor-20260531T054732Z`: `明天中午`
  personal reminder stored `2026-06-01T12:00:00+09:00` (`2026-06-01T03:00:00Z`)
  and was future/tomorrow-noon; shared reminder row
  `e7c4bcf21a794a57b151be005ea3bea8` was `active` on create and the reply did
  not contain `等确认`; notification fact
  `bc438965883341a3bc3868cce9bc2840` carried creator/title/time facts; rendered
  notification text included `olivers`, title, and time; two delivery attempts
  were `sent` with non-null `message_id`; the marked personal reminder was
  deleted and the marked shared reminder was cancelled.
- Local verification after fixes:
  `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/deploy
  tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_group_shared_reminder_creation_is_one_object_with_participant_projections
  tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_notification_facts_store_structured_data_no_prose_and_partial_delivery_state
  tests/unit/coke/llm/test_interaction_agent.py::test_render_notification_context_exposes_structured_facts_to_agent
  -v` -> `13 passed in 2.89s`.
- `git diff --check` exited 0.
