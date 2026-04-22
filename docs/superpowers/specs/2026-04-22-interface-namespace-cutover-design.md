# Interface Namespace Cutover Design

## Goal

Remove the remaining Coke-branded compatibility routes and finish the namespace
cutover so URLs describe audience and resource instead of historical product
stages.

## Problem

The repository currently mixes four different naming schemes for the same
customer lifecycle:

- action-oriented auth URLs: `/auth/*`, `/api/auth/*`
- resource-oriented channel URLs: `/channels/wechat-personal`,
  `/api/customer/channels/wechat-personal/*`
- legacy Coke product-shell URLs: `/coke/payment`, `/api/coke/*`
- internal gateway routes that are separately namespaced under `/api/internal/*`

That creates two concrete problems:

1. the public surface no longer has a single rule for what a path segment means
2. docs and tests drift because multiple historical names still look valid

## Design Principles

- Public web URLs must express the screen or resource the customer is looking
  at.
- Public API URLs must express audience first, then resource.
- Internal gateway integration routes must stay under `/api/internal/*`.
- Legacy compatibility URLs are removed, not redirected.
- Stripe/webhook/public-token routes use neutral integration naming instead of
  the Coke product shell.

## Target Contract

### Web

- Auth flow: `/auth/*`
- Personal channel lifecycle: `/channels/wechat-personal`
- Subscription management and checkout status: `/account/subscription`

### Public API

- Customer auth: `/api/auth/*`
- Customer channel lifecycle:
  `/api/customer/channels/wechat-personal[/(connect|disconnect|status)]`
- Customer subscription snapshot: `GET /api/customer/subscription`
- Customer checkout session creation: `POST /api/customer/subscription/checkout`
- Public token checkout handoff:
  `GET /api/public/subscription-checkout?token=...`
- Stripe callback: `POST /api/webhooks/stripe`

### Internal API

- Internal gateway-only routes remain under `/api/internal/*`
- This cutover does not rename existing internal channel/delivery routes

## Migration Safety

The user explicitly chose hard removal:

- delete the legacy `/coke/*` and `/api/coke/*` entrypoints
- do not keep redirects
- do not keep static explanation pages
- old entrypoints should return `404`

Safety comes from repository-wide caller cutover in the same change:

- update every in-repo web/API caller to the new paths
- remove old auth-token fallback behavior that exists only for compatibility
- update deploy smoke checks and Stripe smoke coverage to the new paths
- add structure and route-level tests that fail if `/api/coke/*` or
  `/coke/payment` is reintroduced

## Implementation Notes

### Auth and Session

- Customer auth becomes the only supported browser token flow.
- Web code should stop depending on separate `coke-user-*` token wrappers for
  public customer pages.
- API middleware and route handlers should stop accepting legacy Coke JWTs for
  customer-facing routes.

### Subscription

- The existing Stripe logic is retained, but moved behind neutral customer and
  public namespaces.
- Renewal URLs generated in access decisions must point to
  `/account/subscription`.
- Public token checkout URLs generated for WhatsApp or similar flows must point
  to `/api/public/subscription-checkout`.

### Documentation

- Add one durable canonical interface contract under `docs/design-docs/`.
- Update rollout and deployment docs so their examples match the new contract.
- Preserve historical plan/spec docs; only live routing docs need updating.

## Verification

- Targeted Vitest for customer auth, customer channel, and subscription routes
- Targeted Vitest for auth, channel, and subscription web pages/libs
- Stripe smoke script tests updated to the new route contract
- Deploy script tests updated to probe `/auth/login` and
  `/account/subscription`
- Repository structure check plus `zsh scripts/check`
