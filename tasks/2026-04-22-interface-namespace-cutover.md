# Task: Interface Namespace Cutover

- Status: In Progress
- Owner: Codex
- Date: 2026-04-22

## Goal

Remove the remaining Coke-branded public routes and APIs, complete the customer
namespace migration, and add one canonical interface contract document for the
repository.

## Scope

- In scope:
  - removing public `/coke/*` and `/api/coke/*` entrypoints
  - moving the subscription flow to a neutral customer/account namespace
  - removing customer-facing Coke JWT compatibility fallbacks
  - adding a canonical interface contract under `docs/design-docs/`
  - updating deploy/live docs and smoke checks
- Out of scope:
  - renaming existing `/api/internal/*` operational routes
  - rewriting historical specs and plans outside live docs

## Touched Surfaces

- gateway-api
- gateway-web
- deploy
- docs
- repo-os

## Acceptance Criteria

- `/coke/payment` and `/api/coke/*` are no longer registered
- subscription UI is available at `/account/subscription`
- customer subscription APIs live under `/api/customer/*`
- public token checkout lives under `/api/public/subscription-checkout`
- Stripe webhook no longer lives under `/api/coke/*`
- the canonical route contract exists in `docs/design-docs/interface-contract.md`
- old public interfaces fail closed instead of redirecting

## Verification

- `pytest tests/unit/test_no_compat_routes.py -v`
- `pnpm --dir gateway/packages/api exec vitest run src/routes/customer-auth-routes.test.ts src/routes/customer-channel-routes.test.ts src/routes/customer-subscription-routes.test.ts src/scripts/stripe-e2e-smoke.test.ts`
- `pnpm --dir gateway/packages/web exec vitest run app/'(customer)'/auth/login/page.test.tsx app/'(customer)'/auth/register/page.test.tsx app/'(customer)'/auth/verify-email/page.test.tsx app/'(customer)'/channels/wechat-personal/page.test.tsx app/'(customer)'/account/subscription/page.test.tsx`
- `bash scripts/test-deploy-compose-to-gcp.sh`
- `pytest tests/unit/test_repo_os_structure.py -v`
- `zsh scripts/check`
