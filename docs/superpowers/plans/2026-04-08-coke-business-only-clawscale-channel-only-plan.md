# Coke Business-Only / Clawscale Channel-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-cut the `wechat_personal` path to the target architecture where Coke owns only business state, Clawscale owns only channel and delivery state, and Bridge only translates normalized messages between them.

**Architecture:** Persist exact `DeliveryRoute(account_id, business_conversation_key)` truth in Clawscale Postgres, mint `business_conversation_key` only in Coke through an explicit open-conversation protocol, remove platform identity and route truth from Coke runtime, and make Bridge handle only normalized inbound/outbound contracts plus short-lived sync correlation.

**Tech Stack:** Python 3.12, Flask, PyMongo, pytest, TypeScript, Hono, Prisma, PostgreSQL, Next.js, Vitest, pnpm

---

## File Structure

### New gateway files

- `gateway/packages/api/src/lib/business-conversation.ts`
  Owns the exact conversation-binding and delivery-route rules in Clawscale: establish, refresh, resolve, invalidate.
- `gateway/packages/api/src/lib/business-conversation.test.ts`
  Covers route upsert, exact resolution, peer replacement invalidation, and missing-route errors.
- `gateway/packages/api/src/routes/coke-delivery-routes.ts`
  Internal authenticated route surface for cutover/backfill tooling to upsert exact `DeliveryRoute` records in Postgres.
- `gateway/packages/api/src/routes/coke-delivery-routes.test.ts`
  Verifies auth, validation, exact upsert semantics, and route replacement behavior.

### Modified gateway files

- `gateway/packages/api/prisma/schema.prisma`
  Adds durable business-conversation binding and exact delivery-route schema to Postgres.
- `gateway/packages/api/src/index.ts`
  Mounts the new internal delivery-route router.
- `gateway/packages/api/src/lib/ai-backend.ts`
  Extends custom backend parsing from plain-text reply to structured reply payloads carrying `business_conversation_key`, `output_id`, and causal identifiers.
- `gateway/packages/api/src/lib/route-message.ts`
  Implements the new protocols: first-turn open conversation, established-conversation inbound, exact route refresh, peer-change re-establishment.
- `gateway/packages/api/src/lib/route-message.test.ts`
  Covers first inbound without a business key, established inbound with a stored key, and peer-change conversation replacement.
- `gateway/packages/api/src/routes/outbound.ts`
  Changes the outbound contract from channel-native routing inputs to normalized business outputs resolved through exact `DeliveryRoute`.
- `gateway/packages/api/src/routes/outbound.test.ts`
  Covers exact route resolution, missing-route failure, stale route replacement, and idempotency semantics.
- `gateway/packages/api/src/lib/outbound-delivery.ts`
  Keeps platform send logic adapter-local while accepting resolved route targets from `DeliveryRoute` instead of Bridge-supplied platform IDs.
- `gateway/packages/api/src/lib/clawscale-user.ts`
  Keeps `Coke Account <-> ClawscaleUser` provisioning idempotent and exposes the tenant/user data needed for hard cutover.
- `gateway/packages/api/src/routes/coke-user-provision.ts`
  Stays the single provision entrypoint but now gates registration success on durable readiness.

### New bridge files

- `connector/clawscale_bridge/gateway_outbound_client.py`
  Typed client for posting normalized business outputs to gateway `/api/outbound`.
- `tests/unit/connector/clawscale_bridge/test_gateway_outbound_client.py`
  Covers auth, payload shape, timeout handling, and structured delivery failures.
- `connector/clawscale_bridge/backfill_delivery_routes.py`
  Hard-cutover tool that provisions missing users/channels, discovers exact active peers, and upserts exact `DeliveryRoute` records before an account is considered cut over.
- `tests/unit/connector/clawscale_bridge/test_backfill_delivery_routes.py`
  Covers eligible-account selection, unmappable-account rejection, and exact-route backfill writes.

### Modified bridge files

- `connector/clawscale_bridge/app.py`
  Removes legacy bind/identity routing from the live path, wires the normalized inbound contract, the normalized outbound dispatcher, and provisioning gates.
- `connector/clawscale_bridge/message_gateway.py`
  Writes normalized Coke input messages with no platform identity fields as required runtime data.
- `connector/clawscale_bridge/reply_waiter.py`
  Correlates synchronous replies by `causal_inbound_event_id` and `sync_reply_token`, not by platform metadata.
