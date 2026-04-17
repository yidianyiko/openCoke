# ClawScale Customer Frontend Relocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move generic customer pages out of `(coke-user)/coke/*` into neutral `(customer)/auth/*` and `(customer)/channels/*` routes while leaving Coke-specific business pages under `/coke/*`.

**Architecture:** Split the current customer web surface into two layers: a generic ClawScale customer shell for auth and channel management, and a Coke agent partition for Coke-only payment / settings / business views. Keep compatibility redirects from the old `/coke/*` generic pages until all internal links, helpers, and tests point to the new route tree.

**Tech Stack:** Next.js App Router, React, TypeScript, Vitest, pnpm

---

## Scope Check

This plan is **follow-up plan 4** from `2026-04-15-clawscale-platformization-design.md`.

This plan covers:

- new `(customer)` route group structure
- relocation of customer auth pages
- relocation of customer channel-management pages
- web helper / API client renames and redirect compatibility

This plan does **not** cover:

- backend auth ownership logic itself
- admin backend pages
- shared-channel claim flow beyond reserving `/auth/claim`

## File Structure

### New Web files

- `gateway/packages/web/app/(customer)/auth/layout.tsx`
  Shared customer-auth shell.
- `gateway/packages/web/app/(customer)/auth/login/page.tsx`
- `gateway/packages/web/app/(customer)/auth/register/page.tsx`
- `gateway/packages/web/app/(customer)/auth/forgot-password/page.tsx`
- `gateway/packages/web/app/(customer)/auth/reset-password/page.tsx`
- `gateway/packages/web/app/(customer)/auth/verify-email/page.tsx`
- `gateway/packages/web/app/(customer)/auth/claim/page.tsx`
  Reserved route; Phase 1 can render a disabled placeholder.
- `gateway/packages/web/app/(customer)/channels/page.tsx`
  Generic customer channel list.
- `gateway/packages/web/app/(customer)/channels/wechat-personal/page.tsx`
  Generic personal WeChat connect / disconnect / archive page.
- `gateway/packages/web/lib/customer-api.ts`
- `gateway/packages/web/lib/customer-auth.ts`
- `gateway/packages/web/lib/customer-wechat-channel.ts`

### Modified Web files

- `gateway/packages/web/app/(coke-user)/coke/*`
  Replace generic pages with redirects to their neutral successors.
- `gateway/packages/web/lib/coke-user-api.ts`
- `gateway/packages/web/lib/coke-user-auth.ts`
- `gateway/packages/web/lib/coke-user-wechat-channel.ts`
  Convert into wrappers or remove after all imports move.
- `gateway/packages/web/lib/i18n.ts`
  Rename generic customer-facing copy out of Coke-specific buckets.

## Task 1: Create the neutral customer route group and shared helpers

**Files:**
- Create: `gateway/packages/web/app/(customer)/auth/layout.tsx`
- Create: `gateway/packages/web/lib/customer-api.ts`
- Create: `gateway/packages/web/lib/customer-auth.ts`
- Create: `gateway/packages/web/lib/customer-wechat-channel.ts`
- Modify: `gateway/packages/web/lib/coke-user-api.ts`
- Modify: `gateway/packages/web/lib/coke-user-auth.ts`
- Modify: `gateway/packages/web/lib/coke-user-wechat-channel.ts`

- [x] Add failing helper tests proving the new neutral libs call `/api/auth/*` and the neutral channel endpoints instead of `/api/coke/*`.
- [x] Run:

```bash
pnpm --dir gateway/packages/web test -- \
  lib/coke-user-api.test.ts \
  lib/coke-user-auth.test.ts \
  lib/coke-user-wechat-channel.test.ts
```

- [x] Introduce the neutral helper names and keep the old Coke-named libs as temporary wrappers.
- [x] Re-run the helper tests and add coverage for the new files.

## Task 2: Relocate auth pages into `(customer)/auth/*`

