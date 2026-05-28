# Agent-Generated Chat Outbound Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route chat-visible product notifications through the normal Interaction Agent LLM path instead of Gateway-authored final prose.

**Architecture:** Gateway stores immutable notification facts in `product_notifications.payload`, resolves the recipient delivery route, and enqueues an async `message_type=product_notification` turn through `/bridge/inbound`. The bridge/worker runtime treats the turn as the normal user-interaction `AgentInput(input_type="user.turn")`, but writes the resulting `outputmessages` as push-deliverable records keyed by `notification_id`; Gateway `/api/outbound` reconciles notification delivery state after successful provider delivery.

**Tech Stack:** TypeScript/Hono/Prisma/Vitest in `gateway/packages/api`, Python runner/bridge code with pytest, Mongo `inputmessages`/`outputmessages`, Postgres `product_notifications`.

---

### Task 1: Gateway Notification Facts And Bridge Enqueue

**Files:**
- Modify: `gateway/packages/api/src/scheduling/notification-service.ts`
- Modify: `gateway/packages/api/src/scheduling/shared-reminder-service.ts`
- Modify: `gateway/packages/api/src/scheduling/user-link-service.ts`
- Test: `gateway/packages/api/src/scheduling/notification-service.test.ts`
- Test: `gateway/packages/api/src/scheduling/shared-reminder-service.test.ts`
- Test: `gateway/packages/api/src/scheduling/user-link-service.test.ts`

- [ ] **Step 1: Write failing Vitest coverage**

Add/update tests proving:

```ts
expect(createdNotification.payload).toEqual({
  facts: expect.objectContaining({
    kind: 'shared_reminder_created',
    resource_type: 'shared_reminder',
    shared_reminder_id: 'sr_1',
  }),
  facts_hash: expect.stringMatching(/^sha256:/),
});
expect(globalThis.fetch).toHaveBeenCalledWith(
  'http://127.0.0.1:8090/bridge/inbound',
  expect.objectContaining({
    method: 'POST',
    headers: expect.objectContaining({ authorization: 'Bearer bridge-secret' }),
    body: expect.stringContaining('"message_type":"product_notification"'),
  }),
);
expect(JSON.parse(String(fetchBody))).toMatchObject({
  customer_id: 'acct_a',
  business_conversation_key: 'bc_latest',
  message_type: 'product_notification',
  product_notification: {
    notification_id: 'pn_1',
    kind: 'shared_reminder_created',
    facts_hash: expect.stringMatching(/^sha256:/),
  },
});
expect(JSON.parse(String(fetchBody)).text).not.toContain('shared "');
```

Also update shared-reminder and direct-friendship service tests so callers pass facts, not final chat text.

- [ ] **Step 2: Run the failing gateway tests**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/notification-service.test.ts src/scheduling/shared-reminder-service.test.ts src/scheduling/user-link-service.test.ts
```

Expected: FAIL because notification service still stores `payload.text` and posts directly to `/api/outbound`.

- [ ] **Step 3: Implement structured facts enqueue**

In `notification-service.ts`:

```ts
import { createHash } from 'node:crypto';

type ProductNotificationFacts = Record<string, unknown> & {
  kind: string;
  resource_type: 'friendship' | 'shared_reminder';
};

