# Architecture Reference

This document describes the clean-rebuild target architecture for Coke. The
requirements source of truth is
`docs/superpowers/specs/2026-05-28-coke-requirements-user-journey-matrix-design.md`;
the technical target is
`docs/superpowers/specs/2026-05-28-coke-clean-rebuild-target-architecture-design.md`.
If this document and those specs disagree, treat the settled specs as the
authority and update this reference.

## Runtime Topology

Coke is a Python backend split into an ingress/egress tier and a worker tier,
with a thin Next.js client. Durable product state lives in Postgres. Redis is
coordination only: stream wake-up, locks, and reply pub/sub. MongoDB: Removed entirely.

Services in the target deployment:

- `coke-api`: Python ingress/egress HTTP tier. It receives provider webhooks,
  exposes the public and customer APIs, enforces identity/access gates, persists
  durable facts and outbox rows, and calls provider adapters for outbound sends.
- `coke-worker`: Python Redis Stream turn workers. It owns The Turn execution,
  context assembly, Interaction Agent invocation, output disposition, and domain
  tool calls.
- `coke-scheduler`: singleton Python reminder scheduler. It creates durable
  reminder-fire facts and outbox wake-ups.
- `coke-outbox-relay`: Postgres outbox to Redis Stream relay. Postgres remains
  the source of truth; Redis only wakes workers.
- `coke-web`: thin Next.js client over the Python API.
- `postgres`: product state, Agno session/history/memory/knowledge, pgvector,
  and the single transactional outbox.
- `redis`: wake-up stream, per-conversation locks, and reply pub/sub.

The TypeScript Gateway API is superseded by the Python API. The standalone
ClawScale bridge is superseded. ClawScale remains only as the `wechat_personal`
provider adapter behind Coke's canonical provider contract.

```text
providers
  -> coke-api (webhooks, account access gate, provider normalization)
  -> Postgres durable facts + outbox
  -> coke-outbox-relay
  -> Redis Stream wake-up
  -> coke-worker (The Turn, domain services, Interaction Agent)
  -> coke-api provider egress

coke-web -> coke-api -> Postgres-backed domains
```

## The Turn

All chat/channel-visible product prose flows through The Turn. Turn triggers are
InboundTurn, ReminderFireTurn, ProactiveFireTurn, NightlySummaryTurn,
NotificationTurn, AccessDeniedTurn, and UndeliveredResendTurn. The only normal
prose producer is the Interaction Agent. The runtime-owned waiting text is the
sole typed signal exception.

Turn execution has one spine:

1. Resolve the trigger and durable `trigger_id`.
2. Apply the pre-LLM gate: identity, account access, channel reachability, and
   claim/handoff validity.
3. Take a per-conversation Redis lock with an ownership token.
4. Assemble trusted context: TrustFraming, SemanticInterpreter, Focus,
   ReferenceResolver, Freshness, and Memory.
5. Invoke the Interaction Agent in interactive mode for inbound user turns or
   render mode for structured reminder, notification, access, and recovery facts.
6. Validate the first returned structured output. Malformed, empty, blocked, or
   timed-out-after-budget output is a failed turn, not an invented replacement
   reply.
7. Record exactly one turn disposition:
   `replied | no_reply | pending_async_reply | failed | superseded`.
8. Persist outbound messages with deterministic segment ids and provider
   idempotency keys.
9. Deliver through the current channel route and record delivery attempts.
10. Update output-class-specific lifecycle state from delivery callbacks.

Interactive mode exposes domain tools and may mutate product state through
domain services. Render mode receives already-trusted structured facts and has no
business mutation tools.

## Bounded Contexts

IdentityAccess owns account identity, access gate, activation, sessions,
credentials, channel identity, and auth artifacts. ChannelReachability owns the
single reachable channel, delivery route, and delivery attempts.
ConversationRuntime owns conversation order, messages, media references, turns,
and output disposition. Reminder owns reminders, fires, recurrence, scheduler,
and calendar read models. SocialScheduling owns friend links, friendships,
shared reminders, projections, and product notifications. CalendarImport owns
Google authorization, import runs, and per-occurrence import items.

Rules that apply to every bounded context:

- API routes and agent tools are adapters over domain services. They do not own
  business rules or write another context's tables directly.
- Cross-context async work uses the single Postgres outbox. Redis is a wake-up
  signal, not durable state.
- New tables must protect a current product invariant such as identity integrity,
  access gating, single-channel reachability, reminder firing, recurrence
  determinism, friendship uniqueness, shared-reminder projection consistency,
  outbound idempotency, or user-visible turn auditability.
- Legacy compatibility paths, alias routes, and fallback parsers are not kept
  unless a current canonical spec names them as active requirements.

## Storage Topology

Postgres stores all durable state:

- IdentityAccess: `account`, `agent_settings`, `user_profile`,
  `account_activation`, `account_access`, `credential`, `session`,
  `channel_identity`, and `auth_artifact`.
- ChannelReachability: `channel`, `delivery_route`, and `delivery_attempt`.
- ConversationRuntime: `conversation`, `message`, `inbound_media`, `turn`,
  `output_disposition`, and the shared `outbox`.
