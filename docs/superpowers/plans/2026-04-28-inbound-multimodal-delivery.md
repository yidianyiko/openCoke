# Inbound Multimodal Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carry inbound media from Gateway adapters through the Python bridge into Worker-visible `inputmessages` metadata and fallback text without regressing text-only inbound behavior.

**Architecture:** Add a shared Gateway attachment normalizer at the `routeInboundMessage` boundary, then use the same contract in HTTP/webhook entrypoints. Add an equivalent Python normalizer in the bridge, preserve normalized attachments in `inputmessages.metadata`, and build redacted fallback text for existing Worker prompt generation.

**Tech Stack:** TypeScript Hono/Vitest Gateway API, Python bridge pytest tests, Mongo-shaped message documents.

---

## File Structure

- Create `gateway/packages/api/src/lib/inbound-attachments.ts`
  - Shared Gateway attachment normalization, limits, `safeDisplayUrl`, and trust-gated `data:` handling.
- Create `gateway/packages/api/src/lib/inbound-attachments.test.ts`
  - Focused normalizer tests for URL schemes, limits, redaction, defaults, and invalid entries.
- Modify `gateway/packages/api/src/lib/route-message.ts`
  - Normalize attachments at the central routing boundary before persistence/history/backend dispatch.
  - Keep backend history built from normalized attachments.
- Modify `gateway/packages/api/src/lib/route-message.test.ts`
  - Cover persistence, history, direct-adapter normalization, and malformed attachment dropping.
- Modify `gateway/packages/api/src/lib/ai-backend.ts`
  - Redact `data:` image attachments from OpenAI/OpenClaw image parts in this pass.
- Add or modify `gateway/packages/api/src/lib/ai-backend.test.ts`
  - Cover `data:` redaction and `http(s)` image preservation in backend message conversion.
- Modify `gateway/packages/api/src/gateway/message-router.ts`
  - Extend generic inbound route schema for attachments.
  - Normalize generic route attachments without `data:` trust.
  - Extract WhatsApp Evolution media attachments and route media-only events.
- Modify `gateway/packages/api/src/gateway/message-router.test.ts`
  - Cover generic route media behavior and WhatsApp Evolution media routing.
- Create `connector/clawscale_bridge/inbound_attachments.py`
  - Python attachment normalization, data URL limits, safe display text, and fallback formatting.
- Modify `connector/clawscale_bridge/app.py`
  - Read top-level and message-level attachments in `_normalize_inbound`.
  - Ignore empty normalized inbound after account validation.
  - Pass attachments and original inbound text to `CokeMessageGateway.enqueue`.
- Modify `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
  - Cover bridge inbound attachment sources, empty ignores, and override behavior.
- Modify `connector/clawscale_bridge/message_gateway.py`
  - Store normalized attachment metadata and `mediaUrls`.
  - Set `message_type` for single image/audio attachments.
- Modify `tests/unit/connector/clawscale_bridge/test_message_gateway.py`
  - Cover metadata, message type mapping, dedupe unchanged, and text-only unchanged.
- Modify or add `tests/unit/agent/test_message_util_clawscale_routing.py`
  - Cover final Worker prompt formatting for image, voice, mixed, and redacted `data:` fallback text.

## Task 1: Gateway Shared Attachment Normalizer

**Files:**
- Create: `gateway/packages/api/src/lib/inbound-attachments.ts`
- Create: `gateway/packages/api/src/lib/inbound-attachments.test.ts`

- [ ] **Step 1: Write failing normalizer tests**

Create `gateway/packages/api/src/lib/inbound-attachments.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
  normalizeInboundAttachments,
  MAX_INBOUND_ATTACHMENTS,
} from './inbound-attachments.js';

