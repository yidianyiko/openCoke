# Spec: Eyun/Ecloud Shared WeChat Channel for Coke

## Status

Proposed, awaiting written-spec review.

## Summary

Add a shared-channel gateway integration named `wechat_ecloud` so Coke can use
the Eyun/Ecloud WeChat service for the same ordinary messaging surface that the
old private GitHub `yidianyiko/coke` repository provided through
`connector/ecloud`.

This is a gateway shared-channel integration, not a login/session-management
feature. It must follow the current `whatsapp_evolution` shape:

- inbound webhooks enter gateway
- gateway normalizes the sender and message
- `routeInboundMessage()` provisions or reuses the shared-channel customer
- replies and proactive output use the current ClawScale delivery route model

The integration must not reintroduce a direct Coke-worker connector that writes
Mongo `inputmessages` or polls Mongo `outputmessages` outside ClawScale.

## Confirmed Sources

### Old GitHub `coke` behavior

The old private GitHub repository `yidianyiko/coke` has Ecloud code on the
full-code branches such as `origin/coke-scheduler`:

- `connector/ecloud/ecloud_input.py`
- `connector/ecloud/ecloud_adapter.py`
- `connector/ecloud/ecloud_api.py`
- `connector/ecloud/ecloud_output.py`

The old connector supported these normal message capabilities:

- inbound private text, Ecloud `messageType = "60001"`
- inbound private quote/reference, Ecloud `messageType = "60014"`
- inbound private voice, Ecloud `messageType = "60004"`, converted to text by
  downloading the voice file and running ASR
- inbound private image, Ecloud `messageType = "60002"`, converted to text by
  downloading the image and running image-to-text
- outbound text, voice, and image

The old repository also had a hardcoded Moments command path that called
`snsSendImage`, but that was not part of the ordinary inbound/outbound message
channel.

### Current Eyun documentation

The current Eyun docs are served from `https://wkteam.cn/`.

Relevant message APIs from the current docs:

- base API examples use `https://api.geweapi.com`
- API auth uses the `X-GEWE-TOKEN` header
- text send uses `POST /gewe/v2/api/message/postText`
- image send uses `POST /gewe/v2/api/message/postImage`
- file send uses `POST /gewe/v2/api/message/postFile`
- video send uses `POST /gewe/v2/api/message/postVideo`
- callback configuration can be set in the console or through
  `/gewe/v2/api/login/setCallback`

The docs also include QR-code and login APIs, but this integration explicitly
does not use them.

## Goals

- Add a channel type named `wechat_ecloud`.
- Let platform admins create a shared `wechat_ecloud` channel and bind it to a
  shared agent.
- Accept Eyun/Ecloud message callbacks for an already-provisioned `appId`.
- Route ordinary private WeChat text and reference messages into the same
  shared-channel customer provisioning path as `whatsapp_evolution`.
- Preserve old Coke's Ecloud message semantics in the design without copying
  the old Mongo connector architecture.
- Send ordinary outbound text through Eyun/Ecloud using the current
  `/api/outbound` text-only contract.
- Keep all login, QR-code, reconnect, and session lifecycle behavior outside
  this implementation.
- Keep `snsSendImage` / Moments publishing outside this implementation.

## Non-Goals

- QR-code login, dialog login, reconnect, or account lifecycle UI.
- A gateway-owned WeChat session.
- Direct writes to `inputmessages` or direct polling of `outputmessages`.
- Group chat support.
- Moments / `snsSendImage` publishing.
- Expanding the current `/api/outbound` schema beyond text in the first
  implementation.
- Moving ASR or image-to-text dependencies into gateway unless a later plan
  explicitly designs that runtime boundary.
- Changing shared-channel claim, merge, or deletion semantics for `unclaimed`
  customers.

## Approaches Considered

### Approach A: Text-first shared-channel adapter

Add `wechat_ecloud` as a normal ClawScale shared channel. Route text and
reference callbacks into `routeInboundMessage()` and send outbound text through
Eyun `postText`. Preserve voice/image parsing as a designed extension point,
but do not broaden the outbound contract in the first implementation.

Pros:

- matches `whatsapp_evolution`
- stays inside the current ClawScale architecture
- avoids moving AI media processing into gateway prematurely
- keeps the first patch reviewable

Cons:

- old Coke's voice/image conversion is not fully restored in the first patch
- outbound voice/image remains a follow-up

Decision: recommended.

