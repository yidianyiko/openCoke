# Linq Shared Channel Design

Date: 2026-04-28

## Purpose

Add Linq as a gateway shared-channel adapter, matching the integration shape
used by `whatsapp_evolution`. Linq should support inbound user messages,
immediate replies, and proactive outbound delivery through the existing Coke
gateway, bridge, and worker boundaries.

The implementation must not add a new Coke bridge connector. It should plug
into the existing gateway channel model so the bridge and worker continue to
use `routeInboundMessage()` and `/api/outbound`.

## External API Facts

Linq Partner API v3 is served from:

```text
https://api.linqapp.com/api/partner/v3
```

Authentication uses:

```text
Authorization: Bearer <LINQ_API_KEY>
```

Creating an outbound chat uses:

```http
POST /chats
```

with a body shaped like:

```json
{
  "from": "+13213108456",
  "to": ["+8615201780593"],
  "message": {
    "parts": [
      {
        "type": "text",
        "value": "Hello World"
      }
    ]
  }
}
```

Webhooks are created with:

```http
POST /webhook-subscriptions
```

The subscription target URL should pin the payload version:

```text
https://<gateway-public-base>/gateway/linq/<channelId>/<webhookToken>?version=2026-02-03
```

Webhook requests include `X-Webhook-Signature`,
`X-Webhook-Timestamp`, `X-Webhook-Event`, and
`X-Webhook-Subscription-ID`. Signature verification is
HMAC-SHA256 over:

```text
<timestamp>.<raw request body>
```

using the Linq webhook signing secret returned at subscription creation.

## Configuration

The gateway runtime reads these environment variables:

```env
LINQ_API_KEY=<bearer token>
LINQ_API_BASE_URL=https://api.linqapp.com/api/partner/v3
LINQ_FROM_NUMBER=+13213108456
```

The actual bearer token is stored in `.env`, not committed to docs.

Each `linq` shared channel stores this JSON config:

```json
{
  "fromNumber": "+13213108456",
  "webhookToken": "local-random-token",
  "webhookSubscriptionId": "linq-subscription-id",
  "signingSecret": "linq-webhook-signing-secret"
}
```

Only `fromNumber` and `webhookSubscriptionId` may be returned through admin
APIs. `webhookToken` and `signingSecret` are secret server-side values and
must be represented only through booleans such as `hasWebhookToken` and
`hasSigningSecret`.

Legacy or manually created rows with only `fromNumber` are valid while
disconnected. Connect should backfill a `webhookToken`, create a Linq webhook
subscription, and store the returned `webhookSubscriptionId` and
`signingSecret`. Connected Linq channels without all three values are
misconfigured and must reject inbound webhook traffic.

Every API path that returns channel config must use a shared Linq serializer.
This includes `/api/admin/shared-channels`, `/api/channels/:id`, and any future
admin route that includes a channel `config`. No route may return
`webhookToken` or `signingSecret` directly.

## Channel Model

Add `linq` to the channel type surfaces:

- Prisma `ChannelType`
- shared TypeScript `ChannelType`
- API route kind validation
- admin channel filters and shared-channel forms
- external identity normalization provider set

`linq` is a shared channel kind. It should follow the same ownership rules as
`whatsapp_evolution`:

- `ownershipKind: "shared"`
- `agentId` connects to the selected shared agent
- `customerId` remains null on the channel
- per-sender customers are provisioned by `provisionSharedChannelCustomer()`

Linq identities are phone-number based. The shared-channel identity type should
be `phone_number`, and values should normalize to E.164-like digits with a
leading `+` when the input contains a phone number. For example:

```text
+86 152 017 80593 -> +8615201780593
8615201780593 -> +8615201780593
```

If a value cannot be reduced to digits, keep the trimmed original value so
unexpected handle formats are not collapsed into an empty identity.

`routeInboundMessage()` must explicitly recognize connected shared `linq`
channels. During `provisionSharedChannelCustomer()`, it must pass:

```ts
{
  provider: 'linq',
  identityType: 'phone_number',
  rawIdentityValue: externalId
}
```