- `connector/clawscale_bridge/output_dispatcher.py`
  Dispatches normalized Coke outputs to gateway exact-route delivery instead of looking up routes in Mongo.
- `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
  Covers registration gating, first-turn conversation establishment, established-conversation sync replies, and structured failure responses.
- `tests/unit/connector/clawscale_bridge/test_message_gateway.py`
  Covers normalized inbound document shape and first-turn business-conversation establishment payloads.
- `tests/unit/connector/clawscale_bridge/test_reply_waiter.py`
  Covers sync correlation, retry polling, and expired `sync_reply_token` behavior.
- `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`
  Covers normalized outbound dispatch, exact-route-only behavior, and retryable vs terminal delivery failures.

### Modified Coke files

- `agent/util/message_util.py`
  Stops writing platform and route truth into Coke output messages; emits only normalized business output contract fields.
- `tests/unit/agent/test_message_util_clawscale_routing.py`
  Verifies that Coke outputs stay platform-free and carry only business identity and causal correlation.

### Legacy files to delete after cutover tasks pass

- `connector/clawscale_bridge/identity_service.py`
- `connector/clawscale_bridge/wechat_bind_session_service.py`
- `dao/clawscale_push_route_dao.py`
- `dao/external_identity_dao.py`
- `dao/wechat_bind_session_dao.py`
- `dao/binding_ticket_dao.py`
- `tests/unit/connector/clawscale_bridge/test_identity_service.py`
- `tests/unit/dao/test_clawscale_push_route_dao.py`
- `tests/unit/dao/test_external_identity_dao.py`
- `tests/unit/dao/test_wechat_bind_session_dao.py`
- `tests/unit/dao/test_binding_ticket_dao.py`

### E2E and regression files

- `scripts/run_wechat_personal_e2e.py`
  Extend the fake-provider runner so it verifies first-turn conversation establishment, steady-state sync reply, and proactive reminder delivery through exact `DeliveryRoute`.
- `tests/unit/test_run_wechat_personal_e2e.py`
  Covers the harness bootstrap assumptions and new proactive-delivery assertions.

---

## Task 1: Add durable business-conversation binding and exact delivery routes to Clawscale

**Files:**
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Create: `gateway/packages/api/src/lib/business-conversation.ts`
- Create: `gateway/packages/api/src/lib/business-conversation.test.ts`

- [ ] **Step 1: Write failing gateway route-state tests**

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';

const db = vi.hoisted(() => ({
  conversation: {
    update: vi.fn(),
    findUnique: vi.fn(),
  },
  deliveryRoute: {
    upsert: vi.fn(),
    findUnique: vi.fn(),
    updateMany: vi.fn(),
  },
}));

vi.mock('../db/index.js', () => ({ db }));

import {
  bindBusinessConversation,
  invalidateRoutesForChannelReplacement,
  resolveExactDeliveryRoute,
} from './business-conversation.js';

describe('bindBusinessConversation', () => {
  beforeEach(() => vi.clearAllMocks());

  it('writes the Coke-minted business key onto the gateway conversation and upserts the exact route', async () => {
    db.conversation.update.mockResolvedValue({ id: 'conv_gateway_1', businessConversationKey: 'bc_1' });
    db.deliveryRoute.upsert.mockResolvedValue({
      id: 'route_1',
      cokeAccountId: 'acc_1',
      businessConversationKey: 'bc_1',
      channelId: 'ch_1',
      endUserId: 'eu_1',
      externalEndUserId: 'wxid_1',
      isActive: true,
    });

    await bindBusinessConversation({
      tenantId: 'ten_1',
      gatewayConversationId: 'conv_gateway_1',
      cokeAccountId: 'acc_1',
      businessConversationKey: 'bc_1',
      channelId: 'ch_1',
      endUserId: 'eu_1',
      externalEndUserId: 'wxid_1',
    });

    expect(db.conversation.update).toHaveBeenCalledWith({
      where: { id: 'conv_gateway_1' },
      data: { businessConversationKey: 'bc_1' },
    });
    expect(db.deliveryRoute.upsert).toHaveBeenCalled();
  });
});

describe('resolveExactDeliveryRoute', () => {
  beforeEach(() => vi.clearAllMocks());

  it('resolves only the exact route for account_id + business_conversation_key', async () => {
    db.deliveryRoute.findUnique.mockResolvedValue({
      id: 'route_1',
      tenantId: 'ten_1',
      channelId: 'ch_1',
      endUserId: 'eu_1',
      externalEndUserId: 'wxid_1',
      isActive: true,
    });

    const route = await resolveExactDeliveryRoute({
      cokeAccountId: 'acc_1',
      businessConversationKey: 'bc_1',
    });

    expect(route?.channelId).toBe('ch_1');
    expect(route?.externalEndUserId).toBe('wxid_1');
  });

  it('throws missing_delivery_route when no exact route exists', async () => {
    db.deliveryRoute.findUnique.mockResolvedValue(null);

    await expect(
      resolveExactDeliveryRoute({
        cokeAccountId: 'acc_1',
        businessConversationKey: 'bc_missing',
      }),
    ).rejects.toMatchObject({ code: 'missing_delivery_route' });
  });
});

describe('invalidateRoutesForChannelReplacement', () => {
  beforeEach(() => vi.clearAllMocks());

  it('marks old routes inactive when a personal channel is archived and replaced', async () => {
    db.deliveryRoute.updateMany.mockResolvedValue({ count: 2 });

    await invalidateRoutesForChannelReplacement({
      tenantId: 'ten_1',
      channelId: 'ch_old',
    });

    expect(db.deliveryRoute.updateMany).toHaveBeenCalledWith({
      where: { tenantId: 'ten_1', channelId: 'ch_old', isActive: true },
      data: { isActive: false },
    });
  });
});
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `pnpm --dir gateway/packages/api exec vitest run src/lib/business-conversation.test.ts`

Expected: FAIL because `business-conversation.ts` does not exist and Prisma has no `businessConversationKey` or `DeliveryRoute` model.

- [ ] **Step 3: Extend the Prisma schema for hard route truth**

```prisma
model Conversation {
  id                      String   @id
  tenantId                String   @map("tenant_id")
  channelId               String   @map("channel_id")
  endUserId               String   @map("end_user_id")
  backendId               String?  @map("backend_id")
  businessConversationKey String?  @map("business_conversation_key")
  metadata                Json     @default("{}")
  createdAt               DateTime @default(now()) @map("created_at")
  updatedAt               DateTime @updatedAt @map("updated_at")

  @@index([tenantId])
  @@index([businessConversationKey])
  @@map("conversations")
}

