# Evolution-Backed Shared WhatsApp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Evolution-backed shared WhatsApp channel to ClawScale so the existing `coke-whatsapp-personal` instance can auto-provision one Coke customer per sender and support both immediate replies and proactive outbound delivery.

**Architecture:** Introduce a new `whatsapp_evolution` shared-channel kind in gateway, add an Evolution control/delivery client plus a dedicated inbound webhook route, then extend the shared-channel admin surface with secret-safe config handling and explicit connect/disconnect lifecycle actions. Keep Coke bridge and the exact `DeliveryRoute` model unchanged; the new adapter plugs into the existing `routeInboundMessage()` and `/api/outbound` seams.

**Tech Stack:** Hono, Prisma/Postgres, Next.js, Vitest, Node fetch, existing ClawScale shared-channel runtime, existing Evolution API instance on `gcp-coke`.

---

### Task 1: Add the `whatsapp_evolution` channel kind and normalization foundation

**Files:**
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Create: `gateway/packages/api/prisma/migrations/20260419190000_whatsapp_evolution_shared_channel/migration.sql`
- Modify: `gateway/packages/shared/src/types/channel.ts`
- Modify: `gateway/packages/api/src/lib/external-identity.ts`
- Modify: `gateway/packages/api/src/lib/route-message.ts`
- Modify: `gateway/packages/api/src/routes/admin-shared-channels.ts`
- Modify: `gateway/packages/api/src/routes/admin-channels.ts`
- Modify: `gateway/packages/api/src/routes/channels.ts`
- Test: `gateway/packages/api/src/lib/external-identity.test.ts`
- Test: `gateway/packages/api/src/lib/route-message.test.ts`
- Test: `gateway/packages/api/src/routes/admin-shared-channels.test.ts`

- [ ] **Step 1: Write failing tests for the new kind and provider normalization**

Add assertions to the existing tests so they fail before implementation:

```ts
// gateway/packages/api/src/lib/external-identity.test.ts
it('normalizes whatsapp_evolution wa_id values to digits only', () => {
  expect(
    normalizeExternalIdentity({
      provider: 'whatsapp_evolution',
      identityType: 'wa_id',
      rawValue: '8619917902815@s.whatsapp.net',
    }),
  ).toEqual({
    provider: 'whatsapp_evolution',
    identityType: 'wa_id',
    identityValue: '8619917902815',
  });
});
```

```ts
// gateway/packages/api/src/lib/route-message.test.ts
it('derives wa_id identityType for whatsapp_evolution shared channels', async () => {
  // channel.type = 'whatsapp_evolution'
  // expect provisionSharedChannelCustomer to be called with identityType: 'wa_id'
  // and provider: 'whatsapp_evolution'
});
```

```ts
// gateway/packages/api/src/routes/admin-shared-channels.test.ts
it('accepts whatsapp_evolution as a shared channel kind', async () => {
  // POST /api/admin/shared-channels with kind: 'whatsapp_evolution'
  // expect 201 and kind echoed back
});
```

- [ ] **Step 2: Run targeted tests to confirm the new assertions fail**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/external-identity.test.ts \
  src/lib/route-message.test.ts \
  src/routes/admin-shared-channels.test.ts
```

Expected: failures mentioning unknown provider handling or enum validation rejecting `whatsapp_evolution`.

- [ ] **Step 3: Add the new channel kind across schema and validation surfaces**

Apply the new enum value consistently:

```prisma
// gateway/packages/api/prisma/schema.prisma
enum ChannelType {
  whatsapp
  whatsapp_business
  whatsapp_evolution
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
  wechat_personal
}
```

```sql
-- gateway/packages/api/prisma/migrations/20260419190000_whatsapp_evolution_shared_channel/migration.sql
ALTER TYPE "ChannelType" ADD VALUE IF NOT EXISTS 'whatsapp_evolution';
```

```ts
// gateway/packages/shared/src/types/channel.ts
export type ChannelType =
  | 'whatsapp'
  | 'whatsapp_business'
  | 'whatsapp_evolution'
  | 'telegram'
  | 'slack'
  | 'discord'
  | 'instagram'
  | 'facebook'
  | 'line'
  | 'signal'
  | 'teams'
  | 'matrix'
  | 'web'
  | 'wechat_work'
  | 'wechat_personal';
