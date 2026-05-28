# Coke Clean-Rebuild Target Architecture

Status: proposed
Created: 2026-05-28
Scope: whole-runtime target architecture for a destructive rebuild
Derived from: the 2026-05-28 architecture review
(`docs/issues/2026-05-28-architecture-review.md`), which stays as the
evidence/findings layer; this document is the prescriptive target and keeps only
the findings that justify a choice, dropping all migration/debt/dormant/drift
framing.
Companion: `2026-05-28-coke-requirements-user-journey-matrix-design.md` is the
product-requirements/user-journey constraint; this document must serve those
journeys, not architectural aesthetics.

## 0. Premises

This is a clean-selection rebuild, not a migration.

- No historical production data, protocol, or server state is preserved. Every
  deploy is a fresh start.
- No backwards-compatibility shims, alias routes, fallback parsers, or dual-write
  bridges are designed in. Code carries only the target contract.
- Framework lock-in to Agno is explicitly accepted (see §5).
- Current-server operational tuning (swap, disk thresholds, the specific
  `gcp-coke` box) is out of scope; this is a software-architecture target.

Grounding facts that justify the choices below:

- Live data is tiny — MongoDB ~30 MB total, Postgres ~12 MB. There is no scale
  reason to keep Mongo; its only real cost today is being used as a polled
  message bus.
- Agno ships first-class `postgres` / `async_postgres` / `redis` storage
  backends (`agno/db/`) and native `memory`, `knowledge`, and `vectordb`
  subsystems (`agno/`). Coke currently uses almost none of this — it wires Agno
  as a thin agent loop with a Mongo session store and hand-rolls everything
  else.
- The legacy Volcano Coke server was simpler because its live product shape was
  narrower: connector + worker + background loop + Mongo/Redis, with user,
  reminder, and future/proactive messages reusing one handler pipeline. That
  simplicity is useful evidence for what to collapse, but legacy-only product
  features are not evidence for rebuilding media, numeric relationship
  simulation, busy/hold, LangBot, or ad-hoc admin command surfaces.

## 1. Target System Shape

One Python backend (two tiers) + one Next.js web frontend + two datastores. The
backend is consolidated to a single language: the worker, the inbound/outbound
boundary, and the former TypeScript Gateway API (social scheduling domain, control
plane, provider webhook normalization, outbound delivery) are all reimplemented
in Python on one Postgres schema. Next.js web is unchanged and becomes a thin
client over the Python API, with deleted access-gate screens removed or hidden.

- **Ingress/egress tier** (Python): receives provider webhooks + the
  customer/admin API; normalizes provider payloads into Coke's canonical inbound
  contract; writes durable message + outbox rows to Postgres; runs
  provider-specific outbound delivery. It absorbs the old bridge inbound
  boundary, the bridge outbound dispatcher, and the TypeScript Gateway API, and
  is the anti-corruption boundary against providers. Customer/admin API routes
  are adapters over domain modules such as Reminder and Social Scheduling; they
  do not own those business rules. Reply waiting is Redis pub/sub, so it holds
  no per-request state and scales horizontally.
- **Worker tier** (Python): consumes work-wake from Redis Streams, takes a
  per-conversation Redis lock, builds trusted-blocks plus one optional
  current-action focus, and runs a single Agno `Agent` per turn. Worker tools and
  system turns are also adapters over Reminder and Social Scheduling; they do not
  own those business rules. There is no worker→Gateway HTTP Social Scheduling
  hop. The reminder scheduler is a single pinned instance (§7). Agno
  session/history lives in Postgres.
- **Web frontend** (Next.js, thin client): customer + admin UI over the Python
  API. It is repointed to the Python backend and stripped of deleted
  subscription/access-gate screens; the only language boundary left is web ⇄
  backend.

```text
provider ⇄ ingress/egress tier (Python: webhooks in / outbound out; normalize; canonical contract)
               │ Postgres (durable rows + single outbox)       ▲ local domain calls
               ▼                                               │
            Redis (work-wake / reply pub/sub) ───► worker tier (Python: Agno turn;
                                                   Reminder scheduler;
                                                   Social Scheduling adapter)
Next.js web ──HTTP──► Python API (same backend)
```