model DeliveryRoute {
  id                      String   @id
  tenantId                String   @map("tenant_id")
  cokeAccountId           String   @map("coke_account_id")
  businessConversationKey String   @map("business_conversation_key")
  channelId               String   @map("channel_id")
  endUserId               String   @map("end_user_id")
  externalEndUserId       String   @map("external_end_user_id")
  isActive                Boolean  @default(true) @map("is_active")
  createdAt               DateTime @default(now()) @map("created_at")
  updatedAt               DateTime @updatedAt @map("updated_at")

  tenant  Tenant  @relation(fields: [tenantId], references: [id], onDelete: Cascade)
  channel Channel @relation(fields: [channelId], references: [id], onDelete: Cascade)
  endUser EndUser @relation(fields: [endUserId], references: [id], onDelete: Cascade)

  @@unique([cokeAccountId, businessConversationKey])
  @@index([tenantId, channelId])
  @@index([tenantId, endUserId])
  @@map("delivery_routes")
}
```

- [ ] **Step 4: Implement the gateway route-state service**

```ts
export async function bindBusinessConversation(input: {
  tenantId: string;
  gatewayConversationId: string;
  cokeAccountId: string;
  businessConversationKey: string;
  channelId: string;
  endUserId: string;
  externalEndUserId: string;
}) {
  await db.conversation.update({
    where: { id: input.gatewayConversationId },
    data: { businessConversationKey: input.businessConversationKey },
  });

  return db.deliveryRoute.upsert({
    where: {
      cokeAccountId_businessConversationKey: {
        cokeAccountId: input.cokeAccountId,
        businessConversationKey: input.businessConversationKey,
      },
    },
    update: {
      tenantId: input.tenantId,
      channelId: input.channelId,
      endUserId: input.endUserId,
      externalEndUserId: input.externalEndUserId,
      isActive: true,
    },
    create: {
      id: generateId('route'),
      tenantId: input.tenantId,
      cokeAccountId: input.cokeAccountId,
      businessConversationKey: input.businessConversationKey,
      channelId: input.channelId,
      endUserId: input.endUserId,
      externalEndUserId: input.externalEndUserId,
      isActive: true,
    },
  });
}
```

- [ ] **Step 5: Run the targeted gateway tests and schema generation**

Run:
- `pnpm --dir gateway/packages/api exec prisma generate`
- `pnpm --dir gateway/packages/api exec vitest run src/lib/business-conversation.test.ts`

Expected: PASS.

- [ ] **Step 6: Commit the schema and service foundation**

Commit: `feat(gateway): add exact business conversation routes`

---

## Task 2: Teach gateway inbound and outbound flows the new protocols

**Files:**
- Modify: `gateway/packages/api/src/lib/ai-backend.ts`
- Modify: `gateway/packages/api/src/lib/route-message.ts`
- Modify: `gateway/packages/api/src/lib/route-message.test.ts`
- Modify: `gateway/packages/api/src/routes/outbound.ts`
- Modify: `gateway/packages/api/src/routes/outbound.test.ts`
- Modify: `gateway/packages/api/src/lib/outbound-delivery.ts`
- Create: `gateway/packages/api/src/routes/coke-delivery-routes.ts`
- Create: `gateway/packages/api/src/routes/coke-delivery-routes.test.ts`
- Modify: `gateway/packages/api/src/index.ts`

- [ ] **Step 1: Write failing tests for first-turn establishment and exact outbound resolution**

```ts
it('stores the Coke-minted business conversation key after the first inbound turn', async () => {
  db.aiBackend.findMany.mockResolvedValue([cokeBridgeBackend]);
  mockGenerateReply.mockResolvedValue({
    text: 'hello back',
    businessConversationKey: 'bc_1',
    outputId: 'out_1',
    causalInboundEventId: 'in_evt_1',
  });

  await routeInboundMessage({
    channelId: 'ch_1',
    externalId: 'wxid_peer_1',
    text: 'hello',
    meta: { platform: 'wechat' },
  });

  expect(db.conversation.update).toHaveBeenCalledWith(
    expect.objectContaining({
      data: expect.objectContaining({ businessConversationKey: 'bc_1' }),
    }),
  );
});

