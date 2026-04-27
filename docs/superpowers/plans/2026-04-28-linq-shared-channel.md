# Linq Shared Channel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Linq-backed gateway shared-channel adapter with inbound webhooks, immediate replies, proactive outbound delivery, typed admin management, and secret-safe config handling.

**Architecture:** Implement `linq` as a gateway shared-channel kind, parallel to `whatsapp_evolution`, while keeping Coke bridge and worker boundaries unchanged. Linq HTTP details live in focused client/config modules; gateway routing calls `routeInboundMessage()` for inbound and `deliverOutboundMessage()` for outbound.

**Tech Stack:** TypeScript, Hono, Prisma, Vitest, Next.js admin UI, Linq Partner API v3.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-04-28-linq-shared-channel-design.md`
- Task: `tasks/2026-04-28-linq-shared-channel.md`
- Verification matrix: `docs/fitness/coke-verification-matrix.md`

## File Structure

- Create `gateway/packages/api/src/lib/linq-config.ts`: parse, normalize, scrub, and backfill Linq channel config.
- Create `gateway/packages/api/src/lib/linq-config.test.ts`: config parser and public serializer coverage.
- Create `gateway/packages/api/src/lib/linq-api.ts`: Linq Partner API client for chat send and webhook subscription lifecycle.
- Create `gateway/packages/api/src/lib/linq-api.test.ts`: Linq request shape and error wrapping coverage.
- Modify `gateway/packages/api/prisma/schema.prisma`: add `linq` to `ChannelType`.
- Create `gateway/packages/api/prisma/migrations/20260428120000_linq_shared_channel/migration.sql`: Postgres enum migration.
- Modify `gateway/packages/shared/src/types/channel.ts`: add shared channel type and form schema label.
- Modify `gateway/packages/api/src/lib/external-identity.ts` and test: add Linq phone-number normalization.
- Modify `gateway/packages/api/src/lib/route-message.ts` and test: treat shared Linq like shared WhatsApp for provisioning/access, with `phone_number` identity.
- Modify `gateway/packages/api/src/routes/admin-channels.ts` and test: allow `linq` filters.
- Modify `gateway/packages/api/src/routes/channels.ts` and test: accept `linq`, scrub config on detail response, preserve generic route behavior.
- Modify `gateway/packages/api/src/routes/admin-shared-channels.ts` and test: typed Linq create/patch/connect/disconnect/delete lifecycle.
- Modify `gateway/packages/api/src/gateway/message-router.ts` and test: Linq webhook route, fail-closed HMAC verification, immediate replies.
- Modify `gateway/packages/api/src/lib/outbound-delivery.ts` and test: Linq proactive outbound.
- Modify `gateway/packages/web/app/(admin)/admin/shared-channels/page.tsx` and test: typed Linq create form.
- Modify `gateway/packages/web/app/(admin)/admin/shared-channels/detail/page.tsx` and test: typed Linq detail, secret indicators, connect/disconnect.
- Modify `gateway/packages/web/lib/admin-copy.ts`: admin copy for Linq labels.
- Modify `.env`: add Linq local runtime values.

## Task 1: Add Linq Channel Type And Identity Foundation

**Files:**
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Create: `gateway/packages/api/prisma/migrations/20260428120000_linq_shared_channel/migration.sql`
- Modify: `gateway/packages/shared/src/types/channel.ts`
- Modify: `gateway/packages/api/src/lib/external-identity.ts`
- Modify: `gateway/packages/api/src/lib/external-identity.test.ts`
- Modify: `gateway/packages/api/src/lib/route-message.ts`
- Modify: `gateway/packages/api/src/lib/route-message.test.ts`
- Modify: `gateway/packages/api/src/routes/admin-channels.ts`
- Modify: `gateway/packages/api/src/routes/admin-channels.test.ts`

- [ ] **Step 1: Write failing external identity tests**

Add these cases to `gateway/packages/api/src/lib/external-identity.test.ts`:

```ts
it('normalizes linq phone_number identities to E.164-like values', () => {
  expect(
    normalizeExternalIdentity({
      provider: 'linq',
      identityType: 'phone_number',
      rawValue: '+86 152 017 80593',
    }),
  ).toEqual({
    provider: 'linq',
    identityType: 'phone_number',
    identityValue: '+8615201780593',
  });

  expect(
    normalizeExternalIdentity({
      provider: 'linq',
      identityType: 'phone_number',
      rawValue: '8615201780593',
    }),
  ).toEqual({
    provider: 'linq',
    identityType: 'phone_number',
    identityValue: '+8615201780593',
  });
});

it('keeps unexpected linq phone_number identities trimmed when no digits exist', () => {
  expect(
    normalizeExternalIdentity({
      provider: 'linq',
      identityType: 'phone_number',
      rawValue: ' user@example.com ',
    }),
  ).toEqual({
    provider: 'linq',
    identityType: 'phone_number',
    identityValue: 'user@example.com',
  });
});
```

- [ ] **Step 2: Run identity tests and verify RED**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/external-identity.test.ts
```

Expected: FAIL because `linq` phone-number identities are not normalized.

- [ ] **Step 3: Implement Linq identity normalization**

In `gateway/packages/api/src/lib/external-identity.ts`, add a Linq provider set and phone normalizer:

```ts
const WHATSAPP_PROVIDERS = new Set(['whatsapp', 'whatsapp_business', 'whatsapp_evolution']);
const LINQ_PROVIDERS = new Set(['linq']);

function normalizePhoneNumber(rawValue: string): string {
  const digitsOnly = rawValue.replace(/\D+/g, '');
  return digitsOnly.length > 0 ? `+${digitsOnly}` : rawValue.trim();
}
```

Then update `identityValue` selection:

```ts
identityValue:
  WHATSAPP_PROVIDERS.has(provider) && identityType === 'wa_id'
    ? normalizeWhatsAppWaId(trimmedValue)
    : LINQ_PROVIDERS.has(provider) && identityType === 'phone_number'
      ? normalizePhoneNumber(trimmedValue)
      : trimmedValue,
```

- [ ] **Step 4: Verify identity tests GREEN**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/external-identity.test.ts
```

Expected: PASS.

- [ ] **Step 5: Write failing route-message tests for shared Linq provisioning**

Add a test to `gateway/packages/api/src/lib/route-message.test.ts` near the existing shared-channel provisioning tests:

```ts
it('provisions linq shared channels with phone_number identity and shared access semantics', async () => {
  db.channel.findUnique.mockResolvedValue({
    id: 'ch_1',
    tenantId: 'ten_1',
    type: 'linq',
    customerId: null,
    ownershipKind: 'shared',
    agentId: 'agent_shared',
    status: 'connected',
    scope: 'tenant_shared',
    ownerClawscaleUserId: null,
    ownerClawscaleUser: null,
  });

  await routeInboundMessage({
    channelId: 'ch_1',
    externalId: '+86 152 017 80593',
    displayName: 'Alice',
    text: 'hello from linq',
    meta: { platform: 'linq' },
  });

  expect(provisionSharedChannelCustomer).toHaveBeenCalledWith(
    expect.objectContaining({
      channelId: 'ch_1',
      agentId: 'agent_shared',
      provider: 'linq',
      identityType: 'phone_number',
      rawIdentityValue: '+86 152 017 80593',
    }),
  );
  expect(resolveCokeAccountAccess).toHaveBeenCalledWith(
    expect.objectContaining({
      requireEmailVerified: false,
    }),
  );
});
```

- [ ] **Step 6: Run route-message test and verify RED**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/route-message.test.ts -t "provisions linq shared channels"
```

Expected: FAIL because Linq is treated as `external_id` and not included in shared access semantics.

- [ ] **Step 7: Implement route-message Linq shared-channel handling**

In `gateway/packages/api/src/lib/route-message.ts`, replace the WhatsApp-only shared-channel checks with helper functions near the top-level helper area:

```ts
function isSharedAutoProvisionedChannelType(type: string | null): boolean {
  return type === 'whatsapp' ||
    type === 'whatsapp_business' ||
    type === 'whatsapp_evolution' ||
    type === 'linq';
}

function getSharedChannelIdentityType(provider: string): string {
  return provider === 'linq' ? 'phone_number' : 'wa_id';
}
```

Use them for:

```ts
const isSharedAutoProvisionedChannel =
  channel.ownershipKind === 'shared' &&
  isSharedAutoProvisionedChannelType(channel.type);
```

and:

```ts
const identityType = getSharedChannelIdentityType(sharedChannelProvider);
```

Rename downstream uses of `isSharedWhatsAppChannel` to
`isSharedAutoProvisionedChannel`.

- [ ] **Step 8: Verify route-message test GREEN**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/route-message.test.ts -t "provisions linq shared channels"
```

Expected: PASS.

- [ ] **Step 9: Add Linq enum/type/filter tests**

Extend `gateway/packages/api/src/routes/admin-channels.test.ts`:

```ts
it('accepts linq as a kind filter', async () => {
  db.channel.findMany.mockResolvedValueOnce([
    {
      id: 'ch_linq',
      name: 'Linq Shared',
      type: 'linq',
      status: 'connected',
      ownershipKind: 'shared',
      customerId: null,
      createdAt: new Date('2026-04-28T10:00:00.000Z'),
      updatedAt: new Date('2026-04-28T10:10:00.000Z'),
    },
  ]);
  db.channel.count.mockResolvedValueOnce(1);

  const res = await app.request('/api/admin/channels?kind=linq');

  expect(res.status).toBe(200);
  expect(db.channel.findMany).toHaveBeenCalledWith(expect.objectContaining({
    where: expect.objectContaining({ type: 'linq' }),
  }));
});
```

- [ ] **Step 10: Run enum/filter tests and verify RED**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/routes/admin-channels.test.ts -t "linq"
```

