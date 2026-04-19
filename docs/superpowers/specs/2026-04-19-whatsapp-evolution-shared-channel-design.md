# Spec: Evolution-Backed Shared WhatsApp for Coke

## Status

Proposed

## Summary

Integrate the already-running `evolution-api` instance `coke-whatsapp-personal`
into the current ClawScale shared-channel runtime so that:

- each inbound WhatsApp sender is auto-provisioned as an independent Coke
  customer
- Coke can reply immediately in the same WhatsApp thread
- Coke can later send proactive outbound messages to that same sender through
  the exact ClawScale `DeliveryRoute`

The implementation must reuse the current platformization model:

- shared-channel customer auto-provisioning
- exact `DeliveryRoute` resolution
- `/api/outbound` for proactive delivery
- Coke bridge request/response plus async push behavior

The implementation must **not** bypass ClawScale by wiring Evolution directly
into `coke-bridge`, and it must **not** reuse the existing gateway `whatsapp`
channel type that means “gateway owns the Baileys session locally”.

## Current State

### Runtime facts confirmed on `gcp-coke`

- The main Coke deployment is healthy:
  - `gateway` is healthy on `127.0.0.1:4041`
  - `coke-bridge` is healthy on `127.0.0.1:8090`
- Evolution is deployed separately under `~/evolution` and is healthy on
  `127.0.0.1:8081`
- Evolution reports version `2.3.7`
- The existing Evolution instance is:
  - `name = coke-whatsapp-personal`
  - `integration = WHATSAPP-BAILEYS`
  - `connectionStatus = open`
  - `ownerJid = 8619917902815@s.whatsapp.net`
- `GET /webhook/find/coke-whatsapp-personal` currently returns `null`, which
  means there is no existing instance webhook to preserve or migrate

### Relevant code already exists

ClawScale already has the platform pieces needed for this integration:

- inbound shared-channel auto-provisioning in
  [shared-channel-provisioning.ts](/data/projects/coke/gateway/packages/api/src/lib/shared-channel-provisioning.ts)
- inbound shared-channel routing in
  [route-message.ts](/data/projects/coke/gateway/packages/api/src/lib/route-message.ts)
- exact proactive outbound routing in
  [outbound.ts](/data/projects/coke/gateway/packages/api/src/routes/outbound.ts)
- Coke bridge async output dispatch in
  [output_dispatcher.py](/data/projects/coke/connector/clawscale_bridge/output_dispatcher.py)
- platform admin shared-channel CRUD in
  [admin-shared-channels.ts](/data/projects/coke/gateway/packages/api/src/routes/admin-shared-channels.ts)

What is missing is the adapter boundary between ClawScale and Evolution:

- no channel type for an Evolution-backed WhatsApp shared channel
- no Evolution webhook ingress route in gateway
- no Evolution outbound sender in gateway
- no shared-channel connect/disconnect lifecycle
- no secret-safe shared-channel config surface for Evolution-backed channels

### Relevant Evolution API contract

From the current official Evolution docs:

- instance webhook configuration is done with
  `POST /webhook/set/{instance}`
- current webhook configuration is read with
  `GET /webhook/find/{instance}`
- plain-text outbound send is done with
  `POST /message/sendText/{instance}`

The current deployment only needs the `MESSAGES_UPSERT` webhook event for
inbound delivery. Proactive outbound can be driven by ClawScale directly and
does not require listening to `SEND_MESSAGE`.

## Goals

- Reuse the current Evolution instance `coke-whatsapp-personal` without moving
  session ownership into gateway.
- Model the Evolution-backed WhatsApp number as a ClawScale `shared` channel.
- Auto-provision one internal Coke customer per external WhatsApp sender using
  normalized `wa_id` identity semantics.
- Route synchronous and proactive replies back to the same sender using the
  current exact `DeliveryRoute` model.
- Let platform admins create, view, connect, disconnect, and retire this
  channel from the existing shared-channel admin surface.
- Keep Evolution control secrets out of browser-visible admin payloads.
- Make the deployment operationally simple on `gcp-coke`: one Evolution
  instance, one ClawScale shared channel, one webhook registration per
  connected channel.

## Non-Goals

- Migrating the existing Evolution session into gateway-owned Baileys.
- Replacing or removing the current `whatsapp` or `whatsapp_business`
  adapters.
- Supporting every Evolution event or every outbound media type in this change.
- Building a multi-instance Evolution control plane beyond what is needed for
  one shared WhatsApp channel.
- Reworking Coke bridge contracts or the Mongo async output pipeline.

