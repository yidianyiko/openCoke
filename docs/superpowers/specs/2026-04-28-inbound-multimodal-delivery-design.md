# Inbound Multimodal Delivery Design

## Summary

Coke now has an explicit outbound media contract, but inbound media is still
partial. Gateway adapters can produce attachments and the Gateway router can
store them, but the Python bridge turns the ClawScale backend request into
plain text before enqueueing `inputmessages`. This spec completes the inbound
half by carrying a normalized attachment payload from Gateway to Bridge to
Worker-visible metadata, while preserving a text fallback for existing Python
prompt generation.

The first implementation is a reliable transport and prompt-fallback path, not
native binary storage or full model-side vision/audio execution in Python.

## Current State

Gateway:

- `routeInboundMessage` accepts `attachments?: Attachment[]`.
- `Attachment` has `url`, `filename`, `contentType`, and optional `size`.
- User messages are persisted with `metadata.attachments` when present.
- `loadHistory` returns attachments to backend calls.
- The JS ClawScale/LLM path can include image attachments in model content when
  multimodal is enabled.
- The generic HTTP route `/gateway/:channelId` currently validates text only.
- WhatsApp Evolution webhook handling reads text only and ignores media-only
  events.

Bridge:

- `/bridge/inbound` accepts the custom backend request shape.
- `BusinessOnlyBridgeGateway._normalize_inbound` reads top-level `input` or
  `messages[-1].content`.
- It does not read top-level `attachments` or message-level `attachments`.
- `CokeMessageGateway.build_input_message` always writes `message_type: "text"`
  and does not preserve media metadata.

Worker:

- Existing Python prompt formatting is text-first.
- `message_type: "image"` has legacy string formatting, but no reliable media
  fetch path.
- `message_type: "voice"` is treated as normal text content with a voice label.

OpenClaw reference pattern:

- Channel adapters normalize channel-specific media into a stable attachment or
  media payload before agent dispatch.
- The agent-facing contract is not channel-specific.
- Unsupported media still appears as visible context rather than being silently
  dropped.

## Goals

- Inbound media must not be silently dropped when a supported Gateway adapter has
  attachment data.
- Bridge must preserve normalized attachments on `inputmessages.metadata`.
- Existing text-only inbound behavior and dedupe must remain unchanged.
- Attachment-only inbound events must be accepted when they have at least one
  valid attachment.
- Python worker prompts must see an explicit fallback line for every attachment.
- The contract must support bounded `data:` URLs for trusted adapter-generated
  media because the current WeChat personal adapter decrypts media to data URLs.

## Non-Goals

- No new media object store in this pass.
- No bridge-side remote media download or data URL decoding.
- No automatic speech-to-text.
- No new OpenAI multimodal API integration in Python worker code.
- No full adapter-by-adapter native media parity. This pass wires the shared
  contract and the known broken WhatsApp Evolution inbound path.

## Inbound Attachment Contract

Normalized attachment shape:

```ts
type InboundAttachment = {
  url: string;
  filename: string;
  contentType: string;
  size?: number;
};
```

Shared normalization boundary:

- Gateway must introduce a shared attachment normalizer and use it at the
  `routeInboundMessage` boundary before persisting messages or building backend
  history.
- HTTP routes and adapters may call the same normalizer earlier for clearer
  route-level errors, but `routeInboundMessage` remains the final guard.
- Bridge must use an equivalent Python normalizer before enqueueing
  `inputmessages`.
- Every normalized attachment includes an internal `safeDisplayUrl` used for
  fallback text and logs. For `http(s)` this is the URL. For `data:` this is a
  redacted marker:

```text
[inline <contentType> attachment: <filename>]
```

Validation rules:

- `url` must be a non-empty string after trimming.
- `url` may be absolute `http://`, absolute `https://`, or `data:`.
- Relative paths and `file://` URLs are rejected.
- `data:` URLs are accepted only when the caller is a trusted adapter or the
  bridge itself is reading Gateway-produced message history. Generic external
  `/gateway/:channelId` requests reject `data:`.
