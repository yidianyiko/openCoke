# Spec: Outbound Multimodal Delivery

## Status

Proposed

## Summary

Coke can still generate `voice` and `photo` outputs in the worker, but the
ClawScale outbound path only reliably accepts and sends text. The broken shape
is:

```text
worker outputmessages
  -> bridge dispatcher
  -> gateway /api/outbound
  -> channel adapter
```

The worker writes voice/image URLs in `outputmessages.metadata.url`, while the
bridge posts only `text` and `message_type`, and Gateway validates
`message_type: text` before calling a text-only delivery helper.

This spec makes outbound media explicit, OpenClaw-style: the cross-system
payload carries text plus optional media URLs and an optional voice hint.
Channels that can send media may do so natively. Channels that cannot must
produce a visible attachment-link fallback or a structured unsupported-media
error. The system must never accept media and then silently drop it.

## Current Failure

### Worker Runtime

`agent/runner/agent_handler.py` can emit:

- `message_type="voice"` with `metadata.url` and `metadata.voice_length`
- `message_type="image"` with `metadata.url`
- `message_type="text"` with normal text

The resource URL is not part of the top-level output document; it is currently
only in metadata.

### Bridge

`connector/clawscale_bridge/output_dispatcher.py` builds gateway arguments from
`outputmessages`, but it sends only:

- `text`
- `message_type`
- routing/idempotency fields

It does not translate `metadata.url` into a sendable media field.

### Gateway API

`gateway/packages/api/src/routes/outbound.ts` validates:

```ts
message_type: z.enum(['text'])
text: z.string().min(1)
```

Media-only outputs cannot pass validation. If the enum were simply widened,
delivery would still be broken because `deliverOutboundMessage()` accepts only
text.

## OpenClaw Reference Pattern

OpenClaw does not make channel output depend primarily on a top-level
`message_type` enum.

Observed pattern in `/data/projects/openclaw`:

- `ReplyPayload` contains `text`, `mediaUrl`, `mediaUrls`, and
  `audioAsVoice`.
- `ChannelOutboundAdapter` exposes `sendPayload`, `sendText`, and `sendMedia`.
- `sendTextMediaPayload()` sends media sequences first when media exists, with
  caption on the first media item, and chunks only text-only payloads.
- Unsupported native media channels degrade explicitly into visible attachment
  links.
- Media loading uses explicit access boundaries such as local roots and
  injected read functions.

Coke should adopt the contract shape, not the full OpenClaw framework.

## Goals

- Make Coke-generated voice and image outputs reliable on the ClawScale
  outbound path.
- Preserve current text delivery behavior.
- Preserve outbound idempotency, duplicate detection, failed-key reclaim, and
  exact route resolution.
- Represent outbound media in a channel-agnostic Gateway contract.
- Make unsupported media behavior explicit and observable.
- Keep the first implementation small enough for the existing worker, bridge,
  and gateway surfaces.

## Non-Goals

- Redesigning worker multimodal generation.
- Adding a durable ClawScale media ingestion service.
- Changing inbound attachment handling.
- Implementing every channel's native media API.
- Changing delivery route ownership or route resolution.
- Adding gateway web UI for failed media deliveries.

## Recommended Design

### 1. Gateway Outbound Payload

Extend `/api/outbound` with optional media fields:

```ts
{
  output_id: string;
  account_id?: string;
  customer_id?: string;
  business_conversation_key: string;
  message_type: 'text' | 'image' | 'voice';
  text?: string;
  mediaUrls?: string[];
  audioAsVoice?: boolean;
  delivery_mode: 'push' | 'request_response';
  expect_output_timestamp: string;
  idempotency_key: string;
  trace_id: string;
  causal_inbound_event_id?: string;
}
```

Validation rules:

- `message_type` remains accepted for compatibility and observability.
- `text` may be absent only when at least one media URL is present.
- `mediaUrls` must be non-empty strings when present.
- Each media URL must be an absolute `http://` or `https://` URL. Gateway does
  not accept local paths, `file://`, data URLs, or relative paths on this API.
- `voice` requires at least one media URL. Gateway coerces `audioAsVoice` to
  `true` for all accepted voice payloads.
- `voice` rejects an explicit `audioAsVoice: false` because that contradicts
  the requested voice delivery semantics.
- `image` requires at least one media URL.
- `image` and `text` reject `audioAsVoice: true`; audio voice rendering is only
  meaningful for `voice`.
- `text` may include media; this supports captions and future generated
  attachments.

The canonical comparable payload for idempotency must include `mediaUrls` and
`audioAsVoice`. Reusing an idempotency key with different media must return the
existing `idempotency_key_conflict`.

The route normalizes all accepted payloads before storage and delivery:

- absent `text` becomes `""`
- absent `mediaUrls` becomes `[]`
- absent `audioAsVoice` becomes `false`, except for `voice`, where it becomes
  `true`

`outboundDelivery.payload` stores the normalized comparable payload plus the
existing stored route target fields. No separate database columns or log fields
are added in this change.

### 2. Bridge Normalization

The bridge dispatcher translates Coke output documents into the Gateway
contract:

- `message_type == "image"` and a non-blank `metadata.url`:
  - `message_type: "image"`
  - `text: message["message"]` when non-empty
  - `mediaUrls: [metadata.url.strip()]`