Consolidation collapses the accidental hops from the old Python/TypeScript split
and the ClawScale bridge legacy: the worker→Gateway social-scheduling HTTP call
becomes a local domain call; inbound double-normalization (Gateway + bridge)
becomes one boundary; the outbound dispatcher→Gateway hop merges into one
outbound step; the delivered callback becomes an in-process write. The one
intentional async hop kept is outbox → Redis → worker, which routes product
events through the agent so chat-visible text has a single producer (§4).

## 2. Storage Topology: Two Stores

Physical single system of record + an ephemeral coordination layer. No "logical
ownership over a dual store" compromise — that was a migration-avoidance idea and
does not apply to a rebuild.

| Data | Store |
|---|---|
| Control plane (tenants, customers, identities, delivery_routes, agent_bindings, ai_backends, end_users) | **Postgres** |
| Social Scheduling + product domain (UserLink, Friendship, SharedReminder, events, ReminderProjection, ProductNotification) | **Postgres** |
| Runtime messages (input/output message content + audit evidence) | **Postgres** |
| Reminder runtime (reminders, fire/replay evidence) | **Postgres** |
| Agno session/history | **Postgres** (`agno.db.postgres`) |
| Embeddings / knowledge | **Postgres** + pgvector via Agno knowledge (§13) |
| Work-wake signal / queue | **Redis Streams** |
| Per-conversation locks | **Redis** (`SET NX PX` + ownership token) |
| Synchronous reply wait | **Redis pub/sub** (keyed by `causal_inbound_event_id`) |
| Outbox → runtime event relay | **Postgres outbox table + Redis Streams** |
| MongoDB | **Removed entirely** |

Redis stops being dead weight (`dbsize=0` today) and earns a real job: bus,
locks, and reply pub/sub. Nothing durable lives only in Redis; losing Redis on
restart is acceptable.

## 3. Message Flow, Bus, and Outbox

A single transactional-outbox pattern replaces Mongo-as-bus polling and the
hand-rolled, reminder-only compensation path. It closes three of the review's
top risks at once (bus polling, partial-write leaks, product-notification dual
ownership).

- **Single outbox:** one shared Postgres `outbox` table. Any producer (ingress
  tier, worker, Reminder, Social Scheduling) appends a row in the same
  transaction as its domain write; one relay process drains it to a Redis Stream.
  Not two outboxes.
- **Work-wake:** the ingress tier writes the durable message row and an `outbox`
  row in one Postgres transaction; the relay publishes to Redis; workers consume
  via a consumer group. Mongo `inputmessages` polling is gone.
- **Locks:** per-conversation Redis lock with an ownership token. Lock TTL is
  derived from the runtime walltime budget; the heartbeat extends it; lock-loss
  is instrumented. This replaces the Mongo poll-and-insert lock and removes the
  brittle 180s-timeout-vs-100s-LLM relationship. Per-conversation ordering is
  enforced by the lock, not by stream partitioning.
- **Reply wait:** the ingress tier subscribes to a Redis channel keyed by
  `causal_inbound_event_id`; the worker publishes on completion. Late replies are
  promoted to the async push path. No in-memory per-request state, so the tier
  scales horizontally.
- **Domain commit boundary:** Coke does not model an entire LLM turn as one
  rollbackable transaction. Once a domain service commits a business fact, that
  fact remains true even if later LLM wording, output protocol handling, reply
  waiting, or outbound delivery fails. Recovery happens through retryable
  generation, delivery, and reconciliation state, not by silently deleting
  already-committed reminders, friendships, or shared reminders.
- **Atomic domain write + outbox:** each domain service commits its business
  facts and the corresponding outbox event in the same Postgres transaction.
  Personal reminder creation, Social Scheduling shared-reminder creation,
  friendship changes, product-notification facts, and lifecycle updates must not
  commit without their durable event evidence.

## 4. Chat Output Ownership And Disposition

Exactly one producer of final assistant prose in chat channels: the Interaction
Agent. This fixes the shared-reminder receiver-notification bug at the
architecture level.

Operational status outcomes are not alternate prose owners. The runtime records
one durable output disposition per turn:

- `replied`: a final Interaction Agent reply was produced and delivery either
  succeeded or is retryable from outbox state.
- `no_reply`: the turn completed and intentionally produced no user message.
- `pending_async_reply`: synchronous waiting timed out, the ingress/egress tier
  may send a fixed operational fallback, and the final agent reply is still
  pending async delivery.
