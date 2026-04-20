# Task: Neutral Auth Register/Verify Cutover

- Status: Verified
- Owner: Codex
- Date: 2026-04-20

## Goal

Repair the customer-facing registration and email verification flow by cutting the web frontend over to the neutral `/api/auth/*` endpoints.

## Scope

- In scope:
  - `gateway/packages/web` register page, verify-email page, and login resend-verification behavior
  - focused tests covering the endpoint cutover and recovery flow
  - keeping `/api/coke/login` temporarily as a compatibility path
- Out of scope:
  - restoring paused `/api/coke/register` or `/api/coke/verify-email*` endpoints
  - full login migration off `/api/coke/login`
  - forgot-password and reset-password flow changes

## Touched Surfaces

- gateway-api
- gateway-web

## Acceptance Criteria

- `/auth/register` uses the neutral register API and no longer depends on paused Coke compatibility endpoints.
- `/auth/verify-email` uses the neutral verify-email and resend-verification APIs.
- login recovery resend uses the neutral resend-verification API.
- web tests fail before the cutover and pass after it.

## Verification

- Command: `pnpm --dir gateway/packages/web test -- app/'(customer)'/auth/register/page.test.tsx app/'(customer)'/auth/login/page.test.tsx app/'(customer)'/auth/verify-email/page.test.tsx`
- Expected evidence: all targeted auth page tests pass with endpoint assertions updated to `/api/auth/*`.
- Command: `pnpm --dir gateway/packages/api test -- src/lib/customer-auth.test.ts src/routes/customer-auth-routes.test.ts src/routes/coke-auth-routes.test.ts`
- Expected evidence: customer auth state transitions and `/api/coke/me` customer-token compatibility tests pass.

## Notes

- Compatibility policy for this task: keep legacy page redirects and `/api/coke/login`, but do not revive paused legacy register/verify APIs.