Expected: FAIL because `linq` is not in route validation.

- [ ] **Step 11: Add channel type surfaces**

Make these edits:

`gateway/packages/api/prisma/schema.prisma`:

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
  linq
  wechat_personal
}
```

`gateway/packages/api/prisma/migrations/20260428120000_linq_shared_channel/migration.sql`:

```sql
ALTER TYPE "ChannelType" ADD VALUE IF NOT EXISTS 'linq';
```

Add `'linq'` to:

- `CHANNEL_KIND_VALUES` in `gateway/packages/api/src/routes/admin-channels.ts`
- `CHANNEL_TYPES` in `gateway/packages/api/src/routes/channels.ts`
- `CHANNEL_KIND_VALUES` in `gateway/packages/api/src/routes/admin-shared-channels.ts`
- `ChannelType` union in `gateway/packages/shared/src/types/channel.ts`
- `CHANNEL_CONFIG_SCHEMA` in `gateway/packages/shared/src/types/channel.ts`

Use this shared config schema entry:

```ts
linq: {
  label: 'Linq',
  fields: [
    { key: 'fromNumber', label: 'From Number', type: 'text', required: false, placeholder: '+13213108456' },
  ],
},
```

- [ ] **Step 12: Verify foundation tests GREEN**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/external-identity.test.ts \
  src/lib/route-message.test.ts \
  src/routes/admin-channels.test.ts
```

Expected: PASS.

- [ ] **Step 13: Generate Prisma client**

Run:

```bash
pnpm --dir gateway/packages/api run db:generate
```

Expected: command exits 0.

- [ ] **Step 14: Commit Task 1**

Run:

```bash
git -C gateway add \
  packages/api/prisma/schema.prisma \
  packages/api/prisma/migrations/20260428120000_linq_shared_channel/migration.sql \
  packages/shared/src/types/channel.ts \
  packages/api/src/lib/external-identity.ts \
  packages/api/src/lib/external-identity.test.ts \
  packages/api/src/lib/route-message.ts \
  packages/api/src/lib/route-message.test.ts \
  packages/api/src/routes/admin-channels.ts \
  packages/api/src/routes/admin-channels.test.ts
git -C gateway commit -m "feat(gateway): add linq shared channel foundation"
```

## Task 2: Add Linq Config And API Client

**Files:**
- Create: `gateway/packages/api/src/lib/linq-config.ts`
- Create: `gateway/packages/api/src/lib/linq-config.test.ts`
- Create: `gateway/packages/api/src/lib/linq-api.ts`
- Create: `gateway/packages/api/src/lib/linq-api.test.ts`

- [ ] **Step 1: Write failing Linq config tests**

Create `gateway/packages/api/src/lib/linq-config.test.ts`:

```ts
import { describe, expect, it } from 'vitest';

import {
  buildPublicLinqConfig,
  ensureStoredLinqConfig,
  hasLinqSigningSecret,
  hasLinqWebhookToken,
  normalizeLinqPhoneNumber,
  parseStoredLinqConfig,
} from './linq-config.js';

describe('linq config helpers', () => {
  it('normalizes Linq phone numbers to E.164-like values', () => {
    expect(normalizeLinqPhoneNumber('+1 (321) 310-8456')).toBe('+13213108456');
    expect(normalizeLinqPhoneNumber('13213108456')).toBe('+13213108456');
  });

  it('rejects malformed phone numbers', () => {
    expect(() => normalizeLinqPhoneNumber('not-a-phone')).toThrow('invalid_linq_phone_number');
  });

  it('scrubs webhook secrets from public config', () => {
    expect(
      buildPublicLinqConfig({
        fromNumber: '+13213108456',
        webhookToken: 'secret-token',
        webhookSubscriptionId: 'sub_1',
        signingSecret: 'signing-secret',
      }),
    ).toEqual({
      fromNumber: '+13213108456',
      webhookSubscriptionId: 'sub_1',
    });
  });

  it('backfills missing webhook tokens for disconnected legacy configs', () => {
    expect(
      ensureStoredLinqConfig({ fromNumber: '+13213108456' }, () => 'token_uuid_1'),
    ).toEqual({
      fromNumber: '+13213108456',
      webhookToken: 'token_uuid_1',
    });
  });

  it('parses connected stored config with required secrets', () => {
    expect(
      parseStoredLinqConfig({
        fromNumber: '+13213108456',
        webhookToken: 'secret-token',
        webhookSubscriptionId: 'sub_1',
        signingSecret: 'signing-secret',
      }),
    ).toEqual({
      fromNumber: '+13213108456',
      webhookToken: 'secret-token',
      webhookSubscriptionId: 'sub_1',
      signingSecret: 'signing-secret',
    });
  });

  it('detects token and signing secret presence', () => {
    const config = {
      fromNumber: '+13213108456',
      webhookToken: 'secret-token',
      signingSecret: 'signing-secret',
    };

    expect(hasLinqWebhookToken(config)).toBe(true);
    expect(hasLinqSigningSecret(config)).toBe(true);
    expect(hasLinqWebhookToken({ fromNumber: '+13213108456' })).toBe(false);
    expect(hasLinqSigningSecret({ fromNumber: '+13213108456' })).toBe(false);
  });
});
```

- [ ] **Step 2: Run config tests and verify RED**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/linq-config.test.ts
```

Expected: FAIL because `linq-config.ts` does not exist.

- [ ] **Step 3: Implement Linq config helpers**

Create `gateway/packages/api/src/lib/linq-config.ts`:

```ts
export interface StoredLinqConfig {
  fromNumber: string;
  webhookToken?: string;
  webhookSubscriptionId?: string;
  signingSecret?: string;
}

export interface PublicLinqConfig {
  fromNumber: string;
  webhookSubscriptionId?: string;
}

function readRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('linq_config_invalid');
  }
  return value as Record<string, unknown>;
}

