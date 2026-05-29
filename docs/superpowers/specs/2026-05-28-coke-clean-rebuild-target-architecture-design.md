# Coke Clean-Rebuild Target Architecture

Status: proposed (rewritten from first principles)
Created: 2026-05-28
Updated: 2026-05-29 (full first-principles rewrite: The Turn as the unifying
runtime abstraction; data model derived from requirement invariants as six
first-class product modules; agent orchestration with SemanticInterpreter
front-gate + encapsulated Detector; account access gate, identity/web-claim,
downtime catch-up, undelivered lifecycle, recurring-window timezone pinning, and
multimodal-input preservation folded in as native design. Then architect-review
round 1: split ChannelReachability from ConversationRuntime, promoted
CalendarImport to a named module, made the runtime-owned waiting text an explicit
typed exception, separated turn disposition from output-class-specific delivery
state, framed Coke's orchestration contract as primary with Agno as substrate,
and added an explicit ReferenceResolver)
Scope: whole-runtime target architecture for a destructive rebuild
Companion: `2026-05-28-coke-requirements-user-journey-matrix-design.md` is the
authoritative product-requirements / user-journey constraint. This document is
the prescriptive technical target and must serve those journeys, not
architectural aesthetics. Where the two disagree, the requirements matrix wins
and this document is wrong.

## 0. Premises

This is a clean-selection rebuild, not a migration. It is derived directly from
the current requirements matrix, not from "legacy minus features".

- No historical production data, protocol, or server state is preserved. Every
  deploy is a fresh start.
- No backwards-compatibility shims, alias routes, fallback parsers, or dual-write
  bridges are designed in. Code carries only the current product contract.
- Destructive refactoring is accepted. Dead and superseded code is deleted, not
  ported.
- Framework lock-in to Agno is explicitly accepted (§11).
- The macro topology decided on 2026-05-28 is taken as settled and is not
  re-opened here: one consolidated Python backend, a Next.js thin client, two
  datastores (Postgres + Redis, Mongo removed), deep Agno binding, ClawScale
  demoted to a `wechat_personal` adapter, and all four channel adapters retained.
  This document re-derives the *data model* and the *agent orchestration* on top
  of that topology.
- Current-server operational tuning (swap, disk thresholds, the specific
  `gcp-coke` box) is out of scope; this is a software-architecture target.

## 1. The Turn — The Unifying Runtime Abstraction

Reduced to its essence, Coke is a per-user, single-persona, agent-mediated event
machine. Every user-visible piece of prose has exactly one producer: the
Interaction Agent. The backend exists only to do five things — hold a trust /
identity boundary, persist durable domain state, schedule time-based work, run
the agent, and adapt to channels.

The central insight of this rebuild: **work enters the agent in only a small,
fixed set of ways, and they all have the same shape** — *something becomes true
in the world → it must reach the user as prose → the agent renders it.* There are
seven trigger types, and only two execution modes:

| Turn trigger | Source | Mode |
|---|---|---|
| `InboundTurn` | channel webhook → durable message → bus | Interactive (full tools) |
| `ReminderFireTurn` (timed / recurring / shared projection) | scheduler | Render |
| `ProactiveFireTurn` | scheduler | Render, **discard on delivery failure** |
| `NightlySummaryTurn` (20:00, no-trigger-time reminders) | scheduler | Render |
| `NotificationTurn` (friendship / shared-reminder / error facts) | domain event → outbox → bus | Render |
| `AccessDeniedTurn` (inbound blocked by access gate) | trust boundary | Render (constrained) |
| `UndeliveredResendTurn` (channel reconnected) | channel recovery | Render |

**The Turn is the spine of the runtime.** Every trigger flows through one
pipeline:

```text
trigger
  → pre-LLM gate                        (identity, access, reachability, handoff;
                                         fail-closed, §6)
  → per-conversation lock               (Redis SET NX PX + ownership token)
  → context assembly                    (TrustFraming, SemanticInterpreter, Focus,
                                         ReferenceResolver, Freshness, Memory — §4)
  → single Interaction Agent invocation (tool/context profile keyed by turn mode)
  → output protocol validation          (first answer; no rewrite, no fallback)
  → output disposition                  (replied | no_reply | pending_async_reply
                                         | failed, + reason)
  → outbound delivery + reply pub/sub    (channel adapter)
  → idempotent delivered callback        (local domain lifecycle update)
```

**Interactive mode** (only `InboundTurn`) runs the full context-assembly stack
and exposes the full tool surface (reminder CRUD, social scheduling, settings,
identity/claim, calendar import). It decides reply-necessity, supports
intentional no-reply, and supports the timeout→waiting-text→async-final contract.

**Render mode** (the six time/event-driven triggers) receives already-trusted
*structured facts* and renders role-toned prose with **no intent tools and no
business mutation**. Lifecycle/delivery updates happen as separate local domain
calls on the delivered callback, never as agent tool-side effects. Render mode is
the same Agno agent invocation with an empty/whitelisted tool set — this is how
the "exactly one prose producer" invariant survives across reminders,
notifications, summaries, and access-denied recovery.

Collapsing all seven triggers onto one pipeline is what lets a single rule —
"only the Interaction Agent writes chat prose" — hold everywhere, instead of
seven divergent handlers each tempted to template their own text.

## 2. Target System Shape

One Python backend (two tiers) + one Next.js thin client + two datastores.

- **Ingress/egress tier** (Python, stateless): receives provider webhooks and the
  customer/admin API; normalizes provider payloads into Coke's canonical inbound
  contract; enforces the account access gate at the trust boundary; writes
  durable message + outbox rows to Postgres in one transaction; runs
  provider-specific outbound delivery. It is the anti-corruption boundary against
  providers and absorbs the old TypeScript Gateway API and the ClawScale bridge
  inbound/outbound boundary. API routes are adapters over domain modules; they do
  not own business rules. Reply waiting is Redis pub/sub, so the tier holds no
  per-request state and scales horizontally.
