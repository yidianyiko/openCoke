# Spec: Per-User `wechat_personal` Channel for Coke and Clawscale

## Status

Proposed

## Summary

Replace the current tenant-shared `wechat_personal` onboarding model with a per-user model.

In v1:

- each `Coke Account` maps 1:1 to one `ClawscaleUser`
- each `ClawscaleUser` belongs to exactly one `Tenant`
- each `ClawscaleUser` may manually create their own personal `wechat_personal` channel
- the login QR shown to the user is the QR for that user's own iLink-backed WeChat channel
- inbound and outbound routing for that channel are owned by the channel's `ClawscaleUser`, not by a tenant-shared bind flow

This v1 changes only `wechat_personal`. Other channel types may later adopt the same personal-channel model, but are out of scope for this document.

## Why This Change Is Required

The current implementation treats `wechat_personal` as a tenant-level shared gateway channel and then binds channel-side identities back to a Coke account. That model is not correct for the intended product.

The intended product behavior is:

- a user registers or signs in to Coke
- the user manually creates their own WeChat channel from the Coke web UI
- the user scans a QR code for their own WeChat login
- that WeChat login belongs to that user, not to the whole tenant
- the user can later add more personal channels of other types

This is also consistent with the upstream OpenClaw / Weixin channel model:

- the official `@tencent-weixin/openclaw-weixin` package documents `openclaw channels login --channel openclaw-weixin`
- its README states that each login creates a new account entry and that multiple WeChat accounts can be online at the same time
- OpenClaw documentation also uses account-scoped session and pairing behavior for multi-account channels

That means the product and protocol assumptions are account-scoped, not tenant-shared.

## Problem Statement

The current tenant-shared `wechat_personal` model creates a structural mismatch:

1. `wechat_personal` is modeled as a shared tenant resource.
2. Coke users are expected to trial and use the product with their own WeChat accounts.
3. The current bind flow links a user to a shared channel-side identity instead of giving the user a personal channel.
4. This makes ownership, login state, and future channel expansion ambiguous.

The issue is not just terminology. The issue is that channel ownership is modeled incorrectly for this product shape.

## Goals

- Define one unified user model across Coke and Clawscale.
- Make `Coke Account` and `ClawscaleUser` strictly 1:1.
- Keep `Member` as a separate operator/admin identity.
- Make `wechat_personal` a personal channel owned by one `ClawscaleUser`.
- Make the user-facing QR flow create or connect that personal channel.
- Remove tenant-shared `wechat_personal` from the primary user onboarding path.
- Preserve room for future personal channels such as Telegram or Discord.
- Preserve room for future tenant-shared channels where that model is actually appropriate.

## Non-Goals

- Generalizing all channels to the new model in v1.
- Redesigning `Member` authentication.
- Redesigning Coke business state such as characters, conversations, reminders, or relationships.
- Defining the final v2 design for every future channel type.
- Solving cross-tenant identity federation.

## Unified Domain Model

### Tenant

A `Tenant` is the organizational and isolation boundary.

It owns:

- operator/admin resources
- tenant-wide configuration
- billing and deployment boundaries
- all `ClawscaleUser` records that live inside that workspace

Every `ClawscaleUser` must belong to exactly one `Tenant`.

#### Auto-created personal tenants

For self-serve individual users who are not invited into an existing tenant, the system automatically creates a personal tenant. The rules are:

- **Trigger:** on first `Coke Account` creation, if and only if the registration flow does not carry an invitation into an existing tenant.
- **Naming:** the personal tenant is marked with an internal flag (e.g. `kind = personal`) so it can be distinguished from team tenants in operator tooling and billing.
- **Operator identity:** an auto-created personal tenant has no `Member` records initially. The end user does not become a `Member` of their own personal tenant in v1. Dashboard/admin access for personal tenants is out of scope and may be added later.
- **Atomicity:** tenant creation, `Coke Account` creation, and `ClawscaleUser` creation for self-serve registration must succeed as a single transactional unit. If any step fails, all three are rolled back and the user is asked to retry. Partial state (e.g. a Coke Account with no ClawscaleUser) is not a legal state.

