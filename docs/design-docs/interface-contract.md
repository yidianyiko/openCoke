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
`docs/design-docs/coke-working-contract.md` for repository planning surfaces
and active feature specs for feature-specific route ownership decisions.

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
- `/account/my-agent`

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
- `/api/customer/agent-instance` — Platform edge, Agent Runtime semantics
- `/api/customer/google-calendar-import` — Calendar Import System
- `/api/customer/calendar-import-handoffs` — Calendar Import System
- `/api/customer/subscription` — Platform System
- `/api/customer/subscription/checkout` — Platform System
- `/api/public/subscription-checkout` — Platform System
- `/api/webhooks/stripe` — Platform System

### Internal API

- `/api/outbound` — Channel System bridge-to-gateway outbound dispatch
- `/api/internal/coke-bindings` — Platform System
- `/api/internal/coke-delivery` — Channel System
- `/api/internal/coke-users/provision` — Platform System
- `/bridge/internal/agent-instances` — Bridge internal edge, Agent Runtime semantics

## Active Payload Compatibility

These are current contracts, not open-ended compatibility permission. New
callers should use the canonical field names.

- `/bridge/inbound` accepts both gateway-normalized top-level snake_case fields
  and ClawScale live-message `metadata` camelCase fields. The bridge normalizes
  `coke_account_id`, `customer_id`, `customerId`, `metadata.cokeAccountId`,
  `metadata.customerId`, and `metadata.customer_id` to the internal
  `coke_account_id` field before enqueueing.
- `/api/outbound` requires `customer_id` at the HTTP edge. `account_id` is not
  an accepted request alias. Its idempotency comparison may still read
  historical text-only stored payloads that predate `mediaUrls` and
  `audioAsVoice`; this is stored-data compatibility only.
- `/api/internal/coke-bindings` requires `customer_id` for the account to bind.
  `account_id` and `coke_account_id` are retired HTTP aliases for this route.
- `/api/internal/coke-users/provision` accepts `customer_id` and
  `coke_account_id`. The latter remains active for synthetic smoke-account
  provisioning until that seeding path is migrated. `account_id` is retired.
- `/api/internal/scheduling/tools/create_shared_reminder` accepts canonical
  invitee fields: `invitee_account_id`, `invitee_name`, or `friendship_id`.
  `friend_id` is retired at the gateway route boundary.
- `/api/internal/scheduling/focus/resolve` and
  `/api/internal/scheduling/focus/bind` are Scheduling Domain Contract
  endpoints for Agent Runtime focus. Agent callers pass `customer_id` plus a
  conversation key to resolve focus, then pass `focus_token` and opaque
  `handle` to bind a selected candidate. Inbound `product_notification`
  candidate payloads are not the source of actionable request IDs.
- Bulk shared-reminder tools are active on
  `/api/internal/scheduling/tools/{accept_pending_shared_reminders_from,reject_pending_shared_reminders_from,cancel_pending_shared_reminders_for}`
  and return per-candidate outcomes instead of all-or-nothing batch state.

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
- remove the retired route handler, alias, and compatibility shim instead of
  preserving a dedicated retired-path response

## Documentation Rule

If a new public or internal namespace is introduced, update this document in
the same change.