- **Worker tier** (Python): consumes work-wake from a Redis Stream consumer
  group, takes the per-conversation Redis lock, and runs The Turn (§1). Worker
  tools and render turns are adapters over the Reminder and Social Scheduling
  domain modules; there is no worker→Gateway HTTP hop. The reminder scheduler is
  a single pinned instance (§8). Agno session/history/memory live in Postgres.
- **Web frontend** (Next.js, thin client): customer + admin UI over the Python
  API. Repointed to the Python backend, package scope de-branded. It keeps the
  account-access-status, subscription-status, and web-claim surfaces (§6, §13);
  the only language boundary left is web ⇄ backend.

```text
provider ⇄ ingress/egress tier (Python: webhooks in / outbound out;
                                normalize; access gate; canonical contract)
               │ Postgres (durable rows + single outbox)     ▲ local domain calls
               ▼                                             │
            Redis (work-wake stream / locks / reply pub/sub) ──► worker tier
                                                   (Python: The Turn;
                                                    Reminder scheduler;
                                                    Social Scheduling)
Next.js web ──HTTP──► Python API (same backend)
```

The one intentional async hop kept is `outbox → Redis → worker`, which routes
product events through the agent so chat-visible text has a single producer (§5).

## 3. Bounded Contexts And Data Model

The data model is derived from the requirement invariants, not from any legacy
schema. The system decomposes into **six first-class product modules** plus the
Agno substrate: **IdentityAccess**, **ChannelReachability**, **ConversationRuntime**,
**Reminder**, **SocialScheduling**, and **CalendarImport**. Identity, access,
single-channel reachability, and tokenized handoff are core product invariants in
their own right, not edge concerns hidden inside provider adapters — so they get
first-class modules, not better adapters. Each module owns its tables and exposes
only in-process domain services; API routes and agent tools are adapters over
those services and must not write another module's tables.

New tables are allowed only when they protect a current invariant: account
access, identity-anchor integrity, single-channel reachability, reminder firing,
recurrence-window determinism, friendship uniqueness, shared-reminder projection
consistency, outbound idempotency, or auditability of a user-visible turn.

### 3.1 Identity & Access

Owns: who this human is, whether they may use the product, and how a messaging
user reaches an authenticated web session. Realizes requirements §5.1, §5.13,
§2 rows 1/14.

| Table | Purpose / invariant |
|---|---|
| `account` | The Coke user. `origin ∈ {web_first, messaging_first}`, profile, one global default timezone, agent-settings fields, proactive switch, memory switch. |
| `account_access` | Access state used as a **product gate**: email-verification state, subscription/access state, suspension state, and the derived `access_allowed` + denial reason. No order/usage/quota metering (§15). |
| `credential` | Web-first only: email + password hash (+ forgot/reset). Messaging-first accounts have no credential; their only web auth path is a one-time claim. |
| `session` | Web session / token. |
| `channel_identity` | A provider-side identity (e.g. a WhatsApp sender address) mapped to exactly one `account`. For messaging-first accounts this is the **account anchor**; it is created atomically with the account on first contact and is non-removable while it is the account's only identity. |
| `auth_artifact` | **Unified** one-time authentication artifact: `type ∈ {login_url, claim_code, pairing_code}`, `target_account`, `expires_at`, `consumed_at`. Single-use, time-limited, bound to exactly one account, never reusable for another account. |

Identity rules (from §5.13): auto-provisioning applies **only** to shared
WhatsApp; a first-seen sender identity provisions a new messaging-first account, a
known sender continues as its existing account. The system never merges or
unlinks accounts and never guesses identity from display name / profile
similarity. Claiming is bidirectional and runs entirely on `auth_artifact`:
chat-initiated `login_url` (assistant issues a one-time URL in conversation) and
web-initiated `claim_code` (web page shows a code; user sends it to the channel).
During a web-first user's channel-connection flow, an inbound carrying a valid
`pairing_code` binds that `channel_identity` to the issuing account instead of
auto-provisioning.

### 3.2 Channel Reachability

Owns: provider-identity binding, the single-channel-per-account rule, channel
lifecycle, the delivery route, anchor-removal guards, and outbound send-attempt
outcomes. Realizes §5.3 and the channel parts of §5.12. This is the "can we reach
this user, and did a send land" module — distinct from the conversation runtime
that decides what to say.

| Table | Purpose / invariant |
|---|---|
| `channel` | The account's reachable personal channel. `provider_type`, connection state (`not_connected | connecting | connected | failed`), bound `channel_identity`. **Cardinality ≤ 1 active per account.** A messaging-first account's anchor channel is non-removable; a web-first user may remove/switch (remove old first). "Connected" means deliverable, not "upstream step succeeded". |
| `delivery_route` | The resolved, stable send target (provider + address) derived from `channel` + `channel_identity`. Reminders, shared-reminder projections, and notifications target a route, not channel internals. May be denormalized onto `channel`, but is modeled explicitly so delivery has one canonical target. |
| `delivery_attempt` | Per-outbound send-attempt outcome (`sent | delivered | failed`) — the raw delivery evidence from which output-class-specific delivery state (§3.4 undelivered, proactive discard, per-projection, per-recipient) is computed. A failed/absent send is never "delivered". |

### 3.3 Conversation Runtime

Owns: the inbound turn ledger, conversation ordering / stale-reply suppression,
the agent-orchestration handle, and the final output disposition. Realizes §5.4
and the conversation parts of §5.9.