## Approaches Considered

### Approach A: Treat Evolution as a hosted WhatsApp adapter inside ClawScale

Add a dedicated Evolution-backed WhatsApp shared-channel type to gateway, wire
Evolution webhooks into `routeInboundMessage()`, and send proactive messages
through Evolution’s `sendText` endpoint.

Pros:

- preserves the current platformization architecture
- reuses `Customer`, `ExternalIdentity`, `DeliveryRoute`, and `/api/outbound`
- keeps synchronous and proactive messaging on one routing model
- operationally matches the current server layout

Cons:

- requires a new adapter and channel type
- requires connect/disconnect logic that talks to Evolution control APIs
- requires tightening the shared-channel admin contract so webhook secrets are
  not exposed in the browser

Decision: recommended.

### Approach B: Add a separate relay service between Evolution and ClawScale

Keep gateway unaware of Evolution details and run a second service that
translates inbound/outbound traffic.

Pros:

- isolates vendor-specific logic outside gateway

Cons:

- adds another deployable component
- duplicates auth, logging, and failure handling boundaries
- makes production debugging harder for no current benefit

Decision: reject.

### Approach C: Send Evolution traffic directly to `coke-bridge`

Bypass shared-channel runtime and let Evolution talk straight to the Coke bridge.

Pros:

- superficially smaller patch

Cons:

- bypasses ClawScale customer auto-provisioning
- bypasses exact `DeliveryRoute`
- breaks the architecture already built in the 2026-04-16 platformization wave
- makes proactive outbound a special case again

Decision: reject.

## Recommended Design

### 1. Add a distinct `whatsapp_evolution` channel type

Introduce a new gateway channel kind named `whatsapp_evolution`.

This type means:

- WhatsApp session ownership lives in Evolution, not in gateway
- gateway owns routing, customer provisioning, outbound delivery, and
  operational connect/disconnect semantics
- the channel is expected to be `ownership_kind = shared`

This type must be added consistently to:

- Prisma `ChannelType`
- shared type definitions in `packages/shared`
- admin route validation lists
- shared-channel admin UI create/edit controls
- any migration baseline or schema guard that enumerates channel kinds

This type must **not** reuse the existing `whatsapp` type because the current
`whatsapp` adapter in
[whatsapp.ts](/data/projects/coke/gateway/packages/api/src/adapters/whatsapp.ts)
assumes gateway itself owns the Baileys auth directory and live socket state.

### 2. Split Evolution control credentials from per-channel config

Per-channel config stored in Postgres for `whatsapp_evolution` should contain:

```json
{
  "instanceName": "coke-whatsapp-personal",
  "webhookToken": "random-shared-secret"
}
```

Global Evolution server access belongs in gateway environment variables:

- `EVOLUTION_API_BASE_URL`
- `EVOLUTION_API_KEY`

Rationale:

- one Evolution server may back multiple channels over time
- the control-plane API key is infrastructure-level, not business-level
- platform admins should not copy the same secret into each channel row

### 3. Add a gateway Evolution client

Create a focused gateway-side client responsible for:

- reading instance webhook config
- setting instance webhook config
- disabling instance webhook config when needed
- sending plain text messages through Evolution

Required calls:

- `GET /webhook/find/{instance}`
- `POST /webhook/set/{instance}`
- `POST /message/sendText/{instance}`

The client should:

- use `EVOLUTION_API_BASE_URL` and `EVOLUTION_API_KEY`
- enforce reasonable request timeouts
- return structured errors suitable for route handlers and logs
- keep request/response formatting isolated from business routing code

### 4. Add a gateway Evolution inbound webhook route

Add a new HTTP route under `/gateway` specifically for Evolution-backed
WhatsApp ingress:

`POST /gateway/evolution/whatsapp/:channelId/:token`

Behavior:

- load the channel by `channelId`
- confirm `type === 'whatsapp_evolution'`
- confirm `status === 'connected'`
- validate `token` against stored channel config
- parse the Evolution `MESSAGES_UPSERT` payload
- ignore payloads that are not end-user inbound messages
- normalize the payload and delegate to `routeInboundMessage()`
- return `200` quickly after processing or after a safe ignore path

The handler must ignore:

- messages with `fromMe = true`
- group/broadcast/system JIDs
- empty or unrecognized messages that cannot produce text or attachment context

Normalized inbound fields should be:

- `channelId`: the shared channel row id
- `externalId`: normalized WhatsApp sender identifier
- `displayName`: `pushName` when present
- `text`: message text or attachment placeholder text
- `meta.platform = 'whatsapp_evolution'`
- `meta.messageId`: original Evolution/WhatsApp message id
- `meta.instanceName`: configured Evolution instance name

