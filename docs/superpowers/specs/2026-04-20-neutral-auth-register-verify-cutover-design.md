# Neutral Auth Register/Verify Cutover Design

## Summary

The customer auth UI has already moved to neutral routes such as `/auth/register`,
`/auth/login`, and `/channels/wechat-personal`, but parts of the implementation
still call paused Coke compatibility endpoints. This cutover repairs the broken
registration and verification path by making those pages call the active
`/api/auth/*` lifecycle directly.

## Decision

We will:

- move `/auth/register` from `/api/coke/register` to `/api/auth/register`
- move `/auth/verify-email` from `/api/coke/verify-email` to `/api/auth/verify-email`
- move resend-verification calls in both `/auth/verify-email` and `/auth/login`
  from `/api/coke/verify-email/resend` to `/api/auth/resend-verification`
- keep `/api/coke/login` in place for now because it still returns the
  compatibility Coke user payload used by the current bind/subscription gating
  flow

We will not revive paused compatibility endpoints. They are no longer the
authoritative contract for new route ownership.

## Rationale

This is the smallest change that restores the end-to-end onboarding path without
expanding the legacy surface. It aligns the frontend with the active gateway API
contract and preserves the still-needed compatibility layer only where the UI
continues to depend on Coke-specific user profile semantics.

## Affected Components

- `gateway/packages/web/app/(customer)/auth/register/page.tsx`
- `gateway/packages/web/app/(customer)/auth/verify-email/page.tsx`
- `gateway/packages/web/app/(customer)/auth/login/page.tsx`
- corresponding auth page tests under `gateway/packages/web/app/(customer)/auth/`

## Verification Strategy

Use focused Vitest coverage on the affected pages to prove the endpoint cutover:

- register submits to `/api/auth/register`
- verify-email submits to `/api/auth/verify-email`
- resend verification submits to `/api/auth/resend-verification`
- redirect and auth-storage behavior remains unchanged
