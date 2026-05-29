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
and added an explicit ReferenceResolver. Then architect-review round 2: Focus
extended to grouped subject-sets, batch reminder-command contract, reminders
target the owner account with fire-time route resolution, per-recipient
notification delivery rows, occurrence-grain calendar dedupe, richer auth_artifact
with deferred claim-code binding + handoff continuation, outbox-as-source-of-truth
ack semantics, durable conversation sequence for stale-reply safety, no_reply
reserved for intentional no-reply only, and the full required web surface list.
Then architect-review round 3: occurrence-grain reminder_fire lifecycle split from
the series lifecycle, friendship removal lifecycle, account_activation projection
owning onboarding, pending_async_reply made an explicitly non-terminal transition,
agent_settings/user_profile split from inferred memory, and the
reconnection_required channel state. Then architect-review round 4: worker-turn
replay idempotency (trigger_id / turn_id+item_index / turn_id+segment_index),
reminder past-time/incomplete-date validation states, trigger-time ↔
no-trigger-time conversion transitions, per-occurrence calendar_import_item with
status+reason, bounded AvailabilityQuery, a Reminder-domain ReminderCalendarReadModel,
and narrowing the prose-producer invariant to chat/channel-visible product prose.
Then architect-review round 5: added a distinct `superseded` disposition (stale
suppression no longer overloads `no_reply`), grouped reminder fire turn keyed by
(owner, due_at), provider-edge outbound idempotency, email-verification /
password-reset auth_artifact types, a sharper inbound-media contract
(agent-visible typed reference + observable unsupported-processing), language as a
non-authoritative hint, and explicit channel_identity ownership. Then
architect-review round 6: type-specific calendar action handles (no direct edit on
shared reminders), subscription page/renewal in the web list, notification `status`
fact, and idempotent shared-reminder cancellation. Then architect-review round 7:
version-gated interactive commits (based_on_inbound_seq as an expected-version
precondition at commit, not just before the reply) and available_participants in
the shared-reminder failure result. Then architect-review round 8: participant-scoped
shared-reminder view/cancel, shared-reminder required-field follow-up states, and
the nightly summary bound to the owner's global timezone. Then architect-review
round 9 (no HIGH/MEDIUM remained): added Reminder-domain calendar-page command
endpoints for page-based create/schedule/edit)
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
machine. Every **chat/channel-visible product message** — assistant replies,
reminder text, notifications, access-denial, and system-recovery prose — has
exactly one producer: the Interaction Agent. (Static web/support pages, e.g. FAQ /
privacy / terms, and UI labels are ordinary product copy, outside this invariant.)
The backend exists only to do five things — hold a trust / identity boundary,
persist durable domain state, schedule time-based work, run the agent, and adapt
to channels.

The central insight of this rebuild: **work enters the agent in only a small,
fixed set of ways, and they all have the same shape** — *something becomes true
in the world → it must reach the user as prose → the agent renders it.* There are
seven trigger types, and only two execution modes:

