# ClawScale Platformization Design

Date: 2026-04-15

## Supersedes

This spec supersedes parts of
`2026-04-10-gateway-auth-email-stripe-design.md` **in full** with respect
to identity/auth ownership:

- Where the 2026-04-10 doc keeps Coke as the owner of `/api/coke/*`
  auth/payment routes, `CokeAccount.id` as the session subject, and
  Mailgun/SMTP-from-Coke email delivery, this spec instead moves auth
  and email to ClawScale-neutral surfaces and positions the Resend
  migration as a ClawScale-owned email capability (see per-plan verdicts
  in "Current-state Gaps #6"). Plan authors MUST follow the 2026-04-15
  spec on identity/auth/email and treat the 2026-04-10 doc as
  historical background only.
- Payment-specific business logic in the 2026-04-10 doc that is
  genuinely Coke-scoped (e.g. Coke subscription tiers) continues to
  apply to the Coke agent partition, subject to relocation under a
  clear Coke namespace (not under generic `coke-*` auth routes).

This spec also supersedes parts of
`2026-04-08-coke-business-only-clawscale-channel-only-design.md`:

- Identity, account, tenant, and member modeling: **superseded** here.
  `ClawscaleUser`, the ad-hoc `Tenant`, `Member`, and the `coke_account_id`
  binding are retired. The new source of truth is Identity + Customer +
  Membership in this document.
- Cross-boundary identifier naming: **superseded**. `account_id` as the
  wire identifier is replaced by `customer_id`.
- Auth ownership: **superseded**. Coke no longer owns auth.

Routing and delivery semantics carried forward unchanged from the
2026-04-08 spec, only with identifier renamed:

- `business_conversation_key` generation, lifetime, and the one-peer-at-
  a-time invariant
- `DeliveryRoute` as the durable resolver for
  `(customer_id, business_conversation_key) -> (channel_id, end_user_id)`
- `OutboundDelivery` idempotency and retry window
- `EndUser` as channel-local peer identity
- `ChannelSession` as live session material
- the channel replacement-via-archive lifecycle
- the inbound/outbound message contract (fields, attachments)

Plan authors must treat this document as authoritative for identity and
auth, and the 2026-04-08 document as the continuing reference for
routing, delivery, and attachment semantics.

## Scope

This document redefines ClawScale as an independent SaaS platform whose job is
to connect AI agents to end-user channels. Coke stops being the only product
and becomes the first agent served by the platform. The design covers:

- product positioning and roles
- identity, tenant, and membership model
- agent and channel ownership
- storage and runtime boundaries between ClawScale and agents
- Coke-side account shutdown and naming compatibility
- admin backend MVP
- current-state gaps and the shape of the follow-up refactors

It does not cover: billing detail, organization-tier features beyond data
model readiness, full agent protocol formalization (deferred to Phase 1.5),
or any migration of Coke business data away from MongoDB.

## Positioning

ClawScale is a standalone multi-channel access platform for AI agents.

- ClawScale owns identity, customers, channels, delivery, and agent routing.
- Agents (currently Coke) own their own business data and are plugged into
  ClawScale through a normalized HTTP message contract.
- Coke is positioned as one agent among potential future agents, not as a
  product that happens to use ClawScale as a backend.

### Two onboarding modes (both first-class)

ClawScale must support **both** onboarding modes concurrently. Plan authors
must not assume the self-service mode is the only path.

1. **Self-service (customer-owned channel).** Customer registers at
   `/auth/register`, is auto-assigned the default agent, and binds their
   own channel (e.g. personal WeChat QR flow). Every channel has an
   explicit `customer_id` owner. This is the path already described in
   the rest of this spec and is what Phase 1 Coke uses today.
2. **Inbound-triggered (shared ingress channel).** A single shared
   official account (e.g. shared iMessage account, WhatsApp Business
   number) receives inbound traffic from many external senders. The
   first message from a previously-unseen sender auto-provisions an
   internal Identity + Customer + AgentBinding + ExternalIdentity
   mapping, with no prior visit to the ClawScale frontend. Subsequent
   messages from the same sender hit the same customer and route.
   Outbound replies go back through the same shared account.

Both modes must work in one deployment. A customer created via mode 2 may
later "claim" their account by completing self-service credentials (see
"Identity claim lifecycle" below).

## Roles

| Role | Who | Surface |
|---|---|---|
| Platform admin | ClawScale internal staff | Internal admin console; no public sign-up |
| Customer | Self-service natural person today; organization later | Public customer frontend |
| End peer | The contact reached through a customer's channel (e.g. a WeChat friend) | No ClawScale login |

Phase 1 constraints:

- one agent per customer, assigned automatically at registration from an admin-configured default
- one channel per kind per customer (Phase 1 supports `wechat_personal` only; Phase 1.5 adds more kinds)
- customers are natural persons; the data model supports organizations, but
  no organization-facing UI is built yet
- **only the self-service (customer-owned channel) onboarding mode is
  live in Phase 1.** The inbound-triggered / shared-channel mode
  described in "Two onboarding modes" is **Phase 1.5 scope**. The
  data model changes that support it (`Identity.claim_status`,
  `Channel.ownership_kind`, nullable `Channel.customer_id`,
  `Channel.agent_id`, `ExternalIdentity`) land in the same Phase 1
  schema migration so Phase 1.5 is purely additive, but no
  shared-channel runtime code, admin UI, or inbound auto-provisioning
  transaction ships in Phase 1. Phase 1 existing-user migration sets
  `claim_status = 'active'` uniformly.

## Identity and Tenant Model

ClawScale introduces a three-table core and drops the legacy
`ClawscaleUser` + ad-hoc `Tenant` + `Member` shape.

### Entities