- Trust is an internal function option such as `{ allowDataUrls: true }` passed
  by in-process adapters or Bridge code. It must never be inferred from
  client-supplied JSON, `meta`, `metadata`, headers, or attachment fields.
- `data:` URLs must use base64 form.
- Allowed `data:` content types are:
  - `image/jpeg`
  - `image/png`
  - `image/webp`
  - `audio/ogg`
  - `audio/mpeg`
  - `audio/silk`
  - `video/mp4`
  - `application/pdf`
- `filename` defaults to `attachment` when absent or blank.
- `contentType` defaults to `application/octet-stream` when absent or blank.
- `size` is retained only when it is a non-negative finite number.
- Invalid attachment entries are dropped.
- If normalized text is blank and all attachments are invalid or absent, the
  inbound request is treated as empty and must not enqueue a worker message.

Limits:

- Maximum attachments per inbound message: 4.
- Maximum URL length for `http(s)` URLs: 4096 characters.
- Maximum decoded bytes per `data:` URL: 2 MiB.
- Maximum total decoded `data:` bytes per inbound message: 4 MiB.
- Maximum total attachment JSON footprint passed across the bridge: 5 MiB.
- Maximum count and footprint are hard failures for the attachment set, not
  truncation rules. If a request has too many attachments or exceeds total
  footprint, all attachments in that request are considered invalid.
- Payloads that exceed a route-level body cap return `413`.
- Payloads with only oversized or invalid attachments and no text return `400`
  at Gateway routes and ignored/no-enqueue at Bridge.
- Payloads with text plus oversized or invalid attachments keep the text and
  drop the invalid attachments.

Supported sources:

- Top-level `attachments` on the bridge request.
- `attachments` on the latest user message in `messages`.
- `messages[-1].attachments` as a compatibility fallback if no user message is
  identifiable.
- Gateway generic `/gateway/:channelId` JSON requests.
- WhatsApp Evolution webhook media payloads.

Top-level bridge attachments override message-level attachments only when they
contain at least one valid normalized attachment. Otherwise the bridge falls back
to message-level attachments.

## Text Fallback Format

Bridge builds a Worker-visible message string from text plus attachment display
references:

```text
<text>

Attachment: <safeDisplayUrl>
Attachment: <safeDisplayUrl>
```

For attachment-only messages:

```text
Attachment: <safeDisplayUrl>
Attachment: <safeDisplayUrl>
```

The fallback text is stored as `inputmessages.message`. This keeps existing
Python prompt generation, embedding, and logging paths useful without requiring
native media readers in the first pass.

The original caption/text is stored separately in metadata as
`metadata.inbound_text` when attachments are present. This lets later native
media work distinguish user caption text from generated fallback lines.

Raw `data:` URLs are never written into fallback text or logs. They are stored
only in normalized metadata so trusted downstream code can use them later.

## Worker Message Shape

`CokeMessageGateway.build_input_message` continues to create a normal
`inputmessages` document. For inbound attachments it adds:

```python
metadata = {
    "attachments": [
        {
            "url": "...",
            "filename": "...",
            "contentType": "...",
            "size": 123,
        }
    ],
    "mediaUrls": ["..."],
    "inbound_text": "original caption",
}
```

`message_type` mapping:

- exactly one image attachment and no non-image attachment: `image`
- exactly one audio attachment and no non-audio attachment: `voice`
- otherwise: `text`

This keeps simple single-media cases visible to legacy message formatting while
avoiding misleading `image` or `voice` types for mixed files.

Because `message_type` changes Python prompt formatting, implementation must
prove that the final `messages_to_str` output still contains every attachment
fallback line for image, voice, mixed, and `data:` redaction cases.

## Gateway Changes

Generic inbound route:

- `/gateway/:channelId` accepts optional `attachments`.
- It accepts attachment-only requests.
- It normalizes and drops invalid attachment entries before calling
  `routeInboundMessage`.
- It returns `400` when both text and normalized attachments are absent.
- It rejects `data:` URLs because it is an external generic endpoint.
- It returns `413` when the JSON body exceeds the configured inbound payload
  cap.

Central route normalization:

- `routeInboundMessage` must re-normalize `input.attachments` with the shared
  normalizer before message persistence, backend history construction, access
  handling, and backend dispatch.
- Attachments from direct adapters are allowed to contain bounded `data:` URLs
  only when the adapter runs in-process and explicitly passes trusted adapter
  metadata.
- Normalized attachments must be the only shape persisted to
  `message.metadata.attachments`.
- Backend history must use normalized attachments, not raw adapter input.

WhatsApp Evolution webhook:

- Continue ignoring self, group, broadcast, and malformed events.
- Extract text from `conversation` or `extendedTextMessage.text`.
- Extract media attachments from known Evolution message shapes:
  - `imageMessage`: caption plus `image/jpeg` default
  - `audioMessage`: `audio/ogg` default
  - `videoMessage`: caption plus `video/mp4` default
  - `documentMessage`: filename plus `application/octet-stream` default
- Use the provider media URL when present.
- For media-only events, route the event with empty text and attachments instead
  of returning early.
- Preserve existing reply behavior by sending text replies through
  `EvolutionApiClient.sendText`.

Gateway message persistence:

- `routeInboundMessage` already stores attachments on `message.metadata`.
- No schema migration is required.
- Tests must prove attachments are passed to `generateReply` history for bridge
  backends.

Gateway backend dispatch:

- `data:` attachments are Bridge/custom-backend-safe metadata, not automatically
  safe for all model providers.
- JS OpenAI/OpenClaw backend image parts may include `http(s)` image URLs.
- JS OpenAI/OpenClaw backend image parts must not include `data:` URLs in this
  pass. They should be represented as text-only redacted attachment references
  unless a later backend capability explicitly allows inline data URLs.
- Non-image attachments continue to be represented as text references.

## Bridge Changes

`BusinessOnlyBridgeGateway._normalize_inbound`:

- Extracts normalized attachments from top-level and message-level sources.
- Extracts text from top-level `input`, latest user message content, or last
  message content.
- Builds fallback input text from text plus attachment display references.
- Stores normalized attachments and original text in the normalized inbound
  dict.
- Applies the same attachment count, URL length, decoded byte, content type, and
  total payload limits as Gateway.

`BusinessOnlyBridgeGateway._enqueue_and_wait`:

- Adds `attachments` and `inbound_text` to the enqueue payload when present.
- Does not change reply waiting, late reply fallback, or access-denied behavior.

`CokeMessageGateway.build_input_message`:

- Adds attachment metadata and media URL metadata.
- Sets `message_type` using the single image/audio rules above.
- Keeps the unique causal inbound event behavior unchanged.

## Error Handling

- Empty inbound after normalization returns a non-enqueue result:

```json
{ "status": "ignored", "reason": "empty_inbound" }
```

- Flask `/bridge/inbound` maps ignored results to HTTP 200 with:

```json
{ "ok": true, "ignored": true, "reason": "empty_inbound" }
```

- Invalid individual attachments are dropped, not fatal.
- A payload with text and invalid attachments still enqueues the text.
- Access-denied replies do not include attachment fallback text.
- Empty detection happens after trusted account context validation in the
  Bridge. A malformed attachment-only request that also lacks account context
  still returns the existing `missing_coke_account_id` error.
- Empty detection happens before enqueue/reply waiting once account context is
  trusted.
- Gateway external routes return `400` for semantically empty requests and
  `413` for body-size violations.

## Compatibility

- Existing text-only Gateway, Bridge, Worker, and dedupe behavior must remain
  byte-for-byte compatible except where new optional attachment metadata exists.