function readOptionalString(record: Record<string, unknown>, key: string): string | undefined {
  const value = record[key];
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

export function normalizeLinqPhoneNumber(value: string): string {
  const digits = value.replace(/\D+/g, '');
  if (!digits) {
    throw new Error('invalid_linq_phone_number');
  }
  return `+${digits}`;
}

export function parseStoredLinqConfig(value: unknown): StoredLinqConfig {
  const record = readRecord(value);
  const fromNumber = readOptionalString(record, 'fromNumber');
  if (!fromNumber) {
    throw new Error('linq_config_invalid:fromNumber');
  }
  return {
    fromNumber: normalizeLinqPhoneNumber(fromNumber),
    ...(readOptionalString(record, 'webhookToken') ? { webhookToken: readOptionalString(record, 'webhookToken') } : {}),
    ...(readOptionalString(record, 'webhookSubscriptionId') ? { webhookSubscriptionId: readOptionalString(record, 'webhookSubscriptionId') } : {}),
    ...(readOptionalString(record, 'signingSecret') ? { signingSecret: readOptionalString(record, 'signingSecret') } : {}),
  };
}

export function buildPublicLinqConfig(value: unknown): PublicLinqConfig {
  const parsed = parseStoredLinqConfig(value);
  return {
    fromNumber: parsed.fromNumber,
    ...(parsed.webhookSubscriptionId ? { webhookSubscriptionId: parsed.webhookSubscriptionId } : {}),
  };
}

export function ensureStoredLinqConfig(
  value: unknown,
  tokenFactory: () => string,
): StoredLinqConfig {
  const parsed = parseStoredLinqConfig(value);
  return {
    ...parsed,
    webhookToken: parsed.webhookToken ?? tokenFactory(),
  };
}

export function hasLinqWebhookToken(value: unknown): boolean {
  try {
    return Boolean(parseStoredLinqConfig(value).webhookToken);
  } catch {
    return false;
  }
}

export function hasLinqSigningSecret(value: unknown): boolean {
  try {
    return Boolean(parseStoredLinqConfig(value).signingSecret);
  } catch {
    return false;
  }
}
```

- [ ] **Step 4: Verify config tests GREEN**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/linq-config.test.ts
```

Expected: PASS.

- [ ] **Step 5: Write failing Linq API client tests**

Create `gateway/packages/api/src/lib/linq-api.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const fetchMock = vi.hoisted(() => vi.fn());

import { LinqApiClient } from './linq-api.js';

describe('LinqApiClient', () => {
  const originalFetch = global.fetch;
  const originalBaseUrl = process.env['LINQ_API_BASE_URL'];
  const originalApiKey = process.env['LINQ_API_KEY'];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('fetch', fetchMock);
    process.env['LINQ_API_BASE_URL'] = 'https://api.linq.example/api/partner/v3';
    process.env['LINQ_API_KEY'] = 'test-linq-token';
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ id: 'ok_1', signing_secret: 'secret' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });

  afterEach(() => {
    global.fetch = originalFetch;
    if (originalBaseUrl === undefined) delete process.env['LINQ_API_BASE_URL'];
    else process.env['LINQ_API_BASE_URL'] = originalBaseUrl;
    if (originalApiKey === undefined) delete process.env['LINQ_API_KEY'];
    else process.env['LINQ_API_KEY'] = originalApiKey;
  });

  it('creates a chat with a single text part', async () => {
    await new LinqApiClient().createChat({
      from: '+13213108456',
      to: ['+8615201780593'],
      text: 'Hello World',
    });

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.linq.example/api/partner/v3/chats',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-linq-token',
          Accept: 'application/json',
          'content-type': 'application/json',
        }),
        body: JSON.stringify({
          from: '+13213108456',
          to: ['+8615201780593'],
          message: { parts: [{ type: 'text', value: 'Hello World' }] },
        }),
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it('creates webhook subscriptions for message.received only and pins payload version', async () => {
    const result = await new LinqApiClient().createWebhookSubscription({
      targetUrl: 'https://coke.example/gateway/linq/ch_1/token_1',
      phoneNumbers: ['+13213108456'],
    });

    expect(result).toEqual({ id: 'ok_1', signingSecret: 'secret' });
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.linq.example/api/partner/v3/webhook-subscriptions',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          target_url: 'https://coke.example/gateway/linq/ch_1/token_1?version=2026-02-03',
          subscribed_events: ['message.received'],
          phone_numbers: ['+13213108456'],
        }),
      }),
    );
  });

  it('deletes webhook subscriptions by id', async () => {
    await new LinqApiClient().deleteWebhookSubscription('sub_1');

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.linq.example/api/partner/v3/webhook-subscriptions/sub_1',
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('wraps network failures with the request path', async () => {
    fetchMock.mockRejectedValueOnce(new Error('socket hang up'));

    await expect(
      new LinqApiClient().createChat({
        from: '+13213108456',
        to: ['+8615201780593'],
        text: 'hello',
      }),
    ).rejects.toThrow('Linq API request failed /chats: socket hang up');
  });
});
```

- [ ] **Step 6: Run API client tests and verify RED**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/linq-api.test.ts
```

Expected: FAIL because `linq-api.ts` does not exist.

- [ ] **Step 7: Implement Linq API client**

Create `gateway/packages/api/src/lib/linq-api.ts`:

```ts
const DEFAULT_TIMEOUT_MS = 10_000;
const WEBHOOK_VERSION = '2026-02-03';
const LINQ_WEBHOOK_EVENTS = ['message.received'] as const;

function trimRequiredEnv(name: 'LINQ_API_BASE_URL' | 'LINQ_API_KEY'): string {
  const value = process.env[name]?.trim() ?? '';
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function buildBaseUrl(value: string): string {
  return value.endsWith('/') ? value.slice(0, -1) : value;
}

function withWebhookVersion(targetUrl: string): string {
  const url = new URL(targetUrl);
  url.searchParams.set('version', WEBHOOK_VERSION);
  return url.toString();
}

async function readErrorBody(response: Response): Promise<string> {
  try {
    return (await response.text()).trim();
  } catch {
    return '';
  }
}

function readErrorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim() ? error.message : 'network_error';
}

export interface CreateLinqChatInput {
  from: string;
  to: string[];
  text: string;
}

export interface CreateLinqWebhookSubscriptionInput {
  targetUrl: string;
  phoneNumbers: string[];
}

export interface LinqWebhookSubscriptionResult {
  id: string;
  signingSecret: string;
}

export class LinqApiClient {
  constructor(
    private readonly baseUrl = trimRequiredEnv('LINQ_API_BASE_URL'),
    private readonly apiKey = trimRequiredEnv('LINQ_API_KEY'),
    private readonly fetchImpl: typeof fetch = fetch,
  ) {}

  async createChat(input: CreateLinqChatInput): Promise<unknown> {
    return this.request('/chats', {
      method: 'POST',
      body: JSON.stringify({
        from: input.from,
        to: input.to,
        message: {
          parts: [{ type: 'text', value: input.text }],
        },
      }),
    });
  }

  async createWebhookSubscription(
    input: CreateLinqWebhookSubscriptionInput,
  ): Promise<LinqWebhookSubscriptionResult> {
    const response = await this.request('/webhook-subscriptions', {
      method: 'POST',
      body: JSON.stringify({
        target_url: withWebhookVersion(input.targetUrl),
        subscribed_events: [...LINQ_WEBHOOK_EVENTS],
        phone_numbers: input.phoneNumbers,
      }),
    });
    const record = response as Record<string, unknown>;
    const id = typeof record['id'] === 'string' ? record['id'] : '';
    const signingSecret = typeof record['signing_secret'] === 'string'
      ? record['signing_secret']
      : typeof record['signingSecret'] === 'string'
        ? record['signingSecret']
        : '';
    if (!id || !signingSecret) {
      throw new Error('Linq API webhook subscription response missing id or signing_secret');
    }
    return { id, signingSecret };
  }

  async deleteWebhookSubscription(subscriptionId: string): Promise<unknown> {
    return this.request(`/webhook-subscriptions/${subscriptionId}`, {
      method: 'DELETE',
    });
  }

  private async request(path: string, init: RequestInit): Promise<unknown> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${buildBaseUrl(this.baseUrl)}${path}`, {
        ...init,
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          Accept: 'application/json',
          ...(init.body ? { 'content-type': 'application/json' } : {}),
          ...(init.headers ?? {}),
        },
        signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
      });
    } catch (error) {
      throw new Error(`Linq API request failed ${path}: ${readErrorMessage(error)}`);
    }

    if (!response.ok) {
      const body = await readErrorBody(response);
      throw new Error(
        body
          ? `Linq API request failed (${response.status}) ${path}: ${body}`
          : `Linq API request failed (${response.status}) ${path}`,
      );
    }

    if (response.status === 204) return null;
    const contentType = response.headers.get('content-type') ?? '';
    return contentType.includes('application/json') ? response.json() : response.text();
  }
}

export { LINQ_WEBHOOK_EVENTS, WEBHOOK_VERSION as LINQ_WEBHOOK_VERSION };
```

- [ ] **Step 8: Verify Linq client tests GREEN**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/linq-config.test.ts src/lib/linq-api.test.ts
```

Expected: PASS.

- [ ] **Step 9: Commit Task 2**

Run:

```bash
git -C gateway add \
  packages/api/src/lib/linq-config.ts \
  packages/api/src/lib/linq-config.test.ts \
  packages/api/src/lib/linq-api.ts \
  packages/api/src/lib/linq-api.test.ts
git -C gateway commit -m "feat(gateway): add linq api client"
```

## Task 3: Add Admin API Linq Lifecycle And Secret Scrubbing

**Files:**
- Modify: `gateway/packages/api/src/routes/admin-shared-channels.ts`
- Modify: `gateway/packages/api/src/routes/admin-shared-channels.test.ts`
- Modify: `gateway/packages/api/src/routes/channels.ts`
- Modify: `gateway/packages/api/src/routes/channels.test.ts`

- [ ] **Step 1: Write failing admin shared-channel Linq create/detail tests**

In `gateway/packages/api/src/routes/admin-shared-channels.test.ts`, extend the hoisted mocks:

```ts
const createWebhookSubscription = vi.hoisted(() => vi.fn());
const deleteWebhookSubscription = vi.hoisted(() => vi.fn());
```

Extend the `vi.mock('../lib/linq-api.js', ...)` mock:

```ts
vi.mock('../lib/linq-api.js', () => ({
  LinqApiClient: vi.fn().mockImplementation(() => ({
    createWebhookSubscription,
    deleteWebhookSubscription,
  })),
}));
```

Add tests:

```ts
it('creates linq shared channels with fromNumber and hidden secrets', async () => {
  db.channel.create.mockResolvedValueOnce({
    id: 'ch_linq',
    name: 'Linq Shared',
    type: 'linq',
    status: 'disconnected',
    ownershipKind: 'shared',
    customerId: null,
    agentId: 'agent_coke',
    config: {
      fromNumber: '+13213108456',
      webhookToken: 'token_uuid_1',
    },
    createdAt: new Date('2026-04-28T11:30:00.000Z'),
    updatedAt: new Date('2026-04-28T11:30:00.000Z'),
    agent: { id: 'agent_coke', slug: 'coke', name: 'Coke' },
  });

  const res = await app.request('/api/admin/shared-channels', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      kind: 'linq',
      name: 'Linq Shared',
      agentId: 'agent_coke',
      config: { fromNumber: '+1 (321) 310-8456' },
    }),
  });

  expect(res.status).toBe(201);
  await expect(res.json()).resolves.toMatchObject({
    ok: true,
    data: {
      id: 'ch_linq',
      kind: 'linq',
      config: { fromNumber: '+13213108456' },
      hasWebhookToken: true,
      hasSigningSecret: false,
    },
  });
  expect(db.channel.create).toHaveBeenCalledWith({
    data: expect.objectContaining({
      type: 'linq',
      config: {
        fromNumber: '+13213108456',
        webhookToken: 'token_uuid_1',
      },
    }),
    select: expect.any(Object),
  });
});

