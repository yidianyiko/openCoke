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
```

### 5. Binding flow in `coke`

Binding is a `coke` feature, not a ClawScale feature.

Phase 1 introduces a minimal standalone bind page plus bind APIs owned by `coke`.

Responsibilities:

- issue one-time binding tickets
- authenticate or verify the user using the `coke` main account system
- attach one ClawScale external identity to one `coke` account
- mark the mapping active

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

## Timeout and Correlation Strategy

Phase 1 needs a stable way to correlate one ClawScale request to one `coke` reply.

Recommended correlation keys:

```text
bridge_request_id
external_message_id
normalized input message id
```

The bridge should:

- persist or pass a correlation id into the `coke` input message metadata
- wait for an output message matching that correlation id
- stop waiting after a bounded timeout

If `coke` emits multiple output messages, Phase 1 should define one conservative rule. Recommended:

- first completed text reply wins for bridge response
- reminders and proactive outputs remain owned by `coke` and delivered through the established output path

## Deployment Shape

Repository layout remains:

```text
/data/projects/coke
  /gateway      # ClawScale sub-system
  /coke code    # existing business brain
  /bridge code  # new integration layer
```

Runtime shape:

- ClawScale runs as its own service
- `coke` runs as its own service
- `CokeBridge` runs as its own service or lightweight process adjacent to `coke`

This preserves service boundaries even in one repository.

## Testing Strategy

### Phase 1 automated tests

Required automated coverage:

1. ClawScale-style request -> bridge normalization
2. unbound identity -> bind ticket generation
3. successful bind ticket consumption -> ExternalIdentity creation
4. bound identity -> `coke` input write
5. bridge correlation -> `coke` output read -> reply return
6. timeout and duplicate handling

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
9. Phase 1 preserves current `coke` behavior and avoids broad refactors.