- **Identity**: a natural person. Holds authentication material (email,
  password hash, OAuth, phone, session state, password reset tokens). This is
  the only place in the system that owns authentication. Identities created
  through the inbound-triggered path start with no credentials; see
  `claim_status` below.
- **Customer**: a service/billing unit. Holds `kind` (`personal` or
  `organization`), display name, and links to the assigned agent and to the
  customer's channels. Phase 1 customers are all `personal`.
- **Membership**: the join between Identity and Customer with a `role` field
  (`owner`, `member`, `viewer`, ...). Phase 1 uses `owner` only and each
  Customer has exactly one Membership.
- **ExternalIdentity**: persistent mapping from an external sender
  identifier (phone number, email handle, `wa_id`, platform-native
  `external_id`) to an internal `customer_id`. See "External Identity
  Mapping" below.

#### Identity.claim_status

Identities have a `claim_status` enum:

- `active` — Identity has credentials (email + password or OAuth) and
  can sign in. This is the steady state for self-service registrations.
- `unclaimed` — Identity was auto-created from an inbound event on a
  shared channel. It has no email/password, no session, and cannot sign
  in. The linked Customer, Membership, and AgentBinding still exist and
  the agent runs against this Customer normally. Only the auth surface
  is dormant.
- `pending` — A claim flow is in progress (e.g. the user was sent an
  out-of-band claim link and has not yet completed credential setup).
  Same access properties as `unclaimed` for auth purposes.

Phase 1 application code enforces: any Identity that owns an
`active` session MUST be `claim_status = 'active'`. Inbound
auto-provisioning creates Identities at `unclaimed`. The transition to
`active` goes through the claim flow described in
"Inbound Auto-Provisioning → Identity claim lifecycle."

### Invariants

- Identity ↔ Customer is N:M through Membership. Phase 1 application code
  enforces exactly one Membership per Customer with `role = owner`. This is
  an **application invariant, not a schema collapse** — no DB uniqueness on
  `(customer_id)` in `Membership`, so Phase 2 can add members without
  schema change. The invariant is enforced in the customer-provisioning
  service (same code path that owns the registration transaction), NOT
  skipped: Phase 1 still actively refuses to create a second Membership
  for any Customer.
- Agent is bound at the Customer level, not the Identity level (and,
  for `shared`-kind channels, agent is additionally pinned on the
  Channel itself — see "Channel Ownership").
- Channels have an explicit `ownership_kind`. `customer`-kind channels
  are owned by a Customer; `shared`-kind channels are not owned by any
  Customer and belong to the platform. Channels are never owned by an
  Identity directly. See "Channel Ownership" for the full rules.
- The data model must be written end-to-end as three tables from day one.
  No "merge now, split later" shortcut.

### Admin identity

Platform admins are **not** Identities. They live in a separate
`AdminAccount` table with their own auth credentials.

- **Same Postgres database** as `Identity` / `Customer` / `Membership`, but
  a different table. No cross-referencing rows.
- **Same password-hash parameters** as `Identity` (argon2id with the same
  memory/time/parallelism settings) so the bootstrap-time hash utility is
  shared code.
- **Separate session cookie name** (e.g. `cs_admin_sid` vs
  `cs_customer_sid`) and **separate session store table**. An admin
  browser and a customer browser must not share session state.
- Admins never appear in `Membership`, are never bound to a `Customer`,
  and never assume a Customer identity.
- Policies like MFA and IP allowlist are allowed but deferred beyond
  Phase 1. The schema must not block them (e.g. leave room for
  `AdminAccount.mfa_secret` nullable from day one).

### Registration atomicity

Two paths create the Identity/Customer/Membership/AgentBinding quartet,
and both are transactional:

**Self-service path.** A customer registration request produces four
rows in a single Postgres transaction: `Identity` (`claim_status =
'active'`), `Customer`, `Membership`, `AgentBinding`. If any of the
four fail, the whole transaction rolls back and the user sees a
registration error.

**Inbound-triggered path.** A first inbound message from an unknown
sender on a shared channel produces five rows in a single Postgres
transaction: `Identity` (`claim_status = 'unclaimed'`, no credentials),
`Customer`, `Membership`, `AgentBinding`, and `ExternalIdentity`
mapping. If any of the five fail, the transaction rolls back and the
inbound request fails at the bridge — the bridge is responsible for
retry or dead-lettering. See "Inbound Auto-Provisioning" for the full
flow.

In both paths, agent-side provisioning (e.g. Coke scaffolding in
MongoDB) happens **after** the transaction commits and is best-effort
with retry. A failed agent-side provision does not block the path —
the customer exists, the binding exists, and a background reconciler
retries agent provisioning. Agents must make their provisioning
endpoint idempotent on `customer_id`.

### Persisted provisioning state

To make "your agent is being set up" gating deterministic and
admin-observable, `AgentBinding` carries explicit provisioning state:

- `provision_status`: enum `pending | ready | error`
- `provision_attempts`: integer, incremented on each reconciler call
- `provision_last_error`: nullable string, last error message from the
  agent's provisioning endpoint
- `provision_updated_at`: timestamp of the last status transition

Semantics:

- Created at `pending` inside the registration transaction.
- Reconciler calls agent's provisioning endpoint; on 2xx flips to
  `ready`. On 4xx/5xx increments `provision_attempts` and records
  `provision_last_error`; after a fixed threshold the status flips to
  `error` and an admin alert fires.
- The customer frontend gates channel-binding UI on
  `provision_status = 'ready'`. Any other value shows the soft
  "setup in progress" state (or an error state if `error`).
- The admin "Customer list" row surfaces this status so staff can
  distinguish "registered but agent not ready" from "fully provisioned."
- The reconciler is idempotent on `customer_id`; re-running on a
  `ready` row is a no-op.

## Agent Ownership

Agents are registered by platform admins, not selected by customers.

