# Task: Remove Retired Dashboard Routes

- Status: Verified
- Owner: Codex
- Date: 2026-04-20

## Goal

Remove the retired `/dashboard/*` front-end route tree instead of keeping legacy redirect stubs.

## Scope

- In scope:
- delete the obsolete `gateway/packages/web/app/dashboard/` route files
- remove tests that only assert the legacy dashboard stubs still exist
- add a regression test that proves the retired dashboard route tree is gone
- Out of scope:
- replacing old `/dashboard/*` URLs with new runtime redirects
- changing live `/admin/*`, `/auth/*`, or `/channels/*` pages

## Touched Surfaces

- gateway-web

## Acceptance Criteria

- `gateway/packages/web/app/dashboard/` no longer ships retired route pages
- tests no longer assert that legacy dashboard redirect stubs exist
- web tests pass with a regression check proving the dashboard tree is removed

## Verification

- Command: `pnpm --dir gateway/packages/web test -- app/dashboard-removal.test.ts`
- Expected evidence: regression test passes and confirms the retired dashboard tree is absent
- Command: `pnpm --dir gateway/packages/web test`
- Expected evidence: web test suite stays green after deleting the retired routes

## Notes

This intentionally removes backwards-compatible `/dashboard/*` entrypoints. Old URLs will 404 instead of redirecting to `/admin/*`.

Verified on 2026-04-20 with:

- `pnpm --dir gateway/packages/web test -- app/dashboard-removal.test.ts`
- `pnpm --dir gateway/packages/web test`
