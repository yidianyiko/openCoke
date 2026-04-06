# ClawScale Personal WeChat Gateway For Coke

## Goal

Use ClawScale as the long-term multi-channel gateway for `coke`, starting with `wechat_personal`, while keeping `coke` as the owner of accounts, business configuration, characters, relationships, reminders, and main conversation workflows.

Phase 1 must deliver a working text-chat path with account binding. Phase 2 can extend the protocol and channel experience without redefining the ownership boundary.

## Design Principles

1. ClawScale is a gateway, not the business brain.
2. `coke` remains the source of truth for main accounts and business state.
3. All channels enter through ClawScale.
4. `coke` receives one normalized input shape regardless of source channel.
5. Binding belongs to `coke`, not to ClawScale.
6. Phase 1 minimizes changes to the current `coke` runtime.
7. Changes should stay upstream-friendly where possible.

## Ownership Boundary

### ClawScale owns

- Tenant
- Channel
- Channel-side end-user identity
- Personal WeChat QR login and message transport
- Channel ingress and reply delivery

### Coke owns

- Main account system
- Phone-number or business-account identity
- Character selection and behavior
- Prompt and business configuration
- Conversation, relation, reminder, and background workflows
- Account binding flow

### Explicit non-goals for Phase 1

- ClawScale owning `coke` accounts
- ClawScale owning `coke` configuration
- Replacing `coke` Mongo-backed runtime
- Adding new business capabilities beyond the current `coke` feature set
- Shipping multimodal support in the first integration slice

## Recommended Architecture

```text
WeChat User
  -> ClawScale wechat_personal channel
  -> ClawScale tenant/channel/end-user
  -> ClawScale custom backend
  -> CokeBridge
  -> ExternalIdentity resolution in coke
  -> binding flow or normalized CokeInput
  -> coke inputmessages/outputmessages main workflow
  -> CokeBridge
  -> ClawScale
  -> WeChat User
```

### Why this architecture

- It preserves ClawScale's long-term value as the gateway layer.
- It avoids forcing `coke` into ClawScale's backend abstraction too early.
- It keeps `coke` business semantics out of ClawScale internals.
- It allows a later migration from a thin bridge to a more formal protocol without invalidating Phase 1.

## Components

### 1. ClawScale `wechat_personal`

Responsibilities:

- QR login
- polling and reply send
- tenant, channel, end-user identity
- forwarding normalized channel messages into the backend route

No `coke` business logic should live here.

### 2. ClawScale backend configuration for `coke`

Phase 1 uses the existing `custom` backend shape, not a new dedicated `coke` backend type.

Responsibilities:

- route tenant/channel traffic to `CokeBridge`
- carry the minimum endpoint and auth config needed to reach the bridge

This avoids an early hard fork of ClawScale's backend model.

### 3. `CokeBridge`

This is the main integration boundary.

Responsibilities:

- accept ClawScale backend requests
- authenticate ClawScale requests with a shared bridge secret
- map ClawScale identities into `coke` external identity records
- decide whether the user is bound
- create a normalized `CokeInput`
- write to `coke`'s current message ingress
- wait for the corresponding `coke` reply
- return plain text to ClawScale

Non-responsibilities:

- account ownership truth
- tenant ownership truth
- character or workflow logic

### 4. `ExternalIdentity` mapping in `coke`

This is how a ClawScale user becomes a `coke` user.

Each record maps one ClawScale-side identity to one `coke` main account.

Recommended fields:

```text
source = "clawscale"
tenant_id
channel_id
platform
external_end_user_id
account_id
status
created_at
updated_at
last_seen_at
is_primary_push_target
```

Uniqueness invariant:

```text
(source, tenant_id, channel_id, platform, external_end_user_id) must be unique
```

One external identity may point to at most one `coke` account at a time.

Recommended statuses:

```text
pending_bind
active
suspended
revoked
```

### 5. Binding flow in `coke`

Binding is a `coke` feature, not a ClawScale feature.

Phase 1 introduces a minimal standalone bind page plus bind APIs owned by `coke`.

Responsibilities:

- issue one-time binding tickets
- authenticate or verify the user using the `coke` main account system
- attach one ClawScale external identity to one `coke` account
- mark the mapping active

### 6. `ClawScaleOutputDispatcher`

Phase 1 needs a dedicated outbound dispatcher for proactive `coke` messages. Request-response waiting in `CokeBridge` is not sufficient for reminders and background outputs.

Responsibilities:

- poll `coke` `outputmessages` for ClawScale-bound proactive messages
- resolve the target ClawScale external identity
- call a ClawScale outbound delivery endpoint
- mark delivery success or failure back into `outputmessages`

Phase 1 therefore requires one minimal ClawScale addition:

- an authenticated outbound delivery endpoint that accepts

```text
tenant_id
channel_id
end_user_id
text
idempotency_key
```

and uses the resolved channel adapter to send a direct outbound message to that ClawScale end-user.

## Identity Model

### Main account model

`coke` keeps its current main account identity model. The canonical user identity is phone-number or business-account based.

### Channel identity model

ClawScale owns channel-local identity:

```text
tenant_id
channel_id
platform
end_user_id
```

### Binding definition

An identity is considered bound only when all of the following are true:

1. an `ExternalIdentity` record exists
2. it points to an existing `coke` main account
3. ownership has been verified
4. its status is `active`

### Cross-channel strategy

The product goal is one `coke` account linked to many ClawScale-side identities. Phase 1 does not require automatic identity merging. It requires explicit binding.

### Push target strategy

Phase 1 supports only one proactive push target per bound account for ClawScale-delivered personal WeChat.

At bind time:

- the bound `ExternalIdentity` becomes `is_primary_push_target = true`
- any previous primary push target for the same account and tenant is cleared

This keeps reminder delivery deterministic in Phase 1.

## Normalized Coke Input

`coke` should not need to care whether a message came from personal WeChat or any future ClawScale channel.

Phase 1 normalized shape:

```text
source
tenant_id
channel_id
platform
external_end_user_id
external_message_id
text
timestamp
metadata
```

This normalized structure is bridge-internal. It can then be translated into the current `coke` message documents.

Phase 1 intentionally excludes channel-specific multimodal semantics.

## Phase 1 Message Flow

### Bound user

```text
1. WeChat user sends text
2. ClawScale receives it through wechat_personal
3. ClawScale routes to CokeBridge
4. CokeBridge resolves ExternalIdentity -> CokeAccount
5. CokeBridge writes a Coke input message
6. Coke poll worker processes the message
7. Coke writes output message(s)
8. CokeBridge waits for the matching reply
9. CokeBridge returns text to ClawScale
10. ClawScale sends reply back to WeChat
```

### Unbound user

```text
1. WeChat user sends text
2. ClawScale routes to CokeBridge
3. CokeBridge finds no active binding
4. Coke issues a one-time BindingTicket
5. CokeBridge returns a bind instruction message
6. User opens the Coke bind page and completes verification
7. ExternalIdentity becomes active
8. Later messages enter the normal chat path
```

### Reply correlation and waiting

Phase 1 uses direct Mongo polling from `CokeBridge`, not oplog tailing, callbacks, or Redis subscription.

Reason:

- it is compatible with the current `coke` runtime
- it avoids adding another transport dependency
- it keeps Phase 1 behavior explicit and easy to test

Concrete rule:

1. `CokeBridge` generates `bridge_request_id`
2. it writes `bridge_request_id` into the input message metadata
3. normal `coke` reply generation already copies the input message metadata into output messages through the existing `send_message_via_context` path
4. `CokeBridge` polls `outputmessages` for:

```text
platform = "clawscale"
status = "pending"
metadata.bridge_request_id = <bridge_request_id>
metadata.delivery_mode = "request_response"
```

5. the first pending text output matching that correlation id is consumed by the bridge
6. the bridge marks that output record handled after returning the reply to ClawScale

Phase 1 request-response metadata contract:

```text
inputmessages.metadata.bridge_request_id
inputmessages.metadata.delivery_mode = "request_response"
```

Because current normal replies already inherit input metadata, no broad `coke` output-pipeline rewrite is required for the synchronous path.

### Proactive and reminder delivery flow

The current `coke` established output path is adapter-specific and does not include ClawScale. Phase 1 therefore introduces a separate proactive push path.

```text
1. coke reminder/background flow emits outputmessage
2. outputmessage is marked for ClawScale push delivery
3. ClawScaleOutputDispatcher polls for that outputmessage
4. dispatcher resolves the account's primary ClawScale external identity
5. dispatcher calls ClawScale outbound delivery endpoint
6. ClawScale delivers text through the wechat_personal adapter
7. dispatcher marks the outputmessage handled or failed
```

Required output metadata for proactive ClawScale delivery:

```text
delivery_mode = "push"
route_via = "clawscale"
tenant_id
channel_id
platform
external_end_user_id
push_idempotency_key
```

This is an intentional targeted `coke` change for proactive flows. It does not contradict the Phase 1 principle of minimizing runtime changes, because the existing runtime does not already have a ClawScale delivery path.

## Binding Flow

Phase 1 uses a standalone minimal bind page owned by `coke`.

Recommended sequence:

```text
1. bridge requests a BindingTicket
2. user receives a bind URL
3. user opens the bind page
4. user authenticates with phone-number or business-account logic owned by coke
5. coke validates the ticket
6. coke writes ExternalIdentity(account_id <- external identity)
7. ticket becomes consumed
8. later messages resolve directly to the main account
```

Recommended `BindingTicket` fields:

```text
ticket_id
tenant_id
channel_id
platform
external_end_user_id
purpose = "bind_account"
status
expires_at
created_at
consumed_at
```

Ticket statuses should at least support:

```text
pending
consumed
expired
revoked
```

Ticket abuse controls for Phase 1:

- one active unexpired bind ticket per external identity
- repeated unbound messages should reuse the current active ticket instead of minting a new one
- ticket issuance should be rate-limited per external identity
- recommended initial limits:

```text
minimum reissue interval = 60 seconds
maximum new tickets per external identity per hour = 5
```

When throttled, the bridge should return the existing bind URL if one is still valid, or a short retry-later message if not.