- Each Agent record describes how ClawScale calls the agent (endpoint, auth
  token, name, version) and can declare capabilities (deferred to Phase 1.5).
- `Agent.id` is a UUID. The slug `coke` may appear as a human-readable
  name/label but is NOT used as the primary key. Plan authors must not
  hard-code `agent_id = 'coke'`.
- Exactly one Agent is marked `is_default`. Enforced by a Postgres partial
  unique index: `CREATE UNIQUE INDEX ON agent (is_default) WHERE
  is_default = true`.
- New customer registration automatically binds the default agent.
- **`Agent` rows are soft-delete only.** Hard delete is forbidden at the
  application layer. `AgentBinding.agent_id → Agent.id` uses `ON DELETE
  RESTRICT` as a belt-and-braces guard against accidental hard deletes,
  but note that `ON DELETE RESTRICT` does **not** fire on soft deletes
  (which are `UPDATE`s, not `DELETE`s). Soft-delete safety — refusing to
  soft-delete an Agent that is `is_default` or that any active
  `AgentBinding` references — is enforced in the Agent service layer,
  not by Postgres.
- `AgentBinding` records `(customer_id, agent_id)` and is constrained to one
  active agent per customer in Phase 1.

Phase 1 has a single Agent row (Coke). Phase 1.5 introduces a formal
registration and capability-declaration protocol.

### Default-agent failure semantics

- **No Agent row is marked `is_default`**: registration returns a
  **generic "registration temporarily unavailable"** message to the
  public form. The detailed reason is logged and triggers an admin
  alert; it is not shown to the user. No Identity / Customer rows are
  created.
- **Default Agent row exists but `endpoint` or `auth_token` is empty /
  unset**: treated as "configuration incomplete." Same response as the
  "no default" case: generic outage message + admin alert. Distinct from
  "endpoint unreachable at runtime."
- **Default Agent endpoint is unreachable at registration time** (DNS
  fail, timeout, 5xx): because agent-side provisioning is
  post-transaction (see "Registration atomicity"), the Customer row
  exists and the reconciler retries. The customer sees a soft state
  "your agent is being set up" and cannot yet bind channels until
  provisioning succeeds.
- **Default agent reachable but handshake fails** (4xx from agent):
  same as "unreachable" — reconciler retries. A repeated 4xx after N
  attempts escalates to admin alert.
- **Admin soft-deletes the Agent that is currently default**: blocked at
  application layer. An agent marked `is_default=true` cannot be
  soft-deleted; admin must first clear `is_default` on another agent (or
  mark a different agent default) before the delete is accepted.
- **Two rows both have `is_default=true`**: cannot occur — prevented by
  the partial unique index defined above. If a migration ever produced
  this state, registration refuses to pick a default and returns the
  generic outage message until the conflict is resolved.
- **Admin changes `is_default` later**: only affects newly registered
  customers. Existing `AgentBinding` rows are NOT rebound. Admin-initiated
  customer-level agent migration is out of scope for Phase 1.
- **`AgentBinding` insert conflict** (e.g. the selected agent was
  soft-deleted between default-lookup and insert): transaction rolls
  back and registration returns the generic outage message. The
  application-layer soft-delete guard (see above) is responsible for
  preventing this in normal operation; a conflict here indicates the
  guard was bypassed or a rare race won.

## Channel Ownership

Channels have two distinct ownership kinds. Both must be supported in
one deployment.

### Channel.ownership_kind

`Channel.ownership_kind` is an enum:

- `customer` — the channel belongs to a single Customer and is created
  through that customer's self-service flow (e.g. personal WeChat QR).
  `Channel.customer_id` is **required** and non-null.
  `Channel.agent_id` is not set on the channel row — the agent is
  resolved through `AgentBinding(customer_id)`.
- `shared` — the channel is a shared ingress (e.g. shared iMessage
  account, WhatsApp Business number) serving many external senders.
  `Channel.customer_id` is **null**. `Channel.agent_id` is **required**
  and points at the agent that handles all traffic arriving on this
  channel. Per-sender customer resolution happens at inbound time via
  `ExternalIdentity`; see "Inbound Auto-Provisioning."

Schema shape:

- `Channel.customer_id` is **nullable**. Non-null for `customer`-kind,
  null for `shared`-kind.
- `Channel.agent_id` is nullable, required when `ownership_kind =
  'shared'`. A check constraint enforces this.
- Uniqueness of `(customer_id, kind)` among non-archived channels
  applies **only when `customer_id` is non-null** (i.e. `customer`-kind).
  Multiple `shared` channels of the same `kind` can coexist as long as
  platform admins distinguish them by identifier.

### Rules carried forward

- `(customer_id, kind)` is unique among non-archived `customer`-kind
  channels. Archived channels retain their rows for history; a customer
  may create a new active channel of the same kind after archiving the
  previous one. The channel replacement-via-archive lifecycle from the
  2026-04-08 spec applies unchanged for `customer`-kind channels.
- `ChannelSession`, `EndUser`, `DeliveryRoute`, and `OutboundDelivery`
  all hang off `Channel`. For `customer`-kind channels these are
  transitively scoped to one Customer. For `shared`-kind channels these
  are scoped to the channel and carry `customer_id` (and where relevant
  `end_user_id`) explicitly on each row.
- `DeliveryRoute` is keyed by `(customer_id, business_conversation_key)`
  and resolves to a single `(channel_id, end_user_id)` at a time. For
  shared channels, multiple DeliveryRoute rows can point at the **same**
  `channel_id` with different `customer_id` / `end_user_id` pairs. The
  hard invariant "one business conversation maps to one channel-local
  peer at a time" is preserved per route.

### Lifecycle

- `customer`-kind channels are created, connected, disconnected, and
  archived by the owning customer (existing flow).
- `shared`-kind channels are provisioned, configured, and retired by
  **platform admins only**. Customers do not see shared channels in
  their channel list and cannot modify them. See "Admin Backend MVP."

