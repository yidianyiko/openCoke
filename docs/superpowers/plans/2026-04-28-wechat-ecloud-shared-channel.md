# WeChat Ecloud Shared Channel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `wechat_ecloud` shared-channel integration that accepts Eyun/Ecloud private WeChat text/reference callbacks and sends outbound text through Eyun without QR-code login or Moments publishing.

**Architecture:** Implement this inside the `gateway` submodule using the existing `whatsapp_evolution` shared-channel pattern. Gateway owns channel config, webhook auth, inbound normalization, shared-customer provisioning, and outbound delivery; Coke workers continue to use ClawScale bridge and `/api/outbound`.

**Tech Stack:** TypeScript, Hono, Prisma/PostgreSQL, Vitest, Next.js admin UI, pnpm workspace, gateway git submodule.

---

## Pre-Flight Context

Implementation work happens in the isolated worktree:

```bash
cd /data/projects/coke/.worktrees/wechat-ecloud-shared-channel
```

The runtime code lives in the `gateway` submodule. Commit gateway changes inside:

```bash
cd /data/projects/coke/.worktrees/wechat-ecloud-shared-channel/gateway
```

Then update the superproject gitlink and plan/task docs from:

```bash
cd /data/projects/coke/.worktrees/wechat-ecloud-shared-channel
```

Before running API tests in a fresh worktree, run:

```bash
cd gateway
pnpm install
pnpm --filter @clawscale/shared build
pnpm --filter @clawscale/api db:generate
```

Baseline evidence from this worktree:

```bash
zsh scripts/check
pnpm --filter @clawscale/api exec vitest run src/gateway/message-router.test.ts src/lib/outbound-delivery.test.ts src/routes/admin-shared-channels.test.ts
pnpm --filter @clawscale/api build
```

All three commands passed before implementation started.

## File Structure

Create or modify these gateway files:

- `gateway/packages/api/prisma/schema.prisma`: add `wechat_ecloud` enum and an inbound receipt table for webhook deduplication.
- `gateway/packages/api/prisma/migrations/20260428010000_wechat_ecloud_shared_channel/migration.sql`: add enum value and receipt table.
- `gateway/packages/shared/src/types/channel.ts`: add `wechat_ecloud` to shared channel type declarations.
- `gateway/packages/api/src/lib/wechat-ecloud-config.ts`: parse stored/public Ecloud config and secret-safe serialization.
- `gateway/packages/api/src/lib/wechat-ecloud-config.test.ts`: config parser tests.
- `gateway/packages/api/src/lib/wechat-ecloud-api.ts`: focused Eyun API client with `postText` success handling.
- `gateway/packages/api/src/lib/wechat-ecloud-api.test.ts`: HTTP/body success and failure tests.
- `gateway/packages/api/src/lib/wechat-ecloud-webhook.ts`: callback normalization, token comparison helper, XML quote parsing, private/self/group filters, and receipt key extraction.
- `gateway/packages/api/src/lib/wechat-ecloud-webhook.test.ts`: webhook normalization and XML hardening tests.
- `gateway/packages/api/src/lib/outbound-delivery.ts`: add `wechat_ecloud` outbound text delivery.
- `gateway/packages/api/src/lib/outbound-delivery.test.ts`: outbound tests.
- `gateway/packages/api/src/lib/route-message.ts`: include `wechat_ecloud` in shared-channel access/provisioning behavior.
- `gateway/packages/api/src/lib/route-message.test.ts`: shared access predicate regression test.
- `gateway/packages/api/src/gateway/message-router.ts`: add `POST /gateway/ecloud/wechat/:channelId/:token`.
- `gateway/packages/api/src/gateway/message-router.test.ts`: inbound route tests.
- `gateway/packages/api/src/routes/admin-shared-channels.ts`: create/update/serialize/connect/disconnect/delete support for `wechat_ecloud`.
- `gateway/packages/api/src/routes/admin-shared-channels.test.ts`: admin API tests.
- `gateway/packages/api/src/routes/admin-channels.ts` and `gateway/packages/api/src/routes/channels.ts` if they enumerate channel kinds.
- `gateway/packages/api/src/routes/admin-channels.test.ts` and `gateway/packages/api/src/routes/channels.test.ts` if needed for enum filters or creation validation.
- `gateway/packages/web/app/(admin)/admin/shared-channels/page.tsx`: create form fields for Ecloud.
- `gateway/packages/web/app/(admin)/admin/shared-channels/detail/page.tsx`: detail/edit/connect/disconnect display for Ecloud.
- `gateway/packages/web/app/(admin)/admin/shared-channels/page.test.tsx`: create form tests.
- `gateway/packages/web/app/(admin)/admin/shared-channels/detail/page.test.tsx`: detail tests.
- `gateway/packages/web/lib/admin-api.ts`: ensure public detail type can represent Ecloud config/callback URL fields.