```

- [ ] **Step 4: Extend WhatsApp-family normalization and shared-channel routing**

Update the shared helpers so the new kind behaves exactly like the other
WhatsApp-family providers for identity purposes:

```ts
// gateway/packages/api/src/lib/external-identity.ts
const WHATSAPP_PROVIDERS = new Set([
  'whatsapp',
  'whatsapp_business',
  'whatsapp_evolution',
]);
```

```ts
// gateway/packages/api/src/lib/route-message.ts
const identityType =
  platform === 'whatsapp' ||
  platform === 'whatsapp_business' ||
  platform === 'whatsapp_evolution'
    ? 'wa_id'
    : 'external_id';
```

Also extend the validation lists in `admin-shared-channels.ts`,
`admin-channels.ts`, and `channels.ts` to include `whatsapp_evolution`.

- [ ] **Step 5: Re-run the focused tests and one wider route regression slice**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/external-identity.test.ts \
  src/lib/route-message.test.ts \
  src/routes/admin-shared-channels.test.ts \
  src/routes/channels.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add \
  gateway/packages/api/prisma/schema.prisma \
  gateway/packages/api/prisma/migrations/20260419190000_whatsapp_evolution_shared_channel/migration.sql \
  gateway/packages/shared/src/types/channel.ts \
  gateway/packages/api/src/lib/external-identity.ts \
  gateway/packages/api/src/lib/route-message.ts \
  gateway/packages/api/src/routes/admin-shared-channels.ts \
  gateway/packages/api/src/routes/admin-channels.ts \
  gateway/packages/api/src/routes/channels.ts \
  gateway/packages/api/src/lib/external-identity.test.ts \
  gateway/packages/api/src/lib/route-message.test.ts \
  gateway/packages/api/src/routes/admin-shared-channels.test.ts

git commit -m "feat(gateway): add whatsapp evolution channel kind"
```

### Task 2: Add the Evolution API client and inbound webhook adapter

**Files:**
- Create: `gateway/packages/api/src/lib/evolution-api.ts`
- Create: `gateway/packages/api/src/lib/evolution-api.test.ts`
- Modify: `gateway/packages/api/src/gateway/message-router.ts`
- Create: `gateway/packages/api/src/gateway/message-router.test.ts`
- Modify: `gateway/packages/api/src/index.ts`
- Test: `gateway/packages/api/src/lib/route-message.test.ts`

- [ ] **Step 1: Write failing tests for Evolution client calls and inbound webhook routing**

Create a dedicated client test file and a message-router test file:

```ts
// gateway/packages/api/src/lib/evolution-api.test.ts
it('sets instance webhook with MESSAGES_UPSERT only', async () => {
  // mock fetch and expect POST /webhook/set/{instance}
});

it('sends plain text through /message/sendText/{instance}', async () => {
  // expect body { number, text }
});
```

```ts
// gateway/packages/api/src/gateway/message-router.test.ts
it('routes whatsapp_evolution inbound messages into routeInboundMessage', async () => {
  // POST /gateway/evolution/whatsapp/ch_1/token_1
  // expect routeInboundMessage called with platform whatsapp_evolution
});

it('ignores fromMe=true payloads with 200', async () => {
  // expect routeInboundMessage not called
});
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/evolution-api.test.ts \
  src/gateway/message-router.test.ts
```

Expected: missing-module failures or route assertions failing because the route does not exist yet.

- [ ] **Step 3: Implement a focused Evolution client**

Create a small wrapper over `fetch`:

```ts
// gateway/packages/api/src/lib/evolution-api.ts
export interface EvolutionWebhookConfig {
  enabled: boolean;
  url: string;
  events: string[];
}

export class EvolutionApiClient {
  constructor(
    private readonly baseUrl = process.env['EVOLUTION_API_BASE_URL'] ?? '',
    private readonly apiKey = process.env['EVOLUTION_API_KEY'] ?? '',
  ) {}

  async setWebhook(instanceName: string, url: string) {
    return this.request(`/webhook/set/${instanceName}`, {
      method: 'POST',
      body: JSON.stringify({
        url,
        events: ['MESSAGES_UPSERT'],
        webhook_by_events: false,
        webhook_base64: false,
      }),
    });
  }

  async clearWebhook(instanceName: string) {
    return this.request(`/webhook/set/${instanceName}`, {
      method: 'POST',
      body: JSON.stringify({
        enabled: false,
        url: 'https://invalid.local/disabled',
        events: ['MESSAGES_UPSERT'],
        webhook_by_events: false,
        webhook_base64: false,
      }),
    });
  }

  async sendText(instanceName: string, number: string, text: string) {
    return this.request(`/message/sendText/${instanceName}`, {
      method: 'POST',
      body: JSON.stringify({ number, text }),
    });
  }

  private async request(path: string, init: RequestInit) {
    // validate env, set apikey header, set timeout, parse non-2xx bodies
  }
}
```

- [ ] **Step 4: Implement the Evolution inbound gateway route**

Add a route branch in `message-router.ts` that:

```ts
// gateway/packages/api/src/gateway/message-router.ts
.post('/evolution/whatsapp/:channelId/:token', async (c) => {
  const channelId = c.req.param('channelId');
  const token = c.req.param('token');
  const body = await c.req.json();

  // load channel, confirm kind/status/token
  // parse body.data.key.remoteJid, body.data.key.fromMe, body.data.pushName
  // extract text from conversation / extendedTextMessage.text
  // ignore unsupported payloads with 200
  // await routeInboundMessage({ ... meta.platform = 'whatsapp_evolution' })

  return c.json({ ok: true });
})
```

Add a small local parser/helper inside `message-router.ts` or a dedicated helper
file if the logic grows beyond a few branches.

- [ ] **Step 5: Re-run the Evolution client and router tests**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/evolution-api.test.ts \
  src/gateway/message-router.test.ts \
  src/lib/route-message.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add \
  gateway/packages/api/src/lib/evolution-api.ts \
  gateway/packages/api/src/lib/evolution-api.test.ts \
  gateway/packages/api/src/gateway/message-router.ts \
  gateway/packages/api/src/gateway/message-router.test.ts \
  gateway/packages/api/src/index.ts \
  gateway/packages/api/src/lib/route-message.test.ts

git commit -m "feat(gateway): add evolution whatsapp ingress"
```

### Task 3: Add shared-channel lifecycle endpoints and secret-safe backend contracts

**Files:**
- Create: `gateway/packages/api/src/lib/whatsapp-evolution-config.ts`
- Create: `gateway/packages/api/src/lib/whatsapp-evolution-config.test.ts`
- Modify: `gateway/packages/api/src/routes/admin-shared-channels.ts`
- Modify: `gateway/packages/api/src/routes/admin-shared-channels.test.ts`
- Modify: `gateway/packages/web/lib/admin-api.ts`

- [ ] **Step 1: Write failing tests for connect/disconnect and secret scrubbing**

Add tests that fail until the API contract is tightened:

```ts
// gateway/packages/api/src/routes/admin-shared-channels.test.ts
it('scrubs webhookToken from shared channel detail responses', async () => {
  // db returns config { instanceName, webhookToken }
  // expect API payload only returns config.instanceName and hasWebhookToken: true
});

it('connects a whatsapp_evolution shared channel by registering an Evolution webhook', async () => {
  // POST /api/admin/shared-channels/ch_1/connect
});

it('disconnects a whatsapp_evolution shared channel by clearing the Evolution webhook', async () => {
  // POST /api/admin/shared-channels/ch_1/disconnect
});

it('refuses to retire a connected channel when remote webhook clear fails', async () => {
  // DELETE should return 502/500 and not archive the row
});
```

- [ ] **Step 2: Run the admin shared-channel tests to verify failure**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/routes/admin-shared-channels.test.ts
```

