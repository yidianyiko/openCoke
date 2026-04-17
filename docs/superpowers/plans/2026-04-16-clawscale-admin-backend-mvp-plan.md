# ClawScale Admin Backend MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 admin backend at `/admin/*` with separate admin auth, read-only operational views, and minimal `AdminAccount` management.

**Architecture:** Stand up a dedicated admin auth stack using `AdminAccount`, then layer small read-only APIs over `Customer`, `Identity`, `Membership`, `AgentBinding`, `Channel`, and `OutboundDelivery`. On the web side, build a new `(admin)` route group instead of extending `/dashboard/*`; reuse display primitives from the old dashboard only where they fit the new information architecture.

**Tech Stack:** TypeScript, Hono, Prisma, PostgreSQL, Next.js, React, Vitest, pnpm

---

## Scope Check

This plan is **follow-up plan 5** from `2026-04-15-clawscale-platformization-design.md`.

This plan covers:

- admin login and session handling
- `/admin/customers`
- `/admin/channels`
- `/admin/deliveries`
- `/admin/agents`
- `/admin/admins`

This plan does **not** cover:

- shared-channel management UI
- delivery retry controls
- org / invite / role expansion
- customer-business-data introspection

## File Structure

### New Gateway API files

- `gateway/packages/api/src/lib/admin-auth.ts`
- `gateway/packages/api/src/lib/admin-auth.test.ts`
- `gateway/packages/api/src/middleware/admin-auth.ts`
- `gateway/packages/api/src/routes/admin-auth-routes.ts`
- `gateway/packages/api/src/routes/admin-auth-routes.test.ts`
- `gateway/packages/api/src/routes/admin-customers.ts`
- `gateway/packages/api/src/routes/admin-customers.test.ts`
- `gateway/packages/api/src/routes/admin-channels.ts`
- `gateway/packages/api/src/routes/admin-channels.test.ts`
- `gateway/packages/api/src/routes/admin-deliveries.ts`
- `gateway/packages/api/src/routes/admin-deliveries.test.ts`
- `gateway/packages/api/src/routes/admin-agents.ts`
- `gateway/packages/api/src/routes/admin-agents.test.ts`
- `gateway/packages/api/src/routes/admin-admins.ts`
- `gateway/packages/api/src/routes/admin-admins.test.ts`
- `gateway/packages/api/src/scripts/bootstrap-admin-account.ts`

### New Web files

- `gateway/packages/web/app/(admin)/admin/layout.tsx`
- `gateway/packages/web/app/(admin)/admin/login/page.tsx`
- `gateway/packages/web/app/(admin)/admin/customers/page.tsx`
- `gateway/packages/web/app/(admin)/admin/channels/page.tsx`
- `gateway/packages/web/app/(admin)/admin/deliveries/page.tsx`
- `gateway/packages/web/app/(admin)/admin/agents/page.tsx`
- `gateway/packages/web/app/(admin)/admin/admins/page.tsx`
- `gateway/packages/web/lib/admin-api.ts`
- `gateway/packages/web/lib/admin-auth.ts`
- `gateway/packages/web/lib/admin-copy.ts`

## Task 1: Add admin auth and bootstrap flow

**Files:**
- Create: `gateway/packages/api/src/lib/admin-auth.ts`
- Create: `gateway/packages/api/src/lib/admin-auth.test.ts`
- Create: `gateway/packages/api/src/middleware/admin-auth.ts`
- Create: `gateway/packages/api/src/routes/admin-auth-routes.ts`
- Create: `gateway/packages/api/src/routes/admin-auth-routes.test.ts`
- Create: `gateway/packages/api/src/scripts/bootstrap-admin-account.ts`
- Modify: `gateway/packages/api/src/index.ts`

- [x] Write failing tests for:
  - admin login succeeds only with `AdminAccount`
  - admin session is independent of customer auth
  - inactive admins cannot log in
- [x] Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/admin-auth.test.ts \
  src/routes/admin-auth-routes.test.ts
