# Neutral Auth Login Cutover Design

## Summary

The register and verify flow already moved to neutral customer auth, but login
still authenticates through `/api/coke/login`. This keeps a deprecated
 compatibility endpoint on the critical path even though the web app and smoke
 tooling can now authenticate through `/api/auth/login` and use the returned
 customer token against Coke compatibility reads.

## Decision

We will:

- move `/auth/login` from `/api/coke/login` to `/api/auth/login`
- hydrate the Coke compatibility session after neutral login by calling
  `/api/coke/me` with the customer token
- move the Stripe smoke login helper from `/api/coke/login` to `/api/auth/login`
- change `/api/coke/login` to the same paused compatibility response used by
  the other deprecated Coke auth endpoints

We will not change page redirects or the remaining Coke compatibility routes in
this task.

## Rationale

This keeps neutral customer auth as the only active login contract while
preserving the minimal Coke compatibility reads still needed by subscription and
channel gating. It reduces legacy surface area without coupling `/api/auth/login`
back to Coke-specific payload semantics.

## Affected Components

- `gateway/packages/web/app/(customer)/auth/login/page.tsx`
- `gateway/packages/web/app/(customer)/auth/login/page.test.tsx`
- `gateway/packages/api/src/routes/coke-auth-routes.ts`
- `gateway/packages/api/src/routes/coke-auth-routes.test.ts`
- `gateway/packages/api/src/scripts/stripe-e2e-smoke.ts`
- `gateway/packages/api/src/scripts/stripe-e2e-smoke.test.ts`

## Verification Strategy

Use focused Vitest coverage to prove the caller cutover and endpoint shutdown:

- login page submits to `/api/auth/login` and hydrates profile from `/api/coke/me`
- unverified and renewal-required routing still depends on the hydrated Coke
  profile
- `/api/coke/login` returns `temporarily_paused` with deprecation headers
- Stripe smoke helpers retain their existing behavior while authenticating
  through neutral login