and the external-identity helper must normalize `phone_number` values for the
`linq` provider. Linq must also be included in shared-channel access handling
that currently special-cases shared WhatsApp channels, so subscription access
and direct delivery-route creation use the provisioned shared customer.

## Linq API Client

Create a focused client module that owns Linq HTTP details:

- `createChat({ from, to, text })`
- `createWebhookSubscription({ targetUrl, phoneNumbers })`
- `deleteWebhookSubscription(subscriptionId)`

The client should:

- default `baseUrl` from `LINQ_API_BASE_URL`
- default token from `LINQ_API_KEY`
- send `Accept: application/json`
- send `Content-Type: application/json` for JSON bodies
- use `Authorization: Bearer <token>`
- apply a finite timeout matching existing gateway API clients
- wrap network and HTTP errors with the Linq request path

For first-version delivery, Coke outbound messages always create a chat with a
single recipient. The implementation does not need to cache Linq chat IDs or
send follow-up messages through `/chats/{chatId}/messages`; exact Linq thread
reuse is explicitly outside this design.

## Admin Shared-Channel Lifecycle

Admin shared-channel create/update/detail should treat `linq` as a typed config
channel instead of raw JSON.

Create accepts:

- `name`
- `kind: "linq"`
- `agentId`
- `config.fromNumber` when `LINQ_FROM_NUMBER` is not configured

If `config.fromNumber` is omitted, the API falls back to `LINQ_FROM_NUMBER`.
When neither value is present, create fails with `linq_config_invalid`. The
stored config should include a generated `webhookToken` and the normalized
`fromNumber`.

Patch allows changing `fromNumber` only while disconnected. It must reject:

- attempts to set `webhookToken`
- attempts to set `signingSecret`
- attempts to change `fromNumber` while connected

Connect should:

1. ensure `webhookToken` exists
2. build the public webhook target URL
3. call Linq `POST /webhook-subscriptions`
4. subscribe only to `message.received` for v1
5. filter the subscription to the configured `fromNumber`
6. store returned `webhookSubscriptionId` and `signingSecret`
7. mark the channel `connected`

If the DB update fails after subscription creation, rollback should delete the
created Linq subscription.

Disconnect should:

1. delete the stored Linq webhook subscription when one exists
2. clear `webhookSubscriptionId` and `signingSecret`
3. keep `fromNumber` and `webhookToken`
4. mark the channel `disconnected`

Delete/archive should disconnect a connected Linq channel before archiving.

## Inbound Webhook Flow

Add:

```text
POST /gateway/linq/:channelId/:token
```

The route should:

1. load the channel by ID
2. require `type === "linq"` and `status === "connected"`
3. require path token to match stored `webhookToken`
4. require stored `webhookSubscriptionId` and `signingSecret`
5. require `X-Webhook-Signature`, `X-Webhook-Timestamp`, and
   `X-Webhook-Subscription-ID`
6. require `X-Webhook-Subscription-ID` to match stored `webhookSubscriptionId`
7. reject timestamps outside a five-minute replay window
8. verify Linq HMAC signature with constant-time comparison
9. compute the signature over `<timestamp>.<raw request body>`
10. reject missing or malformed signature inputs with `403`
11. parse raw JSON after signature verification
12. ignore malformed JSON with a 200 response so Linq does not retry forever
13. process only `message.received`
14. ignore outbound/self messages
15. extract text parts from the payload and join them with newlines
16. call `routeInboundMessage()`
17. if a synchronous reply is returned, send it through `LinqApiClient.createChat()`

The route must not accept token-only webhook authentication for connected Linq
channels. A connected row missing `signingSecret` or `webhookSubscriptionId`
is a server-side misconfiguration and returns `403` for webhook delivery.

Immediate replies target the normalized inbound sender handle. For
`webhook_version: "2026-02-03"`, that is `data.sender_handle.handle`, never
`data.chat.owner_handle.handle`. Owner handle is the Linq virtual number and
must be used as `from`, not `to`.

For webhook version `2026-02-03`, the expected inbound fields are:

- `event_type: "message.received"`
- `event_id`
- `data.chat.id`
- `data.chat.owner_handle.handle`
- `data.id`
- `data.direction: "inbound"`
- `data.sender_handle.handle`
- `data.parts[]`
- `data.service`

