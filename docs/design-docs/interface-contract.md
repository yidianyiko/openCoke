# Interface Contract

This document is the canonical route namespace contract for the Coke clean
rebuild. Product details are indexed in
`docs/product-specs/FEATURE_TREE.md`; runtime ownership is defined in
`docs/ARCHITECTURE.md`.

## Ownership Rule

Routes are adapters over Python domain modules. Product behavior is owned by
IdentityAccess, ChannelReachability, ConversationRuntime, Reminder,
SocialScheduling, and CalendarImport. Provider-specific code normalizes into or
out of Coke's canonical contracts and does not own product state.

Legacy implementation directories are not future ownership contracts. Do not
assign new product behavior to the TypeScript Gateway API or the standalone
ClawScale bridge.

## Public Web

- `/`
- `/faqs`
- `/demos`
- `/privacy`
- `/terms`
- `/u/:code`

## Customer Web

- `/account/*`
- `/channels`
- `/reminders`
- `/friends`
- `/shared-reminders`
- `/settings`
- `/calendar-import`
- `/subscription`
- `/claim`

## Python Public API

- `/api/auth/*`
- `/api/account/*`
- `/api/channels/*`
- `/api/reminders/*`
- `/api/friends/*`
- `/api/shared-reminders/*`
- `/api/settings/*`
- `/api/calendar-import/*`
- `/api/subscription/*`
- `/api/claim/*`

## Provider Webhooks

- `/webhooks/whatsapp/evolution`
- `/webhooks/wechat/personal`
- `/webhooks/wechat/ecloud`
- `/webhooks/linq`

## Internal Runtime

- `/internal/outbound/delivery-callback`
- `/internal/reply-wait/:causal_inbound_event_id`

## Route Semantics

- Public web routes provide explanation, FAQ, demo, policy, terms, and public
  friend-link entry.
- Customer web routes are thin client pages over the Python API.
- Python public API routes enforce auth/access gates, validate request shape,
  and call domain services.
- Provider webhooks normalize provider payloads into canonical inbound events.
- Internal runtime routes are private operational edges for delivery callbacks
  and synchronous reply waiting.

## Deleted Or Out-Of-Scope Route Families

- Legacy public login aliases and Coke-specific old auth aliases.
- Standalone bridge HTTP routes as product architecture.
- Gateway-owned `/api/internal/*` product callbacks.
- Provider-specific product routes that bypass canonical domain modules.
- Friend-request and shared-reminder approval routes.
- Mongo-backed transcript or reminder route surfaces.

Any future route family must be added here and to
`docs/product-specs/FEATURE_TREE.md` in the same change.