| Table | Purpose / invariant |
|---|---|
| `conversation` | The ongoing agent conversation for an account; stable identifier for ordering and locks. |
| `message` | Inbound + outbound messages. Inbound: normalized payload, sender `channel_identity`, `causal_inbound_event_id`. Outbound: rendered text, 1–3 segments, link to disposition + (optional) `notification_id` + `facts_hash`. |
| `inbound_media` | Multimodal inbound (image/voice/etc.) preserved as **processable input** — reference/blob only. No understanding model, no media generation, no media reply (§10). |
| `turn` + `output_disposition` | One row per turn: trigger type, mode, timing, and exactly one **turn disposition** (`replied | no_reply | pending_async_reply | failed`) + small reason code. The audit spine of the runtime. Turn disposition is the turn outcome; per-target *delivery* state is output-class-specific (§4). |
| `outbox` | Single shared transactional outbox; any producer appends in the same transaction as its domain write (§5). Listed here as the runtime's durable event ledger; it is shared infrastructure, not owned business state. |

### 3.4 Reminder

Owns: temporal reminder execution. Realizes §5.5, §5.8, and reminder reachability
in §5.3.

| Table | Purpose / invariant |
|---|---|
| `reminder` | `owner`, `content`, `kind ∈ {timed, no_trigger_time, recurring, proactive, shared_projection}`, `next_fire_at` (nullable for no-trigger-time), recurrence rule, **`captured_timezone`** (pinned at create/last-edit; recurrence windows expand in this tz, see §8), `duration` (default 15 min), lifecycle (`active | completed | deleted | undelivered`), route target. `proactive` reminders are hidden from the calendar and user-immutable. `shared_projection` reminders link to a `shared_reminder` (§3.5). |
| `reminder_fire` | Fire/replay evidence: compare-and-set on fire state (atomic, idempotent, replay-safe), per-reminder delivery result (`delivered | undelivered`), and a **missed/catch-up marker** for triggers the system missed while unavailable. This is the reminder-class delivery state layered on top of the turn disposition (§4). |

Duplicate prevention is a unique constraint, not a heuristic: same owner + same
content + same trigger time (or same owner + same content + both no-trigger-time)
is rejected. Duration, entry point, and phrasing are not part of the key.

### 3.5 Social Scheduling

Owns: relationship-based scheduling. Realizes §5.6, §5.7, §5.9.

| Table | Purpose / invariant |
|---|---|
| `friend_link` | Owner's public link + QR + link code; state `active | disabled`; reset rotates the token. Reset/disable affect only future new friendships. |
| `friendship` | Unique active relationship per unordered pair; established directly (no pending request). Self-friendship forbidden. Establishment requires both sides authenticated/claimed **and** holding a usable channel. |
| `shared_reminder` | Group reminder: creator + participant set, title, trigger time, `captured_timezone`, duration, status (`active | cancelled`). Uniqueness key: creator + participant set + title + local trigger time + timezone + duration (order-insensitive). |
| `reminder_projection` | Per-participant projection (a `kind=shared_projection` `reminder` row). Completion affects only that participant's projection; cancellation by any participant stops all projections. |
| `notification_fact` | Immutable structured facts + `facts_hash` + idempotency key + lifecycle + outbox evidence. **No `payload.text`** — final chat prose is never stored here (§5). |

Availability queries read each friend's personal + shared reminders and return
**privacy-safe busy/free only**, never reminder details. Receiver conflict and
participant channel availability are **hard pre-creation constraints**; the
creator's own conflict is intentionally not checked.

### 3.6 Calendar Import

A first-class supporting module over Reminder, not a placeholder — its Google
authorization handoff and dedupe rules are product-specific and need their own
contract. Realizes §5.10; retained, one-time import. `calendar_import_run` records
the Google auth handle and result counts (imported / skipped / downgraded /
failed); a per-source-event dedup key makes repeated imports skip silently without
user confirmation. Imported events become owner-scoped Coke `reminder` rows
(title+description → content, start → trigger, duration → duration with 15-min
default, all-day → 00:00, recurring → recurring reminder, or downgraded to
one-time future occurrences with an explained result). Historical events are not
imported. Revoking, stopping, or expiring authorization affects only future reads
and never deletes imported reminders.

### 3.7 Agno Substrate

Agno session/history, memory, and knowledge live in Postgres (`agno.db.postgres`
+ pgvector). These are substrate storage owned by the agent runtime, not a
product context (§11).

### Storage topology summary

| Data | Store |
|---|---|
| Identity, access, credential, session, channel identity, auth artifacts | **Postgres** |
| Channel, delivery route, delivery attempts | **Postgres** |
| Conversation, message, inbound media, turn/disposition | **Postgres** |
| Reminder runtime (reminders + fire/replay evidence) | **Postgres** |
| Social Scheduling (links, friendships, shared reminders, projections, notification facts) | **Postgres** |
| Calendar import runs | **Postgres** |
| Agno session/history/memory/knowledge | **Postgres** + pgvector |
| Single transactional outbox | **Postgres** |
| Work-wake queue | **Redis Streams** |
| Per-conversation locks | **Redis** (`SET NX PX` + ownership token) |
| Synchronous reply wait | **Redis pub/sub** (keyed by `causal_inbound_event_id`) |
| MongoDB | **Removed entirely** |

Nothing durable lives only in Redis; losing Redis on restart is acceptable.

## 4. Agent Orchestration (The Turn Internals)

This is the heart of the rebuild. There is exactly **one acting agent** — the
Interaction Agent — and it is the only component with a persona, tools, and the
authority to produce chat prose. "Single-Agent turn" (§5.4) means this: utility
LLM calls for classification or extraction are *not* additional agents; they are
context-construction and tool internals that feed the one agent.

**Coke's orchestration contract is primary; Agno is named second as the substrate
that fills the agent-loop slot.** The contract, independent of any framework, is:

```text
pre-LLM gate  → context builder → reference resolver → domain executor
              → response decision → output model
```

The **pre-LLM gate** must resolve before a normal turn proceeds — identity
binding, account access status (§6), channel reachability, and token/handoff
validation. A failed gate produces an `AccessDeniedTurn` or an explicit failure,
never a guessed turn. Only after the gate passes does the rest of the contract
run. Agno is the chosen implementation substrate for the agent-loop and storage
slots (§0, §11); it implements this contract, it does not define it.

