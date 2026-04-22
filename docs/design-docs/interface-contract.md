# Interface Contract

This document is the canonical contract for public and internal interfaces in
`coke`.

## Core Rule

A path must answer two questions in order:

1. who is this interface for?
2. what resource or workflow surface does it expose?

Historical product names are not valid namespace categories for new interfaces.

## Namespace Rules

### Web

- `/auth/*`
  - customer sign-in, registration, verification, password reset, and claim
- `/channels/*`
  - customer-managed communication channels
- `/account/*`
  - customer account state that is neither authentication nor a channel

### Public API

- `/api/auth/*`
  - customer authentication and session hydration
- `/api/customer/*`
  - customer-owned resources and customer-triggered business actions
- `/api/public/*`
  - unauthenticated tokenized or externally-linked handoff endpoints
- `/api/webhooks/*`
  - third-party callback endpoints
- `/api/admin/*`
  - authenticated admin/operator interfaces

### Internal API

- `/api/internal/*`
  - gateway-to-bridge or gateway-only operational endpoints
  - not for browser navigation or public customer callers

## Current Canonical Surface

### Web

- `/auth/login`
- `/auth/register`
- `/auth/forgot-password`
- `/auth/reset-password`
- `/auth/verify-email`
- `/auth/claim`
- `/channels/wechat-personal`
- `/account/subscription`

### Public API

- `/api/auth/register`
- `/api/auth/login`
- `/api/auth/verify-email`
- `/api/auth/resend-verification`
- `/api/auth/forgot-password`
- `/api/auth/reset-password`
- `/api/auth/me`
- `/api/auth/claim`
- `/api/customer/channels/wechat-personal`
- `/api/customer/channels/wechat-personal/connect`
- `/api/customer/channels/wechat-personal/disconnect`
- `/api/customer/channels/wechat-personal/status`
- `/api/customer/subscription`
- `/api/customer/subscription/checkout`
- `/api/public/subscription-checkout`
- `/api/webhooks/stripe`

### Internal API

- `/api/internal/user/wechat-channel`
- `/api/internal/coke-bindings`
- `/api/internal/coke-delivery`
- `/api/internal/coke-users/provision`

## Forbidden Public Patterns

Do not introduce new public interfaces under:

- `/coke/*`
- `/api/coke/*`
- `/user/*`

Those forms are either historical product-shell leftovers or ambiguous about
audience.

## Migration Rule

When an interface is migrated to this contract:

- update every in-repo caller in the same change
- update deploy/smoke checks in the same change
- update live docs in the same change
- add or update tests so the retired path fails closed

## Documentation Rule

If a new public or internal namespace is introduced, update this document in
the same change.
