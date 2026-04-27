# Outbound Multimodal Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Coke-generated image and voice outputs travel through the ClawScale outbound path as explicit media payloads instead of dying at Gateway text-only validation.

**Architecture:** Keep Worker output format unchanged. Normalize `outputmessages.metadata.url` into `mediaUrls` and `audioAsVoice` in the bridge, then let Gateway validate a normalized text-plus-media payload and deliver media through explicit text-link fallback for current outbound channel types.

**Tech Stack:** Python bridge dispatcher/client tests with pytest; Gateway API TypeScript, Hono, Zod, Prisma JSON payloads, and Vitest.

---

## File Structure

- Modify `connector/clawscale_bridge/output_dispatcher.py`
  - Normalize Coke `image` and `voice` output documents into Gateway media payload arguments.
  - Fail claimed malformed media outputs before posting to Gateway.
- Modify `connector/clawscale_bridge/gateway_outbound_client.py`
  - Accept optional `media_urls` and `audio_as_voice` arguments and serialize them as `mediaUrls` and `audioAsVoice`.
- Modify `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`
  - Cover image payload, voice payload, URL trimming, and malformed media failure.
- Modify `gateway/packages/api/src/lib/outbound-delivery.ts`
  - Replace text-only delivery argument with a structured payload.
  - Format media fallback as visible attachment links for current supported channel types.
- Modify `gateway/packages/api/src/lib/outbound-delivery.test.ts`
  - Update text-only tests for the new payload signature.
  - Add media fallback tests.
- Modify `gateway/packages/api/src/routes/outbound.ts`
  - Validate `text | mediaUrls | audioAsVoice`, normalize the request, persist normalized comparable media fields, and pass a structured payload to delivery.
- Modify `gateway/packages/api/src/routes/outbound.test.ts`
  - Update helper types and existing expectations for structured delivery.
  - Add media validation, normalization, idempotency, and delivery tests.

## Task 1: Bridge Media Payload Normalization

**Files:**
- Modify: `connector/clawscale_bridge/output_dispatcher.py`
- Modify: `connector/clawscale_bridge/gateway_outbound_client.py`
- Test: `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`

- [ ] **Step 1: Write failing dispatcher tests for image and voice payloads**

Append these tests to `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`:

```python
def test_output_dispatcher_posts_image_media_url_to_gateway():
    from connector.clawscale_bridge.output_dispatcher import ClawScaleOutputDispatcher

    mongo = MagicMock()
    collection = MagicMock()
    collection.find_one_and_update.return_value = _build_message_doc(
        status="dispatching",
        message="照片来了",
        message_type="image",
        metadata={
            "business_conversation_key": "bc_1",
            "delivery_mode": "push",
            "idempotency_key": "idem_1",
            "trace_id": "trace_1",
            "output_id": "out_1",
            "url": "  https://cdn.example.com/photo.jpg  ",
        },
    )
    mongo.get_collection.return_value = collection
    gateway_client = MagicMock()
    gateway_client.post_output.return_value.status_code = 200

    dispatcher = ClawScaleOutputDispatcher(mongo=mongo, gateway_client=gateway_client)

    assert dispatcher.dispatch_once() is True
    gateway_client.post_output.assert_called_once_with(
        output_id="out_1",
        customer_id="acc_1",
        business_conversation_key="bc_1",
        text="照片来了",
        message_type="image",
        media_urls=["https://cdn.example.com/photo.jpg"],
        audio_as_voice=False,
        delivery_mode="push",
        expect_output_timestamp=1710000000,
        idempotency_key="idem_1",
        trace_id="trace_1",
        causal_inbound_event_id=None,
    )


def test_output_dispatcher_posts_voice_media_url_and_voice_hint_to_gateway():
    from connector.clawscale_bridge.output_dispatcher import ClawScaleOutputDispatcher

    mongo = MagicMock()
    collection = MagicMock()
    collection.find_one_and_update.return_value = _build_message_doc(
        status="dispatching",
        message="语音内容",
        message_type="voice",
        metadata={
            "business_conversation_key": "bc_1",
            "delivery_mode": "push",
            "idempotency_key": "idem_1",
            "trace_id": "trace_1",
            "output_id": "out_1",
            "url": "https://cdn.example.com/voice.mp3",
            "voice_length": 2000,
        },
    )
    mongo.get_collection.return_value = collection
    gateway_client = MagicMock()
    gateway_client.post_output.return_value.status_code = 200

    dispatcher = ClawScaleOutputDispatcher(mongo=mongo, gateway_client=gateway_client)

    assert dispatcher.dispatch_once() is True
    gateway_client.post_output.assert_called_once_with(
        output_id="out_1",
        customer_id="acc_1",
        business_conversation_key="bc_1",
        text="语音内容",
        message_type="voice",
        media_urls=["https://cdn.example.com/voice.mp3"],
        audio_as_voice=True,
        delivery_mode="push",
        expect_output_timestamp=1710000000,
        idempotency_key="idem_1",
        trace_id="trace_1",
        causal_inbound_event_id=None,
    )
```