## External Identity Mapping

`ExternalIdentity` persistently maps an external sender identifier to
an internal `customer_id`. It is the single lookup used at inbound time
on shared channels to decide whether to route to an existing customer
or auto-provision a new one.

### Schema

| Column | Notes |
|---|---|
| `id` | UUID PK |
| `provider` | e.g. `imessage`, `whatsapp`, `wechat_mp` |
| `identity_type` | e.g. `phone_e164`, `email`, `wa_id`, `external_id` |
| `identity_value` | normalized string (see normalization below) |
| `customer_id` | FK to `Customer` |
| `first_seen_channel_id` | FK to `Channel` where this external identity first arrived (a `shared`-kind channel) |
| `first_seen_at` | timestamp |
| `last_seen_at` | timestamp |
| `created_at`, `updated_at` | audit |

Uniqueness: `UNIQUE (provider, identity_type, identity_value)`. The
mapping is one-way and deterministic: a given external identity maps to
exactly one Customer for the lifetime of the mapping.

### Normalization

`identity_value` MUST be normalized before insert and before lookup:

- phone → E.164
- email → lowercase, trimmed
- `wa_id` → provider's canonical form
- platform-native `external_id` → stored exactly as the platform
  reports it

Both ingest-time write and inbound-time lookup use the same
normalization function. Plan authors must factor this into a single
shared helper.

### Relationship to Identity

`ExternalIdentity.customer_id` is the anchor. The linked `Customer`
has exactly one owner `Membership` pointing to one `Identity`. That
`Identity` is `unclaimed` until the user completes the claim flow.
External identities are **not** attached to Identity directly; they
are attached to Customer, because the external sender reaches a
service unit, not a login account.

A single Customer MAY accumulate multiple `ExternalIdentity` rows over
time (e.g. a user who first messaged from WhatsApp and later from
iMessage, or a user who claimed their account and later added a second
external identifier). Merging is explicitly out of scope for Phase 1 —
if the same physical person shows up through a second provider, they
get a second Customer by default. Claim-flow-driven merge is a Phase
1.5 follow-up.

## Storage Boundary

ClawScale stores only what the gateway needs to operate:

- Identity, Customer, Membership
- Agent, AgentBinding
- Channel, ChannelSession, EndUser
- DeliveryRoute, OutboundDelivery

ClawScale does **not** store agent business data:

- conversation content, character, memory, reminders, workflows, and any
  per-customer agent configuration remain in the agent's own storage (Coke
  keeps these in MongoDB)

The admin backend reads only ClawScale-owned tables. It never queries agent
business data.

### Stranded gateway models (must be resolved before cutover)

The current Prisma schema (`gateway/packages/api/prisma/schema.prisma`)
violates the boundary above: it contains models that this spec says the
gateway must not own. Phase 1 cannot reach the target boundary without
a verdict on each.

| Model | Current use | Target |
|---|---|---|
| `Conversation` | gateway stores conversation rows used for routing/history | **Retire or repurpose.** Business conversation content belongs to the agent. The `DeliveryRoute`-facing minimum (the `business_conversation_key` and its route binding) may remain under a non-`Conversation` model; everything else moves to Coke Mongo. |
| `Message` | gateway stores message rows | **Retire.** Inbound/outbound content flows through the bridge; durable storage is the agent's. Any operational record (delivery attempts, idempotency) already belongs to `OutboundDelivery` and stays. |
| `AiBackend` | gateway models an agent-side AI backend selection | **Retire.** Agent selection is the agent's concern. If a runtime needs routing between backends, it is inside the agent. |
| `Workflow` | gateway stores workflow rows | **Retire.** Workflow semantics are business logic, owned by Coke. |
| `EndUserBackend` | gateway links end-user to backend | **Audit.** If it is only a routing table, keep; if it carries business preference, move to Coke. |

Each retirement needs a migration plan: either (a) copy the data into
Coke's MongoDB and then drop the gateway table, or (b) declare it dead
data and drop it directly. This is explicitly in scope for the
follow-up plans (see "Follow-up Plans" step 1a).

Until the stranded models are resolved, the "ClawScale does not store
agent business data" statement above is **aspirational, not current**.
Plan authors must treat it as a target the follow-up plans are
responsible for reaching, not a property of today's gateway.

## Inbound Auto-Provisioning

This section defines the runtime flow when an inbound message arrives
on a `shared`-kind Channel. It is the only flow in ClawScale that
creates Customers without an explicit registration request.

### Flow

Given an inbound event `(channel_id, raw_sender_identity, message)`
where `channel_id` points at a `shared`-kind Channel:

1. **Resolve provider + identity_type.** The bridge (or its
   provider-specific adapter) inspects the inbound envelope and
   produces `(provider, identity_type, raw_identity_value)`.
2. **Normalize.** Apply the shared normalization helper to get
   `identity_value`.
3. **Lookup.** `SELECT customer_id FROM ExternalIdentity WHERE
   (provider, identity_type, identity_value) = (...)`.
4. **Hit → route.** If a mapping exists: update `last_seen_at`, resolve
   or upsert the `EndUser` for this `(channel_id,
   channel_local_peer_id)`, resolve or insert the `DeliveryRoute` for
   `(customer_id, business_conversation_key)`, hand the message off to
   the agent as a normal inbound. No new identity/customer rows are
   created.