it('rejects proactive outbound delivery when there is no exact route', async () => {
  const res = await app.request('/api/outbound', {
    method: 'POST',
    headers: {
      Authorization: 'Bearer test-outbound-key',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      output_id: 'out_1',
      account_id: 'acc_1',
      business_conversation_key: 'bc_missing',
      message_type: 'text',
      text: 'ping',
      delivery_mode: 'push',
      expect_output_timestamp: '2026-04-08T12:00:00.000Z',
      idempotency_key: 'idem_1',
      trace_id: 'trace_1',
    }),
  });

  expect(res.status).toBe(409);
  expect(await res.json()).toMatchObject({
    ok: false,
    error: 'missing_delivery_route',
  });
});
```

- [ ] **Step 2: Run the gateway protocol tests and confirm they fail**

Run:
- `pnpm --dir gateway/packages/api exec vitest run src/lib/route-message.test.ts`
- `pnpm --dir gateway/packages/api exec vitest run src/routes/outbound.test.ts`

Expected: FAIL because gateway still expects bridge replies to be plain strings and outbound still requires `tenant_id/channel_id/external_end_user_id` instead of normalized business outputs.

- [ ] **Step 3: Extend the backend reply contract**

```ts
export interface BackendReply {
  text: string;
  businessConversationKey?: string;
  outputId?: string;
  causalInboundEventId?: string;
}

function parseJsonAuto(data: Record<string, unknown>): BackendReply {
  if (typeof data.ok === 'boolean' && data.ok === false) {
    throw new Error(`Backend error: ${data.error ?? 'unknown'}`);
  }
  return {
    text: String(data.reply ?? data.content ?? data.message ?? data.text ?? '').trim(),
    businessConversationKey:
      typeof data.business_conversation_key === 'string'
        ? data.business_conversation_key
        : undefined,
    outputId: typeof data.output_id === 'string' ? data.output_id : undefined,
    causalInboundEventId:
      typeof data.causal_inbound_event_id === 'string'
        ? data.causal_inbound_event_id
        : undefined,
  };
}
```

- [ ] **Step 4: Implement the route-message protocol flow**

```ts
const inboundEventId = generateId('in_evt');
const backendReply = await generateReply({
  backend: selectedBackend,
  history,
  sender: displayName,
  platform,
  metadata: {
    tenantId,
    channelId,
    endUserId: endUser.id,
    conversationId: conversation.id,
    externalId,
    cokeAccountId: resolvedCokeAccountId ?? undefined,
    gatewayConversationId: conversation.id,
    businessConversationKey: conversation.businessConversationKey ?? undefined,
    inboundEventId,
  },
});

