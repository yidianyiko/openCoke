# ClawScale Shared Channel and Inbound Auto-Provisioning Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn on Phase 1.5 shared channels, inbound auto-provisioning, parked first-contact handling, outbound shared-channel delivery, and the `/auth/claim` flow.

**Architecture:** Reuse the dormant schema from plan 1 (`Channel.ownership_kind`, `Channel.customer_id`, `Channel.agent_id`, `ExternalIdentity`, `Identity.claim_status`) and add the missing runtime pieces around it: a provider-normalization layer, a single-transaction auto-provision path, `ParkedInbound` retry / drain behavior, shared outbound routing, and a customer claim flow that upgrades `unclaimed` / `pending` identities to `active` without creating a second customer.

**Tech Stack:** TypeScript, Hono, Prisma, PostgreSQL, Vitest, pnpm, Next.js, React, Python 3.12, pytest

---

## Scope Check

This plan is **follow-up plan 7** from `2026-04-15-clawscale-platformization-design.md`.

This plan covers:

- shared-channel provisioning on first inbound
- `ParkedInbound` queue + reconciler
- outbound shared-channel reply routing
- `/auth/claim` token lifecycle
- admin shared-channel management UI
- admin customer-list extensions for claim status and parked-inbound counts

This plan does **not** cover:

- merging two existing customers that belong to the same physical person
- multi-agent routing beyond the shared channel's configured `agent_id`

## File Structure

### New Gateway API files

- `gateway/packages/api/src/lib/external-identity.ts`
  Shared normalization helpers for `(provider, identity_type, identity_value)`.
- `gateway/packages/api/src/lib/external-identity.test.ts`
- `gateway/packages/api/src/lib/shared-channel-provisioning.ts`
  The transaction + post-commit orchestration for first inbound on shared channels.
- `gateway/packages/api/src/lib/shared-channel-provisioning.test.ts`
- `gateway/packages/api/src/lib/parked-inbound.ts`
- `gateway/packages/api/src/lib/parked-inbound.test.ts`
- `gateway/packages/api/src/lib/claim-token.ts`
- `gateway/packages/api/src/lib/claim-token.test.ts`
- `gateway/packages/api/src/routes/customer-claim-routes.ts`
- `gateway/packages/api/src/routes/customer-claim-routes.test.ts`
- `gateway/packages/api/src/routes/admin-shared-channels.ts`
- `gateway/packages/api/src/routes/admin-shared-channels.test.ts`
- `gateway/packages/api/src/scripts/replay-parked-inbounds.ts`
- `gateway/packages/api/src/scripts/verify-shared-channel-runtime.ts`

### Modified Gateway API files

- `gateway/packages/api/prisma/schema.prisma`
  Add `ParkedInbound` plus any missing indexes needed for shared-channel routing.
- `gateway/packages/api/src/lib/route-message.ts`
  Branch shared-channel inbound through the new provisioning flow.
- `gateway/packages/api/src/routes/outbound.ts`
  Deliver replies through shared channels when the customer is shared-channel-owned.
- `gateway/packages/api/src/index.ts`
  Mount `/api/auth/claim` and `/api/admin/shared-channels`.
- provider adapters under `gateway/packages/api/src/adapters/*.ts`
  Supply normalized provider identity input.

### New Web files

- `gateway/packages/web/app/(customer)/auth/claim/page.tsx`
- `gateway/packages/web/app/(admin)/admin/shared-channels/page.tsx`
- `gateway/packages/web/app/(admin)/admin/shared-channels/[id]/page.tsx`
- `gateway/packages/web/lib/shared-channel-api.ts`

### Modified Web files

- `gateway/packages/web/app/(admin)/admin/customers/page.tsx`
  Add claim-status, contact-identifier, and parked-inbound columns.
- `gateway/packages/web/lib/admin-api.ts`
  Fetch shared-channel and claim-state data.

## Task 1: Add normalization, queue, and schema support

**Files:**
- Create: `gateway/packages/api/src/lib/external-identity.ts`
- Create: `gateway/packages/api/src/lib/external-identity.test.ts`
- Create: `gateway/packages/api/src/lib/parked-inbound.ts`
- Create: `gateway/packages/api/src/lib/parked-inbound.test.ts`
- Modify: `gateway/packages/api/prisma/schema.prisma`

- [x] Write failing tests for:
  - provider-specific identity normalization
  - uniqueness of `(provider, identity_type, identity_value)`
  - queueing and draining `ParkedInbound` rows in arrival order
- [x] Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/external-identity.test.ts \
  src/lib/parked-inbound.test.ts
