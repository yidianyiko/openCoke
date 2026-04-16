# ClawScale Auth Ownership Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move customer registration, login, password reset, email verification, and QR-channel self-service onto ClawScale-neutral gateway surfaces backed by `Identity` / `Customer` / `Membership`, while keeping Coke-specific payment logic agent-scoped.

**Architecture:** Reuse the existing Gateway auth/email/payment work, but relocate the generic parts behind neutral `customer` / `auth` boundaries. The new auth stack writes the platform-owned schema introduced by plan 1, emits `customer_id` as the long-term wire identifier, and keeps a short compatibility window that accepts both `account_id` and `customer_id` between ClawScale and Coke. Existing `/api/coke/*` auth routes become temporary aliases and are removed only after frontend relocation lands.

**Tech Stack:** TypeScript, Hono, Prisma, PostgreSQL, Vitest, pnpm, tsx, bcryptjs, jsonwebtoken, Resend, Python 3.12, pytest

---

## Scope Check

This plan is **follow-up plan 2** from `2026-04-15-clawscale-platformization-design.md`.

This plan covers:

- neutral backend auth routes
- neutral email verification / password reset / resend flow
- neutral self-service customer channel routes
- wire compatibility for `account_id` <-> `customer_id`
- relocating the old Resend and one-click-verification work into the new generic surface

This plan does **not** cover:

- deleting Coke Mongo `users` or Postgres `coke_accounts`
- moving the web pages off `(coke-user)/coke/*`
- admin backend auth
- shared-channel claim flow (`/auth/claim`)

## File Structure

### New Gateway API files

- `gateway/packages/api/src/lib/customer-auth.ts`
  Generic credential helpers backed by `Identity` / `Membership` / `Customer`.
- `gateway/packages/api/src/lib/customer-auth.test.ts`
  Covers email normalization, password hashing, JWT issuance, and identity lookup.
- `gateway/packages/api/src/lib/customer-email.ts`
  Generic verification / reset email payload builders that wrap the Resend sender.
- `gateway/packages/api/src/middleware/customer-auth.ts`
  Middleware for customer JWT auth using `customer_id`.
- `gateway/packages/api/src/routes/customer-auth-routes.ts`
  `/api/auth/register`, `/login`, `/verify-email`, `/resend-verification`, `/forgot-password`, `/reset-password`, `/me`.
- `gateway/packages/api/src/routes/customer-auth-routes.test.ts`
  Route tests for the neutral auth lifecycle.
- `gateway/packages/api/src/routes/customer-channel-routes.ts`
  Neutral `/api/customer/channels/*` or `/api/channels/wechat-personal/*` routes replacing Coke-prefixed self-service channel routes.
- `gateway/packages/api/src/routes/customer-channel-routes.test.ts`
  Covers connect / disconnect / archive / status using `customer_id`.
- `gateway/packages/api/src/scripts/audit-wire-identifier-compat.ts`
  CLI that checks where `account_id` still appears on ClawScale <-> Coke contracts.

### Modified Gateway API files

- `gateway/packages/api/src/index.ts`
  Mount neutral auth and customer-channel routes; keep temporary `/api/coke/*` aliases.
- `gateway/packages/api/src/lib/email.ts`
  Keep Resend as the sender, but rename Coke-specific builders to generic auth email builders.
- `gateway/packages/api/src/lib/coke-auth.ts`
  Replace or split into generic `customer-auth.ts` plus Coke-only payment helpers.
- `gateway/packages/api/src/middleware/coke-user-auth.ts`
  Convert into a thin alias or delete after neutral middleware lands.
- `gateway/packages/api/src/routes/coke-auth-routes.ts`
  Downgrade to compatibility wrappers that call the neutral handlers.
- `gateway/packages/api/src/routes/coke-wechat-routes.ts`
  Downgrade to compatibility wrappers that call the neutral channel handlers.
- `gateway/packages/api/src/routes/coke-payment-routes.ts`
  Keep only Coke-specific payment / subscription behavior; remove auth concerns.

### Modified Bridge / Agent files

- `connector/clawscale_bridge/app.py`
- `connector/clawscale_bridge/message_gateway.py`
- `connector/clawscale_bridge/gateway_identity_client.py`
- `connector/clawscale_bridge/gateway_personal_channel_client.py`
- `connector/clawscale_bridge/gateway_outbound_client.py`
- `agent/runner/identity.py`

These files must accept both `customer_id` and `account_id` during the compatibility window, while emitting `customer_id` whenever ClawScale originates the payload.

## Task 1: Build the neutral customer-auth backend

**Files:**
- Create: `gateway/packages/api/src/lib/customer-auth.ts`
- Create: `gateway/packages/api/src/lib/customer-auth.test.ts`
- Create: `gateway/packages/api/src/routes/customer-auth-routes.ts`
- Create: `gateway/packages/api/src/routes/customer-auth-routes.test.ts`
- Modify: `gateway/packages/api/src/index.ts`

