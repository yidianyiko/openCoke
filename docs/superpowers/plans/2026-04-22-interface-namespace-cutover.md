# Interface Namespace Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining Coke-branded public interfaces, complete the customer namespace cutover, and lock the new interface contract in docs and tests.

**Architecture:** Public customer auth remains under `/auth/*` and `/api/auth/*`. Customer-owned resources move under `/channels/*`, `/account/*`, and `/api/customer/*`; public tokenized handoffs move under `/api/public/*`; third-party callbacks move under `/api/webhooks/*`. Legacy `/coke/*` and `/api/coke/*` routes are deleted and must fail closed with `404`.

**Tech Stack:** Next.js 16, React 19, TypeScript, Hono, Vitest, pytest, shell deploy checks

---

### Task 1: Lock the namespace contract in docs and failing tests

**Files:**
- Create: `docs/design-docs/interface-contract.md`
- Create: `docs/superpowers/specs/2026-04-22-interface-namespace-cutover-design.md`
- Create: `docs/exec-plans/2026-04-22-interface-namespace-cutover.md`
- Create: `tasks/2026-04-22-interface-namespace-cutover.md`
- Modify: `docs/design-docs/index.md`
- Modify: `tests/unit/test_no_compat_routes.py`

- [ ] Add the canonical interface contract and link it from the design-docs index.
- [ ] Expand the structure guard so it fails if the legacy `/coke/payment` page or `/api/coke` router wiring remains.
- [ ] Record the new acceptance criteria and verification set in the task file.

### Task 2: Cut the gateway API over to neutral customer/public namespaces

**Files:**
- Modify: `gateway/packages/api/src/index.ts`
- Create: `gateway/packages/api/src/routes/customer-subscription-routes.ts`
- Create: `gateway/packages/api/src/routes/customer-subscription-routes.test.ts`
- Delete: `gateway/packages/api/src/routes/coke-payment-routes.ts`
- Delete: `gateway/packages/api/src/routes/coke-payment-routes.test.ts`
- Delete: `gateway/packages/api/src/routes/coke-wechat-routes.ts`
- Delete: `gateway/packages/api/src/routes/coke-wechat-routes.test.ts`
- Modify: `gateway/packages/api/src/routes/customer-channel-routes.ts`
- Modify: `gateway/packages/api/src/routes/customer-channel-routes.test.ts`
- Modify: `gateway/packages/api/src/lib/coke-public-checkout.ts`
- Modify: `gateway/packages/api/src/lib/coke-public-checkout.test.ts`
- Modify: `gateway/packages/api/src/lib/coke-subscription.ts`
- Modify: `gateway/packages/api/src/lib/coke-subscription.test.ts`
- Modify: `gateway/packages/api/src/middleware/coke-user-auth.ts`
- Modify: `gateway/packages/api/src/lib/route-message.test.ts`
- Modify: `gateway/packages/api/src/scripts/stripe-e2e-smoke.ts`
- Modify: `gateway/packages/api/src/scripts/stripe-e2e-smoke.test.ts`

- [ ] Add failing API tests for `/api/customer/subscription`, `/api/customer/subscription/checkout`, `/api/public/subscription-checkout`, and `/api/webhooks/stripe`.
- [ ] Implement the new router wiring and remove `/api/coke` route registration.
- [ ] Remove legacy Coke-token fallback from customer-facing channel/subscription auth.
- [ ] Update renewal/public-checkout URL generation and Stripe smoke coverage to the new paths.

### Task 3: Cut the web app over to neutral customer/account namespaces

**Files:**
- Create: `gateway/packages/web/app/(customer)/account/subscription/page.tsx`
- Create: `gateway/packages/web/app/(customer)/account/subscription/page.test.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/payment/page.tsx`
- Delete: `gateway/packages/web/app/(coke-user)/coke/payment/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/login/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/login/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/register/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/register/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/verify-email/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/verify-email/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/forgot-password/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/forgot-password/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/reset-password/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/reset-password/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/channels/wechat-personal/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/channels/wechat-personal/page.test.tsx`
- Modify: `gateway/packages/web/components/coke-homepage.tsx`
- Modify: `gateway/packages/web/lib/customer-auth.ts`
- Modify: `gateway/packages/web/lib/coke-user-auth.ts`
- Modify: `gateway/packages/web/lib/coke-user-auth.test.ts`
- Modify: `gateway/packages/web/lib/customer-wechat-channel.ts`
- Modify: `gateway/packages/web/lib/coke-user-wechat-channel.ts`

- [ ] Add failing web tests for the new `/account/subscription` page and for removed `/coke/payment` references.
- [ ] Move all customer-facing links and redirects from `/coke/payment` to `/account/subscription`.
- [ ] Stop customer pages from depending on separate Coke-token compatibility helpers for normal auth flow.

### Task 4: Update rollout docs and verify the whole surface

**Files:**
- Modify: `docs/clawscale_bridge.md`
- Modify: `docs/deploy.md`
- Modify: `docs/roadmap.md`
- Modify: `scripts/deploy-compose-to-gcp.sh`
- Modify: `scripts/test-deploy-compose-to-gcp.sh`

- [ ] Update live docs and deploy checks to the new interface contract.
- [ ] Run targeted API/web tests first, then broaden to deploy and repo-OS checks.
- [ ] Confirm the old `/coke/*` and `/api/coke/*` entrypoints are absent from live docs, route registration, and structure tests.
