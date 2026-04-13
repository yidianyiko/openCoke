# Email/Auth Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining Coke email-auth product and deployment gaps without changing the existing Gateway-owned auth architecture.

**Architecture:** Keep the existing API and web routes, harden registration so email delivery failure does not strand newly created accounts, let verify-email recover the stored email when the URL lacks it, and document the env surface required to run the flow in production. All behavior changes land behind focused API/web tests first.

**Tech Stack:** Hono, Prisma, Next.js, React, Vitest, Docker Compose

---

### Task 1: Lock down the backend registration edge case

**Files:**
- Modify: `gateway/packages/api/src/routes/coke-auth-routes.test.ts`
- Modify: `gateway/packages/api/src/routes/coke-auth-routes.ts`

- [ ] Add a failing route test proving registration still succeeds when `sendCokeEmail` throws.
- [ ] Run: `pnpm -C gateway --filter @clawscale/api test -- src/routes/coke-auth-routes.test.ts`
- [ ] Update the register route to catch verification-email delivery failures, log them, and still return the normal auth payload.
- [ ] Re-run: `pnpm -C gateway --filter @clawscale/api test -- src/routes/coke-auth-routes.test.ts`

### Task 2: Lock down the frontend verify-email recovery flow

**Files:**
- Modify: `gateway/packages/web/app/(coke-user)/coke/verify-email/page.test.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/verify-email/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`

- [ ] Add a failing web test proving verify-email falls back to the stored Coke user email when the query string lacks `email`.
- [ ] Add a failing web test proving the login page exposes a forgot-password link.
- [ ] Run: `pnpm -C gateway --filter @clawscale/web test -- 'app/(coke-user)/coke/verify-email/page.test.tsx'`
- [ ] Implement the fallback email prefill and forgot-password entry.
- [ ] Re-run a focused web test command for the touched pages.

### Task 3: Close deployment/env documentation gaps

**Files:**
- Create: `deploy/env/coke.env.example`
- Modify: `gateway/.env.example`
- Modify: `docs/deploy.md`

- [ ] Add a deployment env example that matches the file referenced by `docs/deploy.md`.
- [ ] Expand the Gateway env example with Coke auth/email/payment variables.
- [ ] Update deployment docs so the production setup path references real files and calls out the required Coke email-auth variables.

### Task 4: Final verification

**Files:**
- No source changes expected

- [ ] Run: `pnpm -C gateway --filter @clawscale/api test -- src/routes/coke-auth-routes.test.ts src/lib/email.test.ts`
- [ ] Run: `pnpm -C gateway --filter @clawscale/web test -- 'app/(coke-user)/coke/verify-email/page.test.tsx'`
- [ ] Run: `pnpm -C gateway --filter @clawscale/web test`
- [ ] Summarize any remaining risk that still depends on production secrets or mail provider setup.