- [ ] Write failing helper and route tests for:
  - register -> `Identity` + `Customer` + `Membership`
  - login by `Identity.email`
  - `/me` returning `customerId`, membership role, and claim status
  - password reset and email verification against the platform-owned tables
- [ ] Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/customer-auth.test.ts \
  src/routes/customer-auth-routes.test.ts
```

- [ ] Implement the neutral auth helper with a response shape like:

```ts
{
  customerId: customer.id,
  identityId: identity.id,
  claimStatus: identity.claimStatus,
  email: identity.email,
  token,
}
```

- [ ] Mount the new routes under `/api/auth/*`.
- [ ] Re-run the focused auth suite.

## Task 2: Relocate email verification and password-reset delivery

**Files:**
- Modify: `gateway/packages/api/src/lib/email.ts`
- Modify: `gateway/packages/api/src/lib/email.test.ts`
- Create: `gateway/packages/api/src/lib/customer-email.ts`
- Modify: `gateway/packages/api/src/routes/customer-auth-routes.ts`

- [ ] Add failing tests that prove the neutral auth routes send verification and reset emails without any Coke-specific copy or route names.
- [ ] Run: `pnpm --dir gateway/packages/api test -- src/lib/email.test.ts src/routes/customer-auth-routes.test.ts`
- [ ] Move the old Resend and one-click-verification logic into generic helpers so links target `/auth/verify-email` and `/auth/reset-password`.
- [ ] Keep the existing registration edge-case behavior: auth succeeds even if email delivery fails, but the failure is logged.
- [ ] Re-run the focused tests.

## Task 3: Move self-service personal-channel APIs to neutral routes

**Files:**
- Create: `gateway/packages/api/src/routes/customer-channel-routes.ts`
- Create: `gateway/packages/api/src/routes/customer-channel-routes.test.ts`
- Modify: `gateway/packages/api/src/routes/coke-wechat-routes.ts`
- Modify: `gateway/packages/api/src/routes/user-wechat-channel.ts`
- Modify: `gateway/packages/api/src/middleware/customer-auth.ts`

- [ ] Write failing route tests for:
  - GET channel status by authenticated `customer_id`
  - connect / disconnect / archive by authenticated `customer_id`
  - denial when `claim_status != active`
- [ ] Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/routes/customer-channel-routes.test.ts \
  src/routes/coke-wechat-routes.test.ts
```

- [ ] Implement neutral handlers under a stable path such as `/api/customer/channels/wechat-personal/*`.
- [ ] Convert `coke-wechat-routes.ts` into compatibility wrappers that call the neutral handlers and emit deprecation headers.
- [ ] Re-run the route tests.

## Task 4: Add wire-identifier compatibility and cutover controls

**Files:**
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `connector/clawscale_bridge/message_gateway.py`
- Modify: `connector/clawscale_bridge/gateway_identity_client.py`
- Modify: `agent/runner/identity.py`
- Create: `gateway/packages/api/src/scripts/audit-wire-identifier-compat.ts`

- [ ] Add failing bridge / agent tests proving both payload forms work during the compatibility window:

```json
{ "customer_id": "ck_123" }
{ "account_id": "ck_123" }
```

- [ ] Implement a shared rule:
  - accept either key on inbound
  - normalize to `customer_id` internally
  - emit `customer_id` on outbound ClawScale-originated payloads
- [ ] Add the audit CLI and run:

```bash
pnpm --dir gateway/packages/api tsx src/scripts/audit-wire-identifier-compat.ts
pytest tests/unit/ -k "identity or gateway"
```

- [ ] Document the maintenance-window behavior: registration and reset endpoints return a temporary paused response during the final retirement in plan 3.

## Task 5: Leave compatibility aliases in place and verify the whole backend

**Files:**
- Modify: `gateway/packages/api/src/routes/coke-auth-routes.ts`
- Modify: `gateway/packages/api/src/routes/coke-user-provision.ts`
- Modify: `gateway/packages/api/src/index.ts`

- [ ] Keep `/api/coke/register`, `/login`, `/verify-email`, `/forgot-password`, `/reset-password`, and `/wechat-channel/*` as wrappers until plan 4 updates the web frontend.
- [ ] Add response headers such as:

```ts
c.header('Deprecation', 'true');
c.header('Link', '</api/auth/login>; rel=\"successor-version\"');
```

- [ ] Run the package verification:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/customer-auth.test.ts \
  src/routes/customer-auth-routes.test.ts \
  src/routes/customer-channel-routes.test.ts \
  src/routes/coke-auth-routes.test.ts \
  src/routes/coke-wechat-routes.test.ts
pnpm --dir gateway/packages/api build
```

- [ ] Record the remaining alias routes that plan 4 must remove.