5. **Miss → auto-provision.** If no mapping exists, open a single
   Postgres transaction and insert:
   - `Identity` with `claim_status = 'unclaimed'`, no email, no
     password hash. `display_name` derived from whatever the platform
     provides (e.g. WhatsApp profile name), else empty.
   - `Customer` with `kind = 'personal'`, `display_name` from the
     same source.
   - `Membership` with `role = 'owner'` linking Identity ↔ Customer.
   - `AgentBinding` with `agent_id = Channel.agent_id`,
     `provision_status = 'pending'`. The agent for an
     inbound-triggered customer is the shared channel's configured
     agent, **not** the platform-wide default agent. Multiple shared
     channels configured with different agents are supported; each
     channel's inbound flow provisions against its own agent.
   - `ExternalIdentity` with the normalized triple and
     `first_seen_channel_id = channel_id`.
   Commit.
6. **Post-commit.**
   - Synchronously call the agent provisioning endpoint for the new
     `customer_id` (same path used by self-service; idempotent on
     `customer_id`). On 2xx, flip `AgentBinding.provision_status` to
     `ready` and continue.
   - Upsert the `EndUser` row and insert the `DeliveryRoute` row.
   - Hand the message off to the agent **only when
     `AgentBinding.provision_status = 'ready'`**. The first-inbound
     handoff must not race provisioning — agent-side side effects
     (e.g. Coke's Mongo scaffolding) must be in place before the
     agent sees traffic for this customer.
7. **Provisioning failure on first inbound.**
   - If the provisioning call fails (non-2xx, timeout, network
     error), the first inbound is **parked**: the `Identity`,
     `Customer`, `Membership`, `AgentBinding` (at `pending` or
     `error`), and `ExternalIdentity` rows are retained; the inbound
     message is written to a `ParkedInbound` queue keyed by
     `customer_id` with the raw payload and receive timestamp.
   - The background reconciler retries provisioning with the same
     threshold as self-service. On success, parked inbounds for that
     `customer_id` are drained in arrival order through the normal
     inbound handoff.
   - On terminal `error` (attempts exhausted), the parked inbounds
     remain queued until an admin resolves the provisioning failure;
     no message is silently dropped. The admin "Customer list" row
     surfaces `provision_status = 'error'` with parked-inbound count.

If the transaction in step 5 fails, the inbound is failed at the
bridge and retried by the bridge's existing retry logic. No partial
rows survive.

### Concurrency

Two inbounds from the same `(provider, identity_type, identity_value)`
arriving concurrently must NOT produce two Customers. The unique index
on `ExternalIdentity (provider, identity_type, identity_value)` is the
serialization point: both transactions attempt the insert; exactly one
succeeds; the losing transaction rolls back, re-runs the lookup (step
3), finds the row the winner inserted, and proceeds through step 4.
Plan authors must implement this as an explicit upsert-then-read, not
an optimistic SELECT-then-INSERT.

### Outbound reply

Outbound replies from the agent for a Customer whose only channel is a
shared one are delivered through that shared `channel_id`, addressed
to the `end_user_id` resolved on inbound. The `OutboundDelivery`
idempotency and retry window from the 2026-04-08 spec apply unchanged.
The shared channel's platform-level auth (bot token, business account
credentials) is used for the send; no per-customer credential is
required.

### Identity claim lifecycle

An `unclaimed` Identity may later be "claimed" so the user gains
access to the customer frontend:

- **Entry point.** The agent or admin issues a claim — typically by
  asking the user for an email and sending a one-time claim link to
  that email. Admin-initiated claim (e.g. bulk import) is also
  supported.
- **State.** Sending the claim link sets `Identity.claim_status =
  'pending'` and stores a single-use claim token.
- **Completion.** The user opens the claim link, sets a password (and
  confirms their email, which doubles as email verification), and the
  server atomically writes the credential material and sets
  `claim_status = 'active'`.
- **Post-claim.** Normal `/auth/login` works. The Customer, agent
  binding, and history are unchanged — the user is binding an identity
  to a pre-existing service unit, not creating a new one.
- **Out of scope for Phase 1.** Merging a claimed Customer with an
  existing Customer that the same physical person already owns.
  Scoping deferred to Phase 1.5.

Claim tokens follow the same security properties as password-reset
tokens (single-use, time-bounded, bound to a specific Identity).

## Cross-boundary Identifier

The cross-boundary identifier is `customer_id`.

- All inbound and outbound wire contracts between ClawScale and agents
  carry `customer_id`. The wire contract never carries agent-local
  aliases.
- Coke internally keeps the field name `account_id` in its own code and
  MongoDB documents. This is a **cosmetic alias only** — its value is
  byte-identical to the corresponding `customer_id`. There is no mapping
  table, no lookup at runtime, and no independently generated value.
  The Mongo field name `account_id` **must not be renamed** by any
  follow-up plan. The alias is a frozen historical name, not an
  invitation to refactor.
- New agents SHOULD use `customer_id` directly and not introduce aliases.

### Migration direction (one-shot)

**Correct current-state baseline** (verified against code at
spec-drafting time — any plan author must re-verify before executing):

- `CokeAccount` (Postgres `coke_accounts`) holds email, password hash,
  display name, verification state. `CokeAccount.id` is a `cuid`.
- `ClawscaleUser` (Postgres) is a separate row with `id` of the form
  `csu_…` generated at provisioning time. `ClawscaleUser.id` is NOT
  equal to `CokeAccount.id`; the two are linked by
  `ClawscaleUser.cokeAccountId` (FK).
- JWT `sub` carried in the Coke customer session is
  **`CokeAccount.id`** (the cuid), NOT `ClawscaleUser.id`.
- Stripe `Subscription.cokeAccountId` also references the cuid.
- Coke MongoDB auth DAO operates on the **`users`** collection (not
  `accounts`); the historical field name inside Coke's Mongo documents
  is `account_id` and its value is the `CokeAccount.id` cuid.

Given this baseline, the migration anchor is:

- **`Customer.id` = existing `CokeAccount.id`** (cuid, byte-identical).
  This is the value today's sessions (JWT `sub`) and Stripe metadata
  already reference, so live sessions and Stripe links continue to
  resolve without re-issuing tokens.