Expected: failures because detail responses still expose raw config and the connect/disconnect endpoints do not exist.

- [ ] **Step 3: Add config helpers that separate stored secrets from browser-safe config**

Create a helper module so the route code stays readable:

```ts
// gateway/packages/api/src/lib/whatsapp-evolution-config.ts
export interface StoredWhatsAppEvolutionConfig {
  instanceName: string;
  webhookToken: string;
}

export interface PublicWhatsAppEvolutionConfig {
  instanceName: string;
}

export function parseStoredWhatsAppEvolutionConfig(value: unknown): StoredWhatsAppEvolutionConfig {
  // validate instanceName + webhookToken are non-empty strings
}

export function buildPublicWhatsAppEvolutionConfig(value: unknown): PublicWhatsAppEvolutionConfig {
  const parsed = parseStoredWhatsAppEvolutionConfig(value);
  return { instanceName: parsed.instanceName };
}
```

- [ ] **Step 4: Add lifecycle endpoints and enforce safe serialization**

Modify `admin-shared-channels.ts` so it:

```ts
// create route
if (parsedBody.data.kind === 'whatsapp_evolution') {
  config = {
    instanceName: parsedBody.data.config.instanceName,
    webhookToken: crypto.randomUUID(),
  };
}
```

```ts
// serializer
return {
  ...base,
  config: row.type === 'whatsapp_evolution'
    ? buildPublicWhatsAppEvolutionConfig(row.config)
    : (options?.includeConfig ? row.config ?? {} : undefined),
  ...(row.type === 'whatsapp_evolution' ? { hasWebhookToken: true } : {}),
};
```

```ts
// connect / disconnect routes
.post('/:id/connect', async (c) => { /* use EvolutionApiClient.setWebhook */ })
.post('/:id/disconnect', async (c) => { /* use EvolutionApiClient.clearWebhook */ })
```

```ts
// retire path
if (existing.type === 'whatsapp_evolution' && existing.status === 'connected') {
  await evolution.clearWebhook(parsed.instanceName);
}
```

Also reject PATCH attempts that try to mutate `webhookToken` or change
`instanceName` while status is `connected`.

- [ ] **Step 5: Re-run the route tests and a config-helper slice**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/whatsapp-evolution-config.test.ts \
  src/routes/admin-shared-channels.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add \
  gateway/packages/api/src/lib/whatsapp-evolution-config.ts \
  gateway/packages/api/src/lib/whatsapp-evolution-config.test.ts \
  gateway/packages/api/src/routes/admin-shared-channels.ts \
  gateway/packages/api/src/routes/admin-shared-channels.test.ts \
  gateway/packages/web/lib/admin-api.ts

git commit -m "feat(gateway): add shared evolution channel lifecycle"
```

### Task 4: Add Evolution-backed outbound delivery and deployment docs

**Files:**
- Modify: `gateway/packages/api/src/lib/outbound-delivery.ts`
- Modify: `gateway/packages/api/src/routes/outbound.test.ts`
- Modify: `gateway/packages/api/src/lib/external-identity.test.ts`
- Modify: `gateway/packages/api/src/lib/route-message.test.ts`
- Modify: `deploy/env/coke.env.example`
- Modify: `docs/deploy.md`

- [ ] **Step 1: Write failing outbound and regression assertions**

Add a direct outbound test and explicit regression assertions for existing
WhatsApp-family code paths:

```ts
// gateway/packages/api/src/routes/outbound.test.ts
it('delivers whatsapp_evolution outbound messages through Evolution sendText', async () => {
  // mocked channel.type = 'whatsapp_evolution'
  // expect EvolutionApiClient.sendText called with instanceName + number + text
});
```

```ts
// gateway/packages/api/src/lib/external-identity.test.ts
it('keeps existing whatsapp and whatsapp_business normalization behavior unchanged', () => {
  // explicit coverage for both legacy providers
});
```

```ts
// gateway/packages/api/src/lib/route-message.test.ts
it('still derives wa_id for whatsapp_business shared channels after whatsapp_evolution is added', async () => {
  // regression guard
});
```

- [ ] **Step 2: Run the outbound/regression slice to verify failure**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/routes/outbound.test.ts \
  src/lib/external-identity.test.ts \
  src/lib/route-message.test.ts
```