For first implementation, support:

- `conversation`
- `extendedTextMessage.text`
- basic attachment placeholders for image/audio/video/document where available

Media download and rich outbound media are explicitly deferred.

### 5. Map Evolution senders onto shared-channel customer provisioning

`routeInboundMessage()` currently treats WhatsApp-family shared channels as
`identityType = 'wa_id'` when the platform is `whatsapp` or
`whatsapp_business`.

That behavior must extend to `whatsapp_evolution`.

The external identity normalization rules in
[external-identity.ts](/data/projects/coke/gateway/packages/api/src/lib/external-identity.ts)
must also treat `whatsapp_evolution` as a WhatsApp-family provider so that:

- `8619917902815@s.whatsapp.net`
- `8619917902815`
- `+86 199 1790 2815`

all normalize to the same `wa_id` row when applicable.

Result:

- first message from a new sender auto-provisions a new customer graph
- repeat messages from the same sender resolve to the same customer
- exact business-conversation and delivery-route logic continues unchanged

### 6. Add Evolution-backed outbound delivery

Extend
[outbound-delivery.ts](/data/projects/coke/gateway/packages/api/src/lib/outbound-delivery.ts)
to support `channel.type === 'whatsapp_evolution'`.

When outbound is resolved to that channel:

- read `instanceName` from channel config
- normalize `externalEndUserId` into the number format expected by Evolution
- call `POST /message/sendText/{instance}`
- send the current text payload only

Outbound semantics stay aligned with the current system:

- `DeliveryRoute` still decides *who* should receive the message
- the Evolution sender only decides *how* to deliver on this channel type

### 7. Add a shared-channel lifecycle surface for connect/disconnect

The current shared-channel admin surface only supports list/get/patch/retire.
That is insufficient for an integration that must actively register and remove
an Evolution webhook.

Add dedicated admin endpoints:

- `POST /api/admin/shared-channels/:id/connect`
- `POST /api/admin/shared-channels/:id/disconnect`

Behavior for connect:

1. validate required config exists
2. build the public webhook URL from the current public base URL plus channel id
   and webhook token
3. call Evolution `POST /webhook/set/{instance}`
4. enable only the events required for this integration
5. persist `status = 'connected'` only if the control-plane call succeeds

Behavior for disconnect:

1. disable or clear the instance webhook via Evolution control API
2. persist `status = 'disconnected'`

Behavior for retire:

- if a `whatsapp_evolution` shared channel is still connected, retire must first
  clear the Evolution webhook and only then archive the channel
- if remote webhook clear fails, retire must fail rather than leave a live
  webhook pointing at an archived channel

Operational rule:

- if `instanceName` changes on an already-connected channel, reject the patch
  and require disconnect first

This avoids stale webhook registrations and cross-wiring one instance to the
wrong shared channel.

### 8. Make the shared-channel config surface secret-safe

The current shared-channel API/detail page returns and edits raw JSON config.
That is incompatible with an internal `webhookToken` secret.

For `whatsapp_evolution`, the admin shared-channel API must stop exposing raw
secret-bearing config as an editable blob.

Required contract changes:

- create accepts typed input for `instanceName`; server generates
  `webhookToken`
- get/list responses expose safe config only, shaped as:

```json
{
  "config": {
    "instanceName": "coke-whatsapp-personal"
  },
  "hasWebhookToken": true
}
```

- patch accepts typed safe config only; token is not patchable from the browser
- the detail page replaces raw JSON editing with typed fields plus
  connect/disconnect controls for `whatsapp_evolution`

Other shared-channel kinds may continue using the current generic JSON config
surface for now. The secret-safe contract is required specifically for the new
Evolution-backed type.

### 9. Preserve admin shared-channel workflow

The admin shared-channel UI remains the right surface for this integration, but
it needs one additional lifecycle state and a safer editor for this specific
kind.

Required UI/backend changes:

- allow `whatsapp_evolution` in shared-channel create/edit forms
- show typed field(s) for `instanceName`
- show current status plus explicit `Connect`, `Disconnect`, `Save`, and
  `Retire` actions
- keep `webhookToken` hidden from the browser at all times
- preserve existing agent assignment behavior for shared channels

No customer-facing UI changes are required.

## Detailed Contracts

### Inbound contract from Evolution to gateway

The integration depends on Evolution’s `MESSAGES_UPSERT` instance webhook.