Coke owns context construction and hosts it on Agno extension points
(`pre_hooks` / `post_hooks`, custom `MemoryManager`, explicit context injection,
`add_session_state_to_context=False`) rather than building a parallel framework
or a multi-stage agent graph. The legacy fixed QueryRewrite / ContextRetrieve
stages are not rebuilt.

The interactive-mode stack, in order:

- **TrustFraming** — inject the trusted identity and relationship facts resolved
  at the trust boundary. The agent never guesses who the user is or which friend
  is referenced beyond what TrustFraming asserts.
- **SemanticInterpreter (front-gate)** — an LLM-semantic classification pass (no
  keyword/regex routing) that decides **reply-necessity**, intent family
  (chit-chat / reminder-op / scheduling / friend-op / settings / post-reminder
  reply / claim), and language. If it classifies the turn as intentional
  no-reply, the runtime records `no_reply` and **skips the expensive Interaction
  Agent entirely**. This keeps intentional no-reply cheap and separately
  evaluable, and keeps it distinguishable from empty-output failure.
- **Focus** — resolve the single optional pointer to the current actionable
  product object (e.g. the reminder just fired), supporting post-reminder replies
  like "done" / "change it to tomorrow". No multi-candidate state, no pending
  accept/reject.
- **ReferenceResolver** — resolve a user reference to a concrete target before any
  action. Deleting `multi_candidate` focus state (§15) does not delete the need to
  disambiguate: duplicate friend names (§5.6), ambiguous shared-reminder
  cancellation (§5.7), and multi-operation or ambiguous reminder matching (§5.8)
  all require clarification. The rule is uniform: resolve a reference to exactly
  one active target; on zero or multiple candidates, ask a clarifying follow-up and
  **mutate nothing** until the user confirms. This is distinct from Focus (the
  single current object) — ReferenceResolver handles N-candidate disambiguation
  through conversation, not a stored pending-workflow surface.
- **Freshness** — stale-reply safety: before acting or sending, confirm this is
  still the latest intent in the conversation. Combined with the per-conversation
  lock and causal ordering, older in-progress work never overwrites a newer
  intent and stale/duplicate replies are suppressed.
- **Memory** — short-term recent context (always available, even when the memory
  switch is off, because it is needed to complete the current turn) plus
  long-term memory via Agno memory storage/retrieval. A custom `MemoryManager`
  owns extraction/injection policy and is gated by the memory switch; Agno's
  automatic user-memory extraction is left off. Short-term and long-term memory
  are one merged subsystem, not two specs.

Then the Interaction Agent runs with the full tool surface. Tools are adapters
over the domain modules (Reminder, Social Scheduling, Identity & Access, Calendar
Import); they do not own business rules and do not write other contexts' tables.

**Detector placement (decided).** The locked reminder/scheduling extractor
(`reminder_detect`, GLM-5.1 thinking-off) is **encapsulated inside the Reminder
and Social Scheduling domain tools**, not run as a pre-agent stage. When the
Interaction Agent decides to create/edit a reminder or schedule a shared
activity, the tool internally invokes the detector to extract precise structured
fields. The detector and the SemanticInterpreter are deliberately **two distinct
components**: the interpreter does high-level routing/reply-necessity up front;
the detector does high-precision field extraction behind the domain boundary.

Rationale for this split over the alternatives:
- A full two-phase design (extract everything up front, then render) fights the
  required follow-up loop — when reminder fields are missing the agent must ask
  follow-up questions (§5.8); rigid pre-extraction makes that loop awkward and
  wastes the detector on classified-but-conversational turns.
- A pure single-reasoning design (detector only as a tool, no interpreter
  front-gate) forces the full persona agent to run on every message just to learn
  whether a reply is needed, and fuses intentional no-reply with empty output —
  exactly the distinction the requirements demand be observable.
- The split gives an explicit, cheap, separately-evaluable reply-necessity gate;
  the agent as the single actor that decides *what to do* (preserving the
  follow-up loop and single prose producer); and the tuned, eval-validated
  detector placed exactly where it is strongest — precise extraction.

**Detector output stays trusted-or-invalid.** Reminder and Social Scheduling
tools do not patch detector or interpreter output with regex recovery
(`duration_minutes`, `receiver_name`, weekday/date mismatch, dropped scheduled
clauses, zero-duration normalization, title repair, etc.). Missing or wrong
semantic fields are prompt/eval failures or invalid decisions, not permanent
runtime guard branches.

**Output contract.** The agent must satisfy the current structured output
contract on the **first** returned answer. Invalid, empty, or structurally
blocked output becomes `no_reply` or `failed`; the runtime does not ask the model
to rewrite, does not convert trusted facts into replacement prose, and does not
send template fallback text.

**The waiting text is the one runtime-owned typed message, and it is not
optional.** When synchronous processing times out while the agent is still
working, the runtime emits a visible waiting text, records `pending_async_reply`,
and delivers the final agent reply asynchronously. This is a required product
contract (§5.4), not a fallback: the waiting text is a typed delivery-status
signal carrying no intent result and no assistant content, so it does not violate
"only the Interaction Agent writes chat prose" (it is not prose *about the user's
request*) and it is explicitly exempt from the no-fallback-prose rule. It is the
only such exception; timeouts, empty output, and protocol violations otherwise
move the turn to `no_reply` or `failed` with no substitute text.

**Turn disposition vs delivery state — two layers.** The four-state
`output_disposition` (§3.3) records the *turn outcome* — was a reply produced, was
it intentional no-reply, did it time out to async, did it fail. It is deliberately
not overloaded to express per-target delivery. Whether a produced message actually
reached each recipient is **output-class-specific delivery state**, computed from
`delivery_attempt` (§3.2):

- **Personal reminder fire** → `reminder_fire.delivery_result` (`delivered |
  undelivered`); undelivered reminders are resent on reconnect and caught up after
  downtime (§8).
- **Proactive follow-up** → no undelivered state at all; on send failure it is
  **discarded** (§8).
