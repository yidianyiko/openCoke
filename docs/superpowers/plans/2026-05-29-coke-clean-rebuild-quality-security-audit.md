# Quality Security Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan Status:** complete

**Goal:** Fix the clean-rebuild plaintext-password and customer-route authorization bugs, then record prioritized security and quality audit findings.

**Architecture:** Passwords are accepted only as raw user secrets at the API boundary, hashed server-side by IdentityAccess, and verified with the same KDF on login/reset. Customer-scoped API routes resolve the acting account from a validated bearer session and ignore client-supplied account identifiers for ownership; public claim/webhook routes stay separate.

**Tech Stack:** Flask route adapters, IdentityAccess domain service/repository, in-memory unit tests, Next.js customer auth client, argon2-cffi for password hashing, pytest and web unit tests where touched.

---

## File Structure

- Modify `requirements.txt`: add `argon2-cffi` as the password KDF dependency.
- Create `coke/domains/identity_access/passwords.py`: small password hashing/verifying adapter around Argon2.
- Modify `coke/domains/identity_access/service.py`: rename raw-password parameters, hash on registration/reset, verify on login.
- Modify `coke/api/auth_helpers.py`: shared bearer-token account resolution for customer route adapters.
- Modify `coke/api/auth_routes.py`: accept `password`, require current session for access-status, keep login/register public.
- Modify `coke/api/channel_routes.py`: require bearer auth on customer channel routes and derive `account_id` from the session.
- Modify `coke/api/reminder_routes.py`: require bearer auth on web reminder routes and derive `owner_account_id` from the session.
- Modify `coke/api/friend_routes.py`: require bearer auth on customer friend routes and derive owner/joiner/account id from the session where the route is customer-scoped.
- Modify `coke/api/shared_reminder_routes.py`: require bearer auth and derive requester/creator/account id from the session.
- Modify `coke/api/calendar_import_routes.py`: require bearer auth and derive `account_id` from the session.
- Modify `coke/api/claim_routes.py`: require bearer auth for pairing-code issuance; leave claim-code issue/poll/redeem/complete public because they are the claim handoff itself.
- Modify `coke/app.py`: pass the identity service into customer route blueprint factories.
- Modify `web/lib/customer-auth.ts` and tests: send `password` instead of `password_hash`.
- Modify route and service unit tests under `tests/unit/coke/**`: encode the new auth and password contracts.
- Create `docs/issues/2026-05-31-quality-security-audit.md`: prioritized findings and fixed/remain status.

### Task 1: Password Contract And Hashing

**Files:**
- Modify: `requirements.txt`
- Create: `coke/domains/identity_access/passwords.py`
- Modify: `coke/domains/identity_access/service.py`
- Modify: `coke/api/auth_routes.py`
- Modify: `web/lib/customer-auth.ts`
- Test: `tests/unit/coke/identity_access/test_identity_access_service.py`
- Test: `tests/unit/coke/identity_access/test_auth_routes.py`
- Test: `web/lib/customer-auth.test.ts`

- [x] **Step 1: Write failing service tests**

Add tests proving registration stores a KDF hash instead of the raw password, login verifies the raw password, wrong passwords fail, and password reset stores a new hash.

- [x] **Step 2: Run service tests to verify RED**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/identity_access/test_identity_access_service.py -v`
Expected: FAIL because the service still accepts and stores `password_hash` directly.

- [x] **Step 3: Write failing auth route and web client tests**

Update route tests to send `password`, expect service calls with `password`, and expect missing `password` errors. Update web tests to assert `/api/auth/register`, `/api/auth/login`, and reset completion send `password`.

- [x] **Step 4: Run auth route and web-client tests to verify RED**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/identity_access/test_auth_routes.py -v`
Expected: FAIL because the route still requires `password_hash`.

Run: `cd web && pnpm test -- customer-auth.test.ts`
Expected: FAIL because the client still sends `password_hash`.

- [x] **Step 5: Implement password hashing**

Add `argon2-cffi`, implement `PasswordHasher`, and update IdentityAccess APIs to hash raw passwords on registration/reset and verify raw passwords on login.

- [x] **Step 6: Update auth route and web client contract**

Change auth routes and `web/lib/customer-auth.ts` to use `password`; keep response shapes unchanged.

- [x] **Step 7: Run focused password/auth tests to verify GREEN**

Run the same focused pytest and web test commands. Expected: all selected tests pass.

- [x] **Step 8: Commit password fix**