if (resolvedCokeAccountId && backendReply.businessConversationKey) {
  await bindBusinessConversation({
    tenantId,
    gatewayConversationId: conversation.id,
    cokeAccountId: resolvedCokeAccountId,
    businessConversationKey: backendReply.businessConversationKey,
    channelId,
    endUserId: endUser.id,
    externalEndUserId: externalId,
  });
}

return reply(backendReply.text, backend.id, backend.name);
```

- [ ] **Step 5: Convert `/api/outbound` to normalized business output resolution**

```ts
const bodySchema = z.object({
  output_id: z.string().min(1),
  account_id: z.string().min(1),
  business_conversation_key: z.string().min(1),
  message_type: z.enum(['text']),
  text: z.string().min(1),
  delivery_mode: z.enum(['push', 'request_response']),
  expect_output_timestamp: z.string().min(1),
  idempotency_key: z.string().min(1),
  trace_id: z.string().min(1),
  causal_inbound_event_id: z.string().min(1).optional(),
});

const route = await resolveExactDeliveryRoute({
  cokeAccountId: body.account_id,
  businessConversationKey: body.business_conversation_key,
});

await deliverOutboundMessage(
  { id: route.channelId, type: channel.type },
  route.externalEndUserId,
  body.text,
);
```

- [ ] **Step 6: Add a cutover/backfill-only internal route surface**

```ts
cokeDeliveryRoutesRouter.post('/', async (c) => {
  const parsed = bodySchema.safeParse(await c.req.json());
  if (!parsed.success) return c.json({ ok: false, error: 'invalid_body' }, 400);

  const route = await bindBusinessConversation(parsed.data);
  return c.json({ ok: true, data: route });
});
```

- [ ] **Step 7: Run the gateway suite for the protocol layer**

Run:
- `pnpm --dir gateway/packages/api exec vitest run src/lib/route-message.test.ts`
- `pnpm --dir gateway/packages/api exec vitest run src/routes/outbound.test.ts`
- `pnpm --dir gateway/packages/api exec vitest run src/routes/coke-delivery-routes.test.ts`

Expected: PASS.

- [ ] **Step 8: Commit the gateway protocol cutover**

Commit: `feat(gateway): route business outputs by exact delivery route`

---

## Task 3: Replace bridge inbound glue with explicit business protocols

**Files:**
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `connector/clawscale_bridge/message_gateway.py`
- Modify: `connector/clawscale_bridge/reply_waiter.py`
- Create: `tests/unit/connector/clawscale_bridge/test_message_gateway.py`
- Create: `tests/unit/connector/clawscale_bridge/test_reply_waiter.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`

- [ ] **Step 1: Write failing bridge tests for first-turn establishment and sync correlation**

```py
def test_bridge_inbound_returns_coke_minted_business_conversation_key(client, monkeypatch):
    monkeypatch.setattr(
        bridge_app,
        'message_gateway',
        StubGateway(enqueue_result='in_evt_1'),
    )
    monkeypatch.setattr(
        bridge_app,
        'reply_waiter',
        StubReplyWaiter(
            reply={
                'reply': 'hello back',
                'business_conversation_key': 'bc_1',
                'output_id': 'out_1',
                'causal_inbound_event_id': 'in_evt_1',
            }
        ),
    )

    res = client.post('/bridge/inbound', json={
        'account_id': 'acc_1',
        'gateway_conversation_id': 'conv_gateway_1',
        'message_type': 'text',
        'text': 'hello',
        'source_message_id': 'src_1',
        'inbound_event_id': 'in_evt_1',
        'trace_id': 'trace_1',
    })

    assert res.status_code == 200
    assert res.get_json()['business_conversation_key'] == 'bc_1'


def test_reply_waiter_matches_by_causal_inbound_event_id(mongo):
    mongo.outputmessages.insert_one({
        'status': 'pending',
        'message': 'pong',
        'metadata': {
            'source': 'clawscale',
            'delivery_mode': 'request_response',
            'causal_inbound_event_id': 'in_evt_1',
            'output_id': 'out_1',
        },
    })

    waiter = ReplyWaiter(mongo=mongo, poll_interval_seconds=0.01, timeout_seconds=1)
    result = waiter.wait_for_reply('in_evt_1', sync_reply_token=None)

    assert result['reply'] == 'pong'
    assert result['output_id'] == 'out_1'