- **Coke Mongo's `account_id` field remains unchanged** because its
  current value already equals `CokeAccount.id` = new `Customer.id`.
- **`ClawscaleUser.id` (the `csu_…` value) is NOT reused as any new
  id.** The `ClawscaleUser` row is dropped during the schema migration.
  Any code, log field, or external reference that currently points at
  `csu_…` must be audited before cutover; ClawScale-side code that
  used `ClawscaleUser.id` is rewritten to use `Customer.id`.
- **`Identity.id` is newly minted (UUID).** No existing field is
  reused. Existing sessions reference `Customer.id`, so minting fresh
  `Identity.id` does not break live sessions.
- **`Membership` rows are synthesized** from the existing 1:1
  `CokeAccount ↔ ClawscaleUser` relation with `role = owner`.
- **`AdminAccount` rows are created manually** via a bootstrap script;
  they are not derived from any existing table.
- After the one-shot migration, Coke's MongoDB `users` auth collection
  is retired (see "Coke-side Account Shutdown"); non-`users`
  collections keep their `account_id` field with its current values.

### Pre-migration verification (required)

Plan authors MUST, before writing the migration:

1. Re-confirm the above baseline by reading current code paths
   (`gateway/packages/api/src/lib/coke-auth.ts`,
   `gateway/packages/api/src/lib/clawscale-user.ts`,
   `gateway/packages/api/src/middleware/coke-user-auth.ts`,
   `gateway/packages/api/prisma/schema.prisma`,
   `dao/user_dao.py`).
2. Audit every non-test occurrence of `csu_` and `ClawscaleUser.id` to
   confirm nothing outside the gateway depends on that value.
3. Audit every non-test occurrence of `account_id` in Coke's MongoDB
   code to confirm the value there matches `CokeAccount.id` today.

Failure of any of these audits invalidates the "no rekey" assumption
and requires a re-plan before implementation.

### Wire compatibility window

For one release after the auth migration lands, the ClawScale ↔ agent wire
contract MUST accept **both** `customer_id` and `account_id` on inbound
payloads, and SHOULD emit `customer_id` on outbound. This avoids breakage
if agent-side deploys lag ClawScale-side deploys. The compatibility window
closes in the release that removes the Coke auth routes; after that, only
`customer_id` is accepted on the wire.

### Migration cutover window

Auth cutover is not instantaneous. The plan must schedule a **short
maintenance window** during which:

- registration and password-reset endpoints are read-only (return "sign-up
  temporarily paused")
- existing sessions continue to work
- the Postgres schema migration + Mongo `users` retirement happens
  inside the window

No dual-write phase is introduced. The window replaces dual-write.

## Coke-side Account Shutdown

Coke no longer owns authentication or an account identity.

- Coke stops being a source of registration, login, password reset,
  verification email, OAuth, or session material. All of that is owned by
  ClawScale.
- Coke's MongoDB `users` auth **collection** is retired (plus Postgres
  `coke_accounts` is retired at the same cutover). Auth fields are
  deleted. Any remaining non-auth fields in either location are migrated
  into clearly business-named objects (`coke_settings`, `characters`,
  `user_profiles`) or dropped if unused. The **field** `account_id`
  on Coke's other Mongo collections (messages, reminders, memory, etc.)
  **survives** — it is not removed. This spec deletes the auth
  collections, not the cross-reference field.
- The field's value is already equal to `Customer.id` after the one-shot
  migration described in "Cross-boundary Identifier → Migration direction",
  so no rewrite of non-`users` Mongo documents is needed.
- Migration is one-shot; no dual-write or long-lived mapping.

### Legacy `users` collection split contract

Before the `users` auth collection is retired, every surviving non-auth
field must land in one of these Mongo destinations:

- `user_profiles`
  - one document per non-character customer, keyed by `account_id`
  - stores user-facing profile data that Coke workflows still need after
    auth retirement
  - minimal Phase 1 shape:
    - `account_id`
    - `name`
    - `display_name`
    - `platforms`
    - `user_info` when that metadata belongs to the human user rather than
      a character
    - `migrated_from_user_id`
    - `migrated_at`
- `coke_settings`
  - one document per non-character customer, keyed by `account_id`
  - stores Coke-specific business settings that are not authentication
    credentials
  - minimal Phase 1 shape:
    - `account_id`
    - `timezone`
    - `access`
    - `migrated_from_user_id`
    - `migrated_at`
- `characters`
  - one document per former `users.is_character = true` record
  - preserves the existing Mongo `_id` so character references do not need
    a second identifier migration during Phase 1
  - minimal Phase 1 shape:
    - `_id`
    - `legacy_user_id`
    - `name`
    - `nickname`
    - `platforms`
    - `user_info`
    - `migrated_at`

Task-level field classification follows this contract:

- auth-only => delete
  - `email`
  - `phone_number`
  - password / verification / session fields
  - top-level human auth lifecycle flags such as the legacy auth `status`
  - the `is_character` sentinel after character docs have moved out
- business-profile => move to `user_profiles`
  - `name`
  - `display_name`
  - non-character `platforms`
  - non-character `user_info`
- Coke setting => move to `coke_settings`
  - `timezone`
  - `access.*`
- character-owned => move to `characters`
  - the full former `is_character = true` document body, excluding any
    auth-only fields
  - preserve the existing Mongo `_id`
  - preserve top-level character `nickname` because Coke runtime and prompt
    paths still read it directly during Phase 1

For non-character legacy `users` documents, `account_id` remains the only
allowed key for `user_profiles` / `coke_settings`. If a document lacks
`account_id`, dry-run must report a `missing_account_id` anomaly and the
real migration must refuse to synthesize a replacement from Mongo `_id` or
any other legacy field.

This split is a migration contract, not an invitation to invent additional
destination schemas during implementation. If implementation finds a legacy
field that does not fit this contract, the plan must stop and be revised
before any destructive step proceeds.