Expected: failures because `outbound-delivery.ts` only supports `wechat_personal` today.

- [ ] **Step 3: Implement the Evolution outbound branch**

Extend the delivery switch:

```ts
// gateway/packages/api/src/lib/outbound-delivery.ts
import { EvolutionApiClient } from './evolution-api.js';
import { parseStoredWhatsAppEvolutionConfig } from './whatsapp-evolution-config.js';

export async function deliverOutboundMessage(channel, externalEndUserId, text) {
  switch (channel.type) {
    case 'wechat_personal':
      await sendWeixinText(channel.id, externalEndUserId, text);
      return;
    case 'whatsapp_evolution': {
      const config = parseStoredWhatsAppEvolutionConfig(channel.config);
      const number = externalEndUserId.replace(/\D+/g, '');
      await new EvolutionApiClient().sendText(config.instanceName, number, text);
      return;
    }
    default:
      throw new Error(`Unsupported outbound channel type: ${channel.type}`);
  }
}
```

Update the tests to pass `config` through the mocked channel object.

- [ ] **Step 4: Document the new required deploy variables**

Update:

```dotenv
# deploy/env/coke.env.example
EVOLUTION_API_BASE_URL=https://coke.keep4oforever.com/evolution-api
EVOLUTION_API_KEY=replace-me
```

And add a `docs/deploy.md` section that says these vars are required whenever a
`whatsapp_evolution` shared channel is used, including the public base path on
`gcp-coke`.

- [ ] **Step 5: Re-run the outbound/regression slice**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/routes/outbound.test.ts \
  src/lib/external-identity.test.ts \
  src/lib/route-message.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add \
  gateway/packages/api/src/lib/outbound-delivery.ts \
  gateway/packages/api/src/routes/outbound.test.ts \
  gateway/packages/api/src/lib/external-identity.test.ts \
  gateway/packages/api/src/lib/route-message.test.ts \
  deploy/env/coke.env.example \
  docs/deploy.md

git commit -m "feat(gateway): deliver evolution whatsapp outbound"
```

### Task 5: Update the admin web UI for typed config and lifecycle actions

**Files:**
- Modify: `gateway/packages/web/lib/admin-api.ts`
- Modify: `gateway/packages/web/lib/admin-copy.ts`
- Modify: `gateway/packages/web/app/(admin)/admin/shared-channels/page.tsx`
- Modify: `gateway/packages/web/app/(admin)/admin/shared-channels/page.test.tsx`
- Modify: `gateway/packages/web/app/(admin)/admin/shared-channels/detail/page.tsx`
- Modify: `gateway/packages/web/app/(admin)/admin/shared-channels/detail/page.test.tsx`

- [ ] **Step 1: Write failing UI tests for the new typed flow**

Add tests that require a typed `instanceName` field and connect/disconnect
buttons for `whatsapp_evolution`:

```tsx
// page.test.tsx
it('creates whatsapp_evolution shared channels with instanceName instead of raw JSON config', async () => {
  // select kind=whatsapp_evolution
  // fill instanceName input
  // expect adminApi.post body { kind, name, agentId, config: { instanceName } }
});
```

```tsx
// detail/page.test.tsx
it('shows connect and disconnect actions for whatsapp_evolution detail pages', async () => {
  // response.data.kind = 'whatsapp_evolution'
  // expect no raw config textarea
  // expect typed instanceName field and connect/disconnect buttons
});
```

- [ ] **Step 2: Run the shared-channel page tests to confirm failure**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  app/(admin)/admin/shared-channels/page.test.tsx \
  app/(admin)/admin/shared-channels/detail/page.test.tsx
```

Expected: failures because the current UI only exposes raw JSON config and save/retire actions.

- [ ] **Step 3: Add the new admin API types and UI states**

Update `admin-api.ts` types:

```ts
export type AdminSharedChannelDetail = AdminSharedChannelRow & {
  config: Record<string, unknown>;
  hasWebhookToken?: boolean;
};
```

Then update the create/detail pages so `whatsapp_evolution` uses a typed
`instanceName` field while other kinds can continue to use the generic JSON
config area.

- [ ] **Step 4: Add connect/disconnect button wiring**

In the detail page, call the new backend lifecycle endpoints:

```ts
await adminApi.post<AdminSharedChannelDetail>(`/api/admin/shared-channels/${id}/connect`);
await adminApi.post<AdminSharedChannelDetail>(`/api/admin/shared-channels/${id}/disconnect`);
```

Update copy labels in `admin-copy.ts` for the new actions and any
`instanceName` field label.

- [ ] **Step 5: Run the shared-channel UI tests and a full web test pass**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  app/(admin)/admin/shared-channels/page.test.tsx \
  app/(admin)/admin/shared-channels/detail/page.test.tsx \
  lib/i18n.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add \
  gateway/packages/web/lib/admin-api.ts \
  gateway/packages/web/lib/admin-copy.ts \
  gateway/packages/web/app/(admin)/admin/shared-channels/page.tsx \
  gateway/packages/web/app/(admin)/admin/shared-channels/page.test.tsx \
  gateway/packages/web/app/(admin)/admin/shared-channels/detail/page.tsx \
  gateway/packages/web/app/(admin)/admin/shared-channels/detail/page.test.tsx

git commit -m "feat(web): manage evolution shared whatsapp channels"
```

### Task 6: Final verification and production smoke

**Files:**
- Modify: none by default; if verification finds a defect, return to the owning task and update the files listed there before re-running this task
- Test: existing gateway/web suites and production runtime on `gcp-coke`

- [ ] **Step 1: Run the API test suites required by this feature**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/external-identity.test.ts \
  src/lib/route-message.test.ts \
  src/lib/evolution-api.test.ts \
  src/lib/whatsapp-evolution-config.test.ts \
  src/gateway/message-router.test.ts \
  src/routes/admin-shared-channels.test.ts \
  src/routes/outbound.test.ts \
  src/routes/channels.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run the web tests and gateway build**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  app/(admin)/admin/shared-channels/page.test.tsx \
  app/(admin)/admin/shared-channels/detail/page.test.tsx \
  lib/i18n.test.ts

pnpm --dir gateway run build
```

Expected: PASS.

- [ ] **Step 3: Deploy to `gcp-coke` and configure the live channel**

Run the normal deploy flow after setting `EVOLUTION_API_BASE_URL` and
`EVOLUTION_API_KEY` in `~/coke/.env`:

```bash
PUBLIC_BASE_URL=https://coke.keep4oforever.com ./scripts/deploy-compose-to-gcp.sh --restart
```

Then verify runtime behavior:

```bash
ssh gcp-coke 'APIKEY=$(grep "^AUTHENTICATION_API_KEY=" ~/evolution/.env | cut -d= -f2-); curl -fsS http://127.0.0.1:8081/webhook/find/coke-whatsapp-personal -H "apikey: $APIKEY"'
ssh gcp-coke 'curl -fsS http://127.0.0.1:4041/health'
ssh gcp-coke 'curl -fsS http://127.0.0.1:8090/bridge/healthz'
```

Expected: gateway and bridge healthy, Evolution webhook present after channel connect.

- [ ] **Step 4: Execute the live WhatsApp smoke**

Checklist:

```text
1. Create shared channel in admin UI with kind=whatsapp_evolution and instanceName=coke-whatsapp-personal
2. Connect the channel and confirm Evolution webhook registration
3. Send one real inbound WhatsApp message from a previously unseen sender
4. Confirm one new Customer / ExternalIdentity / DeliveryRoute path is created
5. Confirm immediate Coke reply arrives in WhatsApp
6. Trigger one proactive outbound message through Coke
7. Confirm proactive outbound arrives in the same WhatsApp chat
8. Disconnect or retire the channel and confirm webhook is removed
```

Expected: all eight checks succeed.