```

- [ ] **Step 2: Run the bridge tests and confirm they fail**

Run:
- `pytest -q tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_reply_waiter.py`

Expected: FAIL because bridge still expects legacy metadata, bridge request IDs, and platform-specific reply matching.

- [ ] **Step 3: Normalize bridge inbound message creation**

```py
bridge_request = {
    'source': 'clawscale',
    'account_id': account_id,
    'message_type': inbound_payload['message_type'],
    'text': inbound_payload['text'],
    'attachments': inbound_payload.get('attachments') or [],
    'metadata': {
        'source': 'clawscale',
        'inbound_event_id': inbound_payload['inbound_event_id'],
        'source_message_id': inbound_payload['source_message_id'],
        'business_conversation_key': inbound_payload.get('business_conversation_key'),
        'gateway_conversation_id': inbound_payload.get('gateway_conversation_id'),
        'sync_reply_token': inbound_payload.get('sync_reply_token'),
        'trace_id': inbound_payload['trace_id'],
    },
}
```

- [ ] **Step 4: Change reply waiting to correlation identifiers, not platform glue**

```py
reply = self.reply_waiter.wait_for_reply(
    inbound_event_id=inbound_payload['inbound_event_id'],
    sync_reply_token=inbound_payload.get('sync_reply_token'),
)
return {
    'ok': True,
    'reply': reply['reply'],
    'business_conversation_key': reply.get('business_conversation_key'),
    'output_id': reply.get('output_id'),
    'causal_inbound_event_id': reply.get('causal_inbound_event_id'),
}
```

- [ ] **Step 5: Run the bridge protocol tests**

Run:
- `pytest -q tests/unit/connector/clawscale_bridge/test_message_gateway.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_reply_waiter.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_bridge_app.py`

Expected: PASS.

- [ ] **Step 6: Commit the bridge protocol translation rewrite**

Commit: `refactor(bridge): normalize inbound conversation protocol`

---

## Task 4: Remove platform and route truth from Coke outputs and dispatch through gateway exact routes

**Files:**
- Modify: `agent/util/message_util.py`
- Modify: `tests/unit/agent/test_message_util_clawscale_routing.py`
- Modify: `connector/clawscale_bridge/output_dispatcher.py`
- Create: `connector/clawscale_bridge/gateway_outbound_client.py`
- Create: `tests/unit/connector/clawscale_bridge/test_gateway_outbound_client.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`

- [ ] **Step 1: Write failing tests that outlaw platform-native route writes from Coke**

```py
def test_proactive_clawscale_output_contains_business_fields_only(user_msg_factory):
    doc = build_clawscale_output_message(
        account_id='acc_1',
        business_conversation_key='bc_1',
        text='remember this',
        delivery_mode='push',
        causal_inbound_event_id=None,
    )

    assert doc['account_id'] == 'acc_1'
    assert doc['metadata']['business_conversation_key'] == 'bc_1'
    assert 'platform' not in doc
    assert 'tenant_id' not in doc['metadata']
    assert 'channel_id' not in doc['metadata']
    assert 'external_end_user_id' not in doc['metadata']


def test_output_dispatcher_posts_normalized_output_to_gateway(mock_gateway_client, mongo):
    mongo.outputmessages.insert_one({
        'status': 'pending',
        'message': 'time to eat',
        'account_id': 'acc_1',
        'metadata': {
            'source': 'clawscale',
            'business_conversation_key': 'bc_1',
            'delivery_mode': 'push',
            'idempotency_key': 'idem_1',
            'trace_id': 'trace_1',
            'output_id': 'out_1',
        },
    })

    dispatcher = ClawScaleOutputDispatcher(mongo=mongo, gateway_client=mock_gateway_client)
    dispatcher.dispatch_once()

    mock_gateway_client.post_output.assert_called_once_with(
        output_id='out_1',
        account_id='acc_1',
        business_conversation_key='bc_1',
        text='time to eat',
        message_type='text',
        delivery_mode='push',
        idempotency_key='idem_1',
        trace_id='trace_1',
        causal_inbound_event_id=None,
    )
```

- [ ] **Step 2: Run the failing Coke/bridge output tests**

Run:
- `pytest -q tests/unit/agent/test_message_util_clawscale_routing.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`

Expected: FAIL because `message_util.py` still writes `route_via`, `platform`, and bridge-side routing metadata, and dispatcher still expects Mongo route registries.

- [ ] **Step 3: Emit normalized outputs from Coke**

```py
metadata = {
    'source': 'clawscale',
    'output_id': output_id,
    'business_conversation_key': business_conversation_key,
    'delivery_mode': delivery_mode,
    'idempotency_key': idempotency_key,
    'trace_id': trace_id,
}
if causal_inbound_event_id:
    metadata['causal_inbound_event_id'] = causal_inbound_event_id