- [ ] **Step 2: Write failing malformed media test**

Append:

```python
def test_output_dispatcher_marks_media_without_url_failed():
    from connector.clawscale_bridge.output_dispatcher import ClawScaleOutputDispatcher

    mongo = MagicMock()
    collection = MagicMock()
    collection.find_one_and_update.return_value = _build_message_doc(
        status="dispatching",
        message_type="image",
        metadata={
            "business_conversation_key": "bc_1",
            "delivery_mode": "push",
            "idempotency_key": "idem_1",
            "trace_id": "trace_1",
            "output_id": "out_1",
            "url": "   ",
        },
    )
    mongo.get_collection.return_value = collection
    gateway_client = MagicMock()

    dispatcher = ClawScaleOutputDispatcher(mongo=mongo, gateway_client=gateway_client)

    assert dispatcher.dispatch_once() is False
    gateway_client.post_output.assert_not_called()
    mongo.update_one.assert_called_once_with(
        "outputmessages",
        {"_id": "out_1", "status": "dispatching"},
        {"$set": {"status": "failed", "handled_timestamp": ANY}},
    )
```

- [ ] **Step 3: Run bridge tests and verify they fail**

Run:

```bash
pytest tests/unit/connector/clawscale_bridge/test_output_dispatcher.py -v
```

Expected: FAIL because `post_output()` is not called with `media_urls` / `audio_as_voice`, and malformed media is not rejected before posting.

- [ ] **Step 4: Implement bridge media normalization**

In `connector/clawscale_bridge/output_dispatcher.py`, add a helper near `_build_gateway_args`:

```python
    def _build_media_args(self, message):
        message_type = message.get("message_type", "text")
        if message_type not in {"image", "voice"}:
            return {"media_urls": None, "audio_as_voice": False}

        metadata = message.get("metadata") or {}
        raw_url = metadata.get("url")
        media_url = raw_url.strip() if isinstance(raw_url, str) else ""
        if not media_url:
            raise ValueError(f"{message_type} output missing metadata.url")

        return {
            "media_urls": [media_url],
            "audio_as_voice": message_type == "voice",
        }
```

Then update `_build_gateway_args` to include the helper output:

```python
        media_args = self._build_media_args(message)
        return {
            "output_id": metadata["output_id"],
            "customer_id": customer_id,
            "business_conversation_key": metadata["business_conversation_key"],
            "text": message.get("message", ""),
            "message_type": message.get("message_type", "text"),
            **media_args,
            "delivery_mode": metadata["delivery_mode"],
            "expect_output_timestamp": message["expect_output_timestamp"],
            "idempotency_key": metadata["idempotency_key"],
            "trace_id": metadata["trace_id"],
            "causal_inbound_event_id": metadata.get("causal_inbound_event_id"),
        }
```

- [ ] **Step 5: Implement Gateway client serialization**

In `connector/clawscale_bridge/gateway_outbound_client.py`, extend `post_output`:

```python
        media_urls: list[str] | None = None,
        audio_as_voice: bool = False,
```

After building the payload:

```python
        if media_urls:
            payload["mediaUrls"] = media_urls
        if audio_as_voice:
            payload["audioAsVoice"] = True
```

- [ ] **Step 6: Run bridge tests and verify they pass**

Run:

```bash
pytest tests/unit/connector/clawscale_bridge/test_output_dispatcher.py -v
```

Expected: all tests in the file pass.

- [ ] **Step 7: Commit Task 1**

Run:

```bash
git add connector/clawscale_bridge/output_dispatcher.py connector/clawscale_bridge/gateway_outbound_client.py tests/unit/connector/clawscale_bridge/test_output_dispatcher.py
git commit -m "feat: normalize outbound media in bridge"
```

## Task 2: Gateway Delivery Fallback Payload

**Files:**
- Modify: `gateway/packages/api/src/lib/outbound-delivery.ts`
- Test: `gateway/packages/api/src/lib/outbound-delivery.test.ts`

- [ ] **Step 1: Update delivery tests for structured text payloads**

In `gateway/packages/api/src/lib/outbound-delivery.test.ts`, update text-only calls from:

```ts
await deliverOutboundMessage(channel, 'wxid_1', 'hello');
```

to:

```ts
await deliverOutboundMessage(channel, 'wxid_1', {
  text: 'hello',
  messageType: 'text',
  mediaUrls: [],
  audioAsVoice: false,
});
```

Apply the same shape to all existing `deliverOutboundMessage` calls.

- [ ] **Step 2: Add failing media fallback tests**

Append:

```ts
  it('delivers wechat media as visible attachment links', async () => {
    await deliverOutboundMessage(
      {
        id: 'ch_wechat_1',
        type: 'wechat_personal',
        status: 'connected',
      },
      'wxid_1',
      {
        text: 'caption',
        messageType: 'image',
        mediaUrls: ['https://cdn.example.com/photo.jpg'],
        audioAsVoice: false,
      },
    );

    expect(sendWeixinText).toHaveBeenCalledWith(
      'ch_wechat_1',
      'wxid_1',
      'caption\n\nAttachment: https://cdn.example.com/photo.jpg',
    );
    expect(sendText).not.toHaveBeenCalled();
  });

  it('delivers media-only fallback without a leading blank caption', async () => {
    await deliverOutboundMessage(
      {
        id: 'ch_wechat_1',
        type: 'wechat_personal',
        status: 'connected',
      },
      'wxid_1',
      {
        text: '',
        messageType: 'voice',
        mediaUrls: ['https://cdn.example.com/voice.mp3'],
        audioAsVoice: true,
      },
    );

    expect(sendWeixinText).toHaveBeenCalledWith(
      'ch_wechat_1',
      'wxid_1',
      'Attachment: https://cdn.example.com/voice.mp3',
    );
  });

  it('delivers whatsapp_evolution media as visible attachment links', async () => {
    await deliverOutboundMessage(
      {
        id: 'ch_wa_1',
        type: 'whatsapp_evolution',
        status: 'connected',
        config: {
          instanceName: 'coke-whatsapp-personal',
          webhookToken: 'secret-token',
        },
      },
      '8619917902815@s.whatsapp.net',
      {
        text: 'caption',
        messageType: 'image',
        mediaUrls: ['https://cdn.example.com/photo.jpg'],
        audioAsVoice: false,
      },
    );

    expect(sendText).toHaveBeenCalledWith(
      'coke-whatsapp-personal',
      '8619917902815',
      'caption\n\nAttachment: https://cdn.example.com/photo.jpg',
    );
    expect(sendWeixinText).not.toHaveBeenCalled();
  });
```

- [ ] **Step 3: Run delivery tests and verify they fail**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/outbound-delivery.test.ts
```

Expected: FAIL because `deliverOutboundMessage` still accepts a string text argument.

- [ ] **Step 4: Implement structured delivery payload and fallback**

In `gateway/packages/api/src/lib/outbound-delivery.ts`, replace the text-only signature with:

```ts
export type OutboundMessagePayload = {
  text: string;
  messageType: 'text' | 'image' | 'voice';
  mediaUrls: string[];
  audioAsVoice: boolean;
};

