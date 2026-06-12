# Disable Email Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a runtime switch that disables web email verification and password recovery while allowing direct registration/login.

**Architecture:** Introduce `Settings.email_auth_enabled` and pass it into `IdentityAccessService`. Keep existing email-auth behavior when enabled. In disabled mode, registration stores verified account access immediately, email-auth endpoints fail closed with `email_auth_disabled`, and the web UI routes users directly into the product.

**Tech Stack:** Python Flask backend, IdentityAccess domain service, Next.js customer web app, pytest, pnpm test.

---

## File Structure

- Modify `coke/config.py`: parse `COKE_EMAIL_AUTH_ENABLED` and relax production `RESEND_API_KEY` requirement when disabled.
- Modify `coke/composition.py`: pass the flag to `IdentityAccessService`.
- Modify `coke/domains/identity_access/models.py`: allow registration results without an email verification artifact.
- Modify `coke/domains/identity_access/service.py`: implement disabled-mode registration and disabled email-auth methods.
- Modify `coke/api/auth_routes.py`: omit `email_verification_artifact_id` when absent.
- Modify `scripts/deploy-compose-to-gcp.sh`: write `COKE_EMAIL_AUTH_ENABLED=0` by default and stop aborting when `RESEND_API_KEY` is absent in disabled mode.
- Modify customer auth pages/tests under `web/app/(customer)/auth/`.
- Update product/deploy/feature docs.

### Task 1: Backend Settings And Service Tests

**Files:**
- Modify: `tests/unit/coke/test_backend_foundation.py`
- Modify: `tests/unit/coke/identity_access/test_identity_access_service.py`
- Modify: `tests/unit/coke/identity_access/test_auth_routes.py`

- [x] Write failing tests for `COKE_EMAIL_AUTH_ENABLED=0`, missing production `RESEND_API_KEY`, direct verified registration, no email artifact/email send, disabled resend/reset methods, disabled route responses, and deploy env behavior.
- [x] Run targeted pytest and confirm the new tests fail on the current implementation.

### Task 2: Backend Implementation

**Files:**
- Modify: `coke/config.py`
- Modify: `coke/composition.py`
- Modify: `coke/domains/identity_access/models.py`
- Modify: `coke/domains/identity_access/service.py`
- Modify: `coke/api/auth_routes.py`
- Modify: `scripts/deploy-compose-to-gcp.sh`

- [x] Add `email_auth_enabled` setting with bool parsing.
- [x] Pass the setting into `IdentityAccessService`.
- [x] Make disabled-mode web registration verified immediately and artifact-free.
- [x] Make email-verification resend and password reset methods raise `IdentityAccessError("email_auth_disabled")`.
- [x] Make the register route omit `email_verification_artifact_id` when no artifact exists.
- [x] Update the deploy script so disabled email auth does not require a Resend key.
- [x] Run targeted backend pytest and confirm it passes: `158 passed`.

### Task 3: Web Tests And Implementation

**Files:**
- Modify: `web/app/(customer)/auth/register/page.tsx`
- Modify: `web/app/(customer)/auth/login/page.tsx`
- Modify: related auth page tests.

- [x] Write failing web tests for direct post-registration routing, hidden password recovery / verification recovery UI, and disabled direct forgot/reset pages.
- [x] Run targeted `pnpm test` filters and confirm the new tests fail.
- [x] Route successful registration directly to `next` or `/channels/wechat-personal`.
- [x] Remove the visible forgot-password link and ignore verification recovery query UI while email auth is disabled.
- [x] Disable the `/auth/verify-email` page itself so old email links no longer attempt verification or resend recovery.
- [x] Run targeted web tests and confirm they pass: auth/i18n target `31 passed`, verify-email page `2 passed`, full web test `214 passed`, web build passed.

### Task 4: Docs, Verification, Commit, Deploy

**Files:**
- Modify: `docs/product-requirements/current.md`
- Modify: `docs/product-specs/FEATURE_TREE.md`
- Modify: `docs/deploy.md`
- Modify: this plan status.

- [x] Update the active product contract and deploy docs for disabled email auth.
- [x] Run diff-aware verification routing with `zsh scripts/suggest-verification --base HEAD~1` and `zsh scripts/review-trigger --base HEAD~1`.
- [x] Run the suggested surface verification or record any classified gap:
  `clean-rebuild-docs` passed inside `zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend clean-rebuild-web repo-os-docs deploy`.
  The run stopped in `clean-rebuild-backend` on six failures from the unrelated dirty file
  `tests/unit/coke/turn/inbound/test_reminder_handler.py`, which now expects reminder
  `validate_trigger_time` calls. This file is not part of the email-auth change and was
  not staged. Email-auth backend targets passed (`158 passed`), full web tests passed
  (`214 passed` after replacing legacy verify-email flow tests with disabled-page tests), and
  `pnpm build` passed.
- [x] Commit the completed change: `33aded3b fix: disable email auth for direct registration`.
- [x] Deploy using the documented clean compose path and smoke registration/current-user/access-status in production:
  clean backend deploy wrote `COKE_EMAIL_AUTH_ENABLED=0`, migrations passed, and backend health passed.
  The first deploy did not recreate `coke-web` despite a full tier, so `coke-web` was force-recreated
  manually and the deploy script was tightened to use explicit `backend`, `web`, and `full` branches.
  Production smoke evidence is in `artifacts/evidence/2026-06-12-disable-email-auth-production-smoke.md`:
  server-local register/current-user/access-status/login/password-reset checks passed, DB showed zero
  email auth artifacts for the smoke account, and public API registration/access-status passed with a
  browser user agent.