- `failed`: generation, output protocol validation, or outbound delivery failed
  and needs retry/reconciliation or operator-visible failure handling.

The disposition carries a small `reason` code for observability, but timeout
fallbacks, protocol violations, and delivery failures are not separate state
machines. This keeps the user-visible contract clear without multiplying fields.

- `product_notifications` in Postgres stores immutable structured **facts** plus a
  `facts_hash`. The `payload.text` chat-prose field is removed; no path other
  than the agent writes final chat text.
- Authoritative chain, threaded by a single `notification_id`:

  ```text
  Postgres product_notifications facts
    -> outbox -> Redis event -> worker system turn
    -> Interaction Agent generated text
    -> Postgres outputmessage (carries notification_id + facts_hash)
    -> outbound delivery
    -> idempotent delivered callback (updates Postgres lifecycle)
  ```

- When a user replies after a notification, trusted context is rebuilt from the
  Postgres facts, never from the previous LLM wording.
- **Processing fallback:** the timeout fallback is a product-approved operational
  status message, not final assistant prose and not a substitute for the final
  Interaction Agent reply. A fallback only moves the turn to
  `pending_async_reply`; the late reply path must keep trying to deliver the
  final generated text unless the final disposition becomes `no_reply` or
  `failed`.
- **Strict write-ownership:** product/notification tables are owned by Social
  Scheduling; API routes, worker tools, and output delivery code do not write
  them directly. Delivered/lifecycle updates are local domain calls into Social
  Scheduling — local Postgres transactions, no HTTP callback and no cross-domain
  table write. The single physical Postgres is a deployment fact, not a license
  to cross module ownership.

## 5. Deep Agno Binding (Hosted Model)

Decision: bind deeply to Agno as the runtime substrate, and host Coke's custom
context logic *on Agno's extension points* rather than building a parallel
framework outside it. Lock-in is accepted. Agno's memory / knowledge / guardrail
/ session_state subsystems are all opt-in and pluggable (custom `MemoryManager`,
custom `knowledge_retriever`, `pre_hooks` / `post_hooks`, explicit context
injection), so deep binding does not impose Agno's default behaviors on the Spec
A semantic layer.

Agno owns (substrate):

- Agent loop and tool calling.
- Session/history storage on Postgres (`agno.db.postgres`; backend swap in
  `agent/agno_agent/runtime/session.py` plus config).
- Memory and knowledge *storage + retrieval plumbing* on Postgres + pgvector.
  This replaces the hand-built `memo-runtime` (deleted, §11) and the dead
  brute-force vector search.
- The guardrail hook mechanism (`pre_hooks` / `post_hooks`).

Coke owns (custom logic hosted on Agno extension points, not a separate
framework):

- **CurrentActionFocus, TrustFraming, SemanticInterpreter, Freshness** keep
  ownership of context construction. Trusted-blocks injection stays explicit
  (`add_session_state_to_context=False`). Focus is a single optional pointer to
  the current actionable product object; multi-candidate focus state and pending
  accept/reject workflows are not rebuilt.
- **Intent / semantic interpretation** stays LLM-semantic, never keyword/regex
  routing.
- **Long-term memory** uses Agno memory for storage + retrieval, but a custom
  `MemoryManager` (or post-hook) owns the extraction and injection policy;
  Agno's automatic user-memory extraction is left off. This fixes the long-term
  memory mechanism here — there is no separate deferred memory spec.
- **Guardrails**: Coke's checks run as `pre_hooks` / `post_hooks`.

Runtime decomposition: the ~2,500-line `agent_runtime.py` is split into an
orchestration core plus sibling modules (intent normalization, current-action
focus resolution, envelope parsing + guardrails, Social Scheduling dispatch).

## 6. Channels and ClawScale as an Adapter

Coke owns the canonical message and delivery contract. Providers are edge
adapters behind it, all peers — none is a first-class architectural concept.

- **All four channels are retained** (they are implemented and live):
  `whatsapp_evolution`, `wechat_ecloud` (gewe API), `linq` (SMS),
  `wechat_personal` (ClawScale-backed).
