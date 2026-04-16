# ClawScale Dashboard Deprecation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the obsolete `/dashboard/*` surface after the `/admin/*` MVP is live, replacing it with deterministic redirects and deleting dead code.

**Architecture:** Treat deprecation as a cleanup pass, not a feature rewrite. First add a complete route map from every surviving `/dashboard/*` entry point to either `/admin/*` or `/auth/*`, then delete the old pages, copy modules, and API assumptions so no obsolete dashboard code survives in the repository.

**Tech Stack:** Next.js, React, TypeScript, Vitest, pnpm, ripgrep

---

## Scope Check

This plan is **follow-up plan 6** from `2026-04-15-clawscale-platformization-design.md`.

This plan covers:

- redirecting `/dashboard/*`
- deleting `app/dashboard/*` and `app/(dashboard)/*`
- deleting obsolete dashboard-only copy / helper modules

This plan does **not** cover:

- building the admin MVP itself
- shared-channel admin features

## File Structure

### Modified files

- `gateway/packages/web/next.config.ts`
  Add permanent redirects from `/dashboard/*` to successor routes.
- `gateway/packages/web/app/dashboard/*`
  Delete after redirect coverage is in place.
- `gateway/packages/web/app/(dashboard)/*`
  Fold or delete after the successor pages exist under `(admin)`.
- `gateway/packages/web/lib/dashboard-copy.ts`
- `gateway/packages/web/lib/dashboard-schema-copy.ts`
  Delete once no page imports remain.

## Task 1: Lock the redirect map

**Files:**
- Modify: `gateway/packages/web/next.config.ts`
- Create or update: `gateway/packages/web/app/dashboard/page.test.tsx`
- Modify: `gateway/packages/web/app/dashboard/layout.test.tsx`

- [ ] Write failing tests or redirect assertions for the full mapping:
  - `/dashboard/login` -> `/admin/login`
  - `/dashboard/register` -> `/admin/login`
  - `/dashboard` -> `/admin/customers`
  - `/dashboard/channels` -> `/admin/channels`
  - `/dashboard/conversations` -> `/admin/customers`
  - `/dashboard/ai-backends` -> `/admin/agents`
  - `/dashboard/workflows` -> `/admin/customers`
  - `/dashboard/end-users` -> `/admin/customers`
  - `/dashboard/users` -> `/admin/admins`
  - `/dashboard/settings` -> `/admin/agents`
- [ ] Run: `pnpm --dir gateway/packages/web test -- app/dashboard/page.test.tsx app/dashboard/layout.test.tsx`
- [ ] Implement the redirects in `next.config.ts` or route-level `redirect()` calls.
- [ ] Re-run the focused tests.

## Task 2: Delete the old dashboard trees

**Files:**
- Delete: `gateway/packages/web/app/dashboard/*`
- Delete: `gateway/packages/web/app/(dashboard)/*`

- [ ] Remove every old dashboard page once the redirect map is covered.
- [ ] Delete unused tests that were specific to removed dashboard content.
- [ ] Run:

```bash
rg -n "/dashboard|dashboard-copy|dashboard-schema-copy" gateway/packages/web
```

- [ ] If any runtime import remains, fix it before moving on.

## Task 3: Delete obsolete dashboard copy modules and verify

**Files:**
- Delete: `gateway/packages/web/lib/dashboard-copy.ts`
- Delete: `gateway/packages/web/lib/dashboard-schema-copy.ts`

- [ ] Remove the old dashboard copy modules after the last import is gone.
- [ ] Run:

```bash
pnpm --dir gateway/packages/web test
pnpm --dir gateway/packages/web build
rg -n "/dashboard|dashboard-copy|dashboard-schema-copy" gateway/packages/web
```

- [ ] The final ripgrep output should be empty except for this plan file and the platformization spec.