function factsHash(facts: ProductNotificationFacts): string {
  return `sha256:${createHash('sha256').update(JSON.stringify(facts)).digest('hex')}`;
}
```

Replace `text`/`metadata` input fields with `facts`. Store `payload: { facts, facts_hash }`. Resolve the latest active delivery route with `tenantId`, `channelId`, `endUserId`, `externalEndUserId`, `businessConversationKey`, and channel type/scope when available. POST to `COKE_BRIDGE_INBOUND_URL` with `Authorization: Bearer ${COKE_BRIDGE_API_KEY}` and:

```ts
{
  customer_id: record.recipientAccountId,
  tenant_id: route.tenantId,
  channel_id: route.channelId,
  platform: route.channel?.type ?? 'business',
  external_id: route.externalEndUserId,
  end_user_id: route.endUserId,
  business_conversation_key: route.businessConversationKey,
  inbound_event_id: record.id,
  text: buildProductNotificationInstruction(record.kind, facts),
  message_type: 'product_notification',
  product_notification: {
    notification_id: record.id,
    notification_kind: record.kind,
    kind: record.kind,
    resource_type: facts.resource_type,
    facts,
    facts_hash,
  },
}
```

The instruction should tell the Interaction Agent to deliver the notification using trusted facts and preserve critical fields. It must not be user-visible final prose.

In shared-reminder and user-link services, build fact snapshots containing the IDs, actor/recipient names, local date/time, duration, status, and resource kind already present in the old metadata.

- [ ] **Step 4: Run gateway tests**

Run the same `pnpm --dir gateway/packages/api test -- ...` command. Expected: PASS.

### Task 2: Bridge And Worker Push Metadata

**Files:**
- Modify: `connector/clawscale_bridge/message_gateway.py`
- Modify: `agent/util/message_util.py`
- Modify: `agent/runner/output_delivery.py`
- Test: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- Test: `tests/unit/agent/test_agent_handler.py`
- Test: add focused tests in `tests/unit/agent/test_message_util_clawscale_routing.py` or `tests/unit/agent/test_agent_handler.py`

- [ ] **Step 1: Write failing pytest coverage**

Add tests proving product-notification inbound is stored as push protocol:

```python
assert inbound["message_type"] == "product_notification"
doc = message_gateway.build_input_message(...)
assert doc["metadata"]["business_protocol"]["delivery_mode"] == "push"
assert doc["metadata"]["business_protocol"]["output_id"] == "pn_1"
assert doc["metadata"]["product_notification"]["notification_id"] == "pn_1"
```

Add a message-util test proving an Interaction Agent text output for that input becomes dispatcher-claimable:

```python
output = send_message_via_context(context, "LLM phrasing", message_type="text")
assert output["customer_id"] == "acct_1"
assert output["metadata"]["delivery_mode"] == "push"
assert output["metadata"]["output_id"] == "pn_1"
assert output["metadata"]["notification_id"] == "pn_1"
```

Add/update output-delivery coverage proving `VisibleMessage.metadata` is passed to `send_message_via_context` for text outputs.

- [ ] **Step 2: Run the failing Python tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/agent/test_agent_handler.py tests/unit/agent/test_message_util_clawscale_routing.py -v
```

Expected: FAIL because product-notification input is still request/response and text output metadata is not flattened into push delivery fields.

- [ ] **Step 3: Implement push metadata normalization**

In `message_gateway.py`, when `message_type == "product_notification"` and `product_notification.notification_id` exists, set `business_protocol.delivery_mode = "push"` and add `output_id`, `idempotency_key`, `trace_id`, `business_conversation_key`, and `causal_inbound_event_id` from the notification id / inbound route.

In `message_util.py`, add a helper that detects copied ClawScale push metadata, extracts `customer.id`, flattens `business_protocol` into the output metadata fields required by `ClawScaleOutputDispatcher`, and preserves `product_notification`, `notification_id`, `notification_kind`, `resource_type`, and `facts_hash`.

In `output_delivery.py`, pass `multimodal_response["metadata"]` through to `send_message_via_context` for text/photo/voice outputs, merging media-specific metadata for media outputs.

- [ ] **Step 4: Run Python tests**

Run the same `.venv/bin/python -m pytest ...` command. Expected: PASS.

### Task 3: Outbound Delivery Reconciles Product Notification Status

**Files:**
- Modify: `connector/clawscale_bridge/gateway_outbound_client.py`
- Modify: `connector/clawscale_bridge/output_dispatcher.py`
- Modify: `gateway/packages/api/src/routes/outbound.ts`
- Test: `tests/unit/connector/clawscale_bridge/test_gateway_outbound_client.py`
- Test: `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`
- Test: `gateway/packages/api/src/routes/outbound.test.ts`

- [ ] **Step 1: Write failing delivery reconciliation tests**

Add tests proving dispatcher forwards `product_notification_id` from Mongo metadata:

```python
gateway_client.post_output.assert_called_once_with(
  ...,
  product_notification_id="pn_1",
)
```