### Approach B: Full old Ecloud connector parity immediately

Implement text, reference, voice, image, outbound media, and the old media
conversion behavior in one pass.

Pros:

- closest to the old GitHub `coke` connector's broadest message surface

Cons:

- requires changing `/api/outbound`, bridge output contracts, gateway media
  fetch behavior, ASR/image-to-text runtime ownership, and tests together
- couples gateway to AI/media dependencies that are currently worker concerns
- larger blast radius than needed to add the WeChat shared channel

Decision: reject for the first implementation; keep as phase 2.

### Approach C: Port the old Python connector into this repo

Run a new Python Ecloud service that writes `inputmessages` and polls
`outputmessages` like old `coke`.

Pros:

- superficially close to the old code

Cons:

- bypasses ClawScale shared-channel provisioning
- duplicates outbound delivery routing
- reintroduces platform-specific worker connectors that the current
  architecture removed
- cannot behave like `whatsapp_evolution`

Decision: reject.

## Recommended Design

### Channel Type

Add `wechat_ecloud` consistently to the gateway channel type surfaces:

- Prisma `ChannelType`
- generated migration
- shared package `ChannelType`
- admin channel kind validation
- shared-channel admin create/detail UI options
- any tests or schema guards that enumerate channel kinds

The channel must be managed as a shared channel. It should not be exposed as a
customer-managed personal WeChat flow.

### Stored Config

Per-channel stored config should contain the channel-specific Eyun values:

```json
{
  "appId": "existing-eyun-app-id",
  "token": "eyun-api-token",
  "webhookToken": "random-gateway-secret",
  "baseUrl": "https://api.geweapi.com"
}
```

`baseUrl` may default to `https://api.geweapi.com` if omitted. `webhookToken`
is generated by gateway and must not be mutable through normal patch requests.
Gateway-generated webhook tokens must use at least 128 bits of randomness.

Browser-visible config must mask secrets. Admin detail responses may show
`appId`, `baseUrl`, and whether a webhook token exists, but not the raw
`token` or `webhookToken`.

Secret hygiene requirements:

- compare callback tokens with a constant-time comparison after validating both
  values are non-empty strings
- never log the raw callback URL, raw `token`, or raw `webhookToken`
- allow admins to regenerate `webhookToken` while disconnected if rotation is
  needed
- treat any token mismatch as a rejected request without revealing which part
  of the URL was wrong

### Connect / Disconnect

Because the user explicitly does not want QR-code login support,
connect/disconnect must not call QR or session APIs.

The recommended first implementation treats connect/disconnect as gateway
routing state:

- `connect` validates config, ensures a webhook token, and marks the channel
  `connected`
- `disconnect` marks the channel `disconnected`
- the UI displays the callback URL the operator should configure in Eyun

The first implementation will not call Eyun callback registration APIs. That
keeps login-namespace APIs out of scope even when they are only used for
callback configuration.

The callback URL shape should be:

```text
/gateway/ecloud/wechat/:channelId/:token
```

### Inbound Callback

Add a route equivalent in shape to the existing Evolution route:

```text
POST /gateway/ecloud/wechat/:channelId/:token
```

The route must:

- load the channel by `channelId`
- require `type = wechat_ecloud`
- require `status = connected`
- compare path `token` with stored `webhookToken` using the secret hygiene
  rules above
- parse the callback body defensively
- route only callbacks where `messageType` is one of the phase-1 supported
  private message types
- route only callbacks where `data.self === false`; if `self` is missing or
  not boolean, ignore the callback
- route only callbacks with non-empty string `data.fromUser` and `data.toUser`
- treat any `fromUser`, `toUser`, or chat target containing `@chatroom` as
  group traffic and ignore it in the first implementation
- ignore unsupported message types
- deduplicate before calling `routeInboundMessage()` using a stable inbound key
  derived from `channelId` plus `data.newMsgId` when present, otherwise
  `data.msgId`; duplicate callbacks return `{ ok: true }` without re-routing
- always return quickly with JSON `{ ok: true }` after accepting or ignoring
  a well-formed callback so Eyun does not retry harmless unsupported events

For private text (`60001`):

- external id: `data.fromUser`
- display name: best available callback nickname if present; otherwise the
  external id
- text: `data.content`
- meta: include `platform: "wechat_ecloud"`, `appId`, `messageType`, `msgId`,
  `newMsgId`, `toUser`, `fromUser`, and timestamp fields if present

For private reference (`60014`):