```

- [ ] **Step 4: Replace dispatcher route lookup with gateway outbound posting**

```py
class GatewayOutboundClient:
    def post_output(self, *, output_id, account_id, business_conversation_key, text, message_type,
                    delivery_mode, idempotency_key, trace_id, causal_inbound_event_id=None):
        payload = {
            'output_id': output_id,
            'account_id': account_id,
            'business_conversation_key': business_conversation_key,
            'message_type': message_type,
            'text': text,
            'delivery_mode': delivery_mode,
            'expect_output_timestamp': datetime.utcnow().isoformat() + 'Z',
            'idempotency_key': idempotency_key,
            'trace_id': trace_id,
        }
        if causal_inbound_event_id:
            payload['causal_inbound_event_id'] = causal_inbound_event_id
        return self._session.post(self._api_url, json=payload, headers=self._headers, timeout=10)
```

- [ ] **Step 5: Run the normalized-output suite**

Run:
- `pytest -q tests/unit/agent/test_message_util_clawscale_routing.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_gateway_outbound_client.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`

Expected: PASS.

- [ ] **Step 6: Commit the output normalization cutover**

Commit: `refactor(coke): emit platform-free clawscale outputs`

---

## Task 5: Gate provisioning, codify hard cutover, and backfill exact routes

**Files:**
- Modify: `gateway/packages/api/src/lib/clawscale-user.ts`
- Modify: `gateway/packages/api/src/routes/coke-user-provision.ts`
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- Create: `connector/clawscale_bridge/backfill_delivery_routes.py`
- Create: `tests/unit/connector/clawscale_bridge/test_backfill_delivery_routes.py`
- Modify: `scripts/run_wechat_personal_e2e.py`
- Modify: `tests/unit/test_run_wechat_personal_e2e.py`

- [ ] **Step 1: Write failing tests for provision gating and cutover backfill**

```py
def test_register_rolls_back_when_clawscale_provision_fails(client, failing_provision_client, user_dao):
    res = client.post('/user/register', json={
        'email': 'user@example.com',
        'password': 'secret123',
        'display_name': 'User',
    })

    assert res.status_code == 502
    assert user_dao.find_one({'email': 'user@example.com'}) is None


def test_backfill_delivery_routes_rejects_unmappable_conversation(monkeypatch):
    service = BackfillDeliveryRoutesService(...)
    with pytest.raises(RouteRepairRequired):
        service.backfill_account('acc_missing_route')
```

- [ ] **Step 2: Run the failing provision/backfill tests**

Run:
- `pytest -q tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_backfill_delivery_routes.py`

Expected: FAIL because registration/login are not yet hard-gated on durable provision readiness and no exact-route backfill tool exists.

- [ ] **Step 3: Make registration success depend on durable provision readiness**

```py
account = user_auth_service.register_user(...)
try:
    provision = gateway_user_provision_client.ensure_user(
        coke_account_id=str(account['_id']),
        display_name=account.get('name') or display_name,
    )
except GatewayUserProvisionClientError:
    user_auth_service.delete_user(account['_id'])
    raise
```

- [ ] **Step 4: Implement the hard-cutover backfill tool**

```py
for conversation in active_business_conversations(account_id):
    peer = resolve_exact_current_peer(conversation)
    if not peer:
        raise RouteRepairRequired(account_id=account_id, conversation_id=str(conversation['_id']))

    gateway_delivery_route_client.upsert_route(
        tenant_id=peer.tenant_id,
        gateway_conversation_id=peer.gateway_conversation_id,
        coke_account_id=account_id,
        business_conversation_key=conversation['business_conversation_key'],
        channel_id=peer.channel_id,
        end_user_id=peer.end_user_id,
        external_end_user_id=peer.external_end_user_id,
    )
