# Architecture Reference

This document describes the clean-rebuild target architecture for Coke. The
requirements source of truth is
`docs/product-requirements/current.md`;
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
8. Persist outbound messages with deterministic segment ids.
9. Deliver through the current channel route with provider idempotency keys and
   record delivery attempts.
10. Update output-class-specific lifecycle state from delivery callbacks.

Interactive mode exposes domain tools and may mutate product state through
domain services. Render mode receives already-trusted structured facts and has no
business mutation tools.

Render-mode Interaction Agent construction disables Agno chat history as a fact
source. Render turns use trusted trigger facts, domain results, and dynamic
prompt blocks for product state; recent interactive chat may not supply title,
time, participant, delivery status, or privacy-bearing facts for system turns.
Reminder-fire render turns hydrate fire ids into trusted reminder facts before
the Interaction Agent runs and fail closed if the visible reply cannot reconcile
with those facts.

Structured reply output may contain one to three text segments. Each segment is
persisted as its own outbound message. For message-style channels such as
personal WeChat and shared WhatsApp, each persisted segment is delivered as a
separate ordered visible message with its own message id, idempotency key, and
provider delivery evidence. Aggregated newline-joined text is only an internal
turn summary and must not be used as the provider-visible payload for segmented
replies.

For inbound user turns, no-reply is an Interaction Agent output decision after
the full trusted context is assembled. Semantic interpretation may carry a
reply-necessity signal, but it must not close an inbound user turn before the
Interaction Agent has seen product-notification, reminder, focus, and memory
context. This keeps intentional no-reply observable without making the
pre-agent classifier stricter than the chat workflow.

### Interactive Input Windows And Pre-Reply Interruption

Interactive inbound turns are ordered by conversation input windows, not by a
single inbound message. `conversation.latest_inbound_seq` is the highest inbound
sequence recorded for the conversation. `conversation.last_closed_inbound_seq`
is the highest inbound sequence already covered by a durable close decision. An
interactive turn claims:

```text
input_from_seq = conversation.last_closed_inbound_seq + 1
input_to_seq   = conversation.latest_inbound_seq
```

The current input presented to the Interaction Agent is the ordered set of
inbound messages in `[input_from_seq, input_to_seq]`. Agno session history may
remain enabled, but it is not the source of truth for the current user input.
Inbound sequence assignment is a database-owned ordering invariant: the
conversation row is locked while assigning the next sequence, and inbound
messages are protected by a unique `(conversation_id, direction, seq)` key.

If a newer inbound message arrives in the same conversation before the active
turn has persisted its close decision, the open input window extends. The active
turn becomes `superseded` durably at inbound-record time, its Agno run id is
included in the inbound outbox payload for provider cancellation, and a
replacement turn is scheduled from the unchanged `last_closed_inbound_seq + 1`
through the new `latest_inbound_seq`. The older user message is not discarded;
the replacement turn processes the old and new messages together in sequence
order.

The close boundary is close-result persistence, not provider delivery. A
conversation-closing decision for a claimed input window is `replied` or
product-approved terminal `no_reply`. The close transaction must atomically
verify that no newer inbound has arrived for the claimed window, materialize
staged interactive commands, persist the close result, and advance
`last_closed_inbound_seq` to the turn's `input_to_seq`. `failed` and
`superseded` complete the stale or failed turn audit without claiming the input
window as product-handled.

`pending_async_reply` is an intermediate visibility disposition, not a close
decision. It records that runtime-owned waiting text was attempted, but it must
not materialize staged commands, set `turn.completed_at`, or advance
`last_closed_inbound_seq`.

Waiting delivery evidence is not equivalent to user-visible waiting progress.
Each waiting attempt carries a delivery envelope with its source, logical
delivery intent, traceparent, container, trigger/turn id, provider route,
context-token source and age, retry attempt, latency, and provider error code.
These diagnostics must make waiting-message failures buckettable separately from
final-reply failures even when they use the same provider adapter.

