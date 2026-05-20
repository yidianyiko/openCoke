# Interface Contract

This document is the canonical contract for public and internal interfaces in
`coke`.

## Core Rule

A path must answer two questions in order:

1. who is this interface for?
2. what resource or workflow surface does it expose?

Historical product names are not valid namespace categories for new interfaces.

## Ownership Axis

Interface namespaces describe audience and transport shape. Ownership systems
describe who owns the behavior behind that interface. Use
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`
when deciding whether a route is Platform, Channel, Reminder, Calendar Import,
Bridge, Agent Runtime, or another product system.

A route under `gateway/packages/api` is not automatically Platform-owned. For
example, `/api/customer/reminders` is customer-facing but Reminder-owned, while
`/api/customer/channels/wechat-personal` is Platform-shaped at the HTTP edge
and Channel-owned for provider semantics.

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

- `/api/auth/register` — Platform System
- `/api/auth/login` — Platform System
- `/api/auth/verify-email` — Platform System
- `/api/auth/resend-verification` — Platform System
- `/api/auth/forgot-password` — Platform System
- `/api/auth/reset-password` — Platform System
- `/api/auth/me` — Platform System
- `/api/auth/claim` — Platform System
- `/api/customer/channels/wechat-personal` — Platform edge, Channel semantics
- `/api/customer/channels/wechat-personal/connect` — Platform edge, Channel semantics
- `/api/customer/channels/wechat-personal/disconnect` — Platform edge, Channel semantics
- `/api/customer/channels/wechat-personal/status` — Platform edge, Channel semantics
- `/api/customer/reminders` — Reminder System
- `/api/customer/google-calendar-import` — Calendar Import System
- `/api/customer/calendar-import-handoffs` — Calendar Import System
- `/api/customer/subscription` — Platform System
- `/api/customer/subscription/checkout` — Platform System
- `/api/public/subscription-checkout` — Platform System
- `/api/webhooks/stripe` — Platform System

### Internal API

- `/api/internal/coke-bindings` — Platform System
- `/api/internal/coke-delivery` — Channel System
- `/api/internal/coke-users/provision` — Platform System

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