Add an outbound route test proving successful provider delivery updates the notification:

```ts
expect(db.productNotification.updateMany).toHaveBeenCalledWith({
  where: { id: 'pn_1', status: { in: ['pending_delivery', 'failed'] } },
  data: {
    status: 'delivered',
    businessConversationKey: 'bc_1',
    deliveredAt: expect.any(Date),
    lastError: null,
  },
});
```

Also cover duplicate-success (`duplicate_request`) reconciliation.

- [ ] **Step 2: Run failing delivery tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_gateway_outbound_client.py tests/unit/connector/clawscale_bridge/test_output_dispatcher.py -v
pnpm --dir gateway/packages/api test -- src/routes/outbound.test.ts
```

Expected: FAIL because `product_notification_id` is not part of the outbound protocol and `/api/outbound` does not reconcile `product_notifications`.

- [ ] **Step 3: Implement reconciliation**

Add optional `product_notification_id` to `GatewayOutboundClient.post_output`, `ClawScaleOutputDispatcher._build_gateway_args`, and the Gateway outbound body schema/comparable payload. In `/api/outbound`, after provider delivery succeeds or a duplicate-success response is returned for a matching idempotency key, call:

```ts
await db.productNotification.updateMany({
  where: {
    id: body.product_notification_id,
    status: { in: ['pending_delivery', 'failed'] },
  },
  data: {
    status: 'delivered',
    businessConversationKey: body.business_conversation_key,
    deliveredAt: new Date(),
    lastError: null,
  },
});
```

The update must be skipped when `product_notification_id` is absent.

- [ ] **Step 4: Run delivery tests**

Run the same Python and gateway route tests. Expected: PASS.

### Task 4: Docs And Routed Verification

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify if needed: `docs/product-specs/FEATURE_TREE.md`
- Verify: `docs/superpowers/specs/2026-05-28-agent-generated-chat-outbound-design.md`

- [ ] **Step 1: Update architecture docs**

Replace the current statement that Gateway sends product notifications directly to `/api/outbound` as final push text with the implemented flow: Gateway stores facts, enqueues `/bridge/inbound` product-notification turns, Interaction Agent owns final prose, bridge dispatcher posts outputs to `/api/outbound`, and Gateway reconciles delivery state.

- [ ] **Step 2: Run diff-aware routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Use the suggested commands unless they are strictly superseded by the focused commands above.

- [ ] **Step 3: Run final focused verification**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/notification-service.test.ts src/scheduling/shared-reminder-service.test.ts src/scheduling/user-link-service.test.ts src/routes/outbound.test.ts
.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/connector/clawscale_bridge/test_gateway_outbound_client.py tests/unit/connector/clawscale_bridge/test_output_dispatcher.py tests/unit/agent/test_agent_handler.py tests/unit/agent/test_message_util_clawscale_routing.py -v
git diff --check
```

- [ ] **Step 4: Commit**

After verification, commit the completed change:

```bash
git add docs/superpowers/specs/2026-05-28-agent-generated-chat-outbound-design.md docs/superpowers/plans/2026-05-28-agent-generated-chat-outbound.md docs/ARCHITECTURE.md gateway/packages/api/src/scheduling/notification-service.ts gateway/packages/api/src/scheduling/notification-service.test.ts gateway/packages/api/src/scheduling/shared-reminder-service.ts gateway/packages/api/src/scheduling/shared-reminder-service.test.ts gateway/packages/api/src/scheduling/user-link-service.ts gateway/packages/api/src/scheduling/user-link-service.test.ts gateway/packages/api/src/routes/outbound.ts gateway/packages/api/src/routes/outbound.test.ts connector/clawscale_bridge/message_gateway.py connector/clawscale_bridge/gateway_outbound_client.py connector/clawscale_bridge/output_dispatcher.py tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/connector/clawscale_bridge/test_gateway_outbound_client.py tests/unit/connector/clawscale_bridge/test_output_dispatcher.py agent/util/message_util.py agent/runner/output_delivery.py tests/unit/agent/test_agent_handler.py tests/unit/agent/test_message_util_clawscale_routing.py
git commit -m "feat: route product notifications through interaction agent"
```