Runtime-owned waiting text is emitted independently of the blocked Interaction
Agent call. `coke-outbox-relay` scans active inbound turns and, after
`COKE_WAITING_REPLY_AFTER_SECONDS` (default 20 seconds), persists
`pending_async_reply`, records a segment `0` waiting message, and delivers that
waiting text through the same channel route. The original worker turn remains
active and interruptible. When the Interaction Agent eventually returns, the
same turn may still transition from `pending_async_reply` to `replied` or
`failed` if no newer inbound has arrived. If a newer inbound arrives first, the
pending turn is superseded and any later state-changing command from that stale
turn is rejected before materialization.

Waiting sends use logical delivery intents (`turn_id:waiting:1` and, at most,
`turn_id:waiting:2`) rather than blind provider-idempotency retries. A waiting
send may retry once with jitter only for retryable transport failures, only while
the final reply is not ready, and only if the per-route/account circuit breaker
allows it. Context-token, invalid-token, and provider session-window failures do
not retry; they are recorded as failed waiting delivery evidence and the final
reply remains the authoritative user-visible outcome.

Interactive state-changing tools must stage commands before the close boundary.
They may validate intent, read state, and create turn-local drafts, but they
must not activate reminders, shared-reminder proposals, notifications, or
external adapter effects until the fresh close transaction materializes the
staged commands. This avoids leaving wrong durable side effects when a user sends
a correction before receiving the first agent-visible reply.

The worker tier must observe new inbound while an interactive Agno run is still
active. Interactive execution is therefore supervised per conversation. In
horizontally scaled workers, durable interruption state is shared through
Postgres and the inbound outbox payload; process-local supervisor state is only
an acceleration path. When a replacement worker finds the Redis conversation
lock still held by the old worker, async interactive execution waits for the
lock instead of terminally failing the newer turn. The supervisor calls
`Agent.acancel_run(run_id)`, cancels any local asyncio task awaiting
`Agent.arun(...)`, and relies on ConversationRuntime freshness checks as the
final authority. Agno cancellation is a local execution aid, not durable
correctness.

## Bounded Contexts

IdentityAccess owns account identity, access gate, activation, sessions,
credentials, channel identity, auth artifacts, and onboarding gate state.
ChannelReachability owns the single reachable channel, delivery route, and
delivery attempts.
ConversationRuntime owns conversation order, messages, media references, turns,
and output disposition. Reminder owns reminders, fires, recurrence, scheduler,
and calendar read models. SocialScheduling owns friend links, friendships,
shared reminders, projections, and product notifications. CalendarImport owns
Google authorization, import runs, and per-occurrence import items.

When IdentityAccess marks `onboarding_guidance_required`, The Turn injects an
`onboarding_guidance` trusted fact block into the single Interaction Agent call.
The block may include the configured onboarding prompt/settings and trusted
`user_address_name`; it must describe only current product capabilities.
`first_guidance_sent_at` is stamped only after a committed final onboarding reply
has reached the product-defined visible delivery state, never after waiting
text, failed delivery, no-reply, invalid output, access-denied, failed, or
superseded turns.

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
- ChannelReachability: `channel`, `delivery_route`, and `delivery_attempt`,
  including provider outcome plus diagnostic envelope fields for delivery source,
  logical intent, retry attempt, traceparent, container, context-token source and
  age, latency, provider route, and provider error.
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
domain modules or the Interaction Agent. Personal-WeChat connection is web-first:
each Coke account starts its own iLink bot QR login, and the resulting bot token
and getupdates cursor are scoped to that account. Inbound personal-WeChat events
arrive with the connector session/account association and carry the iLink
`context_token`; outbound personal-WeChat sends must echo the latest stored
conversation `context_token`.

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
- Every terminal `NotificationTurn` path settles each target notification
  recipient as delivered, failed, or undelivered with structured facts. A
  reconciler may repair stale pending recipients after terminal completion, but
  it is a crash/history backstop, not the primary settlement path.
- Shared-reminder creation sends the invitation notification to receivers. The
  creator receives the original interactive creation reply, then receives a
  separate structured delivery-confirmed notification when a receiver's
  invitation notification is delivered.
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
