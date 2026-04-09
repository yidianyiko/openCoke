# Spec: Coke Business-Only, Clawscale Channel-Only

## Status

Proposed

## Summary

This document defines the target architecture for Coke and Clawscale.

The core rule is:

- `Coke` is business-only
- `Clawscale` is channel-only
- `Bridge` is translation-only

In v1, this architecture is applied to the `wechat_personal` personal-channel flow. The same architectural rule should later apply to other personal channels, but those channel types are out of scope for this document.

This is a hard-cutover design. The system does not preserve legacy ownership models for compatibility. The user-facing experience must remain the same, but the internal model is simplified and ownership boundaries are made explicit.

## Why This Change Is Required

The current system still carries historical coupling between:

- Coke business state
- Clawscale channel state
- bridge-owned glue state

That coupling causes repeated ambiguity about:

- who owns user identity
- who owns channel identity
- who owns delivery routing
- where message state should be inspected when something breaks

The result is a system where a single end-user message crosses multiple storage models and multiple partial ownership models.

The target architecture removes that ambiguity.

## Product Invariant

The user-facing product behavior must not change.

A user must still be able to:

1. register or log in to Coke
2. create their own personal `wechat_personal` channel
3. scan a QR code for their own WeChat account
4. send messages from that WeChat account
5. receive synchronous replies
6. receive asynchronous reminders and other proactive messages when an exact delivery route exists and the channel session is healthy, or becomes healthy within the retry retention window

The architecture may change. The product behavior above must not.

## Architectural Principles

### Principle 1: Coke owns business truth

Coke owns:

- account identity
- characters
- business conversations
- reminders
- memories, relations, workflows
- business input/output messages
- user preferences such as timezone

Coke must not own:

- platform-native identity
- channel login state
- external platform routing
- QR session state
- outbound delivery routing truth

### Principle 2: Clawscale owns channel truth

Clawscale owns:

- tenant and member administration
- `ClawscaleUser`
- channel ownership
- channel session state
- channel-local peer identity
- outbound routing and delivery truth
- platform adapter lifecycle and status

Clawscale must not own:

- Coke business memory
- business reminder semantics
- business workflow semantics
- character state

### Principle 3: Bridge is a translation layer, not a source of truth

Bridge translates:

- inbound gateway messages into Coke business inputs
- outbound Coke business outputs into gateway delivery requests

Bridge may orchestrate synchronous and asynchronous flows, but it must not become the long-term owner of:

- user identity truth
- channel ownership truth
- route truth

Bridge may keep short-lived coordination state for retries, correlation, and request/response completion. That state is operational only. It must not become durable business truth or durable routing truth.

### Principle 4: Coke is channel-agnostic

Coke must not model users by platform.

The Coke domain must not depend on fields such as:

- `platforms.wechat`
- `platforms.telegram`
- `external_id`
- `channel_id`
- `tenant_id`
- `end_user_id`

Those concepts belong to Clawscale.

Coke does not know about platforms.

Coke exposes `account_id` as its stable business identity across system boundaries. Channel-agnostic means Coke ignores channel identities, not that other systems cannot reference Coke accounts.

## Goals

- Make the ownership boundary between Coke and Clawscale explicit.
- Remove platform-specific identity from the Coke domain model.
- Make Clawscale the only owner of channel, peer, and delivery routing state.
- Keep the user-visible `wechat_personal` flow unchanged.
- Define the normalized message contract between Clawscale and Coke.
- Define the lifecycle and enforcement model for `Coke Account <-> ClawscaleUser`.
- Remove bridge-owned long-term truth.
- Establish a design that later generalizes to other personal channels.

## Non-Goals

- Migrating all Coke data from MongoDB to Postgres.
- Redesigning the Coke business domain.
- Redesigning the Clawscale dashboard admin model.
- Generalizing every channel type in v1.
- Preserving legacy bridge-owned compatibility paths.

## Target Runtime Architecture

