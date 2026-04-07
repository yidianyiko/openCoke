# Spec: Unified End-User Identity Between Coke and Clawscale

## Status

Proposed

## Summary

Introduce a new `ClawscaleUser` entity on the Clawscale side and map it 1:1 to a `Coke Account` within a tenant boundary. Each channel-specific `EndUser` will attach to one `ClawscaleUser`, allowing a single Coke user to use multiple channels while preserving Clawscale's existing multi-tenant gateway model.

In plain terms:

- One Coke user can have multiple channels.
- Those channels are represented as multiple `EndUser` records in Clawscale.
- All of those `EndUser` records point to one `ClawscaleUser`.
- That `ClawscaleUser` maps to one Coke account.

## Context

Clawscale is a multi-tenant gateway system with this current hierarchy:

`Tenant -> Channel -> EndUser`

Its current stable identity for a channel-side end user is effectively:

`(tenant_id, channel_id, platform, end_user_id)`

Clawscale also has `Member` accounts for tenant administration, but `Member` is not the same as a business end user. `Member` represents an operator or admin who can log into the gateway console. `EndUser` represents the person talking through a channel such as WeChat, Discord, or Telegram.

Today, cross-channel identity is aggregated mainly on the Coke side through account binding. That works, but it leaves Clawscale without a first-class unified user object for the end user.

This spec adds that missing identity layer.

## Problem Statement

The current model treats each channel-side `EndUser` as an independent identity. That creates three problems:

1. Clawscale has no native unified end-user object.
2. A single Coke user with multiple channels is represented as multiple unrelated gateway identities.
3. The system boundary is harder to reason about because the gateway has channels and end users, but no durable user-level aggregation for the person behind those channels.

We want the model to match the product reality:

- Coke owns the business account.
- Clawscale owns channel access and channel-side user identities.
- One Coke user can connect multiple channels.
- Clawscale should expose one unified end-user identity that groups those channels together.

## Goals

- Introduce a first-class `ClawscaleUser` entity for unified end-user identity.
- Make `ClawscaleUser` map 1:1 to a `Coke Account` within a tenant.
- Allow one `ClawscaleUser` to own multiple `EndUser` records across channels.
- Keep `Tenant` and `Member` semantics unchanged.
- Keep Phase 1 binding explicit rather than automatic.

## Non-Goals

- Automatic identity merging based on heuristics.
- Replacing Clawscale `Member` auth with Coke auth.
- Redesigning channel ingestion or message transport.
- Defining a global cross-tenant identity model.

## Domain Model

### Existing concepts

- `Tenant`: the gateway workspace and isolation boundary.
- `Member`: an operator/admin of a tenant. This is not a chat user.
- `Channel`: a configured gateway integration such as WeChat Personal, Discord, or Telegram.
- `EndUser`: the channel-side user identity detected or created by Clawscale.

### New concept

- `ClawscaleUser`: the unified end-user identity inside Clawscale.

### Target hierarchy

`Tenant -> ClawscaleUser -> EndUser`

Channels remain attached to the tenant and are still the transport layer:

`Tenant -> Channel -> EndUser`

The final model is therefore relational rather than a single strict tree:

- `Tenant` owns `Channel`
- `Tenant` owns `ClawscaleUser`
- `Channel` owns `EndUser`
- `EndUser` belongs to one `ClawscaleUser` once bound

## Identity Semantics

The following identifiers must remain distinct:

- `coke_account_id`: the primary business account identity in Coke
- `clawscale_user_id`: the unified end-user identity in Clawscale
- `end_user_id`: the Clawscale platform's channel-local end-user identifier
- `external_id`: the raw channel identifier from the downstream platform, used when a stable channel-native key is needed

Key rule:

- `end_user_id` and `external_id` remain Clawscale-side channel concepts
- `clawscale_user_id` becomes the Clawscale-side person identity
- `coke_account_id` remains the Coke-side business identity

## Mapping Rules

### Core mapping

- One `Coke Account` maps to one `ClawscaleUser` within the same tenant.
- One `ClawscaleUser` can map to many `EndUser` records.
- One `EndUser` can map to only one `ClawscaleUser` at a time.

### Tenant scope

The 1:1 mapping is tenant-scoped, not global. The uniqueness rule should be:

- unique `(tenant_id, coke_account_id)` on `clawscale_users`

This preserves Clawscale's multi-tenant isolation and avoids accidental cross-tenant coupling.

## Data Model Changes

### New table: `clawscale_users`

Suggested fields:

- `id`
- `tenant_id`
- `coke_account_id`
- `status`
- `created_at`
- `updated_at`

Suggested constraints:

- unique `(tenant_id, coke_account_id)`

### Change to `end_users`

Add:

- `clawscale_user_id` nullable foreign key

Constraints:

- one `EndUser` may reference at most one `clawscale_user_id`
- an unbound `EndUser` has `clawscale_user_id = null`