it('scrubs linq secrets from shared channel detail responses', async () => {
  db.channel.findUnique.mockResolvedValueOnce({
    id: 'ch_linq',
    name: 'Linq Shared',
    type: 'linq',
    status: 'connected',
    ownershipKind: 'shared',
    customerId: null,
    agentId: 'agent_coke',
    config: {
      fromNumber: '+13213108456',
      webhookToken: 'secret-token',
      webhookSubscriptionId: 'sub_1',
      signingSecret: 'signing-secret',
    },
    createdAt: new Date('2026-04-28T11:30:00.000Z'),
    updatedAt: new Date('2026-04-28T11:40:00.000Z'),
    agent: { id: 'agent_coke', slug: 'coke', name: 'Coke' },
  });

  const res = await app.request('/api/admin/shared-channels/ch_linq');

  expect(res.status).toBe(200);
  await expect(res.json()).resolves.toMatchObject({
    ok: true,
    data: {
      kind: 'linq',
      config: {
        fromNumber: '+13213108456',
        webhookSubscriptionId: 'sub_1',
      },
      hasWebhookToken: true,
      hasSigningSecret: true,
    },
  });
});
```

- [ ] **Step 2: Run admin shared-channel tests and verify RED**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/routes/admin-shared-channels.test.ts -t "linq"
```

Expected: FAIL because Linq is not accepted or serialized.

- [ ] **Step 3: Implement Linq create/detail serialization**

In `gateway/packages/api/src/routes/admin-shared-channels.ts`:

1. Import Linq helpers:

```ts
import { LinqApiClient } from '../lib/linq-api.js';
import {
  buildPublicLinqConfig,
  ensureStoredLinqConfig,
  hasLinqSigningSecret,
  hasLinqWebhookToken,
  normalizeLinqPhoneNumber,
  parseStoredLinqConfig,
  type StoredLinqConfig,
} from '../lib/linq-config.js';
```

2. Add `linq` to `CHANNEL_KIND_VALUES`.

3. Add input schema:

```ts
const linqConfigInputSchema = z
  .object({
    fromNumber: z.string().trim().min(1).optional(),
  })
  .strict();
```

4. Add helper:

```ts
function readDefaultLinqFromNumber(): string | null {
  const value = process.env['LINQ_FROM_NUMBER']?.trim() ?? '';
  return value ? normalizeLinqPhoneNumber(value) : null;
}

function parseLinqConfigInput(config: Record<string, unknown>) {
  const parsed = linqConfigInputSchema.safeParse(config);
  if (!parsed.success) {
    return { ok: false as const, response: validationError(parsed.error.issues) };
  }
  const fromNumber = parsed.data.fromNumber
    ? normalizeLinqPhoneNumber(parsed.data.fromNumber)
    : readDefaultLinqFromNumber();
  if (!fromNumber) {
    return { ok: false as const, response: { ok: false as const, error: 'linq_config_invalid' } };
  }
  return { ok: true as const, data: { fromNumber } };
}

function buildStoredLinqConfig(input: {
  fromNumber: string;
  webhookToken: string;
  webhookSubscriptionId?: string;
  signingSecret?: string;
}): Prisma.InputJsonObject & StoredLinqConfig {
  return {
    fromNumber: input.fromNumber,
    webhookToken: input.webhookToken,
    ...(input.webhookSubscriptionId ? { webhookSubscriptionId: input.webhookSubscriptionId } : {}),
    ...(input.signingSecret ? { signingSecret: input.signingSecret } : {}),
  };
}
```

5. Update `serializeSharedChannel()`:

```ts
if (row.type === 'linq') {
  return {
    ...base,
    ...(options?.includeConfig ? { config: buildPublicLinqConfig(row.config) } : {}),
    hasWebhookToken: hasLinqWebhookToken(row.config),
    hasSigningSecret: hasLinqSigningSecret(row.config),
  };
}
```

6. Update create path:

```ts
if (parsedBody.data.kind === 'linq') {
  const parsedConfig = parseLinqConfigInput(parsedBody.data.config);
  if (!parsedConfig.ok) return c.json(parsedConfig.response, 400);
  config = buildStoredLinqConfig({
    fromNumber: parsedConfig.data.fromNumber,
    webhookToken: randomUUID(),
  });
}
```

- [ ] **Step 4: Verify create/detail tests GREEN**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/routes/admin-shared-channels.test.ts -t "linq shared channels"
```

Expected: PASS for Linq create/detail tests.

- [ ] **Step 5: Write failing Linq patch/connect/disconnect/delete tests**

Add tests in `gateway/packages/api/src/routes/admin-shared-channels.test.ts`:

```ts
it('rejects linq secret patch attempts and connected fromNumber changes', async () => {
  db.channel.findUnique.mockResolvedValue({
    id: 'ch_linq',
    name: 'Linq Shared',
    type: 'linq',
    status: 'connected',
    ownershipKind: 'shared',
    customerId: null,
    agentId: 'agent_coke',
    config: {
      fromNumber: '+13213108456',
      webhookToken: 'secret-token',
      webhookSubscriptionId: 'sub_1',
      signingSecret: 'signing-secret',
    },
    createdAt: new Date('2026-04-28T11:30:00.000Z'),
    updatedAt: new Date('2026-04-28T11:40:00.000Z'),
    agent: { id: 'agent_coke', slug: 'coke', name: 'Coke' },
  });

  const secretRes = await app.request('/api/admin/shared-channels/ch_linq', {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ config: { fromNumber: '+13213108456', signingSecret: 'new' } }),
  });
  expect(secretRes.status).toBe(400);
  await expect(secretRes.json()).resolves.toEqual({ ok: false, error: 'linq_secret_not_mutable' });

  const numberRes = await app.request('/api/admin/shared-channels/ch_linq', {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ config: { fromNumber: '+14155550100' } }),
  });
  expect(numberRes.status).toBe(409);
  await expect(numberRes.json()).resolves.toEqual({
    ok: false,
    error: 'linq_from_number_not_mutable_while_connected',
  });
});

it('connects linq shared channels by creating a webhook subscription', async () => {
  createWebhookSubscription.mockResolvedValueOnce({
    id: 'sub_1',
    signingSecret: 'signing-secret',
  });
  db.channel.findUnique.mockResolvedValueOnce({
    id: 'ch_linq',
    name: 'Linq Shared',
    type: 'linq',
    status: 'disconnected',
    ownershipKind: 'shared',
    customerId: null,
    agentId: 'agent_coke',
    config: { fromNumber: '+13213108456', webhookToken: 'secret-token' },
    createdAt: new Date('2026-04-28T11:30:00.000Z'),
    updatedAt: new Date('2026-04-28T11:40:00.000Z'),
    agent: { id: 'agent_coke', slug: 'coke', name: 'Coke' },
  });
  db.channel.update.mockResolvedValueOnce({
    id: 'ch_linq',
    name: 'Linq Shared',
    type: 'linq',
    status: 'connected',
    ownershipKind: 'shared',
    customerId: null,
    agentId: 'agent_coke',
    config: {
      fromNumber: '+13213108456',
      webhookToken: 'secret-token',
      webhookSubscriptionId: 'sub_1',
      signingSecret: 'signing-secret',
    },
    createdAt: new Date('2026-04-28T11:30:00.000Z'),
    updatedAt: new Date('2026-04-28T11:40:00.000Z'),
    agent: { id: 'agent_coke', slug: 'coke', name: 'Coke' },
  });

  const res = await app.request('/api/admin/shared-channels/ch_linq/connect', { method: 'POST' });

  expect(res.status).toBe(200);
  expect(createWebhookSubscription).toHaveBeenCalledWith({
    targetUrl: 'https://coke.keep4oforever.com/gateway/linq/ch_linq/secret-token',
    phoneNumbers: ['+13213108456'],
  });
  expect(db.channel.update).toHaveBeenCalledWith({
    where: { id: 'ch_linq' },
    data: {
      status: 'connected',
      config: {
        fromNumber: '+13213108456',
        webhookToken: 'secret-token',
        webhookSubscriptionId: 'sub_1',
        signingSecret: 'signing-secret',
      },
    },
    select: expect.any(Object),
  });
});

it('disconnects linq shared channels by deleting the webhook subscription and clearing remote secrets', async () => {
  deleteWebhookSubscription.mockResolvedValueOnce(null);
  db.channel.findUnique.mockResolvedValueOnce({
    id: 'ch_linq',
    name: 'Linq Shared',
    type: 'linq',
    status: 'connected',
    ownershipKind: 'shared',
    customerId: null,
    agentId: 'agent_coke',
    config: {
      fromNumber: '+13213108456',
      webhookToken: 'secret-token',
      webhookSubscriptionId: 'sub_1',
      signingSecret: 'signing-secret',
    },
    createdAt: new Date('2026-04-28T11:30:00.000Z'),
    updatedAt: new Date('2026-04-28T11:40:00.000Z'),
    agent: { id: 'agent_coke', slug: 'coke', name: 'Coke' },
  });
  db.channel.update.mockResolvedValueOnce({
    id: 'ch_linq',
    name: 'Linq Shared',
    type: 'linq',
    status: 'disconnected',
    ownershipKind: 'shared',
    customerId: null,
    agentId: 'agent_coke',
    config: { fromNumber: '+13213108456', webhookToken: 'secret-token' },
    createdAt: new Date('2026-04-28T11:30:00.000Z'),
    updatedAt: new Date('2026-04-28T11:40:00.000Z'),
    agent: { id: 'agent_coke', slug: 'coke', name: 'Coke' },
  });

  const res = await app.request('/api/admin/shared-channels/ch_linq/disconnect', { method: 'POST' });

  expect(res.status).toBe(200);
  expect(deleteWebhookSubscription).toHaveBeenCalledWith('sub_1');
  expect(db.channel.update).toHaveBeenCalledWith({
    where: { id: 'ch_linq' },
    data: {
      status: 'disconnected',
      config: { fromNumber: '+13213108456', webhookToken: 'secret-token' },
    },
    select: expect.any(Object),
  });
});
```

- [ ] **Step 6: Run lifecycle tests and verify RED**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/routes/admin-shared-channels.test.ts -t "linq"
```