```text
Coke (business state, Mongo)
    |
    | normalized business messages
    v
Bridge (translation only)
    |
    | internal gateway API
    v
Clawscale (channel state, Postgres)
    |
    v
Platforms (WeChat, Telegram, Discord, ...)
```

## Source of Truth

| Concern | Owner | Storage |
|---|---|---|
| Coke account identity | Coke | MongoDB |
| characters / reminders / memory / workflows | Coke | MongoDB |
| business conversations | Coke | MongoDB |
| business input/output messages | Coke | MongoDB |
| tenant / member | Clawscale | Postgres |
| unified gateway user (`ClawscaleUser`) | Clawscale | Postgres |
| channel ownership and lifecycle | Clawscale | Postgres |
| channel-local peer identity (`EndUser`) | Clawscale | Postgres |
| delivery route truth | Clawscale | Postgres |
| outbound delivery status / idempotency | Clawscale | Postgres |
| protocol translation | Bridge | no long-term ownership |

## Domain Model

### Coke Domain

Coke keeps the following first-class entities:

- `Account`
- `Character`
- `BusinessConversation`
- `Reminder`
- `InputMessage`
- `OutputMessage`
- `Memory / Relation / Workflow`

Coke business objects refer to users by `account_id`, not by platform identity.

### Clawscale Domain

Clawscale keeps the following first-class entities:

- `Tenant`
- `Member`
- `ClawscaleUser`
- `Channel`
- `EndUser`
- `ChannelSession`
- `DeliveryRoute`
- `OutboundDelivery`

#### Tenant

`Tenant` remains the operational isolation boundary.

For self-serve v1 users, Clawscale creates one personal tenant per Coke account. That tenant is created automatically during provisioning and is not user-managed through the dashboard path.

#### Member

`Member` remains the dashboard/operator identity.

#### ClawscaleUser

`ClawscaleUser` is the gateway-side unified user and is the owner of personal channels.

`Coke Account` and `ClawscaleUser` remain strictly 1:1.

##### Creation and lifecycle

- `Coke Account` is created by Coke.
- Immediately after Coke account creation, Coke triggers an idempotent provision call to Clawscale before the registration flow is considered successful.
- Clawscale creates or reuses the personal `Tenant` and then upserts exactly one `ClawscaleUser` for that `coke_account_id`.
- Clawscale enforces uniqueness with a unique durable constraint on `coke_account_id`.
- Login also performs the same idempotent ensure operation, so partial failure can be repaired automatically.
- The system must never treat `Coke Account without ClawscaleUser` as a stable legal state for any active user flow.
- Reminder scheduling, channel creation, and active message handling are gated on successful provisioning.

The binding key is `coke_account_id`.

#### Channel

A channel remains a gateway transport resource.

For v1:

- `wechat_personal` is a `personal` channel
- it is owned by exactly one `ClawscaleUser`
- the QR login and channel session belong to that user-owned channel

#### EndUser

`EndUser` remains a channel-local peer identity.

For `wechat_personal`, it represents the peer/contact/session identity inside that user's personal channel. It is not the business-account owner.

#### ChannelSession

`ChannelSession` represents the live channel login/session material for a channel.

For `wechat_personal`, it includes the current iLink session data required for connect, reconnect, health checks, and send/receive operations.

#### DeliveryRoute

`DeliveryRoute` is a Clawscale-owned routing record that binds one business conversation to one exact delivery target.

It answers:

- for this `account_id`
- and this `business_conversation_key`
- which `channel_id` is authoritative
- which `end_user_id` is authoritative
- which external peer identity should receive outbound traffic

This replaces bridge-side route truth.

`DeliveryRoute` is durable. It is not a best-effort cache.

#### OutboundDelivery

`OutboundDelivery` records idempotency, delivery attempts, and final delivery state for actual platform sends.

## Conversation Identity and Routing Invariant

`business_conversation_key` is a Coke-generated, account-scoped, stable business conversation identifier.

Rules:

- Coke creates it.
- Clawscale never invents it.
- The first inbound message for a new peer does not yet carry a `business_conversation_key`; it is established by protocol.
- After establishment, a given `(account_id, business_conversation_key)` maps to exactly one active `(channel_id, end_user_id)` delivery target at a time.
- If the real peer changes, a new `business_conversation_key` must be established.
- Reconnects and session refreshes for the same peer do not change the `business_conversation_key`.

This gives the system a hard invariant:

> one business conversation maps to one channel-local peer on one channel at a time.

That invariant is required so reminders and proactive messages cannot be misdelivered to the wrong peer.

## Explicit Removals From Coke

The target architecture removes the following from the Coke core model:

- platform-specific user fields such as `user.platforms.*`
- platform-native user IDs in the Coke account record
- channel ownership or channel login state
- bridge-owned push route registries as a Coke dependency
- QR login and bind-session concepts as core business entities

The business domain must be cleanly usable without knowing whether the user came from WeChat, Telegram, or any other platform.

## Explicit Removals From Bridge Ownership

Bridge must not be the long-term owner of:

- `external_identities`
- `clawscale_push_routes`
- QR bind session truth
- user-to-channel ownership truth

If Bridge needs transient runtime state, it may keep short-lived coordination state only. Durable truth belongs either to Coke or to Clawscale.

## Message Boundary

### Inbound Contract: Clawscale -> Coke

When a message crosses from Clawscale into Coke, it must be normalized into a business message.

Required fields:

- `inbound_event_id`
- `source_message_id`
- `account_id`
- `message_type`
- `text`
- `attachments` (optional)
- `timestamp`
- `trace_id`

Conditionally required fields:

- `business_conversation_key` for established conversations

Optional fields:

- `sync_reply_token`
- `gateway_conversation_id` for conversation establishment
- `causal_metadata` for observability only

Definitions:

- `inbound_event_id`: Clawscale-generated globally unique event ID for this inbound delivery attempt; it remains stable across retries of the same inbound handoff
- `source_message_id`: platform message ID when available, otherwise adapter-generated stable deduplication key for the source message itself
- `sync_reply_token`: a short-lived token for the immediate synchronous reply path only
- `gateway_conversation_id`: Clawscale-owned conversation identifier used during conversation establishment before a business conversation key exists
- `trace_id`: end-to-end trace/correlation identifier

Coke business logic must not require platform-specific identity fields in order to function.

### Outbound Contract: Coke -> Clawscale

When a message crosses from Coke back into Clawscale, it must be normalized into a business output.

Required fields:

- `output_id`
- `account_id`
- `business_conversation_key`
- `message_type`
- `text`
- `attachments` (optional)
- `delivery_mode`
- `expect_output_timestamp`
- `idempotency_key`
- `trace_id`

Optional fields:

- `causal_inbound_event_id`

Definitions:

- `output_id`: Coke-generated globally unique output identifier
- `idempotency_key`: stable key used by Clawscale outbound delivery and retry logic; its scope is global across outbound deliveries and it must be retained for at least the full outbound retry window
- `causal_inbound_event_id`: set when this output is a direct consequence of a specific inbound event; synchronous replies must set it, proactive outputs usually do not

The outbound contract must not require Coke to specify:

- `platform`
- `tenant_id`
- `channel_id`
- `external_end_user_id`
- platform-native route keys

Clawscale resolves the final delivery route.

## Attachment Contract

Attachments are normalized references, not platform-native session blobs.

For v1:

- Clawscale owns media ingestion and platform-specific media retrieval.
- The cross-system contract carries attachment metadata plus a stable reference.
- Coke may read attachment references but does not own platform media lifecycle.
- Outbound attachment delivery is allowed only when Clawscale can resolve the attachment reference into a platform sendable form.
- If attachment resolution fails, the whole outbound delivery fails with a structured attachment-resolution error. The system does not silently strip attachments.

Attachment objects include:

- `attachment_id`
- `content_type`
- `filename` (optional)
- `size_bytes` (optional)
- `reference_url` or object reference key

## Protocols

### Protocol 1: Provision account and Clawscale user

1. Coke creates `Account`.
2. Before registration success is returned to the user, Coke calls Clawscale provision.
3. Clawscale idempotently ensures:
   - personal `Tenant`
   - `ClawscaleUser` bound to `coke_account_id`
   - default personal-channel prerequisites
4. If provisioning fails, the registration flow is not considered complete.
5. Login retries the same ensure path so interrupted provisioning can self-heal.

### Protocol 2: Establish a new business conversation

This protocol is used for the first inbound message from a peer that does not yet have a mapped `business_conversation_key`.

1. Clawscale receives inbound traffic for `(channel_id, end_user_id)`.
2. Clawscale resolves the owning `account_id`.
3. Clawscale sends an inbound business message to Coke with:
   - `account_id`
   - `gateway_conversation_id`
   - no `business_conversation_key` yet
   - normal message payload and identifiers
4. Coke creates a new business conversation and returns:
   - `business_conversation_key`
   - normal synchronous reply if one exists
5. Clawscale durably writes:
   - `gateway_conversation_id -> business_conversation_key`
   - exact `DeliveryRoute(account_id, business_conversation_key)`

Only Coke mints the business conversation key.

### Protocol 3: Handle inbound for an established conversation

1. Clawscale receives inbound traffic for a peer whose conversation mapping already exists.
2. Clawscale resolves the stored `business_conversation_key`.
3. Clawscale forwards the inbound business message with that key.
4. Coke processes it in the existing business conversation.
5. Clawscale refreshes the exact `DeliveryRoute` for that same conversation.

### Protocol 4: Detect peer change

1. Clawscale detects that traffic is now associated with a different real peer.
2. The previous conversation route is not reused for that new peer.
3. Clawscale starts Protocol 2 again.
4. Coke mints a new `business_conversation_key`.
5. A new exact route is created.

One peer change means one new business conversation.

### Protocol 5: Cutover and backfill

For an existing account, cutover proceeds only if all proactive-capable business conversations can be bound to exact delivery routes.

Backfill procedure:

1. provision `ClawscaleUser` and personal tenant if missing
2. provision personal `wechat_personal` channel structure if missing
3. enumerate active business conversations in Coke that may emit proactive output
4. locate the exact `(channel_id, end_user_id)` currently associated with each conversation
5. write exact `DeliveryRoute` records before cutover
6. verify all future-dated reminders for those conversations resolve to those exact routes

If any active conversation cannot be mapped to an exact peer, cutover for that account stops and requires route repair.

## Routing Rules

### Synchronous request-response

For synchronous replies, Clawscale may reply through the same inbound channel/session that produced the message.

The immediate response path is correlated by `inbound_event_id` and, when needed, `sync_reply_token`. Bridge may keep short-lived coordination state for this path, but no durable route truth is created from that temporary state alone.

`sync_reply_token` is valid only for the short synchronous reply window of that inbound turn. If it expires before a reply is emitted, the message leaves the synchronous path and must be handled as a normal outbound delivery through exact `DeliveryRoute` resolution.

### Asynchronous proactive output

For reminders and other proactive outputs, Clawscale resolves delivery through `DeliveryRoute` in Postgres.

`DeliveryRoute` is updated when Clawscale processes inbound traffic for an already-known `business_conversation_key`, or when a new business conversation is explicitly established between Coke and Clawscale.

### Route resolution precedence

For v1, Clawscale resolves outbound routes only by:

- exact route for `(account_id, business_conversation_key)`

Disallowed fallbacks:

- latest route for `account_id`
- latest route for `channel_id`
- latest active peer

If no exact route exists, the output must fail with a structured delivery error such as `missing_delivery_route`. It must not be delivered to the most recently active peer.

## Channel and Delivery Failure Semantics

### Session invalidation

If a `ChannelSession` is invalidated or the personal channel disconnects:

- the channel remains owned by the same `ClawscaleUser`
- existing `DeliveryRoute` records remain logically associated with that channel/peer
- outbound delivery attempts fail as undeliverable until the channel reconnects
- Clawscale does not reroute to a different peer or a different channel automatically

### Channel replacement

If the user archives a channel and creates a new replacement channel:

- old `DeliveryRoute` entries are invalidated
- a new route must be established for future proactive sends
- proactive outputs without a valid new route fail explicitly

### Delivery failure

If outbound delivery fails because the route is stale, session is dead, or peer mapping is missing:

- `OutboundDelivery` records the failure
- the business output is not silently dropped
- the system surfaces a machine-readable failure reason
- the dispatcher retries while the delivery remains within the outbound retry retention window
- once that retention window expires, delivery becomes terminally failed

## Hard-Cutover Rules

This design is not compatibility-first.

The cutover rules are:

- personal-channel traffic must use the new ownership model immediately once the account is cut over
- new writes must not depend on legacy bridge-owned identity tables
- new writes must not create new platform fields in Coke accounts
- route truth must be established in Clawscale, not in Coke or Bridge
- obsolete compatibility data may be deleted rather than maintained

## Cutover and Backfill Invariant

This is a hard cutover, but user-visible behavior must remain stable.

Therefore cutover for an account is allowed only after these conditions are true:

1. the account has a `ClawscaleUser`
2. the account has its personal tenant and personal `wechat_personal` channel structure
3. every active business conversation that may emit proactive output has an exact `DeliveryRoute`
4. every future-dated reminder tied to that conversation can resolve to that exact route

If these conditions are not met, the account is not considered cut over yet.

This is not compatibility coexistence. It is a preconditioned switch.

If a safe exact route cannot be backfilled for an existing conversation, cutover for that account must stop and require route repair before the new model becomes authoritative.

## v1 Scope

This spec applies directly to:

- `wechat_personal` as a personal user-owned channel

This spec also defines the architectural rule for future personal channels, but those channels are not implemented in v1.

## User-Facing Invariants

The following user-visible behavior must remain true after cutover:

- registration/login still succeeds from the Coke web surface
- the user still manually creates their own WeChat channel
- the user still scans their own QR code
- the user still owns that personal channel
- normal replies still arrive in WeChat
- reminders and other proactive messages still arrive in WeChat when an exact route exists and delivery succeeds within the retry retention window

Internal architecture may change freely as long as these invariants remain true.

## Acceptance Criteria

1. Coke business entities contain no platform-specific identity fields.
2. `ClawscaleUser` remains 1:1 with `Coke Account` and is provisioned idempotently from Coke login/registration flows.
3. `wechat_personal` remains a personal channel owned by a `ClawscaleUser`.
4. `DeliveryRoute` is durable and exact for `(account_id, business_conversation_key)`.
5. Proactive delivery does not use account-level fallback.
6. Clawscale is the only durable owner of delivery routing truth.
7. Bridge does not persist long-term identity or route truth.
8. A user can still complete the full personal WeChat flow without any dashboard/admin action.
9. Synchronous replies still work with explicit correlation identifiers.
10. Asynchronous reminder/proactive delivery still works with exact route resolution.
11. Existing active accounts are cut over only after exact route backfill succeeds for every proactive-capable business conversation.

## Final Architecture Rule

The system should be understandable with this single sentence:

> Coke decides what the business wants to say. Clawscale decides where and how it is sent. Bridge only translates between them.

## Deletion and Deactivation Lifecycle

- If a Coke account is deactivated, Clawscale marks the corresponding `ClawscaleUser` inactive and blocks new channel activity.
- If a Coke account is deleted, its `ClawscaleUser`, personal channels, sessions, and delivery routes are deleted or archived under the same account lifecycle operation.
- Tenant teardown for self-serve personal tenants follows the same account lifecycle and must not leave orphaned `ClawscaleUser` records.
