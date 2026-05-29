# Roadmap

Last updated: 2026-05-29

This document is the primary product and platform direction view for the Coke
clean rebuild. The requirements source is
`docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`;
the target architecture source is
`docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md`.

## Product Direction

Coke is a personal accountability companionship product for individual users. It
keeps the following current product journeys:

- account registration, login, access status, subscription recovery, and account
  claim
- first activation through web-first channel connection or shared WhatsApp
  messaging-first entry
- one reachable personal channel
- daily conversation through The Turn
- personal reminders, recurring reminders, proactive follow-ups, nightly
  summaries, undelivered reminders, and reminder calendar management
- friendship through direct active links/codes
- shared reminders with active friends
- informational product notifications
- one-time Google Calendar import
- assistant settings, global timezone, memory switch, and limited local
  lifecycle actions

The product is not trying to preserve legacy implementation shape. Historical
data migration, old protocols, old route aliases, pending approval workflows,
photo/social features, media generation, and organization/SaaS account graphs are
not current roadmap goals.

## Clean Rebuild Track

The active implementation direction is destructive clean rebuild:

- one Python backend
- one thin Next.js client
- Postgres for durable product and Agno state
- Redis for coordination only
- Mongo removed
- ClawScale demoted to the `wechat_personal` provider adapter
- TypeScript Gateway API superseded by the Python API
- standalone ClawScale bridge superseded by provider adapters in the Python
  ingress/egress tier
- The Turn as the runtime spine
- six product modules: IdentityAccess, ChannelReachability,
  ConversationRuntime, Reminder, SocialScheduling, CalendarImport

Implementation should proceed from the canonical docs and specs rather than from
legacy Gateway/Bridge/Mongo assumptions.

## Platform Priorities

1. Keep canonical documentation synchronized with the clean target architecture.
2. Build the Python domain/API/worker contracts around the six product modules.
3. Repoint and de-brand the Next.js thin client to the Python API.
4. Replace provider-specific runtime ownership with canonical provider adapters.
5. Move durable runtime state to Postgres and coordination to Redis.
6. Preserve strict output and product contracts: no compatibility shims, no
   heuristic parser fallback, and no user-visible prose outside The Turn.

## Route Direction

The discoverable route surface remains the clean-rebuild web, API, provider
webhook, and internal runtime namespace. The authoritative route contract lives
in `docs/design-docs/interface-contract.md`; the product-facing route index
lives in `docs/product-specs/FEATURE_TREE.md`. Roadmap work should update those
two documents instead of duplicating route lists here.

## Verification Direction

Clean-rebuild documentation changes use `clean-rebuild-docs`. Backend work uses
`clean-rebuild-backend`. Web work uses `clean-rebuild-web`. The verification
matrix and surfaces file carry the current command mapping.

## Canonical References

- `docs/ARCHITECTURE.md`: clean-rebuild runtime architecture.
- `docs/product-specs/FEATURE_TREE.md`: route and product surface discovery.
- `docs/design-docs/interface-contract.md`: route namespace contract.
- `docs/clawscale_bridge.md`: ClawScale as `wechat_personal` adapter only.
- `docs/deploy.md`: future clean-rebuild service topology.
- `docs/fitness/coke-verification-matrix.md`: verification routing.