Expected: FAIL on patch/connect/disconnect behavior.

- [ ] **Step 7: Implement Linq lifecycle**

In `gateway/packages/api/src/routes/admin-shared-channels.ts`:

1. Add webhook URL helper:

```ts
function buildLinqWebhookUrl(channelId: string, webhookToken: string): string {
  return `${getGatewayPublicBaseUrl()}/gateway/linq/${channelId}/${webhookToken}`;
}
```

2. In `PATCH`, branch for `existing.type === 'linq'`:

```ts
if ('webhookToken' in parsedBody.data.config || 'signingSecret' in parsedBody.data.config) {
  return c.json({ ok: false, error: 'linq_secret_not_mutable' }, 400);
}
const parsedConfig = parseLinqConfigInput(parsedBody.data.config);
if (!parsedConfig.ok) return c.json(parsedConfig.response, 400);
const storedConfig = ensureStoredLinqConfig(existing.config, randomUUID);
if (existing.status === 'connected' && parsedConfig.data.fromNumber !== storedConfig.fromNumber) {
  return c.json({ ok: false, error: 'linq_from_number_not_mutable_while_connected' }, 409);
}
config = buildStoredLinqConfig({
  fromNumber: parsedConfig.data.fromNumber,
  webhookToken: storedConfig.webhookToken!,
  webhookSubscriptionId: storedConfig.webhookSubscriptionId,
  signingSecret: storedConfig.signingSecret,
});
```

3. In connect route, allow `linq` as supported and add Linq branch before the Evolution branch:

```ts
if (existing.type === 'linq') {
  if (existing.status === 'connected') {
    return c.json({ ok: true, data: serializeSharedChannel(existing as never, { includeConfig: true }) });
  }
  const config = ensureStoredLinqConfig(existing.config, randomUUID);
  const client = new LinqApiClient();
  let subscription;
  try {
    subscription = await client.createWebhookSubscription({
      targetUrl: buildLinqWebhookUrl(existing.id, config.webhookToken!),
      phoneNumbers: [config.fromNumber],
    });
  } catch {
    return c.json({ ok: false, error: 'linq_webhook_register_failed' }, 502);
  }
  try {
    const updated = await db.channel.update({
      where: { id: existing.id },
      data: {
        status: 'connected',
        config: buildStoredLinqConfig({
          fromNumber: config.fromNumber,
          webhookToken: config.webhookToken!,
          webhookSubscriptionId: subscription.id,
          signingSecret: subscription.signingSecret,
        }),
      },
      select: sharedChannelSelect,
    });
    return c.json({ ok: true, data: serializeSharedChannel(updated as never, { includeConfig: true }) });
  } catch (error) {
    await client.deleteWebhookSubscription(subscription.id).catch((rollbackError) => {
      console.error('[shared-channel:linq] Failed to roll back webhook subscription:', rollbackError);
    });
    throw error;
  }
}
```

4. In disconnect/delete, add Linq branch that deletes `webhookSubscriptionId`, clears `signingSecret`, keeps `fromNumber` and `webhookToken`, and marks disconnected/archived.

- [ ] **Step 8: Verify lifecycle tests GREEN**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/routes/admin-shared-channels.test.ts -t "linq"
```

Expected: PASS.

- [ ] **Step 9: Write failing `/api/channels/:id` secret scrubbing test**

In `gateway/packages/api/src/routes/channels.test.ts`, add:

```ts
it('scrubs linq secrets from generic channel detail responses', async () => {
  mocks.findFirst.mockResolvedValueOnce({
    id: 'ch_linq',
    tenantId: 'tnt_1',
    type: 'linq',
    name: 'Linq Shared',
    status: 'connected',
    config: {
      fromNumber: '+13213108456',
      webhookToken: 'secret-token',
      webhookSubscriptionId: 'sub_1',
      signingSecret: 'signing-secret',
    },
  });

  const res = await app.request('/api/channels/ch_linq', {
    headers: { authorization: 'Bearer test-token' },
  });

  expect(res.status).toBe(200);
  await expect(res.json()).resolves.toEqual({
    ok: true,
    data: {
      id: 'ch_linq',
      tenantId: 'tnt_1',
      type: 'linq',
      name: 'Linq Shared',
      status: 'connected',
      config: {
        fromNumber: '+13213108456',
        webhookSubscriptionId: 'sub_1',
      },
      hasWebhookToken: true,
      hasSigningSecret: true,
    },
  });
});
```

- [ ] **Step 10: Run channels test and verify RED**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/routes/channels.test.ts -t "scrubs linq"
```

Expected: FAIL because generic detail returns raw config.

- [ ] **Step 11: Implement generic channel Linq create/patch/detail scrubbing**

In `gateway/packages/api/src/routes/channels.ts`:

1. Import Linq helpers.
2. Add `linq` to `CHANNEL_TYPES`.
3. In create, branch for `body.type === 'linq'`, using `LINQ_FROM_NUMBER` fallback and generated `webhookToken`.
4. In patch, reject Linq secret mutations and connected `fromNumber` changes.
5. In GET `/:id`, return serialized Linq config:

```ts
if (channel.type === 'linq') {
  return c.json({
    ok: true,
    data: {
      ...channel,
      config: buildPublicLinqConfig(channel.config),
      hasWebhookToken: hasLinqWebhookToken(channel.config),
      hasSigningSecret: hasLinqSigningSecret(channel.config),
    },
  });
}
```

- [ ] **Step 12: Verify admin API tests GREEN**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/routes/admin-shared-channels.test.ts \
  src/routes/channels.test.ts \
  src/routes/admin-channels.test.ts
```

Expected: PASS.

- [ ] **Step 13: Commit Task 3**

Run:

```bash
git -C gateway add \
  packages/api/src/routes/admin-shared-channels.ts \
  packages/api/src/routes/admin-shared-channels.test.ts \
  packages/api/src/routes/channels.ts \
  packages/api/src/routes/channels.test.ts
git -C gateway commit -m "feat(gateway): manage linq shared channels"
```

## Task 4: Add Linq Webhook Route And Outbound Delivery

**Files:**
- Modify: `gateway/packages/api/src/gateway/message-router.ts`
- Modify: `gateway/packages/api/src/gateway/message-router.test.ts`
- Modify: `gateway/packages/api/src/lib/outbound-delivery.ts`
- Modify: `gateway/packages/api/src/lib/outbound-delivery.test.ts`

- [ ] **Step 1: Write failing Linq webhook route tests**

In `gateway/packages/api/src/gateway/message-router.test.ts`:

1. Add imports:

```ts
import { createHmac } from 'node:crypto';
```

2. Add hoisted Linq mock:

```ts
const linqCreateChat = vi.hoisted(() => vi.fn());
vi.mock('../lib/linq-api.js', () => ({
  LinqApiClient: class {
    createChat = linqCreateChat;
  },
}));
```

3. Add helper:

```ts
function signLinqPayload(secret: string, timestamp: string, body: string): string {
  return createHmac('sha256', secret).update(`${timestamp}.${body}`).digest('hex');
}
```

4. Add tests:

```ts
describe('gatewayRouter linq route', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    db.channel.findUnique.mockResolvedValue({
      id: 'ch_linq',
      type: 'linq',
      status: 'connected',
      config: {
        fromNumber: '+13213108456',
        webhookToken: 'token_1',
        webhookSubscriptionId: 'sub_1',
        signingSecret: 'signing-secret',
      },
    });
    routeInboundMessage.mockResolvedValue(null);
    linqCreateChat.mockResolvedValue({ id: 'chat_reply' });
  });

  it('routes signed linq message.received webhooks into routeInboundMessage', async () => {
    const app = new Hono();
    app.route('/gateway', gatewayRouter);
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const body = JSON.stringify({
      event_type: 'message.received',
      event_id: 'evt_1',
      data: {
        chat: {
          id: 'chat_1',
          owner_handle: { handle: '+13213108456' },
        },
        id: 'msg_1',
        direction: 'inbound',
        sender_handle: { handle: '+86 152 017 80593' },
        parts: [{ type: 'text', value: 'hello from linq' }],
        service: 'iMessage',
      },
    });

    const res = await app.request('/gateway/linq/ch_linq/token_1', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-webhook-timestamp': timestamp,
        'x-webhook-signature': signLinqPayload('signing-secret', timestamp, body),
        'x-webhook-event': 'message.received',
        'x-webhook-subscription-id': 'sub_1',
      },
      body,
    });

    expect(res.status).toBe(200);
    await expect(res.json()).resolves.toEqual({ ok: true });
    expect(routeInboundMessage).toHaveBeenCalledWith({
      channelId: 'ch_linq',
      externalId: '+8615201780593',
      displayName: '+86 152 017 80593',
      text: 'hello from linq',
      meta: {
        platform: 'linq',
        eventId: 'evt_1',
        chatId: 'chat_1',
        messageId: 'msg_1',
        service: 'iMessage',
        ownerHandle: '+13213108456',
        webhookSubscriptionId: 'sub_1',
      },
    });
  });

  it('sends immediate linq replies to the inbound sender, not the owner handle', async () => {
    routeInboundMessage.mockResolvedValueOnce({
      conversationId: 'conv_1',
      replies: [{ backendId: null, backendName: 'Coke', reply: 'hello back' }],
      reply: 'hello back',
    });
    const app = new Hono();
    app.route('/gateway', gatewayRouter);
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const body = JSON.stringify({
      event_type: 'message.received',
      event_id: 'evt_reply',
      data: {
        chat: { id: 'chat_1', owner_handle: { handle: '+13213108456' } },
        id: 'msg_reply',
        direction: 'inbound',
        sender_handle: { handle: '+8615201780593' },
        parts: [{ type: 'text', value: 'ping' }],
        service: 'iMessage',
      },
    });

    const res = await app.request('/gateway/linq/ch_linq/token_1', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-webhook-timestamp': timestamp,
        'x-webhook-signature': signLinqPayload('signing-secret', timestamp, body),
        'x-webhook-event': 'message.received',
        'x-webhook-subscription-id': 'sub_1',
      },
      body,
    });

    expect(res.status).toBe(200);
    expect(linqCreateChat).toHaveBeenCalledWith({
      from: '+13213108456',
      to: ['+8615201780593'],
      text: 'hello back',
    });
  });

  it('rejects linq webhooks with missing connected-channel signing secrets', async () => {
    const app = new Hono();
    app.route('/gateway', gatewayRouter);
    db.channel.findUnique.mockResolvedValueOnce({
      id: 'ch_linq',
      type: 'linq',
      status: 'connected',
      config: { fromNumber: '+13213108456', webhookToken: 'token_1' },
    });

    const res = await app.request('/gateway/linq/ch_linq/token_1', {
      method: 'POST',
      body: '{}',
    });

    expect(res.status).toBe(403);
    expect(routeInboundMessage).not.toHaveBeenCalled();
  });

  it('rejects stale linq webhook timestamps and bad signatures', async () => {
    const app = new Hono();
    app.route('/gateway', gatewayRouter);
    const staleTimestamp = String(Math.floor(Date.now() / 1000) - 600);
    const body = JSON.stringify({ event_type: 'message.received', data: {} });

    const stale = await app.request('/gateway/linq/ch_linq/token_1', {
      method: 'POST',
      headers: {
        'x-webhook-timestamp': staleTimestamp,
        'x-webhook-signature': signLinqPayload('signing-secret', staleTimestamp, body),
        'x-webhook-subscription-id': 'sub_1',
      },
      body,
    });
    expect(stale.status).toBe(403);

    const freshTimestamp = Math.floor(Date.now() / 1000).toString();
    const bad = await app.request('/gateway/linq/ch_linq/token_1', {
      method: 'POST',
      headers: {
        'x-webhook-timestamp': freshTimestamp,
        'x-webhook-signature': 'bad-signature',
        'x-webhook-subscription-id': 'sub_1',
      },
      body,
    });
    expect(bad.status).toBe(403);
  });
});
```

- [ ] **Step 2: Run Linq webhook tests and verify RED**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/gateway/message-router.test.ts -t "linq"
```