## Behavioral Rules

### 1. Message ingestion

When a message arrives from a channel:

1. Resolve or create the `EndUser` using the existing channel-side identity tuple.
2. If `EndUser.clawscale_user_id` is set, treat the message as belonging to that unified user.
3. If it is not set, treat the sender as an unbound channel identity.

Message transport remains unchanged. The only difference is that Clawscale can now attach a stable unified user identity when it exists.

### 2. Explicit bind flow

When a user completes account binding with Coke:

1. Authenticate the Coke account on the Coke side.
2. Resolve the target tenant in Clawscale.
3. Find or create `ClawscaleUser(tenant_id, coke_account_id)`.
4. Set `EndUser.clawscale_user_id` to that `ClawscaleUser`.
5. Persist or sync the corresponding Coke-side binding record for compatibility and downstream business use.

Phase 1 remains explicit. The system must not merge identities automatically.

### 3. Add another channel

When the same real person connects through another channel:

1. Clawscale creates a new `EndUser` under that channel as usual.
2. The user completes the same explicit bind flow.
3. The new `EndUser` is attached to the existing `ClawscaleUser`.

Result:

- multiple channels
- one Clawscale unified user
- one Coke account

### 4. Rebind and conflict handling

If an `EndUser` is already bound to a different `ClawscaleUser`, the bind request must fail unless an explicit unlink or transfer flow is performed first.

This protects the invariant that one channel-side identity cannot belong to two business users at the same time.

## System Boundaries

### Clawscale owns

- `Tenant`
- `Member`
- `Channel`
- `EndUser`
- `ClawscaleUser`
- channel transport and delivery

### Coke owns

- `Account`
- character, conversation, relationship, reminder, and other business state
- account login and business authorization
- business-level binding workflows and policies

### Shared contract

The shared contract is the identity mapping:

- `Coke Account <-> ClawscaleUser`
- `ClawscaleUser -> EndUser[]`

## Backward Compatibility

This design should be introduced without breaking the current system.

### Compatibility principles

- Existing `EndUser` creation and message ingestion stay unchanged.
- Existing Coke-side binding records remain valid.
- Existing routing can continue to work during migration, but new code should prefer `clawscale_user_id` once present.

### Migration approach

1. Create `clawscale_users`.
2. Add nullable `end_users.clawscale_user_id`.
3. Backfill `ClawscaleUser` from existing Coke-side bindings.
4. Backfill `EndUser.clawscale_user_id` for already bound identities.
5. Switch read paths to prefer `clawscale_user_id`.
6. Keep legacy link logic only as temporary compatibility behavior if needed.

## Relationship to Existing Link Mechanisms

If Clawscale already has peer-to-peer linking concepts such as `EndUser.linkedTo` or short-lived `LinkCode` flows, they should no longer be the primary identity model.

Recommended direction:

- `ClawscaleUser` becomes the canonical aggregation layer.
- `LinkCode` can remain as a binding mechanism.
- any legacy peer linkage should be treated as transitional and eventually removed or downgraded to compatibility logic.

## API and Event Implications

The exact API shape can be decided later, but the system should expose the following capability:

- resolve the unified `clawscale_user_id` for a channel-side event
- bind an `EndUser` to a `Coke Account`
- query all `EndUser` records for a `ClawscaleUser`

At the event level, downstream services should be able to receive:

- `tenant_id`
- `channel_id`
- `platform`
- `end_user_id`
- `clawscale_user_id` when available
- `coke_account_id` when available through binding context

## Risks and Trade-Offs

### Advantages

- The model matches the product mental model: one user, many channels.
- Clawscale gains a first-class end-user identity instead of relying only on channel identities.
- Coke and Clawscale boundaries become easier to explain and maintain.

### Trade-offs

- There is one more identity object to manage.
- Binding and migration logic becomes more explicit.
- Some existing link logic may need to coexist temporarily during migration.

## Acceptance Criteria

- A Coke user can bind multiple channel identities to one unified Clawscale user.
- A bound `EndUser` always resolves to exactly one `ClawscaleUser`.
- A `ClawscaleUser` always resolves to exactly one Coke account within a tenant.
- `Member` behavior and tenant administration remain unchanged.
- Unbound `EndUser` flows continue to work.
- Existing channel ingestion behavior does not regress.

## Open Decisions

These decisions are intentionally left for implementation planning:

- exact schema naming conventions
- whether `status` is needed in `clawscale_users` for Phase 1
- whether Coke-side compatibility writes are synchronous or asynchronous
- when legacy link fields can be retired

## Final Statement

The target model is:

- Coke business identity: `Account`
- Clawscale unified end-user identity: `ClawscaleUser`
- Clawscale channel identity: `EndUser`

One Coke account maps to one Clawscale user within a tenant, and one Clawscale user can own many channel-side end users. This is the intended meaning of "one Coke user can have multiple channels."