- `message_type == "voice"` and a non-blank `metadata.url`:
  - `message_type: "voice"`
  - `text: message["message"]` when non-empty
  - `mediaUrls: [metadata.url.strip()]`
  - `audioAsVoice: true`
- `message_type == "text"`:
  - unchanged text-only payload

Malformed image/voice outputs without a usable URL are payload-construction
failures. The dispatcher should mark the claimed output failed, matching the
existing malformed-message behavior.

The first implementation reads only `metadata.url`; it does not introduce a
multi-media worker contract. If a future worker emits multiple URLs, that must
be added as a separate worker contract change and covered by bridge tests.

### 3. Gateway Delivery Model

Change `deliverOutboundMessage()` to accept a structured payload:

```ts
type OutboundMessagePayload = {
  text: string;
  messageType: 'text' | 'image' | 'voice';
  mediaUrls: string[];
  audioAsVoice: boolean;
};
```

Delivery behavior:

- If `mediaUrls` is empty, send text exactly as today.
- For this first Coke implementation, all currently supported Gateway outbound
  channel types use text fallback for media:
  - `wechat_personal`
  - `whatsapp_evolution`
- The helper formats media as visible attachment links:

```text
<caption>

Attachment: <url>
Attachment: <url>
```

For media-only fallback, the exact output is:

```text
Attachment: <url>
Attachment: <url>
```

This fallback is acceptable for `wechat_personal` and `whatsapp_evolution` in
the first implementation because it turns the half-dead path into reliable,
visible output without guessing an unverified native platform media API.

Native media support is intentionally not part of this change. A future change
may add per-channel native media delivery by introducing an explicit adapter
capability and tests for that adapter.

### 4. WeChat Adapter Boundary

Do not invent a native WeChat media send format in this change unless the
adapter contract is already known and tested.

For the first reliable slice:

- keep `sendWeixinText()` as the concrete WeChat delivery primitive
- send media payloads as text with attachment links
- leave a focused adapter seam for future `sendWeixinMedia()` once the
  ClawScale WeChat send-message item contract is verified

### 5. Error Handling

The system should fail closed on malformed media:

- Bridge media output with no `metadata.url`: mark outputmessage `failed`.
- Gateway media request with no media URLs: `400 validation_error`.
- Gateway media URL that is blank or not a string: `400 validation_error`.
- Gateway media URL that is not absolute `http://` or `https://`:
  `400 validation_error`.
- Delivery helper receiving media for a channel without a configured fallback:
  throw `Unsupported outbound media for channel type: <type>`.

Delivery failures continue to update `outboundDelivery.status = failed` with a
stored error before the route throws.

### 6. Tests

Focused test coverage should include:

- Bridge dispatcher sends `mediaUrls` for image.
- Bridge dispatcher sends `mediaUrls` and `audioAsVoice` for voice.
- Bridge dispatcher marks image/voice without URL as failed.
- Gateway route accepts image media payloads and stores media fields in
  idempotency payload.
- Gateway route accepts media-only voice payloads.
- Gateway route rejects media message types without media URLs.
- Gateway route rejects local, relative, `file://`, and data media URLs.
- Gateway route coerces accepted voice payloads to `audioAsVoice: true`.
- Gateway route rejects contradictory `audioAsVoice` values.
- Gateway route detects idempotency conflict when media URL changes.
- Gateway route preserves current text-only duplicate/idempotency behavior.
- Gateway delivery falls back to visible attachment links for WeChat.
- Gateway delivery falls back to visible attachment links for
  `whatsapp_evolution`.

## Implementation Surfaces

- Worker runtime:
  - No first-pass production change expected.
  - Existing worker output format is the source to normalize.
- Bridge:
  - `connector/clawscale_bridge/output_dispatcher.py`
  - `connector/clawscale_bridge/gateway_outbound_client.py`
  - `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`
- Gateway API:
  - `gateway/packages/api/src/routes/outbound.ts`
  - `gateway/packages/api/src/routes/outbound.test.ts`
  - `gateway/packages/api/src/lib/outbound-delivery.ts`
  - `gateway/packages/api/src/lib/outbound-delivery.test.ts`

## Verification

Use the smallest useful cross-surface set:

```bash
pytest tests/unit/connector/clawscale_bridge/ -v
pnpm --dir gateway/packages/api test -- src/routes/outbound.test.ts src/lib/outbound-delivery.test.ts
```

If delivery helper changes spill into broader shared gateway contracts, run:

```bash
pnpm --dir gateway/packages/api test
```

## Risks

- Text-link fallback is reliable but less rich than native voice/photo delivery.
  That is intentional for the first fix because the current product capability
  is unreliable and the native WeChat media send contract is not verified here.
- Media URLs generated by worker tools must be externally retrievable absolute
  HTTP(S) URLs. If a URL expires too quickly, the system will deliver a visible
  but unusable link. A durable media store is a separate follow-up.
- Existing idempotency records created before this change do not contain media
  fields. Retries for historical failed media outputs may conflict or remain
  failed depending on their stored payload shape.

## Acceptance Criteria

- Coke image and voice outputs no longer die at Gateway validation.
- Media-bearing outbound payloads are persisted in `outboundDelivery.payload`
  with normalized comparable media fields.
- Media is never silently dropped.
- Existing text outbound tests still pass.
- Focused bridge and gateway tests cover the new contract.