- **ClawScale is not a first-class module in the target.** It decomposes into:
  1. one provider adapter for the `wechat_personal` channel, peer to the other
     three, behind Coke's canonical delivery contract;
  2. the inbound/outbound anti-corruption responsibility, folded into the Python
     ingress/egress tier (no separate "clawscale bridge" process name);
  3. the TypeScript Gateway API, reimplemented in Python (§1); the Next.js web
     package is renamed off the `@clawscale/*` scope to a Coke scope but is
     otherwise unchanged.
- **Identity is modeled once, in Coke terms.** Account identity, conversation
  identity, and delivery route each have a single canonical model; provider-
  specific shapes are mapped at the adapter edge. The duplicate identity concepts
  that exist only for historical integration are not carried forward.

## 7. Reminder And Social Scheduling

Reminder and Social Scheduling are separate domain modules with different
invariants:

- **Reminder** owns temporal reminder execution: reminder CRUD, recurrence,
  `next_fire_at`, fire/replay safety, completion/deletion semantics, and reminder
  output events.
- **Social Scheduling** owns relationship-based scheduling business:
  friendships, shared reminders, receiver conflict checks, participant reminder
  projections, product-notification facts, lifecycle, and idempotency.

API routes and worker tools/system turns are adapters over these domain modules.
They may call the modules in-process, but they do not own friendship,
shared-reminder, reminder-projection, or product-notification business rules and
must not write those tables directly. There is no worker→Gateway HTTP hop, no
circuit breaker, and no split ownership between a route handler and a worker
handler.

- The **reminder scheduler runs as a single pinned instance** (APScheduler,
  single process, Postgres jobstore), so there is no multi-replica duplicate-fire
  race. Message workers can still scale to N; only the scheduler is singleton.
- Reminder fire stays atomic/idempotent and replay-safe (§10).

## 8. Cross-Cutting Runtime Concerns

- **Single datastore access layer:** one injected factory exposing a shared
  Postgres connection pool and a shared Redis client, both component-tagged
  (`appName` equivalent). No per-DAO client construction. With Mongo gone, the
  fragmented-pool problem disappears by construction.
- **Stateless ingress/egress tier:** Redis-backed reply waiting means the tier
  holds no per-request state and scales horizontally.
- **Input messages are a real DAO**, not a module-level singleton masquerading as
  a domain.
- **Cross-process tracing:** W3C `traceparent` + OpenTelemetry spans across the
  ingress → bus → worker → egress path. The trace id is carried on the `outbox`
  row so the async hop stays correlated. This replaces ad-hoc
  `causal_inbound_event_id` log stitching as the primary correlation mechanism.
- **Internal service auth:** the existing single shared static key per internal
  edge is kept as-is for this rebuild (per-caller identities / key rotation are
  not in scope); localhost binding remains the main mitigation.

## 9. Web

The Next.js web app remains a thin client in this rebuild. It repoints to the
Python API, renames its package scope, and removes or hides screens that belong
only to deleted subscription/access-gate flows. The admin/customer surface split
is shelved.

Known auth gaps are recorded as a recommended follow-up, not part of this backend
rebuild: tokens currently live in `localStorage` (XSS-exposed) and protected
pages have no edge/server auth check. Moving tokens to httpOnly cookies and
enforcing auth at the edge (middleware / RSC) for admin routes is advised when web
is next touched.

## 10. Invariants to Preserve

The rebuild must retain these correctness properties already proven in the
current system; they are design requirements, not debt:

- Reminder lifecycle is atomic and idempotent (compare-and-set on fire state;
  replay-safe fire handling).
- The ingress trust boundary requires a coherent identity tuple before any
  enqueue (anti-corruption layer).
- Every turn records exactly one output disposition: `replied`, `no_reply`,
  `pending_async_reply`, or `failed`, plus a small reason code.
- Social Scheduling writes are transactional with idempotency via unique
  constraints and deterministic ids.
- Lock release verifies ownership and never releases another worker's lock.
- The repo-OS governance layer (surfaces, guardrails, verification routing) and
  the clean eval↔product decoupling.
- Tight network posture: services bind localhost; only the edge is public;
  secrets are environment placeholders.

## 11. Deletion List

Per the clean-contract rule, the following built-but-unwired or superseded code
is deleted in the rebuild. (Product-feature candidates were reviewed and declined
for this rebuild: subscription access-gating, quota enforcement, Focus
multi-candidate disambiguation, and all media — image input/understanding, image
generation, photo album, Moments, voice. Anything later wanted is designed fresh,
not resurrected.)