Run: `git add requirements.txt coke/domains/identity_access/passwords.py coke/domains/identity_access/service.py coke/api/auth_routes.py web/lib/customer-auth.ts tests/unit/coke/identity_access/test_identity_access_service.py tests/unit/coke/identity_access/test_auth_routes.py web/lib/customer-auth.test.ts docs/superpowers/plans/2026-05-29-coke-clean-rebuild-quality-security-audit.md && git commit -m "fix: hash customer passwords server side"`

Completed in combined security commit `f07724c3 fix: secure customer auth boundary`.

### Task 2: Customer Route Session Authorization

**Files:**
- Create: `coke/api/auth_helpers.py`
- Modify: `coke/api/channel_routes.py`
- Modify: `coke/api/reminder_routes.py`
- Modify: `coke/api/friend_routes.py`
- Modify: `coke/api/shared_reminder_routes.py`
- Modify: `coke/api/calendar_import_routes.py`
- Modify: `coke/api/claim_routes.py`
- Modify: `coke/app.py`
- Test: route tests under `tests/unit/coke/channel_reachability/`, `tests/unit/coke/reminder/`, `tests/unit/coke/social_scheduling/`, `tests/unit/coke/calendar_import/`, and `tests/unit/coke/identity_access/`

- [x] **Step 1: Write failing route auth tests**

Add tests proving customer routes reject missing bearer tokens before service calls, call `identity_service.current_user`, and use the resolved account id even when a body/query account id spoofs another user.

- [x] **Step 2: Run focused route tests to verify RED**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/channel_reachability/test_channel_routes.py tests/unit/coke/reminder/test_reminder_routes.py tests/unit/coke/social_scheduling/test_social_scheduling_routes.py tests/unit/coke/calendar_import/test_calendar_import_routes.py tests/unit/coke/identity_access/test_auth_routes.py -v`
Expected: FAIL because the route adapters do not yet require the bearer session.

- [x] **Step 3: Implement shared customer auth helper**

Create a helper that extracts `Authorization: Bearer <token>`, calls `identity_service.current_user`, and returns the resolved account id or raises a JSON route error before business-service calls.

- [x] **Step 4: Wire customer route adapters**

Update customer blueprint factories to accept `identity_service`, require auth for customer-scoped routes, derive ownership from the resolved account, and leave provider webhooks plus public claim handoff routes unchanged.

- [x] **Step 5: Wire app factory**

Update `create_app` to pass `identity_access_service` into customer route blueprint factories when both the domain service and identity service are available.

- [x] **Step 6: Run focused route tests to verify GREEN**

Run the same focused pytest command. Expected: all selected tests pass.

- [x] **Step 7: Commit route auth fix**

Run: `git add coke/api/auth_helpers.py coke/api/channel_routes.py coke/api/reminder_routes.py coke/api/friend_routes.py coke/api/shared_reminder_routes.py coke/api/calendar_import_routes.py coke/api/claim_routes.py coke/app.py tests/unit/coke/channel_reachability/test_channel_routes.py tests/unit/coke/reminder/test_reminder_routes.py tests/unit/coke/social_scheduling/test_social_scheduling_routes.py tests/unit/coke/calendar_import/test_calendar_import_routes.py tests/unit/coke/identity_access/test_auth_routes.py docs/superpowers/plans/2026-05-29-coke-clean-rebuild-quality-security-audit.md && git commit -m "fix: require sessions on customer routes"`

Completed in combined security commit `f07724c3 fix: secure customer auth boundary`.

### Task 3: Audit Report And Verification

**Files:**
- Create: `docs/issues/2026-05-31-quality-security-audit.md`
- Modify: `docs/superpowers/plans/2026-05-29-coke-clean-rebuild-quality-security-audit.md`

- [x] **Step 1: Audit remaining authz and error surfaces**

Search customer API routes for raw `account_id` ownership inputs, public claim/webhook exceptions, internal auth, secret/PII exposure, and broad exception handling.

- [x] **Step 2: Write audit issue report**

Record P0/P1/P2 findings with file:line references, fixed status, remaining risk, and evidence commands.

- [x] **Step 3: Run full unit suite**

Run: `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke -q`
Expected: all unit tests pass.

- [x] **Step 4: Run diff-aware verification routing**

Run: `zsh scripts/suggest-verification --base HEAD~1`
Run: `zsh scripts/review-trigger --base HEAD~1`
Expected: commands complete and any additional suggested local checks are run or documented as not run.

- [x] **Step 5: Mark plan complete after verification**

Update this plan's checkboxes and set `Plan Status` to `complete` only after the verification commands pass.

- [x] **Step 6: Commit audit report and plan closeout**

Run: `git add docs/issues/2026-05-31-quality-security-audit.md docs/superpowers/plans/2026-05-29-coke-clean-rebuild-quality-security-audit.md && git commit -m "docs: record quality security audit"`