describe('normalizeInboundAttachments', () => {
  it('normalizes http attachments with defaults and safe display URLs', () => {
    const result = normalizeInboundAttachments([
      { url: ' https://cdn.example.com/photo.jpg ', filename: ' ', contentType: ' ' },
    ]);

    expect(result).toEqual({
      attachments: [
        {
          url: 'https://cdn.example.com/photo.jpg',
          filename: 'attachment',
          contentType: 'application/octet-stream',
          safeDisplayUrl: 'https://cdn.example.com/photo.jpg',
        },
      ],
      rejected: false,
    });
  });

  it('rejects data URLs unless explicitly trusted', () => {
    const dataUrl = 'data:image/png;base64,' + Buffer.from('png').toString('base64');

    expect(normalizeInboundAttachments([{ url: dataUrl }])).toEqual({
      attachments: [],
      rejected: false,
    });
    expect(normalizeInboundAttachments([{ url: dataUrl }], { allowDataUrls: true })).toEqual({
      attachments: [
        {
          url: dataUrl,
          filename: 'attachment',
          contentType: 'image/png',
          safeDisplayUrl: '[inline image/png attachment: attachment]',
          size: 3,
        },
      ],
      rejected: false,
    });
  });

  it('drops unsupported schemes and malformed entries', () => {
    const result = normalizeInboundAttachments([
      { url: 'file:///tmp/a.png' },
      { url: '/tmp/a.png' },
      { url: '' },
      null,
    ]);

    expect(result).toEqual({ attachments: [], rejected: false });
  });

  it('hard rejects over-count attachment sets', () => {
    const attachments = Array.from({ length: MAX_INBOUND_ATTACHMENTS + 1 }, (_, index) => ({
      url: `https://cdn.example.com/${index}.jpg`,
    }));

    expect(normalizeInboundAttachments(attachments)).toEqual({
      attachments: [],
      rejected: true,
      reason: 'attachment_limit_exceeded',
    });
  });

  it('hard rejects oversized trusted data URLs', () => {
    const oversized = 'data:image/png;base64,' + Buffer.alloc(2 * 1024 * 1024 + 1).toString('base64');

    expect(normalizeInboundAttachments([{ url: oversized }], { allowDataUrls: true })).toEqual({
      attachments: [],
      rejected: true,
      reason: 'attachment_payload_too_large',
    });
  });
});
```

- [ ] **Step 2: Verify RED**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run src/lib/inbound-attachments.test.ts
```

Expected: FAIL because `inbound-attachments.ts` does not exist.

- [ ] **Step 3: Implement normalizer**

Create `gateway/packages/api/src/lib/inbound-attachments.ts`:

```ts
export const MAX_INBOUND_ATTACHMENTS = 4;
export const MAX_HTTP_URL_LENGTH = 4096;
export const MAX_DATA_URL_BYTES = 2 * 1024 * 1024;
export const MAX_TOTAL_DATA_URL_BYTES = 4 * 1024 * 1024;
export const MAX_ATTACHMENT_JSON_BYTES = 5 * 1024 * 1024;

const ALLOWED_DATA_CONTENT_TYPES = new Set([
  'image/jpeg',
  'image/png',
  'image/webp',
  'audio/ogg',
  'audio/mpeg',
  'audio/silk',
  'video/mp4',
  'application/pdf',
]);

export type InboundAttachment = {
  url: string;
  filename: string;
  contentType: string;
  size?: number;
  safeDisplayUrl: string;
};

export type NormalizeInboundAttachmentsOptions = {
  allowDataUrls?: boolean;
};

export type NormalizeInboundAttachmentsResult = {
  attachments: InboundAttachment[];
  rejected: boolean;
  reason?: 'attachment_limit_exceeded' | 'attachment_payload_too_large';
};

function readRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function readString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function readSize(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : undefined;
}

function parseDataUrl(value: string): { contentType: string; bytes: number } | null {
  const match = value.match(/^data:([^;,]+);base64,([A-Za-z0-9+/=]+)$/);
  if (!match) return null;
  const contentType = match[1]!.toLowerCase();
  if (!ALLOWED_DATA_CONTENT_TYPES.has(contentType)) return null;
  const bytes = Buffer.from(match[2]!, 'base64').byteLength;
  return { contentType, bytes };
}

function jsonFootprintBytes(value: unknown): number {
  return Buffer.byteLength(JSON.stringify(value ?? null), 'utf8');
}

export function normalizeInboundAttachments(
  rawAttachments: unknown,
  options: NormalizeInboundAttachmentsOptions = {},
): NormalizeInboundAttachmentsResult {
  if (!Array.isArray(rawAttachments) || rawAttachments.length === 0) {
    return { attachments: [], rejected: false };
  }
  if (rawAttachments.length > MAX_INBOUND_ATTACHMENTS) {
    return { attachments: [], rejected: true, reason: 'attachment_limit_exceeded' };
  }
  if (jsonFootprintBytes(rawAttachments) > MAX_ATTACHMENT_JSON_BYTES) {
    return { attachments: [], rejected: true, reason: 'attachment_payload_too_large' };
  }

  let totalDataBytes = 0;
  const attachments: InboundAttachment[] = [];
  for (const raw of rawAttachments) {
    const record = readRecord(raw);
    const url = readString(record?.['url']);
    if (!url) continue;

    const filename = readString(record?.['filename']) ?? 'attachment';
    const explicitContentType = readString(record?.['contentType']);
    const size = readSize(record?.['size']);

    if (url.startsWith('data:')) {
      if (!options.allowDataUrls) continue;
      const data = parseDataUrl(url);
      if (!data) continue;
      if (data.bytes > MAX_DATA_URL_BYTES) {
        return { attachments: [], rejected: true, reason: 'attachment_payload_too_large' };
      }
      totalDataBytes += data.bytes;
      if (totalDataBytes > MAX_TOTAL_DATA_URL_BYTES) {
        return { attachments: [], rejected: true, reason: 'attachment_payload_too_large' };
      }
      attachments.push({
        url,
        filename,
        contentType: data.contentType,
        safeDisplayUrl: `[inline ${data.contentType} attachment: ${filename}]`,
        size: size ?? data.bytes,
      });
      continue;
    }

    try {
      const parsed = new URL(url);
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') continue;
      if (url.length > MAX_HTTP_URL_LENGTH) continue;
      attachments.push({
        url,
        filename,
        contentType: explicitContentType ?? 'application/octet-stream',
        safeDisplayUrl: url,
        ...(size !== undefined ? { size } : {}),
      });
    } catch {
      continue;
    }
  }

  return { attachments, rejected: false };
}
```