function formatTextWithAttachmentLinks(text: string, mediaUrls: string[]): string {
  const trimmedText = text.trim();
  const attachmentText = mediaUrls.map((url) => `Attachment: ${url}`).join('\n');
  if (!trimmedText) return attachmentText;
  if (!attachmentText) return trimmedText;
  return `${trimmedText}\n\n${attachmentText}`;
}
```

Then update delivery:

```ts
export async function deliverOutboundMessage(
  channel: { id: string; type: string; status?: string; config?: unknown },
  externalEndUserId: string,
  payload: OutboundMessagePayload,
): Promise<void> {
  assertConnectedChannel(channel);
  const text = payload.mediaUrls.length > 0
    ? formatTextWithAttachmentLinks(payload.text, payload.mediaUrls)
    : payload.text;

  switch (channel.type) {
    case 'wechat_personal':
      await sendWeixinText(channel.id, externalEndUserId, text);
      return;
    case 'whatsapp_evolution': {
      const config = parseStoredWhatsAppEvolutionConfig(channel.config);
      await new EvolutionApiClient().sendText(
        config.instanceName,
        normalizeWhatsAppTarget(externalEndUserId),
        text,
      );
      return;
    }
    default:
      if (payload.mediaUrls.length > 0) {
        throw new Error(`Unsupported outbound media for channel type: ${channel.type}`);
      }
      throw new Error(`Unsupported outbound channel type: ${channel.type}`);
  }
}
```

- [ ] **Step 5: Run delivery tests and verify they pass**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/outbound-delivery.test.ts
```

Expected: all delivery tests pass.

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git -C gateway add packages/api/src/lib/outbound-delivery.ts packages/api/src/lib/outbound-delivery.test.ts
git -C gateway commit -m "feat: deliver outbound media as attachment links"
git add gateway
git commit -m "chore: update gateway media delivery submodule"
```

## Task 3: Gateway Outbound Route Media Contract

**Files:**
- Modify: `gateway/packages/api/src/routes/outbound.ts`
- Modify: `gateway/packages/api/src/routes/outbound.test.ts`

- [ ] **Step 1: Update route test helper types**

In `gateway/packages/api/src/routes/outbound.test.ts`, change `OutboundBody` to:

```ts
interface OutboundBody {
  output_id: string;
  account_id?: string;
  customer_id?: string;
  business_conversation_key: string;
  message_type: string;
  text?: string;
  mediaUrls?: string[];
  audioAsVoice?: boolean;
  delivery_mode: string;
  expect_output_timestamp: string;
  idempotency_key: string;
  trace_id: string;
  causal_inbound_event_id?: string;
}
```

Change `normalizePayload` to return normalized media fields:

```ts
function normalizePayload(body: OutboundBody): Record<string, string | boolean | string[]> {
  const normalizedCustomerId = body.customer_id ?? body.account_id ?? '';
  const payload: Record<string, string | boolean | string[]> = {
    output_id: body.output_id,
    customer_id: normalizedCustomerId,
    business_conversation_key: body.business_conversation_key,
    message_type: body.message_type,
    text: body.text ?? '',
    mediaUrls: body.mediaUrls ?? [],
    audioAsVoice: body.audioAsVoice ?? false,
    delivery_mode: body.delivery_mode,
    expect_output_timestamp: body.expect_output_timestamp,
    idempotency_key: body.idempotency_key,
    trace_id: body.trace_id,
  };
  if (body.causal_inbound_event_id) {
    payload.causal_inbound_event_id = body.causal_inbound_event_id;
  }
  return payload;
}
```

- [ ] **Step 2: Update existing text delivery expectations**

Replace existing expectations like:

```ts
expect(deliverOutboundMessage).toHaveBeenCalledWith(channel, 'wxid_1', 'hello');
```

with:

```ts
expect(deliverOutboundMessage).toHaveBeenCalledWith(channel, 'wxid_1', {
  text: 'hello',
  messageType: 'text',
  mediaUrls: [],
  audioAsVoice: false,
});
```

- [ ] **Step 3: Add failing media route tests**

Append tests inside `describe('outbound router', () => { ... })`:

```ts
  it('accepts image media payloads and stores normalized media fields', async () => {
    const body = makeBody({
      message_type: 'image',
      text: 'photo caption',
      mediaUrls: ['https://cdn.example.com/photo.jpg'],
    });

    const res = await postOutbound(body);

    expect(res.status).toBe(200);
    expect(db.outboundDelivery.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        payload: expect.objectContaining({
          message_type: 'image',
          text: 'photo caption',
          mediaUrls: ['https://cdn.example.com/photo.jpg'],
          audioAsVoice: false,
          channel_id: 'ch_1',
          external_end_user_id: 'wxid_1',
        }),
      }),
    });
    expect(deliverOutboundMessage).toHaveBeenCalledWith(channel, 'wxid_1', {
      text: 'photo caption',
      messageType: 'image',
      mediaUrls: ['https://cdn.example.com/photo.jpg'],
      audioAsVoice: false,
    });
  });

  it('accepts media-only voice payloads and coerces audioAsVoice', async () => {
    const res = await postOutbound(
      makeBody({
        message_type: 'voice',
        text: undefined,
        mediaUrls: ['https://cdn.example.com/voice.mp3'],
      }),
    );

    expect(res.status).toBe(200);
    expect(deliverOutboundMessage).toHaveBeenCalledWith(channel, 'wxid_1', {
      text: '',
      messageType: 'voice',
      mediaUrls: ['https://cdn.example.com/voice.mp3'],
      audioAsVoice: true,
    });
  });

  it('rejects media message types without media URLs', async () => {
    const res = await postOutbound(
      makeBody({
        message_type: 'image',
        text: 'caption',
        mediaUrls: [],
      }),
    );

    expect(res.status).toBe(400);
    expect(deliverOutboundMessage).not.toHaveBeenCalled();
  });

  it.each(['file:///tmp/photo.jpg', '/tmp/photo.jpg', 'photo.jpg', 'data:image/png;base64,abc'])(
    'rejects unsupported media URL %s',
    async (mediaUrl) => {
      const res = await postOutbound(
        makeBody({
          message_type: 'image',
          mediaUrls: [mediaUrl],
        }),
      );

      expect(res.status).toBe(400);
      expect(deliverOutboundMessage).not.toHaveBeenCalled();
    },
  );

  it('rejects voice payloads that explicitly disable audioAsVoice', async () => {
    const res = await postOutbound(
      makeBody({
        message_type: 'voice',
        mediaUrls: ['https://cdn.example.com/voice.mp3'],
        audioAsVoice: false,
      }),
    );

    expect(res.status).toBe(400);
    expect(deliverOutboundMessage).not.toHaveBeenCalled();
  });

  it('rejects audioAsVoice on non-voice payloads', async () => {
    const res = await postOutbound(
      makeBody({
        message_type: 'image',
        mediaUrls: ['https://cdn.example.com/photo.jpg'],
        audioAsVoice: true,
      }),
    );

    expect(res.status).toBe(400);
    expect(deliverOutboundMessage).not.toHaveBeenCalled();
  });

  it('returns 409 for conflicting media payload with reused idempotency key', async () => {
    const original = makeBody({
      message_type: 'image',
      mediaUrls: ['https://cdn.example.com/original.jpg'],
    });
    vi.mocked(db.outboundDelivery.findUnique).mockResolvedValue({
      id: 'outbound_1',
      status: 'succeeded',
      payload: normalizePayload(original),
    } as never);

    const res = await postOutbound(
      makeBody({
        message_type: 'image',
        mediaUrls: ['https://cdn.example.com/changed.jpg'],
      }),
    );

    expect(res.status).toBe(409);
    await expect(res.json()).resolves.toEqual({
      ok: false,
      error: 'idempotency_key_conflict',
      idempotency_key: 'idem_1',
    });
    expect(deliverOutboundMessage).not.toHaveBeenCalled();
  });