### Member

A `Member` is a back-office operator or administrator.

A `Member`:

- logs into the dashboard
- manages tenant settings and operational resources
- is not the end-user chat identity

`Member` remains separate from Coke user accounts.

The same human may later hold both identities:

- a `Coke Account` as an end user
- a `Member` as an operator

If that happens, they remain distinct records with distinct authentication and authorization paths. Holding one identity must not imply the privileges or ownership of the other.

### Coke Account

A `Coke Account` is the business-side primary user identity.

It is:

- created and maintained by Coke
- the account a real end user registers and logs into
- the owner of business state in Coke
- **scoped to exactly one `Tenant`**

Cross-tenant identity federation — the same human holding accounts in multiple tenants — is explicitly out of scope (see Non-Goals). If the same person registers into two tenants, those are two distinct `Coke Account` records, each with its own `ClawscaleUser`. This is what makes the 1:1 mapping below a hard invariant rather than an eventual property.

### ClawscaleUser

A `ClawscaleUser` is the gateway-side unified end-user identity.

It is:

- created and maintained by Clawscale
- mapped 1:1 to a `Coke Account`
- the owner of personal channels in Clawscale

The mapping rule is strict:

- one `Coke Account` maps to one `ClawscaleUser`
- one `ClawscaleUser` maps to one `Coke Account`

#### Creation lifecycle

`ClawscaleUser` is created **eagerly**, atomically with the `Coke Account` it belongs to. Specifically:

- Self-serve registration: tenant (if auto-created), `Coke Account`, and `ClawscaleUser` are created in a single transactional unit.
- Invited registration into an existing tenant: `Coke Account` and `ClawscaleUser` are created in a single transactional unit; the tenant already exists.
- A `Coke Account` without a corresponding `ClawscaleUser` is not a legal state at any point in time. Code paths downstream of registration may assume the `ClawscaleUser` already exists and must not lazily create one.

This makes the 1:1 mapping a true invariant rather than an eventual property and removes a class of races between registration and the first `POST /user/wechat-channel` call.

### Channel

A `Channel` remains the gateway transport resource, but channels now have explicit ownership scope.

A channel can be one of two ownership types:

- `tenant_shared`: owned by the tenant
- `personal`: owned by one `ClawscaleUser`

In v1:

- `wechat_personal` must use `personal` ownership for the user-facing Coke flow
- tenant-shared `wechat_personal` is legacy only and must not be used as the primary onboarding path

### EndUser

An `EndUser` remains a channel-local peer identity.

In the new model, `EndUser` is no longer the primary object that determines which Coke user owns a `wechat_personal` connection.

Instead:

- channel ownership determines which `ClawscaleUser` and `Coke Account` own the channel
- `EndUser` remains useful for peer-level message routing and conversation isolation inside that channel

For personal channels, `EndUser` should be treated as a peer/contact/session-side identity, not as the primary business-account binding object.

## Ownership Rules

### Core mapping

- `Coke Account` <-> `ClawscaleUser` is 1:1
- `ClawscaleUser` -> many personal channels
- `Tenant` -> many `ClawscaleUser`
- `Tenant` -> many tenant-shared channels

### v1 channel rule for WeChat

- each `ClawscaleUser` may have at most one `wechat_personal` personal channel
- that channel is owned by the `ClawscaleUser`
- its login state, token, and QR flow are private to that user

#### Channel lifecycle and uniqueness

For v1 `wechat_personal`, the user-visible lifecycle is:

- `missing`: no channel row exists yet for this user and type
- `disconnected`: channel row exists but no live iLink login is active
- `pending`: QR login is in progress
- `connected`: iLink login is active
- `error`: the most recent connect attempt or session health check failed
- `archived`: channel has been intentionally retired and must not be used for routing

Legal transitions:

- `missing -> disconnected`: user creates their personal WeChat channel
- `disconnected -> pending`: user starts or restarts QR login
- `pending -> connected`: QR scan and phone confirmation succeed
- `pending -> error`: QR flow times out or iLink rejects the login session
- `connected -> disconnected`: user explicitly disconnects, or iLink login is invalidated remotely
- `error -> pending`: user retries the connection flow
- `disconnected -> archived`: user deletes the channel
- `error -> archived`: user deletes the broken channel instead of retrying
- `connected -> archived`: only after an explicit disconnect/revoke step clears the live login

For uniqueness, `active` means any non-archived row. The invariant is therefore:

- at most one non-archived personal `wechat_personal` channel per `ClawscaleUser`

If a user wants to abandon a broken or stale channel and create a fresh one, the old row must first transition to `archived`. A `disconnected` or `error` channel may either be reused via reconnect, or archived and replaced.

### Future extensibility

Future channel types may choose one of these modes:

- personal-only
- tenant-shared-only
- both

But that decision is per channel type. It is not globally fixed for all channels.

## Product Flows

### Flow A: Personal self-serve Coke user

1. User registers or signs in to Coke.
2. Coke resolves the user's `Coke Account`.
3. The system resolves or creates the matching `ClawscaleUser`.
4. The user opens the Coke WeChat setup page.
5. The page shows a manual action such as `Create my WeChat channel`.
6. When clicked, the system creates or reuses that user's personal `wechat_personal` channel.
7. The system starts the iLink QR login flow for that personal channel.
8. The page displays the login QR for that user's own WeChat channel.
9. The user scans and confirms on their phone.
10. The personal channel becomes connected.
11. Future inbound and outbound traffic on that channel are owned by that user's `ClawscaleUser` and `Coke Account`.

This is the primary v1 user journey.

### Flow B: Dashboard operator

1. An operator signs in as a `Member`.
2. The operator manages the tenant, users, support views, or operational tooling.
3. The operator does not act as the user's chat identity.

This flow stays separate.

## Data Model Changes

## `clawscale_users`

Keep `clawscale_users` as the gateway-side unified user table.

Suggested invariant:

- unique `(tenant_id, coke_account_id)`

If Coke account IDs are globally unique in practice, that remains compatible, but tenant scoping should stay explicit in the schema.

## `channels`

Extend `channels` with ownership metadata.

Suggested new fields:

- `scope`: enum
  - `tenant_shared`
  - `personal`
- `owner_clawscale_user_id`: nullable foreign key to `clawscale_users.id`

Suggested invariants:

- if `scope = personal`, `owner_clawscale_user_id` is required
- if `scope = tenant_shared`, `owner_clawscale_user_id` is null
- for `wechat_personal`, user-facing v1 creation must always create `scope = personal`

Suggested uniqueness rule for v1:

- at most one non-archived personal `wechat_personal` channel per `owner_clawscale_user_id`

This may be enforced with an application invariant first, then tightened with a database constraint if needed.

#### iLink credential storage

In v1, durable iLink login credentials for `wechat_personal` continue to live on the owned `channels` row, inside channel-scoped config/credential fields, because that is the smallest migration from the current implementation. Runtime processes may cache those credentials in memory, but the durable source of truth remains the owned channel record.

This spec does not introduce a separate `channel_sessions` or `channel_credentials` table in v1. If a future security hardening pass extracts credentials into a dedicated store, that should preserve the same ownership model and API semantics.

## `end_users`

No major semantic expansion is required for v1.

`EndUser` stays channel-local.

The important semantic change is ownership:

- ownership of a personal `wechat_personal` channel is determined by `Channel.owner_clawscale_user_id`
- not by binding the Coke user to a tenant-shared `EndUser`

## Routing Rules

### Inbound routing for personal `wechat_personal`

For a personal WeChat channel:

1. Resolve the channel.
2. Read `owner_clawscale_user_id` from the channel.
3. Resolve the mapped `coke_account_id` from `ClawscaleUser`.
4. Route the message to that Coke account.
5. Continue using channel-local `EndUser` information for peer/session isolation as needed.