- **Shared reminder** → per-projection delivery; each participant's projection
  succeeds or fails independently (§9).
- **Product notification** → per-recipient delivery plus partial-failure *facts*;
  a partial failure is recorded as notification fact state, not a turn failure
  (§9).

One generic failure bucket would erase these required differences; the turn
disposition and the class-specific delivery state are separate on purpose.

**Runtime decomposition.** The orchestration core (The Turn) is split into
focused sibling modules matching the contract: trigger intake, pre-LLM gate
(identity/access/reachability/handoff), lock management, context assembly
(TrustFraming / SemanticInterpreter / Focus / ReferenceResolver / Freshness /
Memory), agent invocation + output-protocol validation, disposition recording, and
outbound delivery. No single ~2,500-line runtime file.

## 5. Message Flow, Bus, And Outbox

A single transactional-outbox pattern is the only inter-component async
mechanism. It closes bus-polling, partial-write leaks, and product-notification
dual-ownership at once.

- **Single outbox:** one shared Postgres `outbox` table. Any producer (ingress
  tier, worker, Reminder, Social Scheduling) appends a row in the same
  transaction as its domain write; one relay drains it to a Redis Stream. Not two
  outboxes.
- **Work-wake:** the ingress tier writes the durable `message` row and an
  `outbox` row in one transaction; the relay publishes; workers consume via a
  consumer group.
- **Locks:** per-conversation Redis lock with ownership token; TTL derived from
  the runtime walltime budget; heartbeat extends it; lock-loss is instrumented.
  Per-conversation ordering is enforced by the lock, not by stream partitioning.
- **Reply wait:** the ingress tier subscribes to a Redis channel keyed by
  `causal_inbound_event_id`; the worker publishes on completion. Late replies are
  promoted to the async push path. No in-memory per-request state.
- **Domain commit boundary:** Coke does not model an LLM turn as one rollbackable
  transaction. Once a domain service commits a business fact, that fact stays true
  even if later wording, output validation, reply waiting, or delivery fails.
  Recovery is via retryable generation, delivery, and reconciliation state — never
  by silently deleting committed reminders, friendships, or shared reminders.
- **Atomic domain write + outbox:** each domain service commits its facts and the
  corresponding outbox event in one Postgres transaction. Personal reminder
  creation, shared-reminder creation, friendship changes, notification facts, and
  lifecycle updates must not commit without their durable event evidence.

**Chat output ownership.** `notification_fact` stores immutable structured facts
plus `facts_hash`; there is no chat-prose field. The authoritative chain, threaded
by a single `notification_id`:

```text
Postgres notification_fact
  -> outbox -> Redis event -> worker NotificationTurn (render mode)
  -> Interaction Agent generated text
  -> Postgres outbound message (carries notification_id + facts_hash)
  -> outbound delivery
  -> idempotent delivered callback (local domain lifecycle update)
```

When a user replies after a notification, trusted context is rebuilt from the
Postgres facts, never from the previous LLM wording. Delivered/lifecycle updates
are local Postgres transactions into the owning domain — no HTTP callback, no
cross-domain table write. A single physical Postgres is a deployment fact, not a
license to cross module ownership.

**Validation cut line.** Strong validation lives at three boundaries only:
ingress (identity tuple, channel/provider envelope, route key, body shape,
timezone, RRULE, duration, schedule), durable facts (unique constraints,
idempotency keys, state transitions, outbox append, delivery lifecycle), and the
agent output boundary (structured-output contract on the first answer).
Everything else is observability plus explicit failure. No business rollback
compensation, no generic fallback prose, no message-document retry/rollback
counters, no synchronous provider rollback choreography, no migration-era
recovery paths, and no schema inflation to defend against every LLM mistake.

## 6. Identity, Account Access Gate, And Web Claim

Account access is a **product gate**, not just a display status (§5.1, §3). At
the ingress trust boundary, every inbound and every gated web action resolves the
account and checks `account_access`. When access is denied — email verification
still required, subscription/access inactive, or account suspended — the system
**fails closed**: it does not run normal inbound assistant processing, does not
allow channel connection, and does not allow calendar import.

A denied inbound does not silently drop and does not run the user's intent.
Instead it produces an `AccessDeniedTurn`: a structured access-status fact (with
denial reason and, for messaging-first subscription-inactive cases, a public
checkout link) is rendered by the Interaction Agent in constrained render mode.
This keeps the single-prose-producer invariant intact even on the recovery path —
the recovery message is generated prose over a trusted fact, not templated
operational text and not normal intent execution.

This gate is the *only* monetization-adjacent runtime concept retained. There is
no order ledger, no usage metering, and no quota enforcement (§15); access state
is an input, and checkout is an external URL surfaced as a fact field.

**Web claim** runs entirely on `auth_artifact` (§3.1). A messaging-first user
reaches an authenticated web session by claiming their existing account, never by
registering a second one — bidirectionally via a chat-initiated `login_url` or a
web-initiated `claim_code`. A web-first user connecting a channel binds a new
`channel_identity` via a `pairing_code` carried on an inbound message. Web entry
points surface the claim path so messaging users authenticate as their existing
account rather than registering a new one.

## 7. Channels And ClawScale As An Adapter

Coke owns the canonical message and delivery contract; providers are edge
adapters behind it, all peers, none a first-class architectural concept.

- **"Current product channels" and "retained provider adapters" are explicitly
  different layers.** The current product channels — what a user may connect as
  their one personal channel (§5.3) — are **personal WeChat** (`wechat_personal`,
  web-first, connection-first) and **shared WhatsApp** (`whatsapp_evolution`, the
  only messaging-first auto-provisioning path). Separately, **all four provider
  adapters are retained** behind the canonical contract (`whatsapp_evolution`,
  `wechat_personal`, `wechat_ecloud` (gewe), `linq` (SMS)); `wechat_ecloud` and
  `linq` are peer adapters not currently surfaced as product channels. Keeping the
  two layers distinct stops accidental provider surface area from leaking into the
  product contract.