Expected: FAIL because `/gateway/linq/:channelId/:token` does not exist.

- [ ] **Step 3: Implement Linq webhook route**

In `gateway/packages/api/src/gateway/message-router.ts`:

1. Import crypto and Linq helpers:

```ts
import { createHmac, timingSafeEqual } from 'node:crypto';
import { LinqApiClient } from '../lib/linq-api.js';
import { normalizeLinqPhoneNumber, parseStoredLinqConfig } from '../lib/linq-config.js';
```

2. Add helpers:

```ts
const LINQ_REPLAY_WINDOW_SECONDS = 300;

function verifyLinqSignature(secret: string, rawBody: string, timestamp: string, signature: string): boolean {
  const timestampSeconds = Number.parseInt(timestamp, 10);
  if (!Number.isFinite(timestampSeconds)) return false;
  const nowSeconds = Math.floor(Date.now() / 1000);
  if (Math.abs(nowSeconds - timestampSeconds) > LINQ_REPLAY_WINDOW_SECONDS) return false;
  const expected = createHmac('sha256', secret).update(`${timestamp}.${rawBody}`).digest('hex');
  try {
    const expectedBuffer = Buffer.from(expected, 'hex');
    const signatureBuffer = Buffer.from(signature, 'hex');
    return expectedBuffer.length === signatureBuffer.length &&
      timingSafeEqual(expectedBuffer, signatureBuffer);
  } catch {
    return false;
  }
}

function readLinqTextParts(parts: unknown): string | null {
  if (!Array.isArray(parts)) return null;
  const text = parts
    .filter((part): part is { type: string; value: string } =>
      Boolean(part) &&
      typeof part === 'object' &&
      (part as Record<string, unknown>)['type'] === 'text' &&
      typeof (part as Record<string, unknown>)['value'] === 'string',
    )
    .map((part) => part.value.trim())
    .filter(Boolean)
    .join('\n');
  return text || null;
}
```

3. Add route before LINE route:

```ts
.post('/linq/:channelId/:token', async (c) => {
  const channelId = c.req.param('channelId');
  const token = c.req.param('token');
  const channel = await db.channel.findUnique({
    where: { id: channelId },
    select: { id: true, type: true, status: true, config: true },
  });
  if (!channel || channel.type !== 'linq' || channel.status !== 'connected') {
    return c.json({ ok: false, error: 'Channel not found or not connected' }, 404);
  }

  let config;
  try {
    config = parseStoredLinqConfig(channel.config);
  } catch {
    return c.json({ ok: false, error: 'Forbidden' }, 403);
  }
  if (
    !config.webhookToken ||
    !config.webhookSubscriptionId ||
    !config.signingSecret ||
    token !== config.webhookToken
  ) {
    return c.json({ ok: false, error: 'Forbidden' }, 403);
  }

  const timestamp = c.req.header('x-webhook-timestamp') ?? '';
  const signature = c.req.header('x-webhook-signature') ?? '';
  const subscriptionId = c.req.header('x-webhook-subscription-id') ?? '';
  const rawBody = await c.req.text();
  if (
    subscriptionId !== config.webhookSubscriptionId ||
    !timestamp ||
    !signature ||
    !verifyLinqSignature(config.signingSecret, rawBody, timestamp, signature)
  ) {
    return c.json({ ok: false, error: 'Forbidden' }, 403);
  }

  let body: Record<string, unknown>;
  try {
    body = JSON.parse(rawBody) as Record<string, unknown>;
  } catch {
    return c.json({ ok: true });
  }
  if (body['event_type'] !== 'message.received') {
    return c.json({ ok: true });
  }

  const data = body['data'];
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    return c.json({ ok: true });
  }
  const record = data as Record<string, unknown>;
  if (record['direction'] === 'outbound' || record['is_from_me'] === true) {
    return c.json({ ok: true });
  }

  const chat = record['chat'] && typeof record['chat'] === 'object'
    ? record['chat'] as Record<string, unknown>
    : null;
  const ownerHandleRecord = chat?.['owner_handle'] && typeof chat['owner_handle'] === 'object'
    ? chat['owner_handle'] as Record<string, unknown>
    : null;
  const senderHandleRecord = record['sender_handle'] && typeof record['sender_handle'] === 'object'
    ? record['sender_handle'] as Record<string, unknown>
    : null;
  const legacyFromHandleRecord = record['from_handle'] && typeof record['from_handle'] === 'object'
    ? record['from_handle'] as Record<string, unknown>
    : null;

  const senderHandle =
    typeof senderHandleRecord?.['handle'] === 'string'
      ? senderHandleRecord['handle']
      : typeof legacyFromHandleRecord?.['handle'] === 'string'
        ? legacyFromHandleRecord['handle']
        : typeof record['from'] === 'string'
          ? record['from']
          : '';
  if (!senderHandle) {
    return c.json({ ok: true });
  }

  const message = record['message'] && typeof record['message'] === 'object'
    ? record['message'] as Record<string, unknown>
    : null;
  const text = readLinqTextParts(record['parts'] ?? message?.['parts']);
  if (!text) {
    return c.json({ ok: true });
  }

  const normalizedSender = normalizeLinqPhoneNumber(senderHandle);
  const result = await routeInboundMessage({
    channelId,
    externalId: normalizedSender,
    displayName: senderHandle,
    text,
    meta: {
      platform: 'linq',
      eventId: typeof body['event_id'] === 'string' ? body['event_id'] : undefined,
      chatId: typeof chat?.['id'] === 'string' ? chat['id'] : typeof record['chat_id'] === 'string' ? record['chat_id'] : undefined,
      messageId: typeof record['id'] === 'string' ? record['id'] : typeof message?.['id'] === 'string' ? message['id'] : undefined,
      service: typeof record['service'] === 'string' ? record['service'] : undefined,
      ownerHandle: typeof ownerHandleRecord?.['handle'] === 'string' ? ownerHandleRecord['handle'] : undefined,
      webhookSubscriptionId: config.webhookSubscriptionId,
    },
  });

  if (result?.reply) {
    await new LinqApiClient().createChat({
      from: config.fromNumber,
      to: [normalizedSender],
      text: result.reply,
    });
  }

  return c.json({ ok: true });
})
```