This means the account owner is derived from channel ownership, not from a bind ticket against a shared channel.

### Legacy routing for `tenant_shared` channels

Routing for `tenant_shared` channels is unchanged from the current behavior and is out of scope for this spec, except that new Coke self-serve WeChat onboarding must not use that path.

This includes any legacy shared `wechat_personal` records that remain during migration. They continue to route through the current shared-channel logic until explicitly reset or retired.

### Outbound routing for personal `wechat_personal`

For a personal WeChat channel:

- outbound delivery uses the user's own connected personal channel
- the channel token and iLink session belong to that user's channel record

If the channel is `disconnected`, `error`, or `archived`, outbound delivery must fail fast with a channel-state error and must not silently fall back to another user's channel or to a tenant-shared WeChat channel.

### Disconnect behavior and in-flight traffic

If a personal `wechat_personal` channel is disconnected while traffic is active:

- the runtime stops long-polling iLink for new updates as soon as the disconnect is observed
- any inbound message batch already fetched before the disconnect may complete one final processing pass
- inbound messages arriving after the disconnect are ignored until the user reconnects
- outbound sends issued after the disconnect fail with a reconnect-required error

## API / Service Changes

### Coke-facing user API

The user-facing Coke web flow should stop pretending that binding is only an external identity link.

Instead, it should expose a user-owned channel lifecycle.

Suggested behavior:

- `POST /user/wechat-channel`
  - create or reuse the caller's personal `wechat_personal` channel
- `POST /user/wechat-channel/connect`
  - start or refresh the QR login session for that channel
- `GET /user/wechat-channel/status`
  - return channel state: `missing | disconnected | pending | connected | error | archived`
  - if `pending`, return the QR or connect URL needed by the page
- `POST /user/wechat-channel/disconnect`
  - revoke the live login and move the channel to `disconnected`
- `DELETE /user/wechat-channel`
  - archive the channel so the user may later create a fresh one

The exact path names may vary, but the semantics should be channel lifecycle, not just bind-session lifecycle.

The path is WeChat-specific in v1. The intended long-term generalization is:

- `POST /user/channels/{type}`
- `POST /user/channels/{type}/connect`
- `GET /user/channels/{type}/status`

New personal channel types should extend that generalized shape rather than adding more singular endpoints.

### Gateway internal API

Gateway should expose internal authenticated operations for:

- resolve or create the caller's personal `wechat_personal` channel
- start QR login for that channel
- fetch current QR/status for that channel
- disconnect or archive that personal channel

### Existing bind-session service

The current `WechatBindSessionService` is designed around binding a Coke account to a shared channel-side identity.

That should no longer be the primary model for v1 WeChat onboarding.

It may be:

- removed for `wechat_personal` personal onboarding
- or narrowed to legacy compatibility only

### Observability naming

The user-facing API and UI should rename the flow from `bind` to `channel lifecycle`.

In v1, internal logs, metrics, and events may keep existing bind-oriented names where needed for continuity, but any event emitted by the new personal-channel flow must include enough ownership context to disambiguate the new model, at minimum:

- `tenant_id`
- `clawscale_user_id`
- `coke_account_id`
- `channel_type`
- `channel_scope`
- `channel_lifecycle_action`

Full observability renaming is out of scope for this spec.

## UI Changes

### Coke user web

The Coke user page should change from `bind your WeChat identity` to `create and connect your WeChat channel`.

Recommended page states:

- no channel yet
  - show `Create my WeChat channel`
- channel exists but disconnected
  - show `Connect WeChat`
- channel pending
  - show live QR and pending status
- channel connected
  - show connected state and reconnect / disconnect actions
- channel error
  - show reconnect and delete actions
- channel archived
  - show `Create my WeChat channel` again

The QR on this page must be the QR for the user's own personal WeChat channel.

### Dashboard

Dashboard may still show the user's personal channel for support or diagnostics, but the user-facing creation flow should live in Coke web, not in the admin dashboard.