**Files:**
- Create: `gateway/packages/web/app/(customer)/auth/login/page.tsx`
- Create: `gateway/packages/web/app/(customer)/auth/register/page.tsx`
- Create: `gateway/packages/web/app/(customer)/auth/forgot-password/page.tsx`
- Create: `gateway/packages/web/app/(customer)/auth/reset-password/page.tsx`
- Create: `gateway/packages/web/app/(customer)/auth/verify-email/page.tsx`
- Create: `gateway/packages/web/app/(customer)/auth/claim/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/register/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/forgot-password/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/reset-password/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/verify-email/page.tsx`

- [x] Write failing page tests that assert:
  - login renders at `/auth/login`
  - register renders at `/auth/register`
  - verify-email success redirects no longer point at `/coke/*`
  - `/coke/login` and `/coke/register` issue redirects
- [x] Run:

```bash
pnpm --dir gateway/packages/web test -- \
  "app/(coke-user)/coke/login/page.test.tsx" \
  "app/(coke-user)/coke/register/page.test.tsx" \
  "app/(coke-user)/coke/verify-email/page.test.tsx"
```

- [x] Move the page implementations into `(customer)/auth/*`, keeping the old files as thin `redirect()` wrappers.
- [x] Reserve `/auth/claim` with a stable placeholder page so plan 7 has a landing point.
- [x] Re-run the focused auth page suite.

## Task 3: Relocate channel management into `(customer)/channels/*`

**Files:**
- Create: `gateway/packages/web/app/(customer)/channels/page.tsx`
- Create: `gateway/packages/web/app/(customer)/channels/wechat-personal/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.test.tsx`

- [x] Add failing tests that assert the personal-channel page now lives at `/channels/wechat-personal`.
- [x] Run:

```bash
pnpm --dir gateway/packages/web test -- \
  "app/(coke-user)/coke/bind-wechat/page.test.tsx"
```

- [x] Move the implementation into the neutral channels route group.
- [x] Keep `/coke/bind-wechat` as a redirect until all entry points move.
- [x] Add a lightweight `/channels` page that links to the supported channel surfaces for Phase 1.
- [x] Re-run the channel page tests.

## Task 4: Update copy, navigation, and redirect compatibility

**Files:**
- Modify: `gateway/packages/web/lib/i18n.ts`
- Modify: `gateway/packages/web/app/(coke-user)/coke/layout.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/layout.tsx`

- [x] Move generic labels from Coke-specific copy buckets to neutral customer copy buckets.
- [x] Update all internal links and buttons so they point at:
  - `/auth/login`
  - `/auth/register`
  - `/auth/forgot-password`
  - `/auth/reset-password`
  - `/auth/verify-email`
  - `/channels/wechat-personal`
- [x] Keep explicit redirects from the old routes until no internal caller remains.
- [x] Run:

```bash
pnpm --dir gateway/packages/web test
```

- [x] Record any remaining `/coke/*` generic links that plan 6 must delete outright.
  - `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`
  - `gateway/packages/web/app/(coke-user)/coke/register/page.tsx`
  - `gateway/packages/web/app/(coke-user)/coke/forgot-password/page.tsx`
  - `gateway/packages/web/app/(coke-user)/coke/reset-password/page.tsx`
  - `gateway/packages/web/app/(coke-user)/coke/verify-email/page.tsx`
  - `gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.tsx`
  - Follow-up note: the redirect-wrapper inventory is unchanged after the Task 4 spec-fix; generic auth/channel copy now lives only in `customerLayout`/`customerPages`, while Coke business copy stays in `cokeUserLayout`/`cokeUserPages`.
  - Final review note: `/channels/*` now uses the shared customer shell again via a dedicated channels layout, and the `/channels` index plus `/auth/claim` placeholder copy are sourced from the locale catalog.
  - Compatibility follow-up note: `/api/customer/channels/wechat-personal` now accepts both neutral customer sessions and legacy Coke tokens during the migration window, re-applies the old Coke access gates server-side for create/connect, and `/channels/wechat-personal` sign-out clears both auth stores.