```

- [ ] **Step 5: Extend the fake-WeChat E2E harness to assert the cutover invariants**

```py
result = run_flow(...)
assert result['first_turn']['business_conversation_key'].startswith('bc_')
assert result['steady_state']['reply_text']
assert result['proactive']['delivered_count'] >= 1
assert result['mongo_assertions']['output_platform_fields_present'] is False
```

- [ ] **Step 6: Run provision, backfill, and E2E verification**

Run:
- `pytest -q tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_backfill_delivery_routes.py`
- `pytest -q tests/unit/test_run_wechat_personal_e2e.py`
- `.venv/bin/python scripts/run_wechat_personal_e2e.py`

Expected: PASS.

- [ ] **Step 7: Commit the provisioning gate and cutover tooling**

Commit: `feat(cutover): gate provision and backfill exact routes`

---

## Task 6: Delete the legacy bridge-owned identity model and lock in the hard cutover

**Files:**
- Delete: `connector/clawscale_bridge/identity_service.py`
- Delete: `connector/clawscale_bridge/wechat_bind_session_service.py`
- Delete: `dao/clawscale_push_route_dao.py`
- Delete: `dao/external_identity_dao.py`
- Delete: `dao/wechat_bind_session_dao.py`
- Delete: `dao/binding_ticket_dao.py`
- Delete: `tests/unit/connector/clawscale_bridge/test_identity_service.py`
- Delete: `tests/unit/dao/test_clawscale_push_route_dao.py`
- Delete: `tests/unit/dao/test_external_identity_dao.py`
- Delete: `tests/unit/dao/test_wechat_bind_session_dao.py`
- Delete: `tests/unit/dao/test_binding_ticket_dao.py`
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`

- [ ] **Step 1: Write the failing app-level tests that prove the old bind/runtime path is gone**

```py
def test_bridge_app_has_no_bind_required_flow(client):
    res = client.post('/bridge/inbound', json={
        'account_id': 'acc_1',
        'gateway_conversation_id': 'conv_gateway_1',
        'message_type': 'text',
        'text': 'hi',
        'source_message_id': 'src_1',
        'inbound_event_id': 'in_evt_1',
        'trace_id': 'trace_1',
    })

    assert res.status_code == 200
    assert 'bind_url' not in res.get_json()
    assert res.get_json()['ok'] is True
```

- [ ] **Step 2: Run the app-level regression tests and confirm they fail**

Run: `pytest -q tests/unit/connector/clawscale_bridge/test_bridge_app.py`

Expected: FAIL because app wiring still imports and constructs the legacy identity/bind services.

- [ ] **Step 3: Remove the old ownership model from the live bridge**

```py
# app.py
message_gateway = CokeMessageGateway(...)
reply_waiter = ReplyWaiter(...)
outbound_dispatcher = ClawScaleOutputDispatcher(...)

# no ExternalIdentityDAO
# no ClawscalePushRouteDAO
# no WechatBindSessionService
# no bind-ticket runtime
```

- [ ] **Step 4: Delete the dead bridge-owned identity modules and their tests**

Delete the files listed in this task once `app.py` and the test suite no longer import them.

- [ ] **Step 5: Run the focused regression suite after deletion**

Run:
- `pytest -q tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_message_gateway.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_reply_waiter.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`

Expected: PASS.

- [ ] **Step 6: Commit the hard-cutover cleanup**

Commit: `refactor(bridge): delete legacy identity and bind runtime`

---

## Task 7: Run final system verification for the new ownership model

**Files:**
- No new product code; use the test and runtime surfaces from Tasks 1-6.

- [ ] **Step 1: Run the gateway targeted suite**

Run:
- `pnpm --dir gateway/packages/api exec vitest run src/lib/business-conversation.test.ts`
- `pnpm --dir gateway/packages/api exec vitest run src/lib/route-message.test.ts`
- `pnpm --dir gateway/packages/api exec vitest run src/routes/outbound.test.ts`
- `pnpm --dir gateway/packages/api exec vitest run src/routes/coke-delivery-routes.test.ts`

Expected: PASS.

- [ ] **Step 2: Run the Python targeted suite**

Run:
- `pytest -q tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_message_gateway.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_reply_waiter.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_gateway_outbound_client.py`
- `pytest -q tests/unit/agent/test_message_util_clawscale_routing.py`
- `pytest -q tests/unit/connector/clawscale_bridge/test_backfill_delivery_routes.py`
- `pytest -q tests/unit/test_run_wechat_personal_e2e.py`

Expected: PASS.

- [ ] **Step 3: Run the automated fake-WeChat E2E**

Run: `.venv/bin/python scripts/run_wechat_personal_e2e.py`

Expected: PASS with evidence for:
- first-turn `business_conversation_key` establishment
- steady-state synchronous replies
- proactive reminder delivery through exact `DeliveryRoute`
- no required platform identity fields in Coke runtime documents

- [ ] **Step 4: Commit the verification checkpoint**

Commit: `test(wechat): verify business-only channel-only cutover`