```

- [x] Implement admin auth plus a bootstrap script that creates the first admin account from env vars.
- [x] Mount `/api/admin/login`, `/logout`, and `/session`.
- [x] Re-run the focused admin-auth suite.

## Task 2: Build read-only admin APIs

**Files:**
- Create: `gateway/packages/api/src/routes/admin-customers.ts`
- Create: `gateway/packages/api/src/routes/admin-channels.ts`
- Create: `gateway/packages/api/src/routes/admin-deliveries.ts`
- Create: `gateway/packages/api/src/routes/admin-agents.ts`
- Create: `gateway/packages/api/src/routes/admin-admins.ts`
- Create: the matching `*.test.ts` files

- [x] Add failing route tests that assert:
  - `/api/admin/customers` returns contact identifier, claim status, registered-at / first-seen-at, agent, and channel summary
  - `/api/admin/channels` filters by status and kind
  - `/api/admin/deliveries` returns recent failed `OutboundDelivery` rows only
  - `/api/admin/agents` returns the single Coke agent detail
  - `/api/admin/admins` supports add/remove for `AdminAccount`
- [x] Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/routes/admin-customers.test.ts \
  src/routes/admin-channels.test.ts \
  src/routes/admin-deliveries.test.ts \
  src/routes/admin-agents.test.ts \
  src/routes/admin-admins.test.ts
```

- [x] Implement the APIs with paging and filters where the spec requires them.
- [x] Re-run the focused admin route suite.

## Task 3: Build the `/admin/*` web shell and pages

**Files:**
- Create: `gateway/packages/web/app/(admin)/admin/layout.tsx`
- Create: `gateway/packages/web/app/(admin)/admin/login/page.tsx`
- Create: `gateway/packages/web/app/(admin)/admin/customers/page.tsx`
- Create: `gateway/packages/web/app/(admin)/admin/channels/page.tsx`
- Create: `gateway/packages/web/app/(admin)/admin/deliveries/page.tsx`
- Create: `gateway/packages/web/app/(admin)/admin/agents/page.tsx`
- Create: `gateway/packages/web/app/(admin)/admin/admins/page.tsx`
- Create: `gateway/packages/web/lib/admin-api.ts`
- Create: `gateway/packages/web/lib/admin-auth.ts`
- Create: `gateway/packages/web/lib/admin-copy.ts`

- [x] Write failing page tests for:
  - unauthenticated admins redirect to `/admin/login`
  - customers page renders the required columns
  - channels and deliveries pages render filters and paging
  - agents page is read-only
  - admins page can add/remove accounts
- [x] Run:

```bash
pnpm --dir gateway/packages/web test -- \
  "app/(admin)/admin/login/page.test.tsx" \
  "app/(admin)/admin/customers/page.test.tsx"
```

- [x] Implement the new `(admin)` route group and shared navigation.
- [x] Reuse old dashboard components only after renaming them into admin-owned files; do not keep `/dashboard/*` imports inside the new pages.
- [x] Re-run the focused admin web tests.

## Task 4: Verify the MVP and freeze the old dashboard

**Files:**
- Modify: `gateway/packages/web/app/dashboard/*` only where needed to point users at `/admin/*`
- Modify: `gateway/packages/api/src/index.ts`

- [x] Run the full admin verification:

```bash
pnpm --dir gateway/packages/api test -- \
  src/routes/admin-auth-routes.test.ts \
  src/routes/admin-customers.test.ts \
  src/routes/admin-channels.test.ts \
  src/routes/admin-deliveries.test.ts \
  src/routes/admin-agents.test.ts \
  src/routes/admin-admins.test.ts
pnpm --dir gateway/packages/web test
pnpm --dir gateway/packages/api build
pnpm --dir gateway/packages/web build
```

- [x] Record the remaining `/dashboard/*` entry points that plan 6 must remove.
  - `/dashboard`
  - `/dashboard/login`
  - `/dashboard/register`
  - `/dashboard/onboard` (still needs an explicit successor mapping in plan 6)
  - `/dashboard/conversations`
  - `/dashboard/channels`
  - `/dashboard/ai-backends`
  - `/dashboard/workflows`
  - `/dashboard/end-users`
  - `/dashboard/users`
  - `/dashboard/settings`