- [ ] **Step 4: Verify webhook tests GREEN**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/gateway/message-router.test.ts -t "linq"
```

Expected: PASS.

- [ ] **Step 5: Write failing outbound delivery test**

In `gateway/packages/api/src/lib/outbound-delivery.test.ts`, add Linq mock:

```ts
const createChat = vi.hoisted(() => vi.fn());
vi.mock('./linq-api.js', () => ({
  LinqApiClient: vi.fn().mockImplementation(() => ({
    createChat,
  })),
}));
```

Add test:

```ts
it('delivers linq messages by creating a chat from the configured virtual number', async () => {
  createChat.mockResolvedValueOnce({ id: 'chat_1' });

  await deliverOutboundMessage(
    {
      id: 'ch_linq_1',
      type: 'linq',
      status: 'connected',
      config: {
        fromNumber: '+13213108456',
        webhookToken: 'secret-token',
        webhookSubscriptionId: 'sub_1',
        signingSecret: 'signing-secret',
      },
    },
    '+86 152 017 80593',
    'hello from coke',
  );

  expect(createChat).toHaveBeenCalledWith({
    from: '+13213108456',
    to: ['+8615201780593'],
    text: 'hello from coke',
  });
  expect(sendWeixinText).not.toHaveBeenCalled();
  expect(sendText).not.toHaveBeenCalled();
});
```

- [ ] **Step 6: Run outbound test and verify RED**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/outbound-delivery.test.ts -t "linq"
```

Expected: FAIL because `linq` is unsupported.

- [ ] **Step 7: Implement Linq outbound delivery**

In `gateway/packages/api/src/lib/outbound-delivery.ts`:

1. Import:

```ts
import { LinqApiClient } from './linq-api.js';
import { normalizeLinqPhoneNumber, parseStoredLinqConfig } from './linq-config.js';
```

2. Add switch branch:

```ts
case 'linq': {
  const config = parseStoredLinqConfig(channel.config);
  await new LinqApiClient().createChat({
    from: config.fromNumber,
    to: [normalizeLinqPhoneNumber(externalEndUserId)],
    text,
  });
  return;
}
```

- [ ] **Step 8: Verify webhook and outbound tests GREEN**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/gateway/message-router.test.ts \
  src/lib/outbound-delivery.test.ts
```

Expected: PASS.

- [ ] **Step 9: Commit Task 4**

Run:

```bash
git -C gateway add \
  packages/api/src/gateway/message-router.ts \
  packages/api/src/gateway/message-router.test.ts \
  packages/api/src/lib/outbound-delivery.ts \
  packages/api/src/lib/outbound-delivery.test.ts
git -C gateway commit -m "feat(gateway): route linq messages"
```

## Task 5: Add Linq Admin Web UI

**Files:**
- Modify: `gateway/packages/web/app/(admin)/admin/shared-channels/page.tsx`
- Modify: `gateway/packages/web/app/(admin)/admin/shared-channels/page.test.tsx`
- Modify: `gateway/packages/web/app/(admin)/admin/shared-channels/detail/page.tsx`
- Modify: `gateway/packages/web/app/(admin)/admin/shared-channels/detail/page.test.tsx`
- Modify: `gateway/packages/web/lib/admin-copy.ts`
- Modify: `gateway/packages/web/lib/admin-api.ts`

- [ ] **Step 1: Write failing create-page Linq test**

In `gateway/packages/web/app/(admin)/admin/shared-channels/page.test.tsx`, add:

```tsx
it('creates linq shared channels with typed fromNumber config', async () => {
  vi.mocked(adminApi.post).mockResolvedValueOnce({
    ok: true,
    data: {
      id: 'ch_linq',
      name: 'Linq Shared',
      kind: 'linq',
      status: 'disconnected',
      ownershipKind: 'shared',
      customerId: null,
      agent: { id: 'agent_coke', slug: 'coke', name: 'Coke' },
      config: { fromNumber: '+13213108456' },
      hasWebhookToken: true,
      hasSigningSecret: false,
      createdAt: '2026-04-28T11:00:00.000Z',
      updatedAt: '2026-04-28T11:00:00.000Z',
    },
  });

  flushSync(() => {
    root.render(
      <LocaleProvider initialLocale="en">
        <AdminSharedChannelsPage />
      </LocaleProvider>,
    );
  });

  await vi.waitFor(() => expect(container.textContent).toContain('Shared channels'));
  (container.querySelector('button[data-testid="open-create-shared-channel"]') as HTMLButtonElement).click();
  await waitForEffects();

  const kindInput = container.querySelector('#shared-channel-kind') as HTMLSelectElement;
  kindInput.value = 'linq';
  kindInput.dispatchEvent(new Event('change', { bubbles: true }));

  await vi.waitFor(() => {
    expect(container.querySelector('#shared-channel-from-number')).toBeTruthy();
    expect(container.querySelector('#shared-channel-config')).toBeNull();
  });

  const nameInput = container.querySelector('#shared-channel-name') as HTMLInputElement;
  const fromNumberInput = container.querySelector('#shared-channel-from-number') as HTMLInputElement;
  const agentInput = container.querySelector('#shared-channel-agent-id') as HTMLInputElement;
  nameInput.value = 'Linq Shared';
  nameInput.dispatchEvent(new Event('input', { bubbles: true }));
  fromNumberInput.value = '+1 (321) 310-8456';
  fromNumberInput.dispatchEvent(new Event('input', { bubbles: true }));
  agentInput.value = 'agent_coke';
  agentInput.dispatchEvent(new Event('input', { bubbles: true }));

  container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  await waitForEffects();

  expect(vi.mocked(adminApi.post)).toHaveBeenCalledWith('/api/admin/shared-channels', {
    name: 'Linq Shared',
    kind: 'linq',
    agentId: 'agent_coke',
    config: { fromNumber: '+1 (321) 310-8456' },
  });
  expect(pushMock).toHaveBeenCalledWith('/admin/shared-channels/detail?id=ch_linq');
});
```

- [ ] **Step 2: Run create-page test and verify RED**

Run:

```bash
pnpm --dir gateway/packages/web test -- 'app/(admin)/admin/shared-channels/page.test.tsx' -t "linq"
```

Expected: FAIL because the UI has no Linq typed mode.

- [ ] **Step 3: Implement create-page Linq UI**

In `gateway/packages/web/app/(admin)/admin/shared-channels/page.tsx`:

1. Add constants:

```ts
const LINQ_KIND = 'linq';
function isLinqKind(kind: string): boolean {
  return kind === LINQ_KIND;
}
```

2. Add state:

```ts
const [fromNumber, setFromNumber] = useState('');
```

3. In submit:

```ts
const nextFromNumber = String(form.get('fromNumber') ?? '').trim();
config: isWhatsAppEvolutionKind(nextKind)
  ? { instanceName: nextInstanceName }
  : isLinqKind(nextKind)
    ? { fromNumber: nextFromNumber }
    : parseConfig(nextConfigText),
