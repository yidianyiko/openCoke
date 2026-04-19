# ClawScale Dashboard Deprecation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the obsolete `/dashboard/*` surface after the `/admin/*` MVP is live, replacing the old UI with deterministic redirect stubs and deleting dead code.

**Architecture:** Treat deprecation as a cleanup pass, not a feature rewrite. Because `packages/web` ships with `output: 'export'`, the implementation must keep static `/dashboard/*` entry points as thin `LegacyRedirectPage` wrappers instead of relying on `next.config` custom redirects. Delete the old page bodies, layout shell, copy modules, and route-group leftovers so no obsolete dashboard runtime code survives in the repository.

**Tech Stack:** Next.js, React, TypeScript, Vitest, pnpm, ripgrep

---

## Scope Check

This plan is **follow-up plan 6** from `2026-04-15-clawscale-platformization-design.md`.

This plan covers:

- redirecting `/dashboard/*` through static-export-safe legacy stubs
- deleting the old `app/dashboard/*` page bodies and `app/(dashboard)/*` leftovers
- deleting obsolete dashboard-only copy / helper modules

This plan does **not** cover:

- building the admin MVP itself
- shared-channel admin features

## File Structure

### Modified files

- `gateway/packages/web/next.config.ts`
  Keep the static-export baseline; do not rely on unsupported custom redirect config.
- `gateway/packages/web/app/dashboard/*`
  Replace the old page bodies with thin legacy redirect stubs.
- `gateway/packages/web/app/(dashboard)/*`
  Delete the obsolete route-group leftovers after successor pages exist under `(admin)`.
- `gateway/packages/web/lib/dashboard-copy.ts`
- `gateway/packages/web/lib/dashboard-schema-copy.ts`
  Delete once no page imports remain.

## Task 1: Lock the redirect map

**Files:**
- Modify: `gateway/packages/web/app/dashboard/page.test.tsx`
- Modify: `gateway/packages/web/app/dashboard/layout.test.tsx`
- Modify: `gateway/packages/web/app/dashboard/retired-pages.test.tsx`

- [x] Write failing tests or redirect assertions for the full mapping:
  - `/dashboard/login` -> `/admin/login`
  - `/dashboard/register` -> `/admin/login`
  - `/dashboard` -> `/admin/customers`
  - `/dashboard/onboard` -> `/admin/channels`
  - `/dashboard/channels` -> `/admin/channels`
  - `/dashboard/conversations` -> `/admin/customers`
  - `/dashboard/ai-backends` -> `/admin/agents`
  - `/dashboard/workflows` -> `/admin/customers`
  - `/dashboard/end-users` -> `/admin/customers`
  - `/dashboard/users` -> `/admin/admins`
  - `/dashboard/settings` -> `/admin/agents`
- [x] Run: `pnpm --dir gateway/packages/web test -- app/dashboard/page.test.tsx app/dashboard/layout.test.tsx app/dashboard/retired-pages.test.tsx`
- [x] Implement the redirects as static-export-safe `LegacyRedirectPage` route stubs instead of `next.config` custom redirects.
- [x] Re-run the focused tests.

## Task 2: Replace the old dashboard trees with redirect stubs

**Files:**
- Modify: `gateway/packages/web/app/dashboard/*`
- Delete: `gateway/packages/web/app/dashboard/layout.tsx`
- Delete: `gateway/packages/web/app/(dashboard)/*`

- [x] Replace every old dashboard page body with a thin redirect stub once the redirect map is covered.
- [x] Delete unused tests and helpers that were specific to removed dashboard content.
- [x] Run:

```bash
rg -n "/dashboard|dashboard-copy|dashboard-schema-copy" gateway/packages/web
```

- [x] If any runtime import remains, fix it before moving on.

## Task 3: Delete obsolete dashboard copy modules and verify

**Files:**
- Delete: `gateway/packages/web/lib/dashboard-copy.ts`
- Delete: `gateway/packages/web/lib/dashboard-schema-copy.ts`

- [x] Remove the old dashboard copy modules after the last import is gone.
- [x] Run:

```bash
pnpm --dir gateway/packages/web test
pnpm --dir gateway/packages/web build
rg -n "/dashboard|dashboard-copy|dashboard-schema-copy" gateway/packages/web
```

- [x] The final ripgrep output should be empty except for this plan file and the platformization spec.