## Task 1: Schema, Config, And Eyun Client

**Files:**
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Create: `gateway/packages/api/prisma/migrations/20260428010000_wechat_ecloud_shared_channel/migration.sql`
- Modify: `gateway/packages/shared/src/types/channel.ts`
- Create: `gateway/packages/api/src/lib/wechat-ecloud-config.ts`
- Create: `gateway/packages/api/src/lib/wechat-ecloud-config.test.ts`
- Create: `gateway/packages/api/src/lib/wechat-ecloud-api.ts`
- Create: `gateway/packages/api/src/lib/wechat-ecloud-api.test.ts`

- [x] **Step 1: Write failing config and Eyun client tests**

Add `gateway/packages/api/src/lib/wechat-ecloud-config.test.ts` with tests that assert:

```ts
import { describe, expect, it } from 'vitest';
import {
  buildPublicWechatEcloudConfig,
  ensureStoredWechatEcloudConfig,
  hasWechatEcloudWebhookToken,
  parseStoredWechatEcloudConfig,
  parseWechatEcloudConfigInput,
} from './wechat-ecloud-config.js';

describe('wechat ecloud config helpers', () => {
  it('parses input config with default baseUrl and generated webhook token', () => {
    const stored = ensureStoredWechatEcloudConfig(
      parseWechatEcloudConfigInput({
        appId: 'app_1',
        token: 'token_1',
      }),
      () => 'generated_token',
    );

    expect(stored).toEqual({
      appId: 'app_1',
      token: 'token_1',
      baseUrl: 'https://api.geweapi.com',
      webhookToken: 'generated_token',
    });
  });

  it('scrubs token and webhookToken from public config', () => {
    expect(
      buildPublicWechatEcloudConfig({
        appId: 'app_1',
        token: 'token_1',
        baseUrl: 'https://api.example.test',
        webhookToken: 'secret',
      }),
    ).toEqual({
      appId: 'app_1',
      baseUrl: 'https://api.example.test',
      callbackPath: '/gateway/ecloud/wechat/:channelId/:token',
    });
  });

  it('requires stored webhook token for delivery routes', () => {
    expect(() =>
      parseStoredWechatEcloudConfig({
        appId: 'app_1',
        token: 'token_1',
      }),
    ).toThrow('invalid_wechat_ecloud_config:webhookToken');
  });

  it('detects whether a stored webhook token exists', () => {
    expect(hasWechatEcloudWebhookToken({ appId: 'app_1', token: 'token_1' })).toBe(false);
    expect(hasWechatEcloudWebhookToken({ appId: 'app_1', token: 'token_1', webhookToken: 'x' })).toBe(true);
  });
});
```

Add `gateway/packages/api/src/lib/wechat-ecloud-api.test.ts` with tests that assert:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WechatEcloudApiClient } from './wechat-ecloud-api.js';