- [ ] **Step 4: Verify GREEN**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run src/lib/inbound-attachments.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git -C gateway add packages/api/src/lib/inbound-attachments.ts packages/api/src/lib/inbound-attachments.test.ts
git -C gateway commit -m "feat: normalize inbound attachments"
git add gateway
git commit -m "chore: update gateway inbound attachment normalizer"
```

## Task 2: Gateway Central Routing And Backend Redaction

**Files:**
- Modify: `gateway/packages/api/src/lib/route-message.ts`
- Modify: `gateway/packages/api/src/lib/route-message.test.ts`
- Modify: `gateway/packages/api/src/lib/ai-backend.ts`
- Modify or create: `gateway/packages/api/src/lib/ai-backend.test.ts`

- [ ] **Step 1: Add failing route-message attachment tests**

In `gateway/packages/api/src/lib/route-message.test.ts`, add tests proving:

```ts
it('normalizes and persists inbound attachments before backend dispatch', async () => {
  await routeInboundMessage({
    channelId: 'ch_1',
    externalId: 'wxid_123',
    displayName: 'Alice',
    text: 'caption',
    attachments: [
      { url: ' https://cdn.example.com/photo.jpg ', filename: '', contentType: 'image/jpeg' },
      { url: 'file:///tmp/secret.png', filename: 'secret.png', contentType: 'image/png' },
    ],
    meta: { platform: 'whatsapp_business' },
  });

  expect(db.message.create).toHaveBeenCalledWith({
    data: expect.objectContaining({
      role: 'user',
      content: 'caption',
      metadata: expect.objectContaining({
        attachments: [
          {
            url: 'https://cdn.example.com/photo.jpg',
            filename: 'attachment',
            contentType: 'image/jpeg',
            safeDisplayUrl: 'https://cdn.example.com/photo.jpg',
          },
        ],
      }),
    }),
  });
  expect(generateReply).toHaveBeenCalledWith(
    expect.objectContaining({
      history: [
        {
          role: 'user',
          content: 'caption',
          attachments: [
            {
              url: 'https://cdn.example.com/photo.jpg',
              filename: 'attachment',
              contentType: 'image/jpeg',
              safeDisplayUrl: 'https://cdn.example.com/photo.jpg',
            },
          ],
        },
      ],
    }),
  );
});
```

Also add a trusted direct-adapter data URL test by passing an internal option:

```ts
it('allows trusted adapter data URLs but persists redacted safe display URL', async () => {
  const dataUrl = 'data:image/png;base64,' + Buffer.from('png').toString('base64');

  await routeInboundMessage({
    channelId: 'ch_1',
    externalId: 'wxid_123',
    text: 'caption',
    attachments: [{ url: dataUrl, filename: 'photo.png', contentType: 'image/png' }],
    attachmentPolicy: { allowDataUrls: true },
    meta: { platform: 'wechat_personal' },
  });

  expect(db.message.create).toHaveBeenCalledWith({
    data: expect.objectContaining({
      metadata: expect.objectContaining({
        attachments: [
          expect.objectContaining({
            url: dataUrl,
            safeDisplayUrl: '[inline image/png attachment: photo.png]',
          }),
        ],
      }),
    }),
  });
});
```

- [ ] **Step 2: Add failing backend redaction tests**

If `ai-backend.test.ts` already exists, add to it. Otherwise create it and mock OpenAI enough to inspect `chat.completions.create` arguments. Add tests proving:

```ts
it('sends http image attachments as image_url parts', async () => {
  // Use generateReply with an llm/openclaw backend and image http attachment history.
  // Assert the mocked OpenAI call includes { type: 'image_url', image_url: { url: 'https://...' } }.
});