```

4. Add `<option value="linq">linq</option>`.

5. Add the mode boolean near `evolutionCreateMode`:

```ts
const linqCreateMode = isLinqKind(kind);
```

6. Replace typed config conditional with:

```tsx
{evolutionCreateMode ? (
  <div>
    <label htmlFor="shared-channel-instance-name" className="label">
      {copy.sharedChannels.fields.instanceName}
    </label>
    <input
      id="shared-channel-instance-name"
      name="instanceName"
      className="input"
      value={instanceName}
      onInput={(event) => setInstanceName(event.currentTarget.value)}
      required
    />
    <p className="mt-2 text-xs text-gray-500">{copy.sharedChannels.instanceNameHelp}</p>
  </div>
) : linqCreateMode ? (
  <div>
    <label htmlFor="shared-channel-from-number" className="label">
      {copy.sharedChannels.fields.fromNumber}
    </label>
    <input
      id="shared-channel-from-number"
      name="fromNumber"
      className="input"
      value={fromNumber}
      onInput={(event) => setFromNumber(event.currentTarget.value)}
      placeholder="+13213108456"
    />
    <p className="mt-2 text-xs text-gray-500">{copy.sharedChannels.fromNumberHelp}</p>
  </div>
) : (
  <div>
    <label htmlFor="shared-channel-config" className="label">
      {copy.sharedChannels.fields.config}
    </label>
    <textarea
      id="shared-channel-config"
      name="config"
      className="input min-h-[120px]"
      value={configText}
      onInput={(event) => setConfigText(event.currentTarget.value)}
    />
  </div>
)}
```

- [ ] **Step 4: Verify create-page test GREEN**

Run:

```bash
pnpm --dir gateway/packages/web test -- 'app/(admin)/admin/shared-channels/page.test.tsx' -t "linq"
```

Expected: PASS.

- [ ] **Step 5: Write failing detail-page Linq test**

In `gateway/packages/web/app/(admin)/admin/shared-channels/detail/page.test.tsx`, add:

```tsx
it('shows typed linq config, hidden secret indicators, and connect/disconnect actions', async () => {
  vi.mocked(adminApi.get).mockResolvedValueOnce({
    ok: true,
    data: {
      id: 'ch_linq',
      name: 'Linq Shared',
      kind: 'linq',
      status: 'connected',
      ownershipKind: 'shared',
      customerId: null,
      agent: { id: 'agent_coke', slug: 'coke', name: 'Coke' },
      config: { fromNumber: '+13213108456', webhookSubscriptionId: 'sub_1' },
      hasWebhookToken: true,
      hasSigningSecret: true,
      createdAt: '2026-04-28T09:00:00.000Z',
      updatedAt: '2026-04-28T10:00:00.000Z',
    },
  });
  vi.mocked(adminApi.patch).mockResolvedValueOnce({
    ok: true,
    data: {
      id: 'ch_linq',
      name: 'Linq Shared',
      kind: 'linq',
      status: 'connected',
      ownershipKind: 'shared',
      customerId: null,
      agent: { id: 'agent_coke', slug: 'coke', name: 'Coke' },
      config: { fromNumber: '+13213108456', webhookSubscriptionId: 'sub_1' },
      hasWebhookToken: true,
      hasSigningSecret: true,
      createdAt: '2026-04-28T09:00:00.000Z',
      updatedAt: '2026-04-28T10:30:00.000Z',
    },
  });

  flushSync(() => {
    root.render(
      <LocaleProvider initialLocale="en">
        <AdminSharedChannelDetailPage />
      </LocaleProvider>,
    );
  });

  await vi.waitFor(() => {
    expect(container.textContent).toContain('Linq Shared');
    expect(container.textContent).toContain('Webhook token');
    expect(container.textContent).toContain('Signing secret');
    expect(container.querySelector('#shared-channel-detail-from-number')).toBeTruthy();
    expect(container.querySelector('#shared-channel-detail-config')).toBeNull();
    expect(container.querySelector('button[data-testid="disconnect-shared-channel"]')).toBeTruthy();
  });

  const fromNumberInput = container.querySelector('#shared-channel-detail-from-number') as HTMLInputElement;
  expect(fromNumberInput.disabled).toBe(true);

  (container.querySelector('button[data-testid="save-shared-channel"]') as HTMLButtonElement).click();
  await waitForEffects();

  expect(vi.mocked(adminApi.patch)).toHaveBeenCalledWith('/api/admin/shared-channels/ch_1', {
    name: 'Linq Shared',
    agentId: 'agent_coke',
    config: { fromNumber: '+13213108456' },
  });
});
```

- [ ] **Step 6: Run detail-page test and verify RED**

Run:

```bash
pnpm --dir gateway/packages/web test -- 'app/(admin)/admin/shared-channels/detail/page.test.tsx' -t "linq"
```

Expected: FAIL because detail page only has Evolution typed mode.

- [ ] **Step 7: Implement detail-page Linq UI**

In `gateway/packages/web/app/(admin)/admin/shared-channels/detail/page.tsx`:

1. Add Linq constants/helpers:

```ts
const LINQ_KIND = 'linq';
function isLinqKind(kind: string): boolean {
  return kind === LINQ_KIND;
}
function getLinqFromNumber(config: Record<string, unknown>): string {
  return typeof config.fromNumber === 'string' ? config.fromNumber : '';
}
```

2. Add state:

```ts
const [fromNumber, setFromNumber] = useState('');
```

3. In load/sync functions, set `fromNumber` for Linq records:

```ts
if (isWhatsAppEvolutionKind(nextRecord.kind)) {
  setInstanceName(getEvolutionInstanceName(nextRecord.config));
} else if (isLinqKind(nextRecord.kind)) {
  setFromNumber(getLinqFromNumber(nextRecord.config));
} else {
  setConfigText(JSON.stringify(nextRecord.config ?? {}, null, 2));
}
```

4. In save, send:

```ts
const nextFromNumber = isLinqKind(record.kind)
  ? String(form.get('fromNumber') ?? '').trim() || fromNumber.trim() || getLinqFromNumber(record.config)
  : '';
config: isWhatsAppEvolutionKind(record.kind)
  ? { instanceName: nextInstanceName }
  : isLinqKind(record.kind)
    ? { fromNumber: nextFromNumber }
    : parseConfig(nextConfigText),
```

5. Allow `handleConnect()` and `handleDisconnect()` for Evolution or Linq:

```ts
const managedLifecycleChannel = record
  ? isWhatsAppEvolutionKind(record.kind) || isLinqKind(record.kind)
  : false;
```

Use `managedLifecycleChannel` in both handlers instead of only checking
`isWhatsAppEvolutionKind(record.kind)`.

6. Render Linq typed panel with this JSX branch before the raw JSON textarea:

```tsx
{linqChannel ? (
  <>
    <div>
      <label htmlFor="shared-channel-detail-from-number" className="label">
        {copy.sharedChannels.fields.fromNumber}
      </label>
      <input
        id="shared-channel-detail-from-number"
        name="fromNumber"
        className="input"
        value={fromNumber}
        onInput={(event) => setFromNumber(event.currentTarget.value)}
        disabled={record.status === 'connected'}
      />
      <p className="mt-2 text-xs text-gray-500">
        {record.status === 'connected' ? copy.sharedChannels.fromNumberLocked : copy.sharedChannels.fromNumberHelp}
      </p>
    </div>
    <div className="grid gap-4 md:grid-cols-3">
      <div>
        <p className="text-sm font-medium text-gray-500">{copy.sharedChannels.fields.webhookSubscriptionId}</p>
        <p className="mt-1 text-base text-gray-900">
          {typeof record.config.webhookSubscriptionId === 'string' ? record.config.webhookSubscriptionId : '-'}
        </p>
      </div>
      <div>
        <p className="text-sm font-medium text-gray-500">{copy.sharedChannels.fields.webhookToken}</p>
        <p className="mt-1 text-base text-gray-900">
          {record.hasWebhookToken ? copy.sharedChannels.webhookTokenHidden : '-'}
        </p>
      </div>
      <div>
        <p className="text-sm font-medium text-gray-500">{copy.sharedChannels.fields.signingSecret}</p>
        <p className="mt-1 text-base text-gray-900">
          {record.hasSigningSecret ? copy.sharedChannels.signingSecretHidden : '-'}
        </p>
      </div>
    </div>
  </>
) : null}
```

- [ ] **Step 8: Add admin copy**

In both English and Chinese sections of `gateway/packages/web/lib/admin-copy.ts`, add fields:

```ts
fromNumber: 'From number',
signingSecret: 'Signing secret',
webhookSubscriptionId: 'Webhook subscription',
```

Add messages:

```ts
fromNumberHelp: 'Defaults to LINQ_FROM_NUMBER when left blank.',
fromNumberLocked: 'Disconnect before changing the Linq sender number.',
signingSecretHidden: 'Hidden and managed server-side.',
```

Use these Chinese values in the zh section:

```ts
fromNumber: '发送号码',
signingSecret: '签名密钥',
webhookSubscriptionId: 'Webhook 订阅',
fromNumberHelp: '留空时使用 LINQ_FROM_NUMBER。',
fromNumberLocked: '断开 Linq 通道后才能修改发送号码。',
signingSecretHidden: '已隐藏，由服务器端管理。',
```

- [ ] **Step 9: Verify web tests GREEN**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  'app/(admin)/admin/shared-channels/page.test.tsx' \
  'app/(admin)/admin/shared-channels/detail/page.test.tsx'
```

Expected: PASS.

- [ ] **Step 10: Commit Task 5**

Run:

```bash
git -C gateway add \
  'packages/web/app/(admin)/admin/shared-channels/page.tsx' \
  'packages/web/app/(admin)/admin/shared-channels/page.test.tsx' \
  'packages/web/app/(admin)/admin/shared-channels/detail/page.tsx' \
  'packages/web/app/(admin)/admin/shared-channels/detail/page.test.tsx' \
  packages/web/lib/admin-copy.ts \
  packages/web/lib/admin-api.ts
git -C gateway commit -m "feat(web): manage linq shared channels"
```

## Task 6: Add Local Env And Final Verification

**Files:**
- Modify: `.env`

- [ ] **Step 1: Add Linq local env values**

Append or update these keys in `.env`:

```env
LINQ_API_KEY=826ecb12-ec88-58a5-a08e-c203d955a1ce
LINQ_API_BASE_URL=https://api.linqapp.com/api/partner/v3
LINQ_FROM_NUMBER=+13213108456
```

Do not commit `.env` if it is ignored or contains secrets. If `.env` is tracked,
stage only if the user explicitly confirms committing secrets; otherwise leave it
as a local working-tree change.

- [ ] **Step 2: Run focused API verification**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/linq-api.test.ts \
  src/lib/linq-config.test.ts \
  src/lib/external-identity.test.ts \
  src/lib/route-message.test.ts \
  src/lib/outbound-delivery.test.ts \
  src/gateway/message-router.test.ts \
  src/routes/admin-shared-channels.test.ts \
  src/routes/channels.test.ts \
  src/routes/admin-channels.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run focused web verification**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  'app/(admin)/admin/shared-channels/page.test.tsx' \
  'app/(admin)/admin/shared-channels/detail/page.test.tsx'
```

Expected: PASS.

- [ ] **Step 4: Run broad gateway API verification if focused tests pass**

Run:

```bash
pnpm --dir gateway/packages/api test
```

Expected: PASS.

- [ ] **Step 5: Run broad gateway web verification if focused tests pass**

Run:

```bash
pnpm --dir gateway/packages/web test
```

Expected: PASS.

- [ ] **Step 6: Review diffs**

Run:

```bash
git -C gateway status --short
git -C gateway diff --stat HEAD
git -C gateway log --oneline -6
git status --short
```

Expected:

- gateway has committed task changes
- root repo shows the gateway submodule pointer changed
- `.env` may be modified locally and should not be committed without explicit approval

- [ ] **Step 7: Commit root submodule pointer if gateway commits are ready**

Run:

```bash
git add gateway
git commit -m "feat: add linq shared channel adapter"
```

Expected: root repo records the gateway submodule update only. Do not include `.env` in this commit unless the user explicitly approves committing the secret-bearing file.