```

- [ ] **Step 4: Run route tests and verify they fail**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/routes/outbound.test.ts
```

Expected: FAIL because `/api/outbound` still rejects image/voice and still calls `deliverOutboundMessage` with a text string.

- [ ] **Step 5: Implement schema, normalization, and comparable payload**

In `gateway/packages/api/src/routes/outbound.ts`, replace the schema with a permissive base schema plus `superRefine`:

```ts
const messageTypeSchema = z.enum(['text', 'image', 'voice']);
const mediaUrlSchema = z.string().trim().url().refine((value) => {
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}, 'media URL must be absolute http(s)');

const bodySchema = z.object({
  output_id: z.string().min(1),
  account_id: z.string().min(1).optional(),
  customer_id: z.string().min(1).optional(),
  business_conversation_key: z.string().min(1),
  message_type: messageTypeSchema,
  text: z.string().optional(),
  mediaUrls: z.array(mediaUrlSchema).optional(),
  audioAsVoice: z.boolean().optional(),
  delivery_mode: z.enum(['push', 'request_response']),
  expect_output_timestamp: z.string().min(1),
  idempotency_key: z.string().min(1),
  trace_id: z.string().min(1),
  causal_inbound_event_id: z.string().min(1).optional(),
}).superRefine((body, ctx) => {
  const text = body.text?.trim() ?? '';
  const mediaUrls = body.mediaUrls ?? [];
  if (!text && mediaUrls.length === 0) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['text'], message: 'text or mediaUrls is required' });
  }
  if ((body.message_type === 'image' || body.message_type === 'voice') && mediaUrls.length === 0) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['mediaUrls'], message: `${body.message_type} requires mediaUrls` });
  }
  if (body.message_type === 'voice' && body.audioAsVoice === false) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['audioAsVoice'], message: 'voice requires audioAsVoice' });
  }
  if (body.message_type !== 'voice' && body.audioAsVoice === true) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['audioAsVoice'], message: 'audioAsVoice is only valid for voice' });
  }
});
```

