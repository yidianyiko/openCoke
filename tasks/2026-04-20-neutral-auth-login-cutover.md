# Task: Neutral Auth Login Cutover

- Status: Verified
- Owner: Codex
- Date: 2026-04-20

## Goal

Remove the active `/api/coke/login` dependency by moving repository callers to
neutral customer auth login and keeping Coke compatibility only for profile and
subscription surfaces.

## Scope

- In scope:
  - `gateway/packages/web` login page submission flow
  - `gateway/packages/api` Stripe smoke login helper
  - pausing `/api/coke/login` as a deprecated compatibility endpoint
  - focused tests covering the caller cutover and paused login behavior
- Out of scope:
  - removing page-level `/coke/login` redirects
  - removing `/api/coke/me`, `/api/coke/subscription`, or `/api/coke/checkout`
  - forgot-password and reset-password changes

## Touched Surfaces

- gateway-api
- gateway-web

## Acceptance Criteria

- `/auth/login` authenticates through `/api/auth/login`, then hydrates Coke
  compatibility state through `/api/coke/me`.
- the Stripe smoke script logs in through `/api/auth/login` and continues using
  the returned customer token against existing Coke compatibility routes.
- `/api/coke/login` returns the paused compatibility response with deprecation
  headers instead of performing authentication.
- focused web and API tests fail before the cutover and pass after it.

## Verification

- Command: `pnpm --dir gateway/packages/web test -- app/'(customer)'/auth/login/page.test.tsx`
- Expected evidence: login page tests pass with `/api/auth/login` plus
  `/api/coke/me` hydration assertions.
- Command: `pnpm --dir gateway/packages/api test -- src/routes/coke-auth-routes.test.ts src/scripts/stripe-e2e-smoke.test.ts`
- Expected evidence: paused `/api/coke/login` behavior and neutral smoke login
  caller expectations pass.

## Notes

- Compatibility policy for this task: preserve page redirects and Coke profile
  compatibility reads, but stop treating `/api/coke/login` as a live path.