describe('WechatEcloudApiClient', () => {
  const fetchImpl = vi.fn();

  beforeEach(() => {
    fetchImpl.mockReset();
  });

  it('posts text with X-GEWE-TOKEN and treats ret=200 as success', async () => {
    fetchImpl.mockResolvedValue(
      new Response(JSON.stringify({ ret: 200, msg: 'success', data: { msgId: 'm1' } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );

    await new WechatEcloudApiClient('https://api.example.test/', 'token_1', fetchImpl as never).sendText(
      'app_1',
      'wxid_1',
      'hello',
    );

    expect(fetchImpl).toHaveBeenCalledWith(
      'https://api.example.test/gewe/v2/api/message/postText',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'X-GEWE-TOKEN': 'token_1',
          'content-type': 'application/json',
        }),
        body: JSON.stringify({ appId: 'app_1', toWxid: 'wxid_1', content: 'hello' }),
      }),
    );
  });

  it('throws on application-level failure even with HTTP 200', async () => {
    fetchImpl.mockResolvedValue(
      new Response(JSON.stringify({ ret: 500, msg: 'bad token' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );

    await expect(
      new WechatEcloudApiClient('https://api.example.test', 'token_1', fetchImpl as never).sendText(
        'app_1',
        'wxid_1',
        'hello',
      ),
    ).rejects.toThrow('Ecloud API request failed');
  });
});
```

- [x] **Step 2: Run tests to verify they fail**

```bash
cd gateway
pnpm --filter @clawscale/api exec vitest run src/lib/wechat-ecloud-config.test.ts src/lib/wechat-ecloud-api.test.ts
```

Expected: fail because the new modules do not exist.

- [x] **Step 3: Implement schema and helpers**

Update Prisma enum:

```prisma
enum ChannelType {
  whatsapp
  telegram
  slack
  discord
  instagram
  facebook
  line
  signal
  teams
  matrix
  web
  wechat_work
  whatsapp_business
  whatsapp_evolution
  wechat_personal
  wechat_ecloud
}
```

Add model:

```prisma
model InboundWebhookReceipt {
  id             String   @id @default(cuid())
  channelId      String   @map("channel_id")
  provider       String
  idempotencyKey String   @map("idempotency_key")
  payload        Json?
  createdAt      DateTime @default(now()) @map("created_at")

  channel Channel @relation(fields: [channelId], references: [id], onDelete: Cascade)

  @@unique([provider, idempotencyKey])
  @@index([channelId, createdAt])
  @@map("inbound_webhook_receipts")
}
```

Add the corresponding `Channel` relation:

```prisma
inboundWebhookReceipts InboundWebhookReceipt[]
```

Create migration SQL:

```sql
ALTER TYPE "ChannelType" ADD VALUE IF NOT EXISTS 'wechat_ecloud';

CREATE TABLE IF NOT EXISTS "inbound_webhook_receipts" (
  "id" TEXT NOT NULL,
  "channel_id" TEXT NOT NULL,
  "provider" TEXT NOT NULL,
  "idempotency_key" TEXT NOT NULL,
  "payload" JSONB,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "inbound_webhook_receipts_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "inbound_webhook_receipts_provider_idempotency_key_key"
  ON "inbound_webhook_receipts"("provider", "idempotency_key");

CREATE INDEX IF NOT EXISTS "inbound_webhook_receipts_channel_id_created_at_idx"
  ON "inbound_webhook_receipts"("channel_id", "created_at");

ALTER TABLE "inbound_webhook_receipts"
  ADD CONSTRAINT "inbound_webhook_receipts_channel_id_fkey"
  FOREIGN KEY ("channel_id") REFERENCES "channels"("id") ON DELETE CASCADE ON UPDATE CASCADE;
```

Add `wechat_ecloud` to `gateway/packages/shared/src/types/channel.ts` union and `CHANNEL_CONFIG_SCHEMA` with `appId`, `token`, and optional `baseUrl` fields.

Implement `wechat-ecloud-config.ts` with:

```ts
export const DEFAULT_WECHAT_ECLOUD_BASE_URL = 'https://api.geweapi.com';

export interface WechatEcloudConfigInput {
  appId: string;
  token: string;
  baseUrl: string;
}

export interface StoredWechatEcloudConfig extends WechatEcloudConfigInput {
  webhookToken: string;
}

export interface PublicWechatEcloudConfig {
  appId: string;
  baseUrl: string;
  callbackPath: '/gateway/ecloud/wechat/:channelId/:token';
}
```

Implement `parseWechatEcloudConfigInput`, `parseStoredWechatEcloudConfig`, `ensureStoredWechatEcloudConfig`, `hasWechatEcloudWebhookToken`, and `buildPublicWechatEcloudConfig`. Use trimmed non-empty strings and error names prefixed with `invalid_wechat_ecloud_config`.

Implement `wechat-ecloud-api.ts` with:

```ts
const DEFAULT_TIMEOUT_MS = 10_000;

export class WechatEcloudApiClient {
  constructor(
    private readonly baseUrl: string,
    private readonly token: string,
    private readonly fetchImpl: typeof fetch = fetch,
  ) {}

  async sendText(appId: string, toWxid: string, content: string): Promise<unknown> {
    return this.request('/gewe/v2/api/message/postText', {
      method: 'POST',
      body: JSON.stringify({ appId, toWxid, content }),
    });
  }
}
```

The private request method must:

- trim trailing slash from `baseUrl`
- send `X-GEWE-TOKEN`
- use `AbortSignal.timeout(10_000)`
- throw on network errors, HTTP non-2xx, invalid JSON, or JSON body where `ret !== 200`
- return parsed JSON on success

- [x] **Step 4: Run task tests**

```bash
cd gateway
pnpm --filter @clawscale/api db:generate
pnpm --filter @clawscale/api exec vitest run src/lib/wechat-ecloud-config.test.ts src/lib/wechat-ecloud-api.test.ts
pnpm --filter @clawscale/api build
```

Expected: all pass.

- [x] **Step 5: Commit gateway task**

```bash
cd gateway
git add packages/api/prisma/schema.prisma \
  packages/api/prisma/migrations/20260428010000_wechat_ecloud_shared_channel/migration.sql \
  packages/shared/src/types/channel.ts \
  packages/api/src/lib/wechat-ecloud-config.ts \
  packages/api/src/lib/wechat-ecloud-config.test.ts \
  packages/api/src/lib/wechat-ecloud-api.ts \
  packages/api/src/lib/wechat-ecloud-api.test.ts
git commit -m "feat: add wechat ecloud config and api client"
```

## Task 2: Outbound Delivery And Shared-Channel Access

**Files:**
- Modify: `gateway/packages/api/src/lib/outbound-delivery.ts`
- Modify: `gateway/packages/api/src/lib/outbound-delivery.test.ts`
- Modify: `gateway/packages/api/src/lib/route-message.ts`
- Modify: `gateway/packages/api/src/lib/route-message.test.ts`

- [x] **Step 1: Write failing tests**

In `outbound-delivery.test.ts`, mock `WechatEcloudApiClient`:

```ts
const ecloudSendText = vi.hoisted(() => vi.fn());

vi.mock('./wechat-ecloud-api.js', () => ({
  WechatEcloudApiClient: vi.fn().mockImplementation((_baseUrl, _token) => ({
    sendText: ecloudSendText,
  })),
}));
```

Add test:

```ts
it('delivers wechat_ecloud messages through Eyun postText', async () => {
  await deliverOutboundMessage(
    {
      id: 'ch_ecloud_1',
      type: 'wechat_ecloud',
      status: 'connected',
      config: {
        appId: 'app_1',
        token: 'token_1',
        baseUrl: 'https://api.example.test',
        webhookToken: 'secret-token',
      },
    },
    'wxid_target',
    'hello from coke',
  );

  expect(ecloudSendText).toHaveBeenCalledWith('app_1', 'wxid_target', 'hello from coke');
});
```

In `route-message.test.ts`, add a regression test modeled after the existing shared WhatsApp access test. Use channel type `wechat_ecloud`, shared ownership, an unclaimed owner membership, and assert `resolveCokeAccountAccess` is called with `requireEmailVerified: false` and the backend receives shared account metadata.

- [x] **Step 2: Run tests to verify failure**

```bash
cd gateway
pnpm --filter @clawscale/api exec vitest run src/lib/outbound-delivery.test.ts src/lib/route-message.test.ts
```

Expected: outbound rejects `wechat_ecloud`, and route-message keeps it on the legacy non-WhatsApp path.

- [x] **Step 3: Implement outbound and shared access**

In `outbound-delivery.ts`:

```ts
import { WechatEcloudApiClient } from './wechat-ecloud-api.js';
import { parseStoredWechatEcloudConfig } from './wechat-ecloud-config.js';
```

Add switch case:

```ts
case 'wechat_ecloud': {
  const config = parseStoredWechatEcloudConfig(channel.config);
  await new WechatEcloudApiClient(config.baseUrl, config.token).sendText(
    config.appId,
    externalEndUserId,
    text,
  );
  return;
}
```

In `route-message.ts`, replace the WhatsApp-only predicate with a named helper:

```ts
function isSharedChannelAccessProvider(type: string | null | undefined): boolean {
  return (
    type === 'whatsapp' ||
    type === 'whatsapp_business' ||
    type === 'whatsapp_evolution' ||
    type === 'wechat_ecloud'
  );
}
```

Use it for `isSharedWhatsAppChannel` or rename the variable to `isSharedAutoProvisionedChannel`. Preserve WhatsApp identity type behavior:

```ts
const identityType =
  sharedChannelProvider === 'whatsapp' ||
  sharedChannelProvider === 'whatsapp_business' ||
  sharedChannelProvider === 'whatsapp_evolution'
    ? 'wa_id'
    : 'external_id';
```

Do not give `wechat_ecloud` `wa_id`; it remains `external_id`.

- [x] **Step 4: Run task tests**

```bash
cd gateway
pnpm --filter @clawscale/api exec vitest run src/lib/outbound-delivery.test.ts src/lib/route-message.test.ts
pnpm --filter @clawscale/api build
```

Expected: all pass.

- [x] **Step 5: Commit gateway task**

```bash
cd gateway
git add packages/api/src/lib/outbound-delivery.ts \
  packages/api/src/lib/outbound-delivery.test.ts \
  packages/api/src/lib/route-message.ts \
  packages/api/src/lib/route-message.test.ts
git commit -m "feat: route wechat ecloud outbound delivery"
```

## Task 3: Ecloud Webhook Normalization And Gateway Route

**Files:**
- Create: `gateway/packages/api/src/lib/wechat-ecloud-webhook.ts`
- Create: `gateway/packages/api/src/lib/wechat-ecloud-webhook.test.ts`
- Modify: `gateway/packages/api/src/gateway/message-router.ts`
- Modify: `gateway/packages/api/src/gateway/message-router.test.ts`

- [x] **Step 1: Write failing webhook helper tests**

Create tests for:

- text callback `60001` normalizes to `{ externalId, displayName, text, meta, receiptKey }`
- reference callback `60014` extracts XML `displayname` and `content`
- malformed reference XML routes title with `meta.referenceParseError = true`
- `data.self !== false` is ignored
- `@chatroom` in `fromUser` or `toUser` is ignored
- `60004` and `60002` return ignored unsupported-media decisions
- callback without `msgId` or `newMsgId` is ignored before route

Use sample payload:

```ts
const textPayload = {
  wcId: 'wxid_bot',
  messageType: '60001',
  data: {
    self: false,
    fromUser: 'wxid_user',
    toUser: 'wxid_bot',
    content: 'hello',
    msgId: 123,
    newMsgId: '456',
    timestamp: 1710000000,
  },
};
```

- [x] **Step 2: Write failing gateway route tests**

In `message-router.test.ts`, add Ecloud mocks and cases:

- valid text callback calls `routeInboundMessage` with `platform: 'wechat_ecloud'`
- duplicate `newMsgId` is inserted once and second request returns 200 without routing
- bad token returns 403
- disconnected or wrong channel type returns 404
- self/group/unsupported callbacks return 200 without routing
- route failure logs and returns 200

Mock `db.inboundWebhookReceipt.create`:

```ts
const db = vi.hoisted(() => ({
  channel: { findUnique: vi.fn() },
  inboundWebhookReceipt: { create: vi.fn() },
}));
```

For duplicate test, have create reject with `{ code: 'P2002' }`.

- [x] **Step 3: Run tests to verify failure**

```bash
cd gateway
pnpm --filter @clawscale/api exec vitest run src/lib/wechat-ecloud-webhook.test.ts src/gateway/message-router.test.ts
```

Expected: fail because helper and route are missing.

- [x] **Step 4: Implement helper and route**

In `wechat-ecloud-webhook.ts`, export:

```ts
export type WechatEcloudWebhookDecision =
  | { kind: 'route'; externalId: string; displayName?: string; text: string; meta: Record<string, unknown>; receiptKey: string }
  | { kind: 'ignore'; reason: string; receiptKey?: string };

export function normalizeWechatEcloudWebhook(payload: unknown, appId: string): WechatEcloudWebhookDecision;
export function timingSafeEqualString(a: string, b: string): boolean;
```

Use `node:crypto` `timingSafeEqual`. Convert strings to `Buffer` only after non-empty validation and equal byte length check.

Bound XML input to 64 KiB before parsing. Use the JavaScript runtime's safe parsing approach available in this repo; do not introduce a new XML package unless the repo already has one. If no parser exists, extract only simple `<displayname>` and `<content>` text with bounded, non-global regexes after rejecting `<!DOCTYPE` and `<!ENTITY`.

In `message-router.ts`, add route:

```ts
.post('/ecloud/wechat/:channelId/:token', async (c) => {
  // load channel, parse config, timing-safe token check, normalize payload,
  // create inbound receipt, route, swallow downstream errors, return { ok: true }
})
```

Use `parseStoredWechatEcloudConfig`, `normalizeWechatEcloudWebhook`, and `timingSafeEqualString`.

Receipt creation:

```ts
await db.inboundWebhookReceipt.create({
  data: {
    channelId,
    provider: 'wechat_ecloud',
    idempotencyKey: `${channelId}:${decision.receiptKey}`,
    payload: body as Prisma.InputJsonValue,
  },
});
```

If Prisma unique error code `P2002`, return `{ ok: true }` without routing.

- [x] **Step 5: Run task tests**

```bash
cd gateway
pnpm --filter @clawscale/api exec vitest run src/lib/wechat-ecloud-webhook.test.ts src/gateway/message-router.test.ts
pnpm --filter @clawscale/api build
```

Expected: all pass.

- [x] **Step 6: Commit gateway task**

```bash
cd gateway
git add packages/api/src/lib/wechat-ecloud-webhook.ts \
  packages/api/src/lib/wechat-ecloud-webhook.test.ts \
  packages/api/src/gateway/message-router.ts \
  packages/api/src/gateway/message-router.test.ts
git commit -m "feat: route wechat ecloud webhooks"
```

## Task 4: Admin API And Web UI

**Files:**
- Modify: `gateway/packages/api/src/routes/admin-shared-channels.ts`
- Modify: `gateway/packages/api/src/routes/admin-shared-channels.test.ts`
- Modify: `gateway/packages/api/src/routes/admin-channels.ts`
- Modify: `gateway/packages/api/src/routes/admin-channels.test.ts`
- Modify: `gateway/packages/api/src/routes/channels.ts`
- Modify: `gateway/packages/api/src/routes/channels.test.ts`
- Modify: `gateway/packages/web/lib/admin-api.ts`
- Modify: `gateway/packages/web/app/(admin)/admin/shared-channels/page.tsx`
- Modify: `gateway/packages/web/app/(admin)/admin/shared-channels/page.test.tsx`
- Modify: `gateway/packages/web/app/(admin)/admin/shared-channels/detail/page.tsx`
- Modify: `gateway/packages/web/app/(admin)/admin/shared-channels/detail/page.test.tsx`

- [x] **Step 1: Write failing admin API tests**

In `admin-shared-channels.test.ts`, add cases:

- creates `wechat_ecloud` with `appId`, `token`, optional `baseUrl`, generated `webhookToken`
- serializes detail without raw `token` or `webhookToken`, includes `hasWebhookToken`, public `appId`, `baseUrl`, and callback URL/path
- patch rejects `token` and `webhookToken` mutation
- patch allows `appId`/`baseUrl` while disconnected and refuses config changes while connected
- connect marks connected without calling `EvolutionApiClient`
- disconnect marks disconnected without remote API call
- delete archives and clears config without remote API call

- [x] **Step 2: Write failing web tests**

Update page tests so the create form supports `wechat_ecloud` and posts:

```ts
{
  kind: 'wechat_ecloud',
  config: {
    appId: 'app_1',
    token: 'token_1',
    baseUrl: 'https://api.geweapi.com'
  }
}
```

Update detail tests so Ecloud detail shows secret-hidden status and connect/disconnect controls without Evolution instance-name text.

- [x] **Step 3: Run tests to verify failure**

```bash
cd gateway
pnpm --filter @clawscale/api exec vitest run src/routes/admin-shared-channels.test.ts src/routes/admin-channels.test.ts src/routes/channels.test.ts
pnpm --filter @clawscale/web test -- app/'(admin)'/admin/shared-channels/page.test.tsx app/'(admin)'/admin/shared-channels/detail/page.test.tsx
```

Expected: fail because `wechat_ecloud` is not supported in API/UI.

- [x] **Step 4: Implement admin API**

In `admin-shared-channels.ts`:

- add `wechat_ecloud` to `CHANNEL_KIND_VALUES`
- import Ecloud config helpers
- create `parseEcloudConfigInput`, `buildStoredEcloudConfig`, `ensureEcloudWebhookToken`
- extend `serializeSharedChannel` for public Ecloud config
- on create, store generated webhook token and status `disconnected`
- on patch, reject raw `token` and `webhookToken`; preserve existing token unless disconnected config replacement intentionally includes a new token field through a dedicated flow
- on connect/disconnect, branch by channel type:
  - `whatsapp_evolution`: existing Evolution remote webhook behavior
  - `wechat_ecloud`: local status update only
- on delete, clear config; no remote API calls for Ecloud

In `admin-channels.ts` and `channels.ts`, add `wechat_ecloud` wherever channel kind validation enumerates allowed types.

- [x] **Step 5: Implement admin web UI**

In shared channel create page:

- add option `<option value="wechat_ecloud">wechat_ecloud</option>`
- add Ecloud mode fields for `appId`, `token`, `baseUrl`
- post typed config instead of raw JSON when kind is `wechat_ecloud`

In detail page:

- detect `record.kind === 'wechat_ecloud'`
- show `appId`, `baseUrl`, and hidden webhook token status
- do not render Evolution instance fields
- use connect/disconnect actions for Ecloud too

Keep styling aligned with existing form controls.

- [x] **Step 6: Run task tests**

```bash
cd gateway
pnpm --filter @clawscale/api exec vitest run src/routes/admin-shared-channels.test.ts src/routes/admin-channels.test.ts src/routes/channels.test.ts
pnpm --filter @clawscale/web test -- app/'(admin)'/admin/shared-channels/page.test.tsx app/'(admin)'/admin/shared-channels/detail/page.test.tsx
pnpm --filter @clawscale/api build
```

Expected: all pass.

- [x] **Step 7: Commit gateway task**

```bash
cd gateway
git add packages/api/src/routes/admin-shared-channels.ts \
  packages/api/src/routes/admin-shared-channels.test.ts \
  packages/api/src/routes/admin-channels.ts \
  packages/api/src/routes/admin-channels.test.ts \
  packages/api/src/routes/channels.ts \
  packages/api/src/routes/channels.test.ts \
  packages/web/lib/admin-api.ts \
  packages/web/app/'(admin)'/admin/shared-channels/page.tsx \
  packages/web/app/'(admin)'/admin/shared-channels/page.test.tsx \
  packages/web/app/'(admin)'/admin/shared-channels/detail/page.tsx \
  packages/web/app/'(admin)'/admin/shared-channels/detail/page.test.tsx
git commit -m "feat: manage wechat ecloud shared channels"
```

## Task 5: Final Verification And Superproject Handoff

**Files:**
- Modify: `tasks/2026-04-28-wechat-ecloud-shared-channel-design.md`
- Modify: `docs/superpowers/plans/2026-04-28-wechat-ecloud-shared-channel.md`
- Modify: `gateway` gitlink

- [x] **Step 1: Run full relevant verification**

```bash
cd /data/projects/coke/.worktrees/wechat-ecloud-shared-channel/gateway
pnpm --filter @clawscale/shared build
pnpm --filter @clawscale/api db:generate
pnpm --filter @clawscale/api exec vitest run src/lib/wechat-ecloud-config.test.ts src/lib/wechat-ecloud-api.test.ts src/lib/wechat-ecloud-webhook.test.ts src/lib/outbound-delivery.test.ts src/lib/route-message.test.ts src/gateway/message-router.test.ts src/routes/admin-shared-channels.test.ts src/routes/admin-channels.test.ts src/routes/channels.test.ts
pnpm --filter @clawscale/api build
```

Run web tests:

```bash
cd /data/projects/coke/.worktrees/wechat-ecloud-shared-channel/gateway
pnpm --filter @clawscale/web test -- app/'(admin)'/admin/shared-channels/page.test.tsx app/'(admin)'/admin/shared-channels/detail/page.test.tsx
```

Run repo-OS check:

```bash
cd /data/projects/coke/.worktrees/wechat-ecloud-shared-channel
zsh scripts/check
```

- [x] **Step 2: Update task evidence**

In `tasks/2026-04-28-wechat-ecloud-shared-channel-design.md`, add an implementation handoff section:

```md
## Implementation Handoff

- Plan: `docs/superpowers/plans/2026-04-28-wechat-ecloud-shared-channel.md`
- Gateway branch: `feature/wechat-ecloud-shared-channel`
- Verification:
  - `pnpm --filter @clawscale/api exec vitest run ...`
  - `pnpm --filter @clawscale/api build`
  - `pnpm --filter @clawscale/web test -- ...`
  - `zsh scripts/check`
```

- [ ] **Step 3: Commit superproject gitlink and docs**

```bash
cd /data/projects/coke/.worktrees/wechat-ecloud-shared-channel
git add gateway docs/superpowers/plans/2026-04-28-wechat-ecloud-shared-channel.md tasks/2026-04-28-wechat-ecloud-shared-channel-design.md
git commit -m "feat: wire wechat ecloud shared channel"
```

- [ ] **Step 4: Final status**

Report:

- worktree path
- gateway branch and latest gateway commit
- superproject branch and latest superproject commit
- verification commands and outcomes
- any follow-up risks, especially phase-2 media handling