- **ClawScale is not a first-class module.** It decomposes into (1) the
  `wechat_personal` provider adapter, peer to the others; (2) the inbound/outbound
  anti-corruption responsibility, folded into the Python ingress/egress tier (no
  separate "clawscale bridge" process); (3) the TypeScript Gateway API,
  reimplemented in Python; the Next.js web package de-branded off `@clawscale/*`.
- **Identity modeled once.** `channel_identity`, `account`, `conversation`, and
  delivery route each have a single canonical model; provider shapes are mapped at
  the adapter edge. Auto-provisioning and pairing (§3.1, §6) are the only
  identity-creation paths; duplicate provider-specific user concepts are not
  carried forward.

## 8. Reminder Execution

- **Single pinned scheduler.** The reminder scheduler runs as one pinned instance
  (APScheduler, single process, Postgres jobstore), so there is no multi-replica
  duplicate-fire race. Message workers still scale to N; only the scheduler is
  singleton.
- **Fire is atomic, idempotent, replay-safe** (compare-and-set on fire state).
  Each due reminder forms a `ReminderFireTurn` that enters the Interaction Agent
  in render mode and is delivered as role-toned text through the user's one usable
  channel.
- **Recurrence timezone pinning.** Recurring windows expand using the reminder's
  `captured_timezone` (set at create/last-edit), not the user's current global
  timezone. A global timezone switch changes display and the timezone applied to
  *newly created* reminders only; it never recomputes existing reminders' trigger
  moments or recurrence windows. Recurrence supports hourly→yearly and custom
  intervals (minimum hourly); sub-daily recurrence is bounded by a time window
  (default 08:00–23:00). After each fire/completion the next valid trigger is
  advanced atomically.
- **No-trigger-time reminders + nightly summary.** Reminders with no trigger time
  are first-class. A scheduled 20:00 per-owner `NightlySummaryTurn` summarizes
  them and asks whether to schedule times.
- **Same-owner same-time merge.** Multiple reminders for the same owner at the
  same trigger time are merged into one rendered reminder message; each reminder
  and its fire evidence remain independent.
- **Undelivered lifecycle.** A reminder due with no usable channel, or whose send
  fails, is never marked delivered; it enters `undelivered`. On channel
  reconnect, an `UndeliveredResendTurn` re-renders pending undelivered reminders
  (merging multiple into one, framed as previously-undelivered). Completed,
  deleted, or already-handled reminders are not resent.
- **Downtime catch-up.** If a reminder's due moment is missed because the system
  itself was unavailable, the scheduler catches it up on recovery — delivering it
  late through a usable channel or retaining an observable `undelivered` state —
  rather than dropping it. Catch-up applies to personal and shared reminders.
- **Proactive is different.** Proactive follow-up reminders are agent-created,
  hidden from the calendar, and user-immutable. Turning the proactive switch off
  cancels untriggered proactive follow-ups; turning it back on does not restore
  them. Proactive follow-up is user-invisible on failure: if the channel is
  unavailable or sending fails, it **expires and is discarded** — never resent,
  never `undelivered`, never shown on the calendar.

## 9. Social Scheduling

Reminder and Social Scheduling are separate domain modules with different
invariants. API routes and worker tools/render turns are adapters over them; they
do not own friendship, shared-reminder, projection, or notification business
rules and must not write those tables directly. There is no worker→Gateway HTTP
hop, no circuit breaker, no split ownership.

- **Friendship** is direct and active (no pending request). Issuing/sharing a
  friend link or link code requires the owner to hold a usable channel;
  establishing friendship requires the joiner to be authenticated/claimed and to
  hold a usable channel — so both sides always have a channel at establishment.
  Friend-link reset/disable affect only future new friendships. Establishment is
  idempotent; the same pair never creates a duplicate active friendship;
  self-friendship is forbidden.
- **Shared reminders** are one group reminder (creator + receivers), not split
  pairwise. Creation resolves each receiver to a unique active friend (ambiguity →
  follow-up), then enforces two hard pre-creation constraints — receiver conflict
  (overlap on duration window, from personal + shared reminders) and participant
  channel availability (creator + every receiver reachable). The creator's own
  conflict is not checked. Failing either reports who conflicts / who is
  unreachable and creates nothing partial. On success the reminder is immediately
  active with a per-participant projection; uniqueness is enforced by the §3.5
  key. Any participant cancels the whole group (stops all projections, notifies
  others); completion affects only one's own projection.
- **Availability** queries return privacy-safe busy/free only, sourced from Coke
  reminders (never Google Calendar), in the user's global timezone.
- **Notifications** are informational facts only (never approval/execution),
  covering friendship creation and shared-reminder creation/cancellation and their
  error/partial-failure/undelivered/conflict cases. Facts carry who/what/object/
  time/timezone/duration; errors map channel failures into product language and
  never expose raw channel errors, internal codes, queue status, or delivery
  attempts. Final visible text is the Interaction Agent rendering the facts (§5).

## 10. Multimodal Input Handling

Inbound media (image, voice, and other channel-carried content) is **received and
preserved as processable input** — normalized and stored as `inbound_media`
references/blobs and associated with the message (§5.4, §3). This satisfies the
"receive into processable input" requirement. The current contract does **not**
require an image-understanding model, media generation, or media replies: output
is text-only. Image generation, photo album, Moments, and voice ASR/TTS are out
of scope (§16). Whether the LLM reasons over preserved media beyond text is a
prompt/agent concern, not a new runtime guarantee in this rebuild.

## 11. Deep Agno Binding (Hosted Model)

Bind deeply to Agno as the runtime substrate and host Coke's custom context logic
*on Agno's extension points* rather than in a parallel framework. Lock-in is
accepted. Agno's memory / knowledge / guardrail / session_state subsystems are
opt-in and pluggable, so deep binding does not impose Agno defaults on Coke's
context layer.