it('redacts data image attachments into text parts instead of image_url parts', async () => {
  // Use generateReply with an llm/openclaw backend and a data:image/png attachment with safeDisplayUrl.
  // Assert no image_url part starts with data:, and a text part contains safeDisplayUrl.
});
```

- [ ] **Step 3: Verify RED**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run src/lib/route-message.test.ts src/lib/ai-backend.test.ts
```

Expected: FAIL because central normalization and data URL redaction are not implemented.

- [ ] **Step 4: Implement central normalization**

In `route-message.ts`:

- Import `normalizeInboundAttachments`.
- Extend `InboundMessage` with an internal-only `attachmentPolicy?: { allowDataUrls?: boolean }`.
- Normalize at function entry:

```ts
const normalizedAttachmentResult = normalizeInboundAttachments(attachments, input.attachmentPolicy);
const normalizedAttachments = normalizedAttachmentResult.attachments;
```

- Use `normalizedAttachments` for message persistence, `runClawscaleAgent`, `runBackend`, and recursive command dispatch.
- Do not infer trust from `meta`.

- [ ] **Step 5: Implement backend redaction**

In `ai-backend.ts`, update `toOpenAiMessage`:

- Only create `image_url` parts for image attachments whose URL starts with `http://` or `https://`.
- For `data:` image attachments and all non-image attachments, append a text part using `safeDisplayUrl ?? url`.

- [ ] **Step 6: Verify GREEN**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run src/lib/inbound-attachments.test.ts src/lib/route-message.test.ts src/lib/ai-backend.test.ts
pnpm --dir gateway/packages/api build
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

Run:

```bash
git -C gateway add packages/api/src/lib/route-message.ts packages/api/src/lib/route-message.test.ts packages/api/src/lib/ai-backend.ts packages/api/src/lib/ai-backend.test.ts
git -C gateway commit -m "feat: guard inbound attachments at routing boundary"
git add gateway
git commit -m "chore: update gateway inbound routing media guard"
```

## Task 3: Gateway HTTP And WhatsApp Evolution Inbound Media

**Files:**
- Modify: `gateway/packages/api/src/gateway/message-router.ts`
- Modify: `gateway/packages/api/src/gateway/message-router.test.ts`

- [ ] **Step 1: Add failing Gateway HTTP route tests**

In `message-router.test.ts`, add tests:

```ts
it('generic inbound route accepts attachment-only http requests', async () => {
  const res = await app.request('/gateway/ch_1', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      externalId: 'user_1',
      text: '',
      attachments: [{ url: 'https://cdn.example.com/photo.jpg', contentType: 'image/jpeg' }],
    }),
  });

  expect(res.status).toBe(200);
  expect(routeInboundMessage).toHaveBeenCalledWith(expect.objectContaining({
    text: '',
    attachments: [expect.objectContaining({ url: 'https://cdn.example.com/photo.jpg' })],
    attachmentPolicy: { allowDataUrls: false },
  }));
});

it('generic inbound route rejects data URLs', async () => {
  const res = await app.request('/gateway/ch_1', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      externalId: 'user_1',
      text: '',
      attachments: [{ url: 'data:image/png;base64,cG5n' }],
    }),
  });

  expect(res.status).toBe(400);
  expect(routeInboundMessage).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Add failing WhatsApp Evolution media tests**

Add tests for:

- `imageMessage` with caption routes text plus attachment.
- `audioMessage` without text routes empty text plus attachment.
- media-only events do not return early.

Use an Evolution payload shape with `data.message.imageMessage.url`, `caption`, `mimetype`, and `fileLength`.

- [ ] **Step 3: Verify RED**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run src/gateway/message-router.test.ts
```