The route should include useful metadata:

```ts
{
  platform: 'linq',
  eventId,
  chatId,
  messageId,
  service,
  ownerHandle,
  webhookSubscriptionId
}
```

For compatibility with older webhook payloads, the parser may also accept:

- `data.from`
- `data.from_handle.handle`
- `data.message.parts`
- `data.chat_id`
- `data.message.id`
- `data.is_from_me`

Non-text media parts can be ignored in the first version, but the raw part
metadata should not prevent text parts in the same message from routing.

## Outbound Flow

Extend `deliverOutboundMessage()` with a `linq` branch.

Given a connected Linq channel, outbound delivery should:

1. parse stored Linq config
2. normalize the delivery target phone number
3. call `LinqApiClient.createChat()`
4. send one text part with the Coke reply text

The implementation should reject disconnected channels through the existing
connected-channel guard and reject targets that cannot normalize to a phone
number.

## Error Handling

Admin lifecycle routes return structured errors:

- `linq_config_invalid`
- `linq_from_number_not_mutable_while_connected`
- `linq_secret_not_mutable`
- `linq_webhook_register_failed`
- `linq_webhook_delete_failed`
- `unsupported_shared_channel_kind`

Webhook routes return:

- `404` for missing, non-Linq, or disconnected channels
- `403` for bad path token, missing connected-channel secrets, mismatched
  subscription ID, stale timestamp, missing signature headers, or bad signature
- `200` for malformed or irrelevant webhook bodies

Runtime webhook processing catches and logs downstream errors, then returns
`200` to avoid repeated Linq retries for Coke-side transient processing errors.
Gateway outbound delivery still records delivery failures through the existing
`/api/outbound` idempotency path.

## UI Behavior

Admin shared-channel create page adds a `linq` option.

When `kind === "linq"`, the form shows a single typed input:

```text
From number
```

The raw JSON textarea is hidden.

Admin detail page for Linq shows:

- channel status
- from number
- webhook subscription ID when present
- hidden webhook token indicator
- hidden signing secret indicator
- connect/disconnect buttons

`fromNumber` is disabled while connected.

## Testing

Gateway API tests should cover:

- `LinqApiClient.createChat()` request shape
- webhook subscription create/delete request shapes
- config parsing and public config scrubbing
- shared-channel create/patch/connect/disconnect/delete lifecycle
- webhook signature verification with constant-time comparison
- missing connected-channel secret fail-closed behavior
- missing or malformed signature headers
- timestamp replay-window rejection
- mismatched webhook subscription ID rejection
- `message.received` payload routing into `routeInboundMessage()`
- immediate reply delivery through Linq
- owner-vs-sender separation for immediate reply target selection
- outbound delivery through `deliverOutboundMessage()`
- external identity normalization for Linq phone-number identities
- `routeInboundMessage()` provisioning Linq shared-channel customers with
  provider `linq` and identity type `phone_number`
- secret scrubbing for every route that returns Linq channel config

Gateway web tests should cover:

- create form uses typed Linq `fromNumber`
- detail page hides secrets and exposes connect/disconnect actions
- connected Linq rows lock the from-number input

Verification command set:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/linq-api.test.ts \
  src/lib/linq-config.test.ts \
  src/lib/external-identity.test.ts \
  src/lib/outbound-delivery.test.ts \
  src/gateway/message-router.test.ts \
  src/routes/admin-shared-channels.test.ts \
  src/routes/channels.test.ts \
  src/routes/admin-channels.test.ts

pnpm --dir gateway/packages/web test -- \
  'app/(admin)/admin/shared-channels/page.test.tsx' \
  'app/(admin)/admin/shared-channels/detail/page.test.tsx'
```

If Prisma enum changes are included, also run:

```bash
pnpm --dir gateway/packages/api run db:generate
```

## Scope Exclusions

This first version does not implement:

- Linq chat ID persistence or follow-up send reuse
- group chat support
- media forwarding into Coke attachments
- webhook event deduplication storage
- Linq read/delivery receipt UI
- production deployment docs or remote environment propagation
- customer-facing Linq channel self-service

These exclusions keep the adapter equivalent in scope to the current shared
WhatsApp Evolution runtime path.