## Compatibility and Migration

### Existing shared WeChat path

Current tenant-shared `wechat_personal` onboarding should be treated as legacy.

For v1 rollout:

- stop using shared `wechat_personal` channels for new Coke user onboarding
- stop treating shared-channel `EndUser` binding as the primary ownership path for WeChat

### Existing bindings

The migration policy may be intentionally hard-reset for WeChat if that is operationally simpler.

That means:

- old shared-channel WeChat bindings may be discarded
- users may be required to create and reconnect their own personal WeChat channels

This is acceptable because the current model is not the correct long-term product shape.

Because this is destructive, rollout requires:

- an explicit operator confirmation gate before the reset job runs
- a one-time user-facing notice that existing shared WeChat bindings will be retired
- a documented statement that there is no rollback to the legacy shared-binding path after the reset is committed

The current reset entrypoint must fail fast unless the operator has explicitly set
`ALLOW_WECHAT_PERSONAL_RESET=yes`. That gate is the operational control that prevents
accidental execution of the destructive migration.

There is no supported product rollback after the reset is committed. If the legacy
shared-bind path ever needs to be recovered, that must happen through a forward migration
or a data restore, not by toggling the system back to the old ownership model.

### Legacy data usage

`external_identities` remains in the system for historical and compatibility reasons, but for personal `wechat_personal` ownership it must not remain the primary source of truth.

Primary source of truth for ownership becomes:

- `channel.owner_clawscale_user_id`
- and the 1:1 mapping from `ClawscaleUser` to `Coke Account`

Policy for v1:

- personal `wechat_personal` flow performs no new ownership writes to `external_identities`
- legacy shared WeChat flow may continue reading existing `external_identities` data during migration
- removal of legacy `external_identities` usage outside shared-flow compatibility is out of scope for this spec

### Account deletion

If a `Coke Account` is deleted:

- the matching `ClawscaleUser` is archived in the same operation
- all personal channels owned by that `ClawscaleUser` are archived in the same operation
- any live iLink login on those channels is revoked or forgotten before archival completes
- archived channels are removed from inbound and outbound routing

No orphaned active personal channels are allowed to outlive the owning `Coke Account`.

## Security and Isolation Invariants

- one user's WeChat login must never be shared with another user's Coke account
- one personal `wechat_personal` channel belongs to exactly one `ClawscaleUser`
- `Member` credentials must never imply ownership of a user's personal channel
- a `Member` of tenant A must not see or manage personal channels owned by `ClawscaleUsers` in tenant B
- personal channel tokens must be stored and used only in the context of that owned channel
- message routing must derive account ownership from channel ownership, not from ambiguous tenant-level shared state

## Acceptance Criteria

1. A user can sign in to Coke and manually create their own `wechat_personal` channel.
2. The QR shown to the user is the QR for that user's own WeChat login session.
3. Scanning that QR connects a personal channel owned by that user.
4. Two different Coke users can each connect different WeChat accounts without sharing channel state.
5. One user's channel login cannot be reused by another user.
6. `Member` remains a separate dashboard-only operator identity.
7. The primary WeChat onboarding path no longer depends on binding a Coke account to a tenant-shared WeChat `EndUser`.
8. A user can disconnect their personal `wechat_personal` channel and later reconnect it.
9. A user can archive a broken or stale personal `wechat_personal` channel and then create a fresh one.
10. Deleting a `Coke Account` archives its matching `ClawscaleUser` and all owned personal channels.
11. The design leaves room for future channel types to be personal, shared, or both.

## Decision Summary

The system should be modeled as:

- `Tenant` = organization / isolation boundary
- `Member` = operator/admin identity
- `Coke Account` = business user identity
- `ClawscaleUser` = gateway-side unified user, 1:1 with `Coke Account`
- `wechat_personal` in v1 = personal channel owned by `ClawscaleUser`
- `EndUser` = peer/session identity inside a channel, not the primary owner binding object

This is the correct model for iLink-backed per-user WeChat onboarding.