Expected useful fields from current Evolution payloads:

- `event`
- `instance`
- `data.key.remoteJid`
- `data.key.fromMe`
- `data.key.id`
- `data.pushName`
- `data.message`
- `data.messageType`

Gateway should tolerate payload variation and read conservatively:

- if a known text payload exists, use it
- if a known media payload exists, produce a placeholder text plus metadata
- if the payload cannot be confidently classified as a user inbound, ignore it

### Outbound contract from gateway to Evolution

Gateway sends:

- endpoint: `POST /message/sendText/{instanceName}`
- headers:
  - `apikey: <EVOLUTION_API_KEY>`
  - `content-type: application/json`
- body:

```json
{
  "number": "8619917902815",
  "text": "hello from Coke"
}
```

Quoted replies, mentions, previews, and media sends are out of scope for the
first change.

## Error Handling

- Missing or invalid webhook token: respond `403`
- Channel not found or wrong type: respond `404`
- Channel exists but is not connected: log and return `200` so Evolution does
  not retry stale deliveries
- Unrecognized but harmless Evolution webhook payload: log and return `200`
- Evolution control-plane failure on connect/disconnect/retire: keep channel
  state unchanged and return explicit error to the admin caller
- Evolution send failure on proactive outbound: let the existing outbound
  failure path record the error; do not invent a second retry state machine

## Deployment and Operations

Gateway production env gains:

- `EVOLUTION_API_BASE_URL`
- `EVOLUTION_API_KEY`

These variables must be added to:

- `deploy/env/coke.env.example`
- `docs/deploy.md`
- the production host `~/coke/.env`

The deploy script does not auto-synthesize these values. Deployment docs must
explicitly say they are required when `whatsapp_evolution` shared channels are
used.

Nginx and public routing do not need a new service; the new webhook lands on
the already-public Coke domain and gateway service.

The initial rollout on `gcp-coke` should be:

1. deploy gateway with the new channel type and Evolution adapter
2. set `EVOLUTION_API_*` in `~/coke/.env`
3. create one admin shared channel pointing to `instanceName = coke-whatsapp-personal`
4. connect that channel so gateway registers the Evolution webhook
5. verify `GET /webhook/find/coke-whatsapp-personal` now returns the expected
   gateway URL and `MESSAGES_UPSERT`
6. send a real inbound WhatsApp message and confirm customer auto-provisioning
7. trigger a proactive outbound send and confirm delivery through Evolution
8. disconnect or retire the channel and confirm `webhook/find` no longer points
   at the Coke gateway route

## Testing Strategy

### Gateway unit/integration tests

- external identity normalization treats `whatsapp_evolution` like WhatsApp
- existing `whatsapp` and `whatsapp_business` normalization tests continue to
  pass unchanged
- Evolution inbound handler ignores `fromMe=true`
- Evolution inbound handler ignores unsupported payloads without error
- Evolution inbound handler routes text payloads into `routeInboundMessage()`
- shared-channel provisioning is invoked with provider `whatsapp_evolution`
- outbound delivery sends text through Evolution for `whatsapp_evolution`
- connect action registers webhook via Evolution client
- disconnect action clears/disables webhook via Evolution client
- retire path clears remote webhook before archiving the channel
- admin shared-channel routes accept and serialize `whatsapp_evolution`
  without exposing `webhookToken`

### Deployment verification

- `gateway/packages/api` tests covering the new adapter pass
- regression tests for existing `whatsapp` / `whatsapp_business` code paths pass
- full gateway build passes
- on `gcp-coke`, `webhook/find/coke-whatsapp-personal` shows the configured
  gateway webhook after connect
- one first-contact WhatsApp sender creates exactly one new customer graph
- one repeat message from the same sender reuses the same customer
- `/api/outbound` can proactively send a text back to that sender

## Acceptance Criteria

- The platform admin can create a `whatsapp_evolution` shared channel that
  points at `coke-whatsapp-personal`.
- The platform admin can connect and disconnect that channel from the shared
  channel detail surface.
- The shared-channel API/UI never exposes `webhookToken` back to the browser.
- Evolution delivers inbound user messages from that number to gateway through
  the configured webhook.
- A previously unseen sender is auto-provisioned as a new Coke customer.
- A previously seen sender reuses the same Coke customer.
- Immediate replies from Coke reach the same WhatsApp chat.
- Proactive outbound messages from Coke also reach that same WhatsApp chat via
  `DeliveryRoute`.
- Disconnecting or retiring the channel removes or disables the Evolution
  webhook and stops new ingress on that route.