```

- [x] Add the `ParkedInbound` model and the indexes required by the spec.
- [x] Implement the normalization helper so all adapters can call one interface:

```ts
normalizeExternalIdentity({
  provider: 'whatsapp',
  identityType: 'wa_id',
  rawValue: '+1 (415) 555-0100',
});
```

- [x] Re-run the focused tests.

## Task 2: Implement first-inbound auto-provisioning and concurrency control

**Files:**
- Create: `gateway/packages/api/src/lib/shared-channel-provisioning.ts`
- Create: `gateway/packages/api/src/lib/shared-channel-provisioning.test.ts`
- Modify: `gateway/packages/api/src/lib/route-message.ts`
- Modify: provider adapters under `gateway/packages/api/src/adapters/*.ts`

- [x] Write failing tests that cover:
  - lookup hit => route existing customer
  - lookup miss => create `Identity`, `Customer`, `Membership`, `AgentBinding`, `ExternalIdentity`
  - concurrent first inbound => one customer only
  - first inbound is parked when provisioning fails
- [x] Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/shared-channel-provisioning.test.ts \
  src/lib/route-message.test.ts
```

- [x] Implement the single-transaction create path and explicit upsert-then-read retry behavior required by the spec.
- [x] Update `route-message.ts` so shared channels enter this path before the old personal-channel logic.
- [x] Re-run the focused tests.

## Task 3: Add reconciler, drain, and outbound shared-channel delivery

**Files:**
- Create: `gateway/packages/api/src/scripts/replay-parked-inbounds.ts`
- Create: `gateway/packages/api/src/scripts/verify-shared-channel-runtime.ts`
- Modify: `gateway/packages/api/src/routes/outbound.ts`

- [x] Add tests proving:
  - parked inbounds drain only after `AgentBinding.provision_status = ready`
  - terminal provisioning errors remain visible
  - outbound replies for shared-channel customers use the shared `channel_id`
- [x] Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/routes/outbound.test.ts \
  src/lib/shared-channel-provisioning.test.ts
```

- [x] Implement the replay / verify scripts and wire shared outbound routing through the existing delivery pipeline.
- [x] Re-run the focused tests and record any delivery-path assumptions inherited from the 2026-04-08 spec.

## Task 4: Implement `/auth/claim` and claim-token lifecycle

**Files:**
- Create: `gateway/packages/api/src/lib/claim-token.ts`
- Create: `gateway/packages/api/src/lib/claim-token.test.ts`
- Create: `gateway/packages/api/src/routes/customer-claim-routes.ts`
- Create: `gateway/packages/api/src/routes/customer-claim-routes.test.ts`
- Create: `gateway/packages/web/app/(customer)/auth/claim/page.tsx`

- [x] Write failing tests for:
  - issuing a claim token sets `claim_status = pending`
  - completing a claim writes credentials and flips to `active`
  - invalid / expired tokens fail without creating a new customer
- [x] Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/claim-token.test.ts \
  src/routes/customer-claim-routes.test.ts
```

- [x] Implement the claim-token flow with the same single-use and expiry guarantees as password reset tokens.
- [x] Add the customer claim page under `/auth/claim`.
- [x] Re-run the focused claim suite.

## Task 5: Build admin shared-channel management and customer-list extensions

**Files:**
- Create: `gateway/packages/api/src/routes/admin-shared-channels.ts`
- Create: `gateway/packages/api/src/routes/admin-shared-channels.test.ts`
- Create: `gateway/packages/web/app/(admin)/admin/shared-channels/page.tsx`
- Create: `gateway/packages/web/app/(admin)/admin/shared-channels/[id]/page.tsx`
- Modify: `gateway/packages/web/app/(admin)/admin/customers/page.tsx`
- Modify: `gateway/packages/web/lib/admin-api.ts`

- [x] Add failing tests for:
  - admin can create / configure / retire shared channels
  - customer list shows contact identifier, claim status, and parked-inbound count
- [x] Run:

```bash
pnpm --dir gateway/packages/api test -- src/routes/admin-shared-channels.test.ts
pnpm --dir gateway/packages/web test -- "app/(admin)/admin/customers/page.test.tsx"
```

- [x] Implement the admin UI and APIs.
- [x] Re-run the focused admin tests.

## Task 6: End-to-end verification

**Files:**
- No new source files expected

- [x] Run the full Phase 1.5 verification:

```bash
pnpm --dir gateway/packages/api exec prisma migrate reset --force
pnpm --dir gateway/packages/api test
pnpm --dir gateway/packages/api tsx src/scripts/verify-shared-channel-runtime.ts
pnpm --dir gateway/packages/web test
pytest tests/unit/ -k "gateway or identity"
```

- [ ] Manually verify these flows on a disposable environment:
  - first inbound on shared channel creates an `unclaimed` customer
  - provisioning failure parks the inbound and later drains it
  - claim link upgrades the customer to `active`
  - outbound replies continue through the shared channel
- [x] Record any remaining Phase 1.5 exclusions explicitly in the closeout note.

### Closeout Note

- Automated verification completed on 2026-04-18 against a temporary local PostgreSQL instance at `postgresql://clawscale:clawscale@localhost:55432/clawscale` after adding the missing `20260418010000_parked_inbound_runtime_support` migration.
- Completed commands:
  - `DATABASE_URL=postgresql://clawscale:clawscale@localhost:55432/clawscale pnpm --dir gateway/packages/api exec prisma migrate reset --force`
  - `DATABASE_URL=postgresql://clawscale:clawscale@localhost:55432/clawscale pnpm --dir gateway/packages/api test`
  - `DATABASE_URL=postgresql://clawscale:clawscale@localhost:55432/clawscale pnpm --dir gateway/packages/api exec tsx src/scripts/verify-shared-channel-runtime.ts`
  - `pnpm --dir gateway/packages/web test`
  - `pytest tests/unit/ -k "gateway or identity"`
- Remaining Phase 1.5 exclusions in this session:
  - Manual disposable-environment verification is still pending because this worktree session does not have a disposable end-to-end stack wired to real shared-channel providers, live inbound traffic, email delivery, or outbound transport.
  - The unverified manual flows are:
    - first inbound on shared channel creates an `unclaimed` customer
    - provisioning failure parks the inbound and later drains it
    - claim link upgrades the customer to `active`
    - outbound replies continue through the shared channel