Add a normalized body type:

```ts
type NormalizedOutboundBody = RawOutboundBody & {
  customer_id: string;
  text: string;
  mediaUrls: string[];
  audioAsVoice: boolean;
};
```

Update `normalizeBody` to return normalized fields:

```ts
function normalizeBody(body: RawOutboundBody): NormalizedOutboundBody | null {
  const customerId = body.customer_id?.trim() ?? body.account_id?.trim() ?? '';
  if (!customerId) return null;

  return {
    ...body,
    customer_id: customerId,
    text: body.text ?? '',
    mediaUrls: body.mediaUrls ?? [],
    audioAsVoice: body.message_type === 'voice' ? true : (body.audioAsVoice ?? false),
  };
}
```

Update `normalizeComparablePayload` and `readComparablePayload` to include:

```ts
mediaUrls: body.mediaUrls,
audioAsVoice: body.audioAsVoice,
```

For `readComparablePayload`, handle arrays and booleans explicitly:

```ts
const mediaUrls = record['mediaUrls'];
if (Array.isArray(mediaUrls) && mediaUrls.every((value) => typeof value === 'string')) {
  comparable['mediaUrls'] = mediaUrls;
}
const audioAsVoice = record['audioAsVoice'];
if (typeof audioAsVoice === 'boolean') {
  comparable['audioAsVoice'] = audioAsVoice;
}
```

- [ ] **Step 6: Pass structured payload to delivery**

Change the delivery call in `outbound.ts` to:

```ts
    await deliverOutboundMessage(
      channel,
      deliveryTarget?.externalEndUserId ?? deliveryRoute!.externalEndUserId,
      {
        text: body.text,
        messageType: body.message_type,
        mediaUrls: body.mediaUrls,
        audioAsVoice: body.audioAsVoice,
      },
    );
```

- [ ] **Step 7: Run route tests and verify they pass**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/routes/outbound.test.ts
```

Expected: all route tests pass.

- [ ] **Step 8: Run focused Gateway tests together**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/routes/outbound.test.ts src/lib/outbound-delivery.test.ts
```

Expected: both focused Gateway test files pass.

- [ ] **Step 9: Commit Task 3**

Run:

```bash
git -C gateway add packages/api/src/routes/outbound.ts packages/api/src/routes/outbound.test.ts
git -C gateway commit -m "feat: accept outbound media payloads"
git add gateway
git commit -m "chore: update gateway outbound media route"
```

## Task 4: Cross-Surface Verification

**Files:**
- Verify only; no production file edits expected.

- [ ] **Step 1: Run bridge verification**

Run:

```bash
pytest tests/unit/connector/clawscale_bridge/ -v
```

Expected: all bridge unit tests pass.

- [ ] **Step 2: Run focused Gateway verification**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/routes/outbound.test.ts src/lib/outbound-delivery.test.ts
```

Expected: both focused Gateway test files pass.

- [ ] **Step 3: Run repo-OS check**

Run:

```bash
zsh scripts/check
```

Expected: check passed.

- [ ] **Step 4: Review final diff**

Run:

```bash
git status --short
git log --oneline --decorate -5
git diff --stat HEAD~4..HEAD
git -C gateway log --oneline --decorate -3
```

Expected: root branch contains the spec/task commit plus task wrapper commits; gateway submodule contains the two Gateway implementation commits.

- [ ] **Step 5: Commit verification note if any docs changed**

If no files changed during verification, do not create a commit. If a worker updates tracked generated metadata, inspect it first and only commit it if it is clearly required by the verification command.