- parse the XML content defensively with external entity resolution disabled,
  bounded input size, and known-field extraction only
- route the visible user message as text
- preserve quote metadata under `meta.reference`
- if `routeInboundMessage()` has no structured quote field, prefix or append
  enough quote context to the routed text for the agent to understand the
  reference
- if XML parsing fails, route the visible title/content text when safe and add
  `meta.referenceParseError = true`; do not fail the webhook solely because the
  quoted XML was malformed

For private voice (`60004`) and image (`60002`) in phase 1:

- do not fail the webhook
- log the message ids and message type with an explicit unsupported-media
  reason
- return `{ ok: true }` without routing the event to the agent

Full voice ASR and image-to-text require a separate phase because the old
connector used worker-side media tools that do not currently belong to gateway.

### Outbound Text

Add an Eyun/Ecloud API client in gateway with a focused method:

```text
sendText(appId, toWxid, content)
```

The client must call:

```text
POST /gewe/v2/api/message/postText
X-GEWE-TOKEN: <token>
{
  "appId": "...",
  "toWxid": "...",
  "content": "..."
}
```

Add a `wechat_ecloud` case to `deliverOutboundMessage()`. It should:

- assert the channel is connected
- parse and validate the stored config
- use `externalEndUserId` as `toWxid`
- send the current text payload through `postText`
- treat Eyun delivery as successful only when the HTTP response is successful
  and the provider body indicates success, for example `ret = 200`
- throw on HTTP failures, timeouts, invalid JSON, or application-level Eyun
  errors so `OutboundDelivery` records failures through the existing gateway
  path

### Identity And Provisioning

`wechat_ecloud` should reuse the existing shared-channel provisioning model.
New WeChat senders become auto-provisioned customers with owner identity
`claim_status = unclaimed`, just like current shared-channel inbound behavior.

The implementation must update gateway shared-channel access predicates that
currently special-case WhatsApp shared channels so `wechat_ecloud` receives the
same unclaimed-customer access behavior. The identity type for Ecloud senders
should remain generic external identity unless a durable WeChat-specific
identity type already exists.

This design does not alter claim flow, merge behavior, or deletion behavior.
Existing unclaimed customers are not hard-deleted or force-merged by the
Ecloud integration.

### Error Handling

- malformed callback body: return `400` only when the request cannot be parsed
  as a callback at all
- bad channel id, wrong type, or disconnected channel: return `404`
- bad webhook token: return `403`
- unsupported message type: return `200` with `{ ok: true }`
- duplicate inbound callback: return `200` with `{ ok: true }`
- downstream route failure: log with channel id and message ids, then return
  `200` to avoid provider retry storms
- outbound provider failure: throw from delivery client so existing
  `OutboundDelivery` failure tracking records it

### Tests

Gateway API tests should cover:

- `wechat_ecloud` is accepted by admin shared-channel creation
- secret fields are not exposed in serialized shared-channel responses
- connect generates or preserves a webhook token without invoking login APIs
- inbound text callback routes into `routeInboundMessage()`
- inbound reference callback preserves quoted context
- self messages, group messages, unsupported types, bad token, wrong channel
  type, and disconnected channels are handled correctly
- duplicate callbacks with the same `newMsgId` or `msgId` do not call
  `routeInboundMessage()` twice
- malformed quote XML falls back safely without external entity expansion
- outbound text calls Eyun `postText` with `appId`, `toWxid`, `content`, and
  `X-GEWE-TOKEN`
- outbound treats HTTP success plus provider success body as required for
  delivery success
- outbound rejects disconnected or invalid-config channels

Schema/tests should cover the new Prisma enum migration and shared type list.

## Rollout

1. Add schema/type/config support for `wechat_ecloud`.
2. Add the Eyun client and outbound text delivery.
3. Add inbound callback route for private text/reference.
4. Add shared-channel admin support and tests.
5. Deploy gateway.
6. Create one shared `wechat_ecloud` channel for the existing Eyun `appId`.
7. Configure the Eyun callback URL in the Eyun console.
8. Smoke test one inbound text, one quoted reply, and one outbound text reply.

## Open Follow-Ups

- Phase 2 can restore old Coke's voice ASR and image-to-text behavior after
  deciding whether media processing belongs in gateway, bridge, or worker.
- Phase 2 can broaden `/api/outbound` for image/voice if Coke agents need to
  proactively send media.
- Moments publishing should remain a separate product design if needed.