Expected: FAIL because the generic schema is text-only and Evolution ignores media-only events.

- [ ] **Step 4: Implement route schema and Evolution extraction**

In `message-router.ts`:

- Extend `inboundSchema` with `text: z.string().default('')` and optional `attachments`.
- Use `normalizeInboundAttachments(..., { allowDataUrls: false })` before calling `routeInboundMessage`.
- Return 400 when `text.trim()` is blank and no valid normalized attachments remain.
- Add media fields to `EvolutionWebhookData`.
- Add `readEvolutionAttachments(data)` for `imageMessage`, `audioMessage`, `videoMessage`, `documentMessage`.
- Route if either text or attachments exists.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run src/gateway/message-router.test.ts src/lib/inbound-attachments.test.ts
pnpm --dir gateway/packages/api build
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git -C gateway add packages/api/src/gateway/message-router.ts packages/api/src/gateway/message-router.test.ts
git -C gateway commit -m "feat: route inbound media from gateway webhooks"
git add gateway
git commit -m "chore: update gateway inbound media webhooks"
```

## Task 4: Bridge Inbound Attachment Normalization

**Files:**
- Create: `connector/clawscale_bridge/inbound_attachments.py`
- Modify: `connector/clawscale_bridge/app.py`
- Test: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`

- [ ] **Step 1: Write failing bridge tests**

Add tests to `test_bridge_app.py`:

```python
def test_bridge_inbound_reads_message_attachments_and_enqueues_fallback(monkeypatch):
    from connector.clawscale_bridge.app import create_app
    import connector.clawscale_bridge.app as bridge_app

    app = create_app(testing=True)
    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "in_evt_media_1"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.return_value = {"reply": "ok"}
    service = bridge_app.BusinessOnlyBridgeGateway(
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        target_character_id="char_1",
    )
    monkeypatch.setitem(app.config, "BRIDGE_GATEWAY", service)

    response = app.test_client().post(
        "/bridge/inbound",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "caption",
                    "attachments": [
                        {
                            "url": "https://cdn.example.com/photo.jpg",
                            "filename": "photo.jpg",
                            "contentType": "image/jpeg",
                        }
                    ],
                }
            ],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "endUserId": "eu_1",
                "externalId": "wxid_123",
                "platform": "wechat_personal",
                "channelScope": "personal",
                "clawscaleUserId": "csu_1",
                "cokeAccountId": "acct_1",
                "inboundEventId": "in_evt_media_1",
            },
        },
    )

    assert response.status_code == 200
    inbound = message_gateway.enqueue.call_args.kwargs["inbound"]
    assert inbound["input"] == "caption\n\nAttachment: https://cdn.example.com/photo.jpg"
    assert inbound["inbound_text"] == "caption"
    assert inbound["attachments"][0]["safeDisplayUrl"] == "https://cdn.example.com/photo.jpg"
```

Add tests for:

- top-level attachments override invalid/absent message-level only when valid
- attachment-only payload enqueues `Attachment: <safeDisplayUrl>`
- data URL fallback is redacted
- invalid attachment-only payload returns ignored response and does not enqueue
- missing account context still returns `missing_coke_account_id` before empty ignore

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py -v
```

Expected: FAIL because bridge attachments are ignored.

- [ ] **Step 3: Implement Python normalizer**

Create `connector/clawscale_bridge/inbound_attachments.py` with:

- `normalize_inbound_attachments(raw_attachments, allow_data_urls=True)`
- the same limits as Gateway
- `safeDisplayUrl`
- `format_input_with_attachments(text, attachments)`

Use Python standard libraries `base64`, `json`, `math`, and `urllib.parse.urlsplit`.

- [ ] **Step 4: Wire bridge normalization**

In `app.py`:

- `_normalize_inbound` extracts top-level attachments, latest user message attachments, and fallback last-message attachments.
- It chooses top-level normalized attachments only when that set has at least one valid attachment.
- It builds `input` with `format_input_with_attachments`.
- It stores `attachments` and `inbound_text` on normalized inbound.
- `handle_inbound` returns `{"status": "ignored", "reason": "empty_inbound"}` after account validation when input is blank and attachments empty.
- `/bridge/inbound` maps ignored to `{ok: true, ignored: true, reason}`.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

Run:

```bash
git add connector/clawscale_bridge/inbound_attachments.py connector/clawscale_bridge/app.py tests/unit/connector/clawscale_bridge/test_bridge_app.py
git commit -m "feat: normalize inbound attachments in bridge"
```

## Task 5: Worker Message Metadata And Prompt Formatting

**Files:**
- Modify: `connector/clawscale_bridge/message_gateway.py`
- Test: `tests/unit/connector/clawscale_bridge/test_message_gateway.py`
- Test: `tests/unit/agent/test_message_util_clawscale_routing.py`

- [ ] **Step 1: Add failing message gateway tests**

In `test_message_gateway.py`, add tests proving:

- `metadata.attachments`, `metadata.mediaUrls`, and `metadata.inbound_text` are stored.
- single image attachment sets `message_type: "image"`.
- single audio attachment sets `message_type: "voice"`.
- mixed/file attachments keep `message_type: "text"`.
- text-only behavior and causal inbound dedupe remain unchanged.

- [ ] **Step 2: Add failing Worker formatter tests**

In `tests/unit/agent/test_message_util_clawscale_routing.py`, add tests:

```python
def test_clawscale_image_message_prompt_keeps_attachment_fallback(monkeypatch):
    from agent.util.message_util import messages_to_str

    monkeypatch.setattr("agent.util.message_util.UserDAO", lambda: MagicMock(get_user_by_id=lambda _: None))
    monkeypatch.setattr("agent.util.message_util.MongoDBBase", lambda: MagicMock(get_vector_by_id=lambda *_: None))

    rendered = messages_to_str([
        {
            "platform": "business",
            "from_user": "acct_1",
            "input_timestamp": 1710000000,
            "message_type": "image",
            "message": "caption\n\nAttachment: https://cdn.example.com/photo.jpg",
            "metadata": {
                "source": "clawscale",
                "coke_account": {"id": "acct_1", "display_name": "Alice"},
            },
        }
    ])

    assert "Attachment: https://cdn.example.com/photo.jpg" in rendered
```

Add equivalent tests for voice, mixed text, and data redaction marker.

- [ ] **Step 3: Verify RED**

Run:

```bash
pytest tests/unit/connector/clawscale_bridge/test_message_gateway.py tests/unit/agent/test_message_util_clawscale_routing.py -v
```

Expected: FAIL because message gateway metadata/type mapping is not implemented.

- [ ] **Step 4: Implement message gateway metadata**

In `message_gateway.py`:

- Extend `enqueue` and `build_input_message` to carry `attachments` and `inbound_text`.
- Add helper `_resolve_message_type(attachments)`:
  - one `image/` attachment only -> `image`
  - one `audio/` attachment only -> `voice`
  - otherwise -> `text`
- Add `metadata.attachments`, `metadata.mediaUrls`, and `metadata.inbound_text` when attachments are present.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
pytest tests/unit/connector/clawscale_bridge/test_message_gateway.py tests/unit/agent/test_message_util_clawscale_routing.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

Run:

```bash
git add connector/clawscale_bridge/message_gateway.py tests/unit/connector/clawscale_bridge/test_message_gateway.py tests/unit/agent/test_message_util_clawscale_routing.py
git commit -m "feat: preserve inbound media on worker messages"
```

## Task 6: Cross-Surface Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run bridge unit surface**

Run:

```bash
pytest tests/unit/connector/clawscale_bridge/ -v
```

Expected: PASS.

- [ ] **Step 2: Run Worker formatter routing surface**

Run:

```bash
pytest tests/unit/agent/test_message_util_clawscale_routing.py -v
```

Expected: PASS.

- [ ] **Step 3: Run Gateway focused surface**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run src/lib/inbound-attachments.test.ts src/gateway/message-router.test.ts src/lib/route-message.test.ts src/lib/ai-backend.test.ts
```

Expected: PASS.

- [ ] **Step 4: Run Gateway full API suite and build**

Run:

```bash
pnpm --dir gateway/packages/api test
pnpm --dir gateway/packages/api build
```

Expected: PASS.

- [ ] **Step 5: Run repo check**

Run:

```bash
zsh scripts/check
```

Expected: PASS.

- [ ] **Step 6: Review final status**

Run:

```bash
git status --short --branch
git -C gateway status --short --branch
git log --oneline --decorate -12
git -C gateway log --oneline --decorate -10
```

Expected: root and Gateway submodule are clean; root branch includes plan and wrapper commits; Gateway submodule includes Gateway implementation commits.