### Unbinding and account lifecycle

If a `coke` account is deleted, suspended, or explicitly unbound:

- all linked active `ExternalIdentity` records for that account become `suspended` or `revoked`
- `is_primary_push_target` is cleared
- future inbound messages from those identities do not enter normal chat
- the bridge returns a bind-again or account-unavailable flow depending on account state

Phase 1 does not require a full end-user self-service unbind UI, but it does require the lifecycle rule above to be explicit in the data model and implementation plan.

## Existing Coke Capabilities That Must Be Preserved

Phase 1 must keep the following existing `coke` behavior:

1. private text chat
2. persona, relation, and conversation continuity
3. reminder and background proactive flows

Phase 1 may postpone:

1. multimodal support
2. channel-specific attachment semantics
3. cross-channel UX enhancements beyond binding

## Why Mongo stays in Phase 1

`Redis` is optional for the integration path. `Mongo` is not.

The current `coke` runtime still relies on Mongo for:

- input and output message storage
- conversations
- relations
- lock management
- reminder and background workflow state

Therefore Phase 1 should preserve Mongo-backed processing and may run `coke` in poll mode instead of Redis-triggered mode if needed.

## Error Handling

### Bridge-level errors

- invalid request auth
- malformed payload
- ClawScale message timeout
- duplicate delivery

Bridge response should be safe, short, and text-only for Phase 1.

### Binding errors

- invalid ticket
- expired ticket
- already consumed ticket
- account verification failure

These should return a user-safe bind failure message plus a retry path.

### Coke processing errors

- worker timeout
- no reply within deadline
- workflow failure

The bridge should surface a gateway-safe fallback reply, not raw stack traces.

## Bridge Authentication

Phase 1 bridge authentication is a shared secret carried in the standard HTTP `Authorization` header:

```text
Authorization: Bearer <COKE_BRIDGE_API_KEY>
```

Why this choice:

- it matches ClawScale's current `custom` backend auth model
- it avoids introducing JWT signing and verification in Phase 1
- it is sufficient for one bridge service behind self-managed infrastructure

The bridge must reject requests with missing or incorrect bearer tokens.

## Timeout and Correlation Strategy

Phase 1 needs a stable way to correlate one ClawScale request to one `coke` reply, and a separate route for proactive push delivery.

Recommended correlation keys:

```text
bridge_request_id
external_message_id
normalized input message id
```

The bridge should:

- persist or pass a correlation id into the `coke` input message metadata
- wait by polling Mongo `outputmessages` for an output message matching that correlation id
- stop waiting after a bounded timeout

If `coke` emits multiple output messages, Phase 1 should define one conservative rule. Recommended:

- first completed text reply wins for bridge response
- reminders and proactive outputs use the dedicated ClawScale push path described above

## Deployment Shape

Repository layout remains:

```text
/data/projects/coke
  /gateway                    # ClawScale sub-system
  /agent                      # existing workflow/business runtime
  /connector/clawscale_bridge # proposed bridge and outbound dispatcher
  /dao                        # existing state/storage layer
```

Runtime shape:

- ClawScale runs as its own service
- `coke` runs as its own service
- `CokeBridge` and `ClawScaleOutputDispatcher` run as their own service or lightweight process adjacent to `coke`

This preserves service boundaries even in one repository.

## Testing Strategy

### Phase 1 automated tests

Required automated coverage:

1. ClawScale-style request -> bridge normalization
2. unbound identity -> bind ticket generation
3. bind ticket reuse and rate limiting
4. successful bind ticket consumption -> ExternalIdentity creation
5. bound identity -> `coke` input write
6. bridge correlation -> `coke` output read -> reply return
7. proactive output -> dispatcher -> ClawScale outbound delivery
8. timeout, duplicate, and auth handling

### Manual-only step that remains unavoidable

Live personal WeChat QR login requires at least one real human scan against the external platform.

Everything else should be built so it can be tested without manual WeChat interaction by simulating the ClawScale backend request shape.

## Phase 2 Evolution

Phase 2 can add:

- multimodal input and output
- better cross-channel account-link UX
- stronger bridge protocol
- upstreamable ClawScale improvements if custom backend abstraction proves insufficient
- gradual reduction of `coke`'s dependence on current message-store coupling

Phase 2 must not change the ownership boundary:

- ClawScale remains the gateway
- `coke` remains the business system of record

## Decision Summary

Final decisions captured by this design:

1. ClawScale stays in the repository as a long-term gateway sub-system.
2. ClawScale owns channel, tenant, and gateway concerns only.
3. `coke` owns accounts, business config, and business state.
4. Personal WeChat is the first channel.
5. A thin `CokeBridge` is the Phase 1 integration boundary.
6. Binding is explicit and owned by `coke`.
7. The first binding UX is a standalone minimal bind page.
8. `coke` sees one normalized input shape regardless of source channel.
9. Request-response replies use Mongo polling plus `bridge_request_id` metadata propagation.
10. Proactive outputs use a separate ClawScale outbound dispatcher path.
11. Phase 1 preserves current `coke` behavior and avoids broad refactors.