Agno owns (substrate): the agent loop and tool calling; session/history storage
on Postgres (`agno.db.postgres`); memory and knowledge storage + retrieval on
Postgres + pgvector (replacing the hand-built `memo-runtime` and the dead
brute-force vector search); the guardrail hook mechanism.

Coke owns (custom logic on Agno extension points): the orchestration contract
itself (§4) — Agno fills the agent-loop slot but does not define the contract;
TrustFraming, SemanticInterpreter, Focus, ReferenceResolver, Freshness, and Memory
injection policy (§4); LLM-semantic intent interpretation (never keyword/regex);
the pre-LLM gate; long-term memory
extraction/injection via a custom `MemoryManager` (Agno auto-extraction off);
executable-boundary validation as `pre_hooks` / `post_hooks` (but not semantic
output repair or claim policing); and the trusted-or-invalid detector contract.

## 12. Cross-Cutting Runtime Concerns

- **Single datastore access layer:** one injected factory exposing a shared
  Postgres pool and a shared Redis client, both component-tagged. No per-DAO
  client construction. With Mongo gone, the fragmented-pool problem disappears by
  construction.
- **Stateless ingress/egress tier:** Redis-backed reply waiting; the tier holds
  no per-request state and scales horizontally.
- **Messages are a real DAO**, not a module-level singleton masquerading as a
  domain.
- **Cross-process tracing:** W3C `traceparent` + OpenTelemetry spans across
  ingress → bus → worker → egress. The trace id is carried on the `outbox` row so
  the async hop stays correlated. This replaces ad-hoc `causal_inbound_event_id`
  log stitching as the primary correlation mechanism (the id remains the reply-wait
  key).
- **Internal service auth:** the existing single shared static key per internal
  edge is kept as-is for this rebuild; per-caller identities / rotation are out of
  scope; localhost binding remains the main mitigation.

## 13. Web

The Next.js web app remains a thin client: it repoints to the Python API and
de-brands its package scope. It **keeps** the account-access-status,
email-verification, subscription/access-status, and web-claim surfaces (one-time
`claim_code` entry, login-URL landing) required by §5.1 and §5.13, plus the
public explanation / FAQ / demo / privacy / terms pages. The admin/customer
surface split is shelved.

Known auth gaps are a recommended follow-up, not part of this backend rebuild:
tokens currently live in `localStorage` (XSS-exposed) and protected pages lack
edge/server auth checks. Moving tokens to httpOnly cookies and enforcing auth at
the edge for admin routes is advised when web is next touched.

## 14. Invariants To Preserve

These correctness properties are design requirements:

- **Access gate fail-closed**: inbound assistant processing, channel connection,
  and calendar import do not proceed when account access is denied; the user gets
  a user-understandable recovery message (§6).
- **Identity integrity**: one messaging identity maps to one account; accounts are
  never merged or unlinked; auth artifacts are one-time, time-limited, single-use,
  bound to one account; messaging-first anchor identity/channel is non-removable.
- **Single reachable channel**: at most one usable personal channel per account.
- **Exactly one prose producer**: only the Interaction Agent writes chat text,
  across all seven turn types. The runtime-owned synchronous-timeout waiting text
  is the sole typed-signal exception and carries no intent result (§4).
- **Exactly one disposition per turn**: `replied | no_reply | pending_async_reply
  | failed` + reason; intentional no-reply is observable and distinct from
  failure.
- **Disposition and delivery state are separate layers**: the turn disposition is
  the turn outcome; per-target delivery (reminder undelivered, proactive discard,
  per-projection, per-recipient notification facts) is output-class-specific and
  never collapsed into one generic failure bucket (§4).
- **Reminder lifecycle** is atomic, idempotent, replay-safe; missed triggers are
  caught up (personal + shared); proactive is discarded on failure; recurrence
  windows are timezone-pinned and never silently recomputed.
- **Trust boundary** requires a coherent identity tuple before any enqueue
  (anti-corruption layer).
- **Social Scheduling writes** are transactional with idempotency via unique
  constraints and deterministic ids; friendship uniqueness and shared-reminder
  projection consistency hold.
- **Lock release** verifies ownership and never releases another worker's lock.
- The repo-OS governance layer and the clean eval↔product decoupling.
- Tight network posture: services bind localhost; only the edge is public;
  secrets are environment placeholders.

## 15. Deletion List

Per the clean-contract rule, the following built-but-unwired or superseded code is
deleted. Anything later wanted is designed fresh, not resurrected.

- **No legacy feature resurrection:** relationship-score simulation, busy/hold,
  daily-script / proactive-chance loops, LangBot, hardcoded admin chat commands,
  and connector-specific platform branches are deleted.
- **No split Gateway/Bridge runtime:** the TypeScript Gateway API, Python
  ClawScale bridge process, bridge reply waiter, bridge outbound dispatcher,
  bridge↔Gateway callbacks, and Gateway→Bridge notification enqueue are not
  rebuilt. Their valid responsibilities move into the Python ingress/egress tier,
  domain services, and outbox.
- **No Mongo runtime surface:** Mongo `inputmessages`, `outputmessages`,
  conversation locks, session/history, reminder storage, and dead vector/search
  helpers are deleted. Postgres durable state + Redis coordination only.
- **No product-notification prose path:** `notification_fact` keeps structured
  facts, idempotency, lifecycle, and outbox evidence only; any `payload.text` or
  route/service that writes final chat prose outside the Interaction Agent is
  deleted.
- **No order/usage/quota metering:** `OrderDAO`, `UsageDAO`, quota enforcement,
  and order-ledger paths are deleted. **Note:** the *account access gate*
  (verification / subscription-access / suspension as a gate input, plus a public
  checkout link as a fact field) is **retained** per §6 — only metering/billing
  ledgers are removed.