- **No legacy feature resurrection:** legacy Volcano Coke proves that one
  connector/worker/background pipeline is enough for the chat/reminder runtime,
  but its old product features are not carried forward unless named in the
  current requirements matrix. Relationship-score simulation, busy/hold,
  daily-script/proactive-chance loops, LangBot, hardcoded admin chat commands,
  and legacy connector-specific platform branches are deleted or left out.
- **No split Gateway/Bridge runtime:** the TypeScript Gateway API, Python
  ClawScale bridge process, bridge reply waiter, bridge outbound dispatcher,
  bridge-to-Gateway delivered callback, and Gateway-to-Bridge product
  notification enqueue path are not rebuilt as separate modules. Their valid
  responsibilities move into the single Python ingress/egress tier, domain
  services, and outbox.
- **No Mongo runtime surface:** Mongo `inputmessages`, `outputmessages`, Mongo
  conversation locks, Mongo session/history, Mongo reminder storage, and dead
  vector/search helpers are deleted. The target has Postgres durable state and
  Redis coordination only.
- **No product-notification prose path:** `product_notifications` keeps
  structured facts, idempotency, lifecycle, and outbox evidence only. Any
  `payload.text` or route/service that writes final chat prose outside the
  Interaction Agent is deleted.
- **No subscription/quota access gate in the core product:** checkout/renewal
  flows, subscription-required branches, quota enforcement, and Mongo `OrderDAO`
  / `UsageDAO` access-gate paths are removed from the runtime architecture.
  Customer identity remains; monetization can be designed later as a separate
  product surface.
- **No pending shared-reminder workflow:** friend requests, shared-reminder
  requests, accept/reject tools, pending-request ambiguity handling, and
  `multi_candidate` focus binding are deleted. The current product contract is
  direct friendship plus active shared reminders.
- `memo-runtime` (replaced by Agno memory storage/retrieval — §5).
- All media: the `framework/tool/*` vendor modules and the `voice_tools` /
  `image_tools` adapters are deleted. Image input/understanding, image
  generation, photo album, Moments, and voice ASR/TTS are all out of scope (§12).
- `OrderDAO` billing / access-gate Mongo path.
- Quota-enforcement path and `UsageDAO` usage-recording surface.
- Focus `multi_candidate` stub (`focus-binding-service` always `none_actionable`;
  disambiguation declined — collapse to single-candidate and remove the stub
  contract surface).
- `clawscale-cli-bridge` dead build artifact.
- `UserDAO` no-op stubs (`update_user`, `delete_user`, `change_status`,
  `get_user_by_phone/email`) — implement real versions only where a caller needs
  one.
- Dead vector code in `dao/mongo.py` (removed with Mongo).
- `create_handler(0)` compatibility singleton.
- Tracked files under gitignored `artifacts/evidence/`.
- The `liblib` `__main__` NSFW demo block.
- The `connector/terminal/*` direct-to-Mongo bypass is deleted. If a terminal
  dev tool is still needed, it must enter through the canonical ingress API.

## 12. Out of Scope

- All media handling: image input/understanding, image generation, photo album,
  Moments, voice ASR/TTS. (Deferred; not implemented in this rebuild.)
- Web changes beyond repointing to the Python API and the package rename
  (auth hardening, admin/customer surface split — §9). Subscription/renewal UI
  tied to the deleted access gate is removed or hidden as part of repointing.
- Per-caller internal-auth identities / key rotation (§8).
- Load and performance testing.
- Current-server operational hardening (swap, disk alerting, systemd specifics).

## 13. Decisions Resolved Here (no deferral)

These were the remaining open points; all are decided in this spec, not pushed to
a later plan or memory spec.

- **Embedding cache / retrieval:** folded into Agno `knowledge` + `vectordb` on
  Postgres + pgvector from the start; no separate plain-row cache.
- **Long-term memory:** Agno memory storage/retrieval with a custom extraction/
  injection policy (§5). There is no separate memory spec.
- **Trace/evidence retention:** traces and evidence are bounded and regenerable —
  stored with a retention cap and rotation (size/age), never appended unbounded.
- **De-branding names (proposal, adjust on review):** the Python backend modules
  drop the `clawscale` name (the ingress/egress tier as e.g. `message_gateway`);
  the Next.js web package `@clawscale/web` → `@coke/web`.