- Existing bridge requests with `messages` but no attachments keep working.
- Existing stored `inputmessages` without attachment metadata keep formatting as
  before.
- Bounded `data:` URLs are accepted inbound only from trusted adapters or Bridge
  history. Outbound continues to require public `http(s)` media URLs.
- Raw `data:` URLs are excluded from fallback text, logs, and JS OpenAI/OpenClaw
  image parts in this pass.

## Tests

Gateway tests:

- Generic inbound route accepts text plus attachments and passes normalized
  attachments to `routeInboundMessage`.
- Generic inbound route accepts attachment-only requests.
- Generic inbound route rejects empty text plus no valid attachments.
- Generic inbound route rejects `data:` attachments.
- Gateway shared normalizer enforces attachment count, URL length, decoded
  `data:` byte, total `data:` byte, content type, and `file://` rejection rules.
- WhatsApp Evolution media-only image/audio events call `routeInboundMessage`
  instead of being ignored.
- WhatsApp Evolution captioned image routes caption plus attachment.
- `routeInboundMessage` persists `metadata.attachments`.
- `routeInboundMessage` passes attachments in `generateReply` history for bridge
  backends.
- `routeInboundMessage` normalizes attachments from direct adapters and drops
  malformed entries before persistence/history.
- JS OpenAI/OpenClaw backend conversion redacts `data:` attachments instead of
  placing raw data URLs in `image_url` parts.

Bridge tests:

- `/bridge/inbound` reads `messages[-1].attachments` and passes them to
  `message_gateway.enqueue`.
- `/bridge/inbound` reads top-level `attachments`.
- Attachment-only bridge requests enqueue fallback `Attachment: <url>` text.
- Malformed attachment-only bridge requests are ignored and do not enqueue.
- `CokeMessageGateway.build_input_message` stores `metadata.attachments`,
  `metadata.mediaUrls`, and `metadata.inbound_text`.
- Single image attachment writes `message_type: "image"`.
- Single audio attachment writes `message_type: "voice"`.
- Mixed or file attachments keep `message_type: "text"`.
- `messages_to_str` retains attachment fallback text for image, voice, mixed,
  and redacted `data:` cases.
- Bridge normalizer enforces max attachments, max URL length, decoded `data:`
  byte limits, total payload limits, and allowed content types.
- Existing text-only tests continue to pass.

Verification commands:

```bash
pytest tests/unit/connector/clawscale_bridge/ -v
pytest tests/unit/agent/test_message_util_clawscale_routing.py -v
pnpm --dir gateway/packages/api exec vitest run src/gateway/message-router.test.ts src/lib/route-message.test.ts
pnpm --dir gateway/packages/api test
pnpm --dir gateway/packages/api build
zsh scripts/check
```

## Acceptance Criteria

- A captioned image from a Gateway adapter reaches Bridge with attachment
  metadata and Worker-visible fallback text.
- A media-only inbound message reaches Bridge as attachment fallback text instead
  of being silently dropped.
- WhatsApp Evolution media-only inbound events are routed.
- Text-only inbound behavior remains unchanged.
- Invalid attachment-only inbound events do not enqueue empty worker messages.
- Inbound accepts bounded trusted-adapter `data:` URLs while outbound continues
  to reject them.
- Generic external inbound rejects `data:` URLs.
- Oversized, over-count, over-footprint, unsupported-type, `file://`, and
  relative-path attachment-only payloads do not enqueue or route worker work.
- Raw `data:` URLs do not appear in fallback text, logs, or JS OpenAI/OpenClaw
  image payloads.
- Top-level bridge attachments override message-level attachments only when the
  top-level set has at least one valid normalized attachment.
- Invalid attachments with valid text are dropped without dropping the text.
- Multiple attachment fallback preserves attachment order.
- Duplicate inbound-event dedupe remains keyed only by causal inbound event id;
  attachment metadata changes on a duplicate event do not mutate the original
  worker message.