| Turn trigger | Source | Mode |
|---|---|---|
| `InboundTurn` | channel webhook → durable message → bus | Interactive (full tools) |
| `ReminderFireTurn` — **grouped by `(owner, due_at)`**, ordered fire-id set (timed / recurring occurrence / shared projection) | scheduler | Render |
| `ProactiveFireTurn` | scheduler | Render, **discard on delivery failure** |
| `NightlySummaryTurn` (20:00 owner-timezone, no-trigger-time reminders) | scheduler | Render |
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
                                         | failed | superseded, + reason)
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
| `account` | The Coke user identity. `origin ∈ {web_first, messaging_first}`, one global default timezone. |
| `agent_settings` | User-controlled, customer-scoped assistant configuration: assistant name, how it addresses the user, persona, background, speaking style, extra rules, **proactive switch**, **memory switch**. Reset restores defaults. These are durable user settings and are **not** gated by the memory switch (§5.11). |
| `user_profile` | User-controlled personalization: real name / nickname / description and relationship description (§3 of requirements). Distinct from *inferred* long-term memory (§11) — preferences, boundaries, disturbance willingness, role goals/attitude — which is gated by the memory switch. |
| `account_activation` | Derived activation projection: `first_inbound_received_at`, `activation_completed_at`, `first_guidance_sent_at`. Onboarding completes only when identity is bound, a usable channel exists, and the first inbound is received (§5.2); first-conversation guidance is injected exactly once, tracked by `first_guidance_sent_at` (§5.4). Owned by IdentityAccess, computed from reachability + conversation signals. |
| `account_access` | Access state used as a **product gate**: email-verification state, subscription/access state, suspension state, and the derived `access_allowed` + denial reason. No order/usage/quota metering (§15). |
| `credential` | Web-first only: email + password hash (+ forgot/reset). Messaging-first accounts have no credential; their only web auth path is a one-time claim. |
| `session` | Web session / token. |
| `channel_identity` | A provider-side identity (e.g. a WhatsApp sender address) mapped to exactly one `account`. For messaging-first accounts this is the **account anchor**; it is created atomically with the account on first contact and is non-removable while it is the account's only identity. |
| `auth_artifact` | **Unified** one-time authentication artifact: `type ∈ {login_url, claim_code, pairing_code, email_verification, password_reset}`, `purpose`, `delivery` (in-conversation / web / **email**), `expires_at`, `consumed_at`, and resend tracking. `email_verification` and `password_reset` are the email-delivered web-first artifacts behind §5.1 (verify email, resend verification, forgot/reset password); they are bound to the issuing account, one-time, time-limited, resendable, with observable delivery state. The account binding differs by type: `login_url` and `pairing_code` are bound to the issuing account at issuance; `claim_code` is issued from an **unauthenticated browser** with **no account yet** — it carries a `browser_session` binding and its `target_account` is **resolved at redemption** (the sender's `channel_identity` determines the account). An optional `continuation` payload (e.g. `friend_link_id`, `calendar_import_run_id`) preserves handoff context across the claim. One-time, time-limited; once redeemed it authenticates/binds exactly one account and is never reusable for another. |

Identity rules (from §5.13): auto-provisioning applies **only** to shared
WhatsApp; a first-seen sender identity provisions a new messaging-first account, a
known sender continues as its existing account. The system never merges or
unlinks accounts and never guesses identity from display name / profile
similarity. Claiming is bidirectional and runs entirely on `auth_artifact`:
- **Chat-initiated `login_url`** — the assistant issues a one-time URL in
  conversation (account known from the conversation); opening it authenticates the
  web session as that account.
- **Web-initiated `claim_code`** — an unauthenticated web page (e.g. a friend link
  or calendar import) issues a code bound to the browser session, account unknown;
  when a messaging user sends the code, the sender's `channel_identity` resolves
  the account and the browser session authenticates as that account, landing back
  in the `continuation` context.
- **`pairing_code`** — during a web-first user's channel-connection flow, an
  inbound carrying a valid pairing code binds that `channel_identity` to the
  issuing account instead of auto-provisioning.

### 3.2 Channel Reachability

Owns: the single-channel-per-account rule, channel lifecycle, the delivery route,
and outbound send-attempt outcomes. Realizes §5.3 and the channel parts of §5.12.
This is the "can we reach this user, and did a send land" module — distinct from
the conversation runtime that decides what to say.

Ownership boundary with IdentityAccess: the `channel_identity` table — the
identity↔account mapping, including auto-provisioning, pairing-code binding, and
anchor protection — is owned by **IdentityAccess** (§3.1). ChannelReachability owns
the `channel`/`delivery_route`/`delivery_attempt` lifecycle and **consults**
IdentityAccess (via its domain service) for the anchor constraint before allowing
a channel removal; it never writes `channel_identity` itself.

| Table | Purpose / invariant |
|---|---|
| `channel` | The account's reachable personal channel. `provider_type`, connection state (`not_connected | connecting | connected | connection_failed | reconnection_required`, matching the user-visible recovery states in §5.3), bound `channel_identity`. **Cardinality ≤ 1 active per account.** A messaging-first account's anchor channel is non-removable; a web-first user may remove/switch (remove old first). "Connected" means deliverable, not "upstream step succeeded". |
| `delivery_route` | The resolved, stable send target (provider + address) derived from `channel` + `channel_identity`. Reminders, shared-reminder projections, and notifications target a route, not channel internals. May be denormalized onto `channel`, but is modeled explicitly so delivery has one canonical target. |
| `delivery_attempt` | Per-outbound send-attempt outcome (`sent | delivered | failed`) — the raw delivery evidence from which output-class-specific delivery state (§3.4 undelivered, proactive discard, per-projection, per-recipient) is computed. A failed/absent send is never "delivered". |

### 3.3 Conversation Runtime

Owns: the inbound turn ledger, conversation ordering / stale-reply suppression,
the agent-orchestration handle, and the final output disposition. Realizes §5.4
and the conversation parts of §5.9.

| Table | Purpose / invariant |
|---|---|
| `conversation` | The ongoing agent conversation for an account; stable identifier for locks and ordering. Carries a **durable monotonic `latest_inbound_seq`** — the ordering invariant that makes stale-reply safety concrete, not just lock-implied. |
| `message` | Inbound + outbound messages. Inbound: normalized payload, sender `channel_identity`, `causal_inbound_event_id`, and a per-conversation `seq`. Outbound: rendered text, 1–3 segments, link to disposition + (optional) `notification_id` + `facts_hash`. |
| `inbound_media` | Multimodal inbound (image/voice/etc.) preserved as **processable input** — reference/blob only. No understanding model, no media generation, no media reply (§10). |
| `turn` + `output_disposition` | One row per turn, **keyed by a stable `trigger_id`** (unique per trigger source — inbound message, reminder fire, notification event, …) so replay reconciles the existing turn instead of creating a new one: trigger type, mode, timing, the `based_on_inbound_seq` it acted on, and exactly one **turn disposition** (`replied | no_reply | pending_async_reply | failed | superseded`) + small reason code. The audit spine of the runtime and the replay-idempotency anchor. Turn disposition is the turn outcome; per-target *delivery* state is output-class-specific (§4). |
| `outbox` | Single shared transactional outbox; any producer appends in the same transaction as its domain write (§5). Listed here as the runtime's durable event ledger; it is shared infrastructure, not owned business state. |

### 3.4 Reminder

Owns: temporal reminder execution. Realizes §5.5, §5.8, and reminder reachability
in §5.3.

| Table | Purpose / invariant |
|---|---|
| `reminder` | `owner`, `content`, `kind ∈ {timed, no_trigger_time, recurring, proactive, shared_projection}`, `next_fire_at` (nullable for no-trigger-time), recurrence rule, **`captured_timezone`** (pinned at create/last-edit; recurrence windows expand in this tz, see §8), `duration` (default 15 min), **series-level** lifecycle (`active | completed | deleted`). Completion is terminal for one-time and no-trigger-time reminders; for a recurring series, completing an occurrence leaves the series `active` and advances the next trigger, while deletion removes the whole series (§5.8). Per-occurrence delivery and handled state live on `reminder_fire`, not here. The durable delivery target is the **owner account**, never a captured route: the usable `delivery_route` is resolved at fire/resend time so a relink to a new channel is honored (§5.3/§5.8). `proactive` reminders are hidden from the calendar and user-immutable. `shared_projection` reminders link to a `shared_reminder` (§3.5). |
| `reminder_fire` | **Occurrence-grain** record (one per fired/expected occurrence): occurrence key, due time, compare-and-set fire state (atomic, idempotent, replay-safe), per-occurrence delivery result (`delivered | undelivered`), user `completed`/`handled` state, and a **missed/catch-up marker** for triggers missed while the system was down. The next valid trigger advances after this occurrence fires or is completed; an undelivered occurrence already handled on the calendar is not resent (§8). This occurrence + delivery state is separate from the series-level `reminder.lifecycle` and from the turn disposition (§4); the route actually used is snapshotted on `delivery_attempt` (§3.2), not here. |

Duplicate prevention is a unique constraint, not a heuristic: same owner + same
content + same trigger time (or same owner + same content + both no-trigger-time)
is rejected. Duration, entry point, and phrasing are not part of the key.

One inbound message may carry several reminder operations (§5.8 batch). The domain
exposes a **batch command contract**: each item is resolved (ReferenceResolver,
§4) and committed independently, with its own result state, so partial success is
the normal case — an ambiguous or failed item isolates to itself and never blocks
clearly-resolved items. The Interaction Agent receives itemized result facts
(succeeded / needs-follow-up / failed) and renders one confirmation that reflects
the true per-item outcome; it never claims a batch fully succeeded when some items
did not.

### 3.5 Social Scheduling

Owns: relationship-based scheduling. Realizes §5.6, §5.7, §5.9.

| Table | Purpose / invariant |
|---|---|
| `friend_link` | Owner's public link + QR + link code; state `active | disabled`; reset rotates the token. Reset/disable affect only future new friendships. |
| `friendship` | Per unordered pair, lifecycle `active | removed`. **Uniqueness is on the active relationship only**, so a removed pair can re-establish through a valid link/code. Established directly (no pending request); self-friendship forbidden; establishment requires both sides authenticated/claimed **and** holding a usable channel — a joiner who authenticates/claims without a usable channel has establishment **deferred** (intent carried on the handoff `continuation`, §3.1), not dropped, and completes automatically on channel connect (§9). Removal flips to `removed`: it drops the pair from active friend lists and blocks new shared reminders, but does not cancel existing shared reminders and does not delete accounts or reminders (§5.6/§5.12). |
| `shared_reminder` | Group reminder: creator + participant set, title, trigger time, `captured_timezone`, duration, status (`active | cancelled`). Uniqueness key: creator + participant set + title + local trigger time + timezone + duration (order-insensitive). |
| `reminder_projection` | Per-participant projection (a `kind=shared_projection` `reminder` row). Completion affects only that participant's projection; cancellation by any participant stops all projections. |
| `notification_fact` | Immutable structured facts (who/what/object/time/timezone/duration/**status**, §5.9) + `facts_hash` (covering `status`) + idempotency key + outbox evidence. **No `payload.text`** — final chat prose is never stored here (§5). One fact can fan out to many recipients (friendship pair, shared-reminder participants). |
| `notification_recipient` | Per-recipient delivery row keyed by `notification_fact` + recipient account + render turn + delivery state, plus user-safe error facts. A multi-recipient notification can be `delivered` to some and `undelivered`/`failed` to others; partial failure is recorded here, not collapsed into one fact lifecycle. This is the notification-class delivery state layered on the turn disposition (§4). |

Availability queries read each friend's personal + shared reminders and return
**privacy-safe busy/free only**, never reminder details. Receiver conflict and
participant channel availability are **hard pre-creation constraints**; the
creator's own conflict is intentionally not checked.

### 3.6 Calendar Import

A first-class supporting module over Reminder, not a placeholder — its Google
authorization handoff and dedupe rules are product-specific and need their own
contract. Realizes §5.10; retained, one-time import. `calendar_import_run` records
the Google auth handle and result counts (imported / skipped / downgraded /
failed). `calendar_import_run` aggregates counts, but those counts are **derived
from** `calendar_import_item`, which covers **every considered source occurrence**
— not only imported ones — at occurrence grain: keyed by (provider calendar id,
source event id, recurrence-instance / original start), with a `status ∈ {imported,
skipped_duplicate, downgraded, failed, historical_skipped}`, source metadata,
linked reminder id(s), and a user-safe reason. This is what lets the result
summary list downgraded items **and** failed items (§5.10), not just totals, and
makes occurrence-grain dedupe exact: a recurring event downgraded into several
one-time future occurrences neither double-imports nor over-skips on repeat, and
repeated imports skip already-present items silently without user confirmation.
Imported events become owner-scoped Coke `reminder` rows
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
| Identity, access, agent settings, user profile, activation, credential, session, channel identity, auth artifacts | **Postgres** |
| Channel, delivery route, delivery attempts | **Postgres** |
| Conversation, message, inbound media, turn/disposition | **Postgres** |
| Reminder runtime (reminders + fire/replay evidence) | **Postgres** |
| Social Scheduling (links, friendships, shared reminders, projections, notification facts + per-recipient rows) | **Postgres** |
| Calendar import runs + per-occurrence import items | **Postgres** |
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
  reply / claim), and a **non-authoritative `language_hint`** — final reply
  language is the Interaction Agent's, identified from the user's language (§5.4),
  not a fixed interpreter decision or settings field. If it classifies the turn as
  intentional
  no-reply, the runtime records `no_reply` and **skips the expensive Interaction
  Agent entirely**. This keeps intentional no-reply cheap and separately
  evaluable, and keeps it distinguishable from empty-output failure.
- **Focus** — resolve the actionable subject of the last rendered message. Because
  reminder render turns merge same-time, undelivered, and nightly-summary
  reminders into one message (§8), the subject is **a single object or an ordered
  set**, backed by a durable `message_subject` recorded on the render turn (the
  ordered reminder/fire ids it rendered). This is what lets "done" complete every
  reminder in that grouped message and "all of these are done" complete the whole
  summary set (§5.8). It is still not multi-candidate disambiguation (that is
  ReferenceResolver) and carries no pending accept/reject.
- **ReferenceResolver** — resolve each user reference to a concrete target before
  acting on *that* reference. Deleting `multi_candidate` focus state (§15) does not
  delete the need to disambiguate: duplicate friend names (§5.6), ambiguous
  shared-reminder cancellation (§5.7), and ambiguous reminder matching (§5.8) all
  require clarification. The rule is **per-reference**: resolve a reference to
  exactly one active target; on zero or multiple candidates for that reference, ask
  a clarifying follow-up and **mutate nothing for that reference** until confirmed.
  Crucially, this is per-item, not per-turn — an ambiguous item never blocks other
  clearly-resolved items in the same turn (§5.8 batch rule). Distinct from Focus
  (the current subject) and from any stored pending-workflow surface.
- **Freshness** — stale-reply safety with a concrete durable invariant, not just
  lock intuition. Each inbound gets a per-conversation `seq`; the conversation
  tracks `latest_inbound_seq`; a turn records the `based_on_inbound_seq` it acted
  on (§3.3). Before an outbound is inserted/delivered, it compare-and-sets against
  the current `latest_inbound_seq` — if a newer inbound has superseded this turn,
  the stale reply is suppressed and the turn resolves to the distinct
  **`superseded`** disposition (never `no_reply`, which is reserved for intentional
  no-reply, and never `failed`, which implies retry/operator attention). Crucially
  this is **not only an outbound check**: for interactive turns, `based_on_inbound_seq`
  is an **expected-version precondition on every state-changing domain commit**
  (reminder/friendship/shared-reminder create/edit/delete), checked atomically at
  commit, not just before send. If a newer inbound has superseded the turn, the
  commit is rejected — no business mutation is applied and no operation facts are
  emitted — and the turn records `superseded`. So a stale, lock-lost, or late-async
  turn cannot *act* on outdated intent, not merely fail to reply about it (§3
  conversation ordering, §5.4). This is consistent with the no-rollback rule (§5):
  facts that *did* commit before supersession stay true; supersession only blocks
  the not-yet-committed stale action.
- **Memory** — short-term recent context (always available, even when the memory
  switch is off, because it is needed to complete the current turn) plus
  long-term memory via Agno memory storage/retrieval. A custom `MemoryManager`
  owns extraction/injection policy and is gated by the memory switch; Agno's
  automatic user-memory extraction is left off. Short-term and long-term memory
  are one merged subsystem, not two specs.

**Activation / onboarding** is owned by the `account_activation` projection
(§3.1), not scattered across handlers. The pre-LLM gate consults it: onboarding is
complete only when identity is bound, a usable channel exists, and the first
inbound is received (§5.2). On the first conversation, context assembly injects
first-use guidance exactly once and stamps `first_guidance_sent_at`, so guidance
is never re-injected on later turns (§5.4).

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
contract on the **first** returned answer. `no_reply` is reserved for **explicit
intentional no-reply only** (the interpreter or agent deliberately deciding the
message warrants no message). Empty output, malformed/invalid output, structurally
blocked output, and timeout-after-budget are **not** `no_reply` — they record
`failed` with a structured reason code, because §5.4 requires intentional no-reply
to be distinguishable from empty-output exception, tool-fallback failure, and
system failure. The runtime does not ask the model to rewrite, does not convert
trusted facts into replacement prose, and does not send template fallback text.

**The waiting text is the one runtime-owned typed message, and it is not
optional.** When synchronous processing times out while the agent is still
working, the runtime emits a visible waiting text, records `pending_async_reply`,
and delivers the final agent reply asynchronously. This is a required product
contract (§5.4), not a fallback: the waiting text is a typed delivery-status
signal carrying no intent result and no assistant content, so it does not violate
"only the Interaction Agent writes chat prose" (it is not prose *about the user's
request*) and it is explicitly exempt from the no-fallback-prose rule. It is the
only such exception. `pending_async_reply` is the **only non-terminal**
disposition: when the async work finishes, the turn **transitions**
`pending_async_reply → replied` (the final outbound and its delivery evidence are
linked to the same turn) or `→ failed`. Empty output and protocol violations are
not waiting-text cases — they go straight to `failed` with no substitute text.

**Turn disposition vs delivery state — two layers.** The five-state
`output_disposition` (§3.3) records the *turn outcome* — was a reply produced
(`replied`), was it intentional no-reply (`no_reply`), did it time out to async
(`pending_async_reply`), did it fail and need retry/attention (`failed`), or was it
suppressed because newer intent superseded it (`superseded`). It is deliberately
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
- **Outbox is the source of truth; Redis is only a wake signal.** An `outbox` row
  is not retired when the relay publishes — it transitions to `processed` only on a
  durable worker ack. The relay replays unacked rows idempotently (dedup by
  outbox/event id). So losing the Redis Stream on restart triggers replay from the
  outbox, never stranded work; "losing Redis is acceptable" means losing the
  *signal*, not the durable rows behind it.
- **Worker-turn idempotency:** replay must not duplicate user-visible work. The
  turn is keyed by `trigger_id`; on replay the worker **resumes/reconciles** the
  existing turn rather than re-invoking the agent once facts or output already
  exist. Domain commands are idempotent by `turn_id + item_index`, and outbound
  messages are unique by `turn_id + segment_index`, so a crash between a domain
  commit / outbound insert and the worker ack cannot create a second reminder, a
  duplicate notification, or a duplicate chat segment. Freshness
  (`latest_inbound_seq`) handles *newer-intent* staleness; this handles
  *same-trigger* replay.
- **Outbound-delivery idempotency at the provider edge.** Persisted-row uniqueness
  (`turn_id + segment_index`) only dedups DB rows; it does not stop a re-send to the
  external provider after a crash between the provider call and the worker ack. So
  each outbound carries a **provider idempotency key**, and the egress step takes a
  short send-lease and checks `delivery_attempt` (§3.2) state before calling the
  provider — replay either rides the provider's own idempotent dedup or skips an
  already-`delivered`/in-flight send rather than double-delivering to the channel.
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
  Conversely, an interactive commit is **version-gated** by `based_on_inbound_seq`
  (§4 Freshness): a turn superseded by newer intent does not commit at all.
  No-rollback governs facts that already committed; it never licenses a stale turn
  to commit outdated intent.
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
- **Fire is atomic, idempotent, replay-safe** (compare-and-set per fire state), but
  the fire *turn* is **grouped, not per-reminder**: due fires are collected into a
  single `ReminderFireTurn` keyed by `(owner, due_at)` carrying the ordered set of
  due fire ids. One turn → one merged role-toned message through the user's one
  usable channel; per-fire lifecycle/delivery is updated individually. Keying by
  `(owner, due_at)` makes `trigger_id`, the rendered message, and outbound
  uniqueness (§5) deterministic, so the same-time merge cannot double-send.
- **Recurrence timezone pinning.** Recurring windows expand using the reminder's
  `captured_timezone` (set at create/last-edit), not the user's current global
  timezone. A global timezone switch changes display and the timezone applied to
  *newly created* reminders only; it never recomputes existing reminders' trigger
  moments or recurrence windows. Recurrence supports hourly→yearly and custom
  intervals (minimum hourly); sub-daily recurrence is bounded by a time window
  (default 08:00–23:00). After each fire/completion the next valid trigger is
  advanced atomically.
- **No-trigger-time reminders + nightly summary.** Reminders with no trigger time
  are first-class. A per-owner `NightlySummaryTurn` fires at **20:00 in the owner's
  current global default timezone** (recalculated after a timezone switch, §5.5),
  summarizes them, and asks whether to schedule times.
- **Same-owner same-time merge.** The grouped `(owner, due_at)` fire turn renders
  all due reminders into one message (its ordered fire-id set is the Focus subject
  set, §4); each reminder and its fire evidence stay independent, and "done"
  completes the whole rendered set.
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
- **Time validation is a domain invariant, not generic schedule parsing.** Per
  batch item, before commit, the Reminder domain classifies the requested time as
  `valid_future`, `needs_past_time_confirmation` (a clear but past time is not
  silently created), `needs_incomplete_date_clarification` (an incomplete date
  whose today-target already passed is not auto-shifted), or `invalid`. Past times
  are never rewritten into the future without Interaction-Agent confirmation; the
  confirmation/follow-up fact is routed back to the agent (§5.8).
- **Trigger-time ↔ no-trigger-time conversion** is explicit domain state, not an
  ad-hoc edit: `schedule_unscheduled` (no-trigger → timed, moves onto the
  calendar), `clear_trigger_time` (one-time → unscheduled, into the 20:00 summary
  set), and for a recurring series whose rule can no longer hold after clearing,
  a confirm step offering `convert_to_unscheduled` or `delete_recurring_series`.
  Conversion preserves content/owner/source and emits a confirmation fact (§5.8).
- **The reminder calendar is a domain read model, not client logic.** A
  `ReminderCalendarReadModel` query (Reminder domain) returns typed entries —
  one-time, recurring-occurrence-in-visible-range, shared projection (with friend
  identifiers), unscheduled, undelivered, and merged groups that expand into
  per-entry actions — with display times in the user's global timezone (§5.8).
  **Action handles are type-specific:** a personal reminder exposes
  edit / complete / delete. For a **recurring-occurrence** entry opened on the
  calendar these handles are series-vs-occurrence grained per §5.8: complete acts
  on **this occurrence** (the series advances), while edit and delete act on the
  **whole series** — there is no edit-one-occurrence or per-occurrence delete
  (§3.4, §5.8). A `shared_projection` exposes only
  complete-own-projection and cancel-whole-shared-reminder — shared reminders are
  **not directly editable** (changing time/content = cancel the group and recreate,
  §5.7). The thin web client renders this read model; it does not re-derive
  reminder state.
- **Calendar-page commands are Reminder-domain endpoints too**, not client logic:
  create a timed reminder from a selected calendar slot (the slot defaults the
  trigger time), create an unscheduled reminder, schedule an unscheduled reminder,
  and edit an ordinary personal reminder's content / trigger / recurrence /
  duration — all reusing the one Reminder domain and its time-validation,
  conversion, and duplicate rules. The shared-reminder no-direct-edit boundary
  still holds: the page may create or cancel a shared reminder but never edits one
  in place (§5.8).

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
  When a friend-link visitor authenticates/claims but does **not yet** hold a
  usable channel, the channel gate defers — not drops — the establishment: the
  friend-link intent (the `friend_link_id` carried on the handoff `continuation`,
  §3.1) persists, and the friendship is established automatically once that joiner
  connects a usable channel (§5.6 step 6). This is a deferred *self-completion*
  gated on the joiner's channel readiness, **not** a pending owner-approval
  request (which §15 deletes) and **not** a silently abandoned link. Friend-link
  reset/disable affect only future new friendships. Establishment is
  idempotent; the same pair never creates a duplicate active friendship;
  self-friendship is forbidden. **Remove-friend** is a domain command that flips
  the friendship to `removed`: the pair leaves both active friend lists and can no
  longer create new shared reminders, but existing shared reminders are not
  cancelled and no accounts or reminders are deleted (§5.6/§5.12); the pair may
  later re-establish an active friendship through a still-valid link or code.
- **Shared reminders** are one group reminder (creator + receivers), not split
  pairwise. Creation first validates required fields — at least one participant,
  title/activity content, trigger time, and any necessary context — returning
  `needs_participants | needs_title | needs_time | needs_context` states that
  mutate nothing and hand follow-up facts to the Interaction Agent before any
  other check (§5.7). It then resolves each receiver to a unique active friend
  (ambiguity → follow-up), then enforces two hard pre-creation constraints —
  receiver conflict
  (overlap on duration window, from personal + shared reminders) and participant
  channel availability (creator + every receiver reachable). The creator's own
  conflict is not checked. Failing either creates nothing partial and returns the
  privacy-safe breakdown — `conflicting_participants`, `unreachable_participants`,
  **and `available_participants`** — so the creator is told who conflicts, who is
  unreachable, *and who is free*, then asked to adjust time or participants (§5.7).
  On success the reminder is immediately
  active with a per-participant projection; uniqueness is enforced by the §3.5
  key. Shared reminders are **participant-scoped**: list/view and
  `cancel_shared_reminder` require the requester to be a participant — a
  non-participant can neither view nor cancel (§5.7), checked before any
  status/idempotency handling. Any participant cancels the whole group:
  `cancel_shared_reminder` is
  status-aware/idempotent — `active → cancelled` stops all projections and emits
  cancellation facts to the others, while `cancelled → cancelled` returns a
  user-safe already-cancelled result and emits no duplicate cancellation (§5.7).
  Completion affects only one's own projection.
- **Availability** is a bounded domain query, `AvailabilityQuery(friend_ids,
  local_date_range, requester_timezone)`: it resolves one or more **active**
  friends (authorize the friendship), expands each friend's personal + shared
  reminder intervals **within the bounded date range** in the requester's global
  timezone, and returns **only coarse busy/free** — never reminder details, never
  Google Calendar (§5.7).
- **Notifications** are informational facts only (never approval/execution),
  covering friendship creation and shared-reminder creation/cancellation and their
  error/partial-failure/undelivered/conflict cases. One `notification_fact` fans
  out to many recipients via `notification_recipient` rows (§3.5), so a multi-party
  notification can land for some participants and fail/undeliver for others; the
  per-recipient partial failure is real state, rendered to the initiator as a
  user-safe error fact, not collapsed away. Facts carry who/what/object/time/
  timezone/duration **and status** (§5.9); errors map channel failures into product
  language and never expose raw channel errors, internal codes, queue status, or
  delivery attempts. Final visible text is the Interaction Agent rendering the
  facts (§5).

## 10. Multimodal Input Handling

Inbound media (image, voice, and other channel-carried content) is **received and
preserved** — normalized and stored as `inbound_media` references/blobs linked to
the message (§5.4, §3). "Processable input" here means two concrete guarantees, not
hidden bytes: (1) the media is durably captured and never silently dropped, and
(2) the Interaction Agent receives an **agent-visible typed reference** for it
(e.g. "[image]", "[voice message]") so it knows media arrived and can respond about
it. The current contract does **not** add an image-understanding model, speech
transcription, media generation, or media replies (this is the round-1 decision:
preserve, don't understand/generate). Output is text-only. When a user's intent
depends on media content the system cannot interpret, that is an **observable
unsupported-processing outcome** surfaced to the user, not a silent loss. Image
generation, photo album, Moments, and voice ASR/TTS remain out of scope (§16).

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

Ownership boundary for personalization: user-controlled, user-visible
configuration (`agent_settings`, `user_profile` — §3.1) is durable structured
state and is **not** gated by the memory switch. *Inferred* facts — preferences,
relationship nuance, boundaries, disturbance willingness, role goals/attitude —
live in long-term memory and **are** gated by the memory switch (off = no use /
add / update, existing memory retained; §5.11). The MemoryManager only governs the
inferred-memory layer, never the explicit settings.

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

The Next.js web app remains a thin client over the Python API; it repoints and
de-brands its package scope. "Thin client" means the business logic moves to the
Python domains, **not** that product pages are dropped. It retains/rebuilds every
web surface the requirements name, all over the Python API:

- registration / login / email-verification / account-access-status and the
  **subscription page** (subscription/access status + the renewal/checkout next
  step) and the web-claim surfaces — one-time `claim_code` entry, login-URL
  landing (§5.1, §5.13);
- channel management (§5.3);
- reminder calendar page (§5.8);
- friends page with friend link + QR (§5.6);
- shared-reminder list with cancel (§5.7);
- agent settings (§5.11);
- calendar import (§5.10);
- public explanation / FAQ / demo / privacy / terms pages (§5.1).

Only auth hardening and the admin/customer surface split are shelved as
follow-ups; no required product page is out of scope.

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
- **Exactly one prose producer**: only the Interaction Agent writes
  chat/channel-visible product-message prose (assistant, reminder, notification,
  access-denial, system-recovery), across all seven turn types. Static web/support
  pages and UI labels are out of scope. The runtime-owned synchronous-timeout
  waiting text is the sole typed-signal exception and carries no intent result
  (§4).
- **Exactly one current disposition per turn**: `replied | no_reply |
  pending_async_reply | failed | superseded` + reason. `pending_async_reply` is the
  only non-terminal disposition and resolves to `replied | failed`, with the final
  async outbound linked to the same turn. The five are kept distinct on purpose:
  intentional `no_reply` ≠ empty-output/system `failed` ≠ newer-intent
  `superseded`.
- **Disposition and delivery state are separate layers**: the turn disposition is
  the turn outcome; per-target delivery (reminder undelivered, proactive discard,
  per-projection, per-recipient notification facts) is output-class-specific and
  never collapsed into one generic failure bucket (§4).
- **Reminder lifecycle** is atomic, idempotent, replay-safe; series lifecycle is
  distinct from occurrence/fire lifecycle (recurring completion is per-occurrence,
  series advances; delete removes the series); missed triggers are caught up
  (personal + shared); proactive is discarded on failure; recurrence windows are
  timezone-pinned and never silently recomputed.
- **Trust boundary** requires a coherent identity tuple before any enqueue
  (anti-corruption layer).
- **Social Scheduling writes** are transactional with idempotency via unique
  constraints and deterministic ids; friendship uniqueness is on the active
  relationship (removal never cascades to shared reminders or accounts, and a
  removed pair can re-establish); shared-reminder projection consistency holds.
- **Lock release** verifies ownership and never releases another worker's lock.
- **Replay idempotency**: turns are keyed by `trigger_id`, domain commands by
  `turn_id + item_index`, outbound by `turn_id + segment_index`; same-trigger
  replay reconciles the existing turn and never duplicates user-visible work.
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
  `fallback` are deleted. The five dispositions of §4 are the only ones
  (`replied | no_reply | pending_async_reply | failed | superseded`); committed
  facts are durable.
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
- Web changes beyond repointing the existing required product surfaces to the
  Python API and de-branding (auth hardening, admin/customer split — §13). No
  required product page is dropped.
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
  from output-class-specific delivery state — `reminder_fire` (undelivered/catch-up),
  proactive discard, per-projection shared delivery, and `notification_recipient`
  per-recipient rows. The waiting text is the sole runtime-owned typed-message
  exception to single-prose-producer. `no_reply` is reserved for intentional
  no-reply only; empty/malformed/blocked/timeout-after-budget → `failed`.
- **Reminders target the owner account, not a captured route**: the usable
  `delivery_route` is resolved at fire/resend time so relink-to-new-channel is
  honored; the route used is snapshotted on `delivery_attempt`.
- **Grouped-message subject + batch commands**: Focus carries the ordered
  subject-set of the last rendered (merged) message so "done" / "all done" act on
  the whole set; multi-op reminder turns use a per-item batch contract where an
  ambiguous/failed item isolates to itself.
- **auth_artifact handles deferred binding**: `claim_code` is issued to a browser
  session with no account and resolves the account at redemption; `login_url` /
  `pairing_code` bind the issuing account; all carry an optional handoff
  `continuation`.
- **Durable ordering + outbox-as-truth**: per-conversation `seq` +
  `latest_inbound_seq` make stale-reply suppression a compare-and-set invariant;
  outbox rows are retired only on durable worker ack with idempotent replay, so
  Redis loss never strands work.
- **Occurrence-grain calendar dedupe** via `calendar_import_item`.
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