- **No SaaS/platform org graph:** `Tenant`, `Member`, `Customer`, `Membership`,
  `AgentBinding`, `AiBackend`, `EndUserBackend` are not rebuilt (no organization
  concept in the current product). **Note:** identity/claim concepts the current
  journeys *do* name — auto-provisioning, `channel_identity` mapping, the unified
  `auth_artifact` (login URL / claim code / pairing code), and the friend
  link/link-code — are **retained** per §3.1, §3.5, §6. The earlier blanket
  deletion of `ParkedInbound` / `LinkCode` is superseded: those capabilities are
  now named by §5.6/§5.13 and are modeled, not deleted.
- **No pending shared-reminder workflow:** friend requests, shared-reminder
  requests, accept/reject tools, pending-request ambiguity handling, and
  `multi_candidate` focus binding are deleted. Direct friendship + active shared
  reminders only.
- **No business rollback/recovery maze:** rollback compensation that cancels
  committed reminders, Mongo input-message `retry_count` / `rollback_count`,
  partial-send de-dup fields, and old dispositions like `rollback` / generic
  `fallback` are deleted. Four dispositions only (§4); committed facts are durable.
- **No provider synchronous rollback choreography:** connect/disconnect rollback
  helpers are not rebuilt. Channel management writes desired state and reconciles
  drift asynchronously or surfaces a clear operator-visible failure.
- **No migration/compatibility recovery tests as product requirements.**
- **No over-defensive LLM schema fields** and **no semantic claim-policing layer**
  (`required_questions`, `prohibited_claims`, regex claim/leak detectors): prompt
  and agent contracts handle semantic quality; schemas protect only executable
  boundaries and persisted facts.
- **No model-output repair/rewrite tests:** tests must not assert protocol-repair
  prompts, second-pass rewrites, domain-summary replacement, template fallback
  prose, detector-output regex recovery, or smoke classifications built around old
  fallback prose. Keep tests for strict validation and fail-closed dispositions.
- `memo-runtime` (replaced by Agno memory).
- All media reasoning/generation: `framework/tool/*` vendor modules and the
  `voice_tools` / `image_tools` adapters; image generation, photo album, Moments,
  voice ASR/TTS. **Note:** inbound media *preservation* (`inbound_media`) is
  retained per §10; only understanding/generation is out.
- Focus `multi_candidate` stub (collapse to single-candidate).
- `clawscale-cli-bridge` dead build artifact.
- `UserDAO` no-op stubs — implement real versions only where a caller needs one.
- Dead vector code in `dao/mongo.py` (removed with Mongo).
- `create_handler(0)` compatibility singleton.
- Tracked files under gitignored `artifacts/evidence/`.
- The `liblib` `__main__` NSFW demo block.
- The `connector/terminal/*` direct-to-Mongo bypass — a terminal dev tool, if
  still needed, enters through the canonical ingress API.

## 16. Out Of Scope

- Media reasoning and generation: image understanding model, image generation,
  photo album, Moments, voice ASR/TTS. (Inbound media is still preserved — §10.)
- Order/usage metering and billing ledgers (the access gate itself is in scope —
  §6, §15).
- Web changes beyond repointing, de-branding, and keeping the access/claim
  surfaces (auth hardening, admin/customer split — §13).
- Per-caller internal-auth identities / key rotation (§12).
- Load and performance testing.
- Current-server operational hardening (swap, disk alerting, systemd specifics).
- Account merging/unlinking, passwords for messaging-first accounts, messaging-first
  auto-provisioning for personal WeChat, more than one channel per account,
  heuristic identity matching (all per §5.13).

## 17. Decisions Resolved Here

- **The Turn** is the central runtime abstraction: seven triggers, two modes
  (interactive / render), one pipeline, one prose producer.
- **Data model** is six first-class product modules (IdentityAccess,
  ChannelReachability, ConversationRuntime, Reminder, SocialScheduling,
  CalendarImport) plus the Agno substrate, derived from requirement invariants —
  not a legacy cut line. Identity, access, reachability, and tokenized handoff are
  modules, not adapter side effects.
- **Account access gate**: minimal access-state gate (verification /
  subscription-access / suspension) as a fail-closed product gate; no metering /
  billing ledger; checkout is an external URL surfaced as a fact.
- **Identity/claim**: unified `auth_artifact` table for login URL / claim code /
  pairing code; shared-WhatsApp-only auto-provisioning; no merge/unlink;
  non-removable anchor.
- **Orchestration contract is primary, Agno is substrate**: the contract
  (pre-LLM gate → context builder → reference resolver → domain executor →
  response decision → output model) is defined independently; Agno fills the
  agent-loop and storage slots but does not define the contract.
- **Agent orchestration**: single Interaction Agent; SemanticInterpreter as the
  LLM-semantic front-gate (reply-necessity + intent family); the locked
  `reminder_detect` encapsulated inside Reminder/Social Scheduling tools, output
  trusted-or-invalid; an explicit **ReferenceResolver** does N-candidate
  disambiguation (mutate nothing until confirmed), replacing the deleted
  `multi_candidate` focus surface.
- **Delivery model is two-layered**: turn disposition (turn outcome) is separate
  from output-class-specific delivery state (reminder undelivered / proactive
  discard / per-projection / per-recipient notification facts). The waiting text
  is the sole runtime-owned typed-message exception to single-prose-producer.
- **Multimodal input** preserved as processable input; understanding/generation
  out of scope.
- **Channels**: current product channels (personal WeChat, shared WhatsApp) are a
  distinct layer from the four retained provider adapters; the extra adapters are
  peers, not surfaced product channels.
- **Embedding/knowledge** folded into Agno knowledge + pgvector from the start.
- **Long-term memory**: Agno storage/retrieval with a custom extraction/injection
  policy; merged with short-term context; no separate memory spec.
- **Trace/evidence retention**: bounded and regenerable — stored with a retention
  cap and rotation, never appended unbounded.
- **De-branding**: Python backend drops the `clawscale` name (ingress/egress tier
  as e.g. `message_gateway`); `@clawscale/web` → `@coke/web`.