## Frontend Ownership

The customer frontend lives in ClawScale's gateway web package.

- Generic pages (register, login, session, forgot-password, channel bind
  QR flow, channel list) are ClawScale-owned and **must** move to neutral
  routes now. They do not stay under `/coke/*` even in Phase 1.
- Agent-specific pages (Coke's character settings, Coke's payment flow,
  Coke's business views) live under an agent-scoped partition at
  `/coke/*`. Only agent-business content belongs there.
- No standalone "Coke frontend" project. Generic flows currently hosted
  under `(coke-user)/coke/*` are misplaced and must move.

### Target route table (Phase 1)

Route groups (parentheses) are Next.js route groups and do not appear in
URLs; they control which layout wraps a page. The "Group" column below is
the on-disk folder group, not a URL segment.

| Route | Group | Owner | Note |
|---|---|---|---|
| `/auth/register` | `(customer)` | ClawScale generic | replaces `/coke/register` |
| `/auth/login` | `(customer)` | ClawScale generic | replaces `/coke/login` |
| `/auth/forgot-password` | `(customer)` | ClawScale generic | replaces `/coke/forgot-password` |
| `/auth/reset-password` | `(customer)` | ClawScale generic | |
| `/auth/verify-email` | `(customer)` | ClawScale generic | replaces `/coke/verify-email` |
| `/auth/claim` | `(customer)` | ClawScale generic | claim flow for `unclaimed`/`pending` Identities (Phase 1.5 scope; route reserved) |
| `/channels` | `(customer)` | ClawScale generic | customer's channel list |
| `/channels/wechat-personal` | `(customer)` | ClawScale generic | QR bind/connect/disconnect/archive; replaces `/coke/bind-wechat` |
| `/coke/settings` | `(customer)` | Coke agent partition | Coke-specific preferences |
| `/coke/payment` | `(customer)` | Coke agent partition | Coke-specific subscription/payment |
| `/coke/...` | `(customer)` | Coke agent partition | other Coke business views |
| `/admin/login` | `(admin)` | Admin backend | admin sign-in |
| `/admin/customers` | `(admin)` | Admin backend | flat customer list |
| `/admin/channels` | `(admin)` | Admin backend | platform Channel status |
| `/admin/deliveries` | `(admin)` | Admin backend | `OutboundDelivery` failure view (read-only) |
| `/admin/agents` | `(admin)` | Admin backend | read-only agent detail (Coke) |
| `/admin/admins` | `(admin)` | Admin backend | add/remove `AdminAccount` rows |

Next.js route groups in `gateway/packages/web/app/` must be renamed to
reflect the split. The existing `(coke-user)` group becomes `(customer)`
after generic routes are relocated into it; a new `(admin)` group hosts
all `/admin/*` routes.

## Admin Backend MVP

The current `/dashboard/*` routes are obsolete and will be replaced.

| Module | Phase 1 shape |
|---|---|
| Agent detail | Read-only page for the single agent (Coke): endpoint, token configured Y/N, last handshake health. No add/edit/delete. |
| Customer list | Flat list, one row per customer. Columns: **contact identifier** (email when the owner Identity is `active`; external identity string e.g. phone/`wa_id` when the owner is `unclaimed`/`pending`; explicitly labeled so admins can tell them apart), **claim status** (`active` / `unclaimed` / `pending`), registered-at / first-seen-at, assigned agent, channel status. Row detail shows channel state and recent `OutboundDelivery` failures (read-only). No org interactions. In Phase 1 all rows are `active` with email, since no inbound auto-provisioning exists yet; the non-email case is wired up with Phase 1.5. |
| Channel status view | Read-only platform-wide Channel status table with filters by `kind` and `status`. Paging required. Phase 1 lists customer-owned channels only (no shared channels exist yet). |
| Delivery failure view | Read-only list of recent `OutboundDelivery` failures with filters. **No retry UI in Phase 1** (retries are handled automatically by the existing delivery pipeline; manual retry is Phase 1.5). |
| Admin accounts | Add/remove rows in `AdminAccount` table. Single `admin` role only. No fine-grained permissions, no MFA, no IP allowlist (all deferred). |
| Admin auth | Separate login page at `/admin/login`. `AdminAccount` credentials are entirely independent of customer `Identity` credentials. |

UI may be flat; the underlying schema remains three-table. Anything not
in this table (manual retry, permission roles, org views, agent add/edit,
customer business-data views) is explicitly out of scope for Phase 1.

## Current-state Gaps

These items are misplaced or obsolete under the new positioning and should
be corrected during the follow-up refactors:

1. `gateway/packages/api/src/routes/` contains Coke-prefixed route modules
   that mix generic platform concerns with Coke-specific business logic.
   Concrete files:
   - generic (move to neutral paths): `coke-auth-routes.ts`,
     `coke-user-provision.ts`, `coke-wechat-routes.ts` (QR bind/connect),
     `coke-delivery-routes.ts`, `user-wechat-channel.ts` (the primary
     WeChat channel surface — generic despite the historical naming),
     parts of `coke-bindings.ts`
   - agent-scoped (stays as Coke-specific under a clear Coke namespace):
     `coke-payment-routes.ts`, Coke-specific parts of `coke-bindings.ts`
   - other referenced route files to audit: `auth.ts`, `tenant.ts`,
     `channels.ts`, `onboard.ts`, `outbound.ts`
2. `gateway/packages/web/app/` uses the Next.js route group
   `(coke-user)/coke/*` for customer pages. Generic routes (register,
   login, forgot-password, verify-email, bind-wechat) must relocate under
   `(customer)/auth/*` and `(customer)/channels/*`; only Coke business
   pages remain under `(customer)/coke/*`.
3. **The obsolete admin surface is the non-grouped folder
   `gateway/packages/web/app/dashboard/`** — it contains `login`,
   `register`, `settings`, `users`, `conversations`, `ai-backends`,
   `workflows`, `end-users`, `onboard`, `channels`. This whole folder is
   deleted and replaced by the new `(admin)` route group under
   `/admin/*`. Separately, the Next.js route group
   `gateway/packages/web/app/(dashboard)/` currently contains only a
   `channels/` subtree; it must be folded into `(admin)` (not deleted
   blindly — the `channels` pages inside it may have useful components to
   lift).
4. Coke MongoDB `users` collection and Postgres `coke_accounts` table
   both carry Coke-owned auth. Both are retired after ClawScale takes
   over auth and the one-shot migration lands. The `account_id` field
   on other Coke Mongo collections survives.
5. The existing `ClawscaleUser`, ad-hoc `Tenant`, and `Member` tables in
   the gateway Postgres schema (see
   `gateway/packages/api/prisma/schema.prisma`) are not aligned with the
   Identity/Customer/Membership model and must be migrated.
6. In-flight plans predating this design, per-plan verdict:

   | Plan | Verdict |
   |---|---|
   | `2026-04-11-gateway-auth-email-stripe-plan.md` | **Relocate**. Generic auth/email/Stripe parts continue but must land under ClawScale-neutral paths, not `coke-*` routes. Coke-specific subscription logic stays agent-scoped. |
   | `2026-04-15-resend-email-migration-plan.md` | **Relocate**. Email delivery is a generic ClawScale capability; finish the Resend migration but land it under a neutral email module, not `coke-*`. |
   | `2026-04-14-email-auth-closure-plan.md` (and design) | **Kill**. The closure logic targeted Coke-owned auth, which is being shut down. Any outstanding bug fixes roll into the auth-ownership-migration plan. |
   | `2026-04-15-one-click-email-verification-design.md` | **Relocate**. Design survives but the implementation must land in ClawScale-generic auth, not Coke. |
   | `2026-04-15-python-tail-cleanup-plan.md` | **Keep**. Independent of identity/auth; proceed as-is. |

## Non-goals

- Formal agent registration and capability-declaration protocol (Phase 1.5).
- Organization-facing UI, invitations, roles beyond `owner`, or
  organization-level reporting (Phase 2).
- Multi-agent routing, per-agent isolation, rate limiting across agents
  (Phase 1.5+).
- Migration of Coke business data out of MongoDB.
- Redesign of Coke's business **semantics** (reminder, memory, character
  logic). Field relocation needed to accommodate the Coke auth shutdown
  (moving non-auth fields off the `users` collection and `coke_accounts`
  table into `CokeSettings` / `Character` / `UserProfile`) is in scope
  and is not considered semantic redesign.

