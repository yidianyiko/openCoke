# Compatibility Caller Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining generic `/coke/*` compatibility pages and paused `/api/coke/*` auth compatibility routes, while keeping the supported Coke business payment flow working.

**Architecture:** Treat `/auth/*` and `/channels/wechat-personal` as the only supported generic customer entrypoints, enrich `/api/auth/me` so the web can hydrate the same profile/subscription state without `/api/coke/me`, and keep Coke business checkout on `/coke/payment` plus `/api/coke/subscription|checkout`.

**Tech Stack:** Bash, Next.js 16, React 19, TypeScript, Vitest, Hono, pytest

---

### Task 1: Lock the hard-removal contract in failing tests

**Files:**
- Modify: `gateway/packages/web/app/(customer)/auth/login/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/verify-email/page.test.tsx`
- Modify: `gateway/packages/api/src/routes/customer-auth-routes.test.ts`
- Create: `tests/unit/test_no_compat_routes.py`

- [x] Update the web tests to hydrate from `/api/auth/me`.
- [x] Update the API route tests to expect the enriched `/api/auth/me` payload.
- [x] Add a repository structure test that fails while the legacy wrapper directories and compatibility router still exist.
- [x] Run the narrow commands once and confirm they fail before implementation.

### Task 2: Remove compatibility surfaces and cut the remaining callers over

**Files:**
- Modify: `gateway/packages/web/app/(customer)/auth/login/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/verify-email/page.tsx`
- Modify: `gateway/packages/api/src/routes/customer-auth-routes.ts`
- Modify: `gateway/packages/api/src/index.ts`
- Modify: `scripts/deploy-compose-to-gcp.sh`
- Modify: `scripts/test-deploy-compose-to-gcp.sh`
- Modify: `docs/clawscale_bridge.md`
- Modify: `docs/roadmap.md`
- Delete: `gateway/packages/api/src/routes/coke-auth-routes.ts`
- Delete: `gateway/packages/api/src/routes/coke-auth-routes.test.ts`
- Delete: `gateway/packages/web/components/legacy-redirect-page.tsx`
- Delete: `gateway/packages/web/components/legacy-redirect-page.test.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/login/page.test.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/register/page.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/register/page.test.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/forgot-password/page.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/forgot-password/page.test.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/reset-password/page.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/reset-password/page.test.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/verify-email/page.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/verify-email/page.test.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.test.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/renew/page.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/renew/page.test.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/payment-success/page.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/payment-cancel/page.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/payment-pages.test.tsx`

- [x] Move the last generic profile hydration path from `/api/coke/me` to `/api/auth/me`.
- [x] Enrich `/api/auth/me` with the profile and subscription fields the web already consumes.
- [x] Delete the generic wrapper pages, compatibility auth router, and legacy redirect helper.
- [x] Update deployment checks and live docs so they no longer point to deleted compatibility routes.

### Task 3: Remove filesystem remnants and verify the repo is clean

**Files:**
- Modify: `tasks/2026-04-21-compat-caller-cutover.md`
- Modify: `docs/exec-plans/2026-04-21-compat-caller-cutover.md`
- Test: `tests/unit/test_no_compat_routes.py`
- Test: `gateway/packages/web/app/(customer)/auth/login/page.test.tsx`
- Test: `gateway/packages/web/app/(customer)/auth/verify-email/page.test.tsx`
- Test: `gateway/packages/api/src/routes/customer-auth-routes.test.ts`
- Test: `scripts/test-deploy-compose-to-gcp.sh`
- Test: `pytest tests/unit/test_repo_os_structure.py -v`
- Test: `zsh scripts/check`

- [x] Remove the empty legacy wrapper directories from the filesystem so structure assertions reflect the real route surface.
- [x] Run the broad verification commands from the task file and confirm they pass.
- [x] Re-scan the repo for live references to the deleted compatibility routes and confirm only historical docs or negative assertions remain.