- Reminder: `reminder`, `reminder_fire`, recurrence data, and reminder calendar
  read models.
- SocialScheduling: `friend_link`, `friendship`, `shared_reminder`,
  `reminder_projection`, `notification_fact`, and `notification_recipient`.
- CalendarImport: `calendar_import_run` and `calendar_import_item`.
- Agno substrate: session, history, memory, knowledge, and pgvector.

Redis stores only coordination state:

- Redis Streams for worker wake-up.
- Per-conversation locks using ownership tokens.
- Reply pub/sub keyed by `causal_inbound_event_id`.

Nothing durable lives only in Redis. A Redis restart may lose wake-up signals,
but unacknowledged Postgres outbox rows are replayed.

## Web Target

The web app is a thin Next.js client over the Python API. It keeps the required
product pages and moves business decisions into Python domains.

The authoritative route namespace lives in
`docs/design-docs/interface-contract.md`; the discoverable product route index
lives in `docs/product-specs/FEATURE_TREE.md`. This architecture reference only
summarizes the route families: public web pages and friend links, customer
account/channel/reminder/social/calendar/subscription/claim pages, Python API
namespaces for the six product modules, provider webhook adapters, and the
private delivery callback and reply-wait runtime endpoints.

## Channel And Provider Boundary

Coke owns the canonical message, identity, route, and delivery contracts.
Providers are edge adapters. Current product channels are personal WeChat and
shared WhatsApp; retained provider adapters are `wechat_personal`,
`whatsapp_evolution`, `wechat_ecloud`, and `linq`.

`wechat_personal` is the only remaining ClawScale-shaped responsibility. It is
an adapter peer, not a runtime center. Provider-specific identity or message
shapes must be normalized at the ingress/egress boundary before they reach
domain modules or the Interaction Agent.

## Product Invariants

- Account access fails closed for inbound assistant processing, channel
  connection, and calendar import.
- One messaging identity maps to one account. Accounts are not merged or
  heuristically matched.
- A messaging-first anchor channel identity is not removable while it is the only
  identity anchoring the account.
- Each account has at most one reachable personal channel.
- Chat/channel-visible product prose is produced by the Interaction Agent, except
  for the runtime-owned waiting text.
- Turn disposition and delivery state are separate. Reminder undelivered state,
  proactive discard, shared-reminder projection delivery, and notification
  recipient delivery are not collapsed into a generic failure bucket.
- Reminder fires are atomic, idempotent, replay-safe, and caught up after
  downtime. Proactive follow-ups are discarded on delivery failure.
- Friendships are direct active relationships, not owner-approval requests.
- Shared reminders are active immediately after validation. Any participant may
  cancel the whole group; completion affects only that participant's projection.
- Product notifications are structured facts rendered by The Turn. Notifications
  are informational and never approval or action-execution workflows.
- Calendar import is one-time import into Coke-owned reminders with
  occurrence-grain dedupe.

## Deleted Legacy Surfaces

The clean rebuild deletes or supersedes these surfaces:

- TypeScript Gateway API product ownership.
- Standalone Python ClawScale bridge process, bridge reply waiter, bridge
  outbound dispatcher, bridge callbacks, and Gateway-to-Bridge notification
  enqueue.
- Mongo runtime storage for messages, sessions, reminders, locks, vector search,
  and runtime transcript state.
- Gateway-owned notification text and any stored final notification prose.
- Pending friend request approval and shared-reminder accept/reject flows.
- Order, usage, quota, and billing ledgers. The access gate remains in scope.
- SaaS organization graph concepts that are not current product requirements.
- LangBot, hardcoded admin chat commands, busy/hold scripts, relationship-score
  simulation, Moments/photo album/media generation, and dead terminal direct
  Mongo bypasses.
- Compatibility shims for old data, old protocols, and old runtime shapes.

## Verification Implications

The canonical docs gate is:

```bash
bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh
```

Docs-only clean-rebuild changes should also run:

```bash
zsh scripts/check
zsh scripts/verify-surface repo-os-docs
```

Implementation tasks should use the new clean-rebuild surfaces in
`docs/fitness/surfaces.yaml` and `docs/fitness/coke-verification-matrix.md`:

- `clean-rebuild-docs`
- `clean-rebuild-backend`
- `clean-rebuild-web`

Structure checks do not prove runtime behavior. Backend work needs Python
domain/API/worker tests. Web work needs the Next.js web test and build. Runtime,
delivery, and agent-output claims need user-path, corpus, or smoke evidence.

## Out Of Scope

- Historical production data preservation, protocol migration, dual writes, and
  compatibility recovery.
- Media understanding, media generation, voice ASR/TTS, photo album, and Moments.
  Inbound media preservation remains in scope.
- Order/usage metering and billing ledgers. Account access status and public
  checkout recovery remain in scope.
- More than one personal channel per account.
- Account merging, unlinking, heuristic identity matching, or passwords for
  messaging-first accounts.
- Performance/load testing and current-server operational hardening.
- Web auth hardening beyond the required product surfaces, unless a later task
  explicitly scopes it.