## Follow-up Plans

This design will be broken into separate plans, to be executed in the
following order. Ordering matters because later plans depend on the
earlier ones.

1. **Identity/Customer/Membership schema migration (Postgres).**
   Introduces the three-table model and `AgentBinding` (with
   `provision_status` / `provision_attempts` / `provision_last_error` /
   `provision_updated_at`), `AdminAccount`, and
   `Identity.claim_status`. `Customer.id` values for existing users
   are **derived from the current `CokeAccount.id` cuid** so JWT
   sessions, Stripe metadata, and downstream Mongo `account_id` values
   do not need rewriting. Includes the `UNIQUE WHERE is_default = true`
   partial index on `Agent`. Existing users are migrated at
   `claim_status = 'active'`.

1a. **Stranded-model resolution.** Before or alongside step 1, produce a
   verdict + migration for `Conversation`, `Message`, `AiBackend`,
   `Workflow`, `EndUserBackend` per "Storage Boundary → Stranded
   gateway models." Each either moves to Coke Mongo or is dropped. Must
   complete before step 2 so the new identity model is not entangled
   with business tables.
2. **Auth ownership migration** (ClawScale takes over registration,
   login, password reset, email verification; Coke auth routes shut
   down). Must follow (1) because it writes to the new tables.
3. **Coke auth-collection retirement** (Mongo `users` + Postgres
   `coke_accounts`). If (1) reuses existing ids correctly, this plan is
   narrowly scoped: verify `account_id` values on non-`users` Mongo
   collections already match `Customer.id` (sanity check, not rewrite),
   then drop `users` and `coke_accounts`. If any drift is found, the
   plan escalates to a targeted rewrite; otherwise it is drop-and-verify.
4. **Frontend relocation** (generic flows out of `(coke-user)/coke/*`
   into `(customer)/auth/*` and `(customer)/channels/*`).
5. **Admin backend MVP rebuild** at `/admin/*`. Phase 1 scope only:
   agent detail, customer list, customer-channel status, delivery
   failure view, admin accounts. Shared-channel management is NOT in
   this plan (lands in 7).
6. **Deprecation of `/dashboard/*`** after (5) is live.

**Phase 1.5:**

7. **Shared channel + inbound auto-provisioning runtime.** The schema
   pieces (`Channel.ownership_kind`, nullable `Channel.customer_id`,
   `Channel.agent_id`, `ExternalIdentity`, `Identity.claim_status`)
   already landed in plan (1) as dormant additions. This plan turns
   them on: inbound auto-provisioning transaction, `ParkedInbound`
   queue, provisioning-gated handoff (see "Inbound Auto-Provisioning"
   steps 6–7), outbound-reply routing through shared channels, admin
   UI for creating/configuring/retiring shared channels, the
   `/auth/claim` route, and the `unclaimed` → `pending` → `active`
   claim flow reusing the password-reset token infrastructure from
   (2). Admin customer-list is extended with the non-email contact
   identifier and claim-status column.

Each plan references this design as its source of truth and references
the 2026-04-08 spec for routing/delivery/attachment semantics that are
unchanged.
