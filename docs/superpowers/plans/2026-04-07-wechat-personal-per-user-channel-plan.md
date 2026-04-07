# WeChat Personal Per-User Channel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the shared `wechat_personal` bind flow with a per-user personal-channel lifecycle where each Coke user owns their own WeChat login session.

**Architecture:** Extend the existing gateway `Channel` model with ownership scope so `wechat_personal` can be owned by `ClawscaleUser`, then shift the Coke bridge and Coke web UI from `bind session` semantics to `personal channel lifecycle` semantics. Keep legacy shared-channel routing intact for compatibility, but make the new Coke onboarding path create, connect, monitor, disconnect, and archive a user-owned personal channel.

**Tech Stack:** Python 3.12, Flask, requests, PyMongo, pytest, PostgreSQL, Prisma, TypeScript, Hono, Next.js, Vitest, pnpm

---

## File Structure

### New gateway files

- `gateway/packages/api/src/lib/personal-wechat-channel.ts`
  Owns personal `wechat_personal` lifecycle rules: create, connect, disconnect, archive, ownership checks, and state transitions.
- `gateway/packages/api/src/lib/personal-wechat-channel.test.ts`
  Covers lifecycle transitions, uniqueness, and owner-based routing helpers.
- `gateway/packages/api/src/routes/user-wechat-channel.ts`
  Internal authenticated route surface for personal WeChat channel lifecycle used by the Coke bridge.
- `gateway/packages/api/src/routes/user-wechat-channel.test.ts`
  Verifies auth, create/reuse, connect, status, disconnect, and archive behavior.

### Modified gateway files

- `gateway/packages/api/prisma/schema.prisma`
  Adds channel ownership scope, owner foreign key, tenant kind marker, and explicit channel lifecycle status support.
- `gateway/packages/api/src/index.ts`
  Mounts the new internal user WeChat channel router.
- `gateway/packages/api/src/lib/route-message.ts`
  Routes inbound personal WeChat traffic by channel ownership first, keeps legacy tenant-shared routing unchanged.
- `gateway/packages/api/src/lib/route-message.test.ts`
  Covers owner-based routing, legacy fallback, and disconnected-channel behavior.
- `gateway/packages/api/src/adapters/wechat.ts`
  Updates login state handling to align with the new channel lifecycle and explicit owner-based personal channel reconnect/disconnect behavior.
- `gateway/packages/api/src/adapters/wechat.test.ts`
  Covers pending, connected, disconnected, and error transitions for personal channels.
- `gateway/packages/api/src/routes/channels.ts`
  Prevents dashboard create/connect flows from remaining the primary path for personal WeChat onboarding and keeps legacy/shared semantics explicit.
- `gateway/packages/api/src/routes/end-users.ts`
  Exposes channel ownership metadata when needed for operator diagnostics.
- `gateway/packages/shared/src/types/conversation.ts`
  Adds personal-channel ownership fields needed by the web dashboard.
- `gateway/packages/web/app/(dashboard)/channels/page.tsx`
  Displays ownership scope and keeps personal WeChat channels read-only or operator-diagnostic only.

### New Coke bridge files

- `connector/clawscale_bridge/personal_wechat_channel_service.py`
  Coke-side service that manages the personal WeChat channel lifecycle through gateway internal APIs.
- `connector/clawscale_bridge/gateway_personal_channel_client.py`
  HTTP client for create/connect/status/disconnect/archive personal WeChat channel operations.
- `tests/unit/connector/clawscale_bridge/test_personal_wechat_channel_service.py`
  Verifies lifecycle translation from gateway responses into Coke user-facing states.
- `tests/unit/connector/clawscale_bridge/test_gateway_personal_channel_client.py`
  Verifies request payloads, auth, malformed responses, and error handling.

### Modified Coke bridge files

- `connector/clawscale_bridge/app.py`
  Wires the new personal channel service into user endpoints and keeps bridge inbound routing compatible.
- `connector/clawscale_bridge/identity_service.py`
  Uses personal-channel ownership metadata as the primary routing signal for `wechat_personal` and keeps tenant-shared legacy handling unchanged.
- `connector/clawscale_bridge/wechat_bind_session_service.py`
  De-scopes or freezes the shared bind-session flow for legacy compatibility only.
- `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
  Covers new user lifecycle endpoints and retained legacy behavior.
- `tests/unit/connector/clawscale_bridge/test_identity_service.py`
  Covers owner-based routing and disconnect/reconnect handling.
- `tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py`
  Shrinks expectations to legacy-only behavior.
- `dao/external_identity_dao.py`
  Freezes ownership writes for the personal WeChat path while keeping shared-flow compatibility reads.
- `tests/unit/dao/test_external_identity_dao.py`
  Verifies that the new flow does not perform ownership writes.
- `conf/config.json`
  Adds any endpoint names or flags needed for the new internal personal-channel API surface.

### New or modified Coke web files

- `gateway/packages/web/lib/coke-user-wechat-channel.ts`
  Client helpers for create/connect/status/disconnect/archive personal WeChat channel lifecycle.
- `gateway/packages/web/lib/coke-user-wechat-channel.test.ts`
  Covers lifecycle API calls and response normalization.
- `gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.tsx`
  Replaces bind-session UX with `Create my WeChat channel`, `Connect WeChat`, status, disconnect, and archive states.
- `gateway/packages/web/app/(coke-user)/coke/register/page.tsx`
  Keeps redirect behavior aligned with the new lifecycle terminology.
- `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`
  Keeps copy aligned with the new lifecycle terminology.

### Docs and ops

- `docs/clawscale_bridge.md`
  Documents the new user-owned channel flow, migration behavior, and legacy freeze policy.
- `docs/superpowers/specs/2026-04-07-wechat-personal-per-user-channel-design.md`
  Source spec for this plan.
- `connector/clawscale_bridge/backfill_clawscale_users.py`
  May need an operator-confirmed legacy reset mode or explicit no-op for personal WeChat ownership.
- `tests/unit/connector/clawscale_bridge/test_backfill_clawscale_users.py`
  Verifies the migration gate / freeze behavior if the script changes.

## Task 1: Add channel ownership scope and lifecycle state to gateway data model

**Files:**
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Test: `gateway/packages/api/src/lib/personal-wechat-channel.test.ts`
- Create: `gateway/packages/api/src/lib/personal-wechat-channel.ts`

- [ ] **Step 1: Write the failing gateway lifecycle tests**

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';

const db = vi.hoisted(() => ({
  channel: {
    findFirst: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
  },
  clawscaleUser: {
    findUnique: vi.fn(),
  },
}));

vi.mock('../db/index.js', () => ({ db }));

import {
  archivePersonalWeChatChannel,
  createOrReusePersonalWeChatChannel,
  disconnectPersonalWeChatChannel,
} from './personal-wechat-channel.js';

describe('createOrReusePersonalWeChatChannel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    db.clawscaleUser.findUnique.mockResolvedValue({
      id: 'csu_1',
      tenantId: 'ten_1',
      cokeAccountId: 'acc_1',
    });
  });

  it('creates a personal wechat_personal channel when none exists', async () => {
    db.channel.findFirst.mockResolvedValueOnce(null);
    db.channel.create.mockResolvedValueOnce({
      id: 'ch_1',
      tenantId: 'ten_1',
      type: 'wechat_personal',
      scope: 'personal',
      ownerClawscaleUserId: 'csu_1',
      status: 'disconnected',
    });

    const result = await createOrReusePersonalWeChatChannel({
      tenantId: 'ten_1',
      clawscaleUserId: 'csu_1',
    });

    expect(db.channel.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          tenantId: 'ten_1',
          type: 'wechat_personal',
          scope: 'personal',
          ownerClawscaleUserId: 'csu_1',
          status: 'disconnected',
        }),
      }),
    );
    expect(result.status).toBe('disconnected');
  });

  it('reuses an existing non-archived personal channel', async () => {
    db.channel.findFirst.mockResolvedValueOnce({
      id: 'ch_existing',
      tenantId: 'ten_1',
      type: 'wechat_personal',
      scope: 'personal',
      ownerClawscaleUserId: 'csu_1',
      status: 'error',
    });

    const result = await createOrReusePersonalWeChatChannel({
      tenantId: 'ten_1',
      clawscaleUserId: 'csu_1',
    });

    expect(db.channel.create).not.toHaveBeenCalled();
    expect(result.id).toBe('ch_existing');
    expect(result.status).toBe('error');
  });
});

describe('disconnectPersonalWeChatChannel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('moves a connected personal channel to disconnected', async () => {
    db.channel.findFirst.mockResolvedValueOnce({
      id: 'ch_1',
      tenantId: 'ten_1',
      type: 'wechat_personal',
      scope: 'personal',
      ownerClawscaleUserId: 'csu_1',
      status: 'connected',
      config: { token: 'bot-token' },
    });
    db.channel.update.mockResolvedValueOnce({ id: 'ch_1', status: 'disconnected' });

    const result = await disconnectPersonalWeChatChannel({
      tenantId: 'ten_1',
      clawscaleUserId: 'csu_1',
    });

    expect(db.channel.update).toHaveBeenCalledWith({
      where: { id: 'ch_1' },
      data: expect.objectContaining({ status: 'disconnected' }),
    });
    expect(result.status).toBe('disconnected');
  });
});

describe('archivePersonalWeChatChannel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('archives a disconnected personal channel so a fresh one can later be created', async () => {
    db.channel.findFirst.mockResolvedValueOnce({
      id: 'ch_1',
      tenantId: 'ten_1',
      type: 'wechat_personal',
      scope: 'personal',
      ownerClawscaleUserId: 'csu_1',
      status: 'disconnected',
    });
    db.channel.update.mockResolvedValueOnce({ id: 'ch_1', status: 'archived' });

    const result = await archivePersonalWeChatChannel({
      tenantId: 'ten_1',
      clawscaleUserId: 'csu_1',
    });

    expect(result.status).toBe('archived');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir gateway/packages/api exec vitest run src/lib/personal-wechat-channel.test.ts`
Expected: FAIL with missing module `./personal-wechat-channel.js` and missing schema fields such as `scope` / `ownerClawscaleUserId`.

- [ ] **Step 3: Update Prisma schema for scope and lifecycle**

```prisma
model Tenant {
  id        String   @id
  slug      String   @unique
  name      String
  kind      String   @default("team")
  settings  Json     @default("{}")
  createdAt DateTime @default(now()) @map("created_at")
  updatedAt DateTime @updatedAt @map("updated_at")

  members         Member[]
  sessions        Session[]
  channels        Channel[]
  endUsers        EndUser[]
  clawscaleUsers  ClawscaleUser[]
  workflows       Workflow[]
  auditLogs       AuditLog[]
  aiBackends      AiBackend[]

  @@map("tenants")
}

enum ChannelScope {
  tenant_shared
  personal
}

enum ChannelStatus {
  connected
  disconnected
  pending
  error
  archived
}

model Channel {
  id                   String        @id
  tenantId             String        @map("tenant_id")
  type                 ChannelType
  scope                ChannelScope  @default(tenant_shared)
  ownerClawscaleUserId String?       @map("owner_clawscale_user_id")
  name                 String
  status               ChannelStatus @default(disconnected)
  config               Json          @default("{}")
  createdAt            DateTime      @default(now()) @map("created_at")
  updatedAt            DateTime      @updatedAt @map("updated_at")

  tenant         Tenant         @relation(fields: [tenantId], references: [id], onDelete: Cascade)
  ownerClawscaleUser ClawscaleUser? @relation(fields: [ownerClawscaleUserId], references: [id], onDelete: SetNull)
  conversations  Conversation[]
  endUsers       EndUser[]

  @@index([tenantId])
  @@index([ownerClawscaleUserId])
  @@map("channels")
}
```

- [ ] **Step 4: Write minimal lifecycle helper implementation**

```ts
import { db } from '../db/index.js';
import { generateId } from './id.js';

export async function createOrReusePersonalWeChatChannel(input: {
  tenantId: string;
  clawscaleUserId: string;
}) {
  const existing = await db.channel.findFirst({
    where: {
      tenantId: input.tenantId,
      ownerClawscaleUserId: input.clawscaleUserId,
      type: 'wechat_personal',
      scope: 'personal',
      NOT: { status: 'archived' },
    },
  });
  if (existing) return existing;

  return db.channel.create({
    data: {
      id: generateId('ch'),
      tenantId: input.tenantId,
      ownerClawscaleUserId: input.clawscaleUserId,
      type: 'wechat_personal',
      scope: 'personal',
      name: 'My WeChat',
      status: 'disconnected',
      config: {},
    },
  });
}

export async function disconnectPersonalWeChatChannel(input: {
  tenantId: string;
  clawscaleUserId: string;
}) {
  const channel = await db.channel.findFirst({
    where: {
      tenantId: input.tenantId,
      ownerClawscaleUserId: input.clawscaleUserId,
      type: 'wechat_personal',
      scope: 'personal',
      NOT: { status: 'archived' },
    },
  });
  if (!channel) throw new Error('personal_channel_not_found');

  return db.channel.update({
    where: { id: channel.id },
    data: { status: 'disconnected', config: {} },
  });
}

export async function archivePersonalWeChatChannel(input: {
  tenantId: string;
  clawscaleUserId: string;
}) {
  const channel = await db.channel.findFirst({
    where: {
      tenantId: input.tenantId,
      ownerClawscaleUserId: input.clawscaleUserId,
      type: 'wechat_personal',
      scope: 'personal',
      NOT: { status: 'archived' },
    },
  });
  if (!channel) throw new Error('personal_channel_not_found');
  if (channel.status === 'connected') throw new Error('disconnect_before_archive');

  return db.channel.update({
    where: { id: channel.id },
    data: { status: 'archived' },
  });
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pnpm --dir gateway/packages/api exec vitest run src/lib/personal-wechat-channel.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add gateway/packages/api/prisma/schema.prisma gateway/packages/api/src/lib/personal-wechat-channel.ts gateway/packages/api/src/lib/personal-wechat-channel.test.ts
git commit -m "feat(gateway): add personal wechat channel lifecycle model"
```

## Task 2: Add internal gateway API for personal WeChat channel lifecycle

**Files:**
- Create: `gateway/packages/api/src/routes/user-wechat-channel.ts`
- Create: `gateway/packages/api/src/routes/user-wechat-channel.test.ts`
- Modify: `gateway/packages/api/src/index.ts`
- Modify: `gateway/packages/api/src/adapters/wechat.ts`
- Modify: `gateway/packages/api/src/adapters/wechat.test.ts`

- [ ] **Step 1: Write the failing router tests**

```ts
import { Hono } from 'hono';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const lifecycle = vi.hoisted(() => ({
  createOrReusePersonalWeChatChannel: vi.fn(),
  disconnectPersonalWeChatChannel: vi.fn(),
  archivePersonalWeChatChannel: vi.fn(),
}));
const wechat = vi.hoisted(() => ({
  startWeixinQR: vi.fn(),
  getWeixinQR: vi.fn(),
  getWeixinStatus: vi.fn(),
}));

vi.mock('../lib/personal-wechat-channel.js', () => lifecycle);
vi.mock('../adapters/wechat.js', () => ({
  startWeixinQR: wechat.startWeixinQR,
  getWeixinQR: wechat.getWeixinQR,
  getWeixinStatus: wechat.getWeixinStatus,
}));

import { userWechatChannelRouter } from './user-wechat-channel.js';

describe('userWechatChannelRouter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('creates or reuses a personal channel for the authenticated user', async () => {
    lifecycle.createOrReusePersonalWeChatChannel.mockResolvedValue({
      id: 'ch_1',
      status: 'disconnected',
      ownerClawscaleUserId: 'csu_1',
    });

    const app = new Hono();
    app.use('*', async (c, next) => {
      c.set('bridgeUser', { tenantId: 'ten_1', clawscaleUserId: 'csu_1', cokeAccountId: 'acc_1' });
      await next();
    });
    app.route('/user/wechat-channel', userWechatChannelRouter);

    const res = await app.request('/user/wechat-channel', { method: 'POST' });
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.data.status).toBe('disconnected');
  });

  it('starts QR connect and returns pending state', async () => {
    wechat.startWeixinQR.mockResolvedValue(undefined);
    wechat.getWeixinStatus.mockReturnValue('qr_pending');
    wechat.getWeixinQR.mockReturnValue({ image: 'data:image/png;base64,abc', url: 'https://liteapp.weixin.qq.com/q/1' });

    const app = new Hono();
    app.use('*', async (c, next) => {
      c.set('bridgeUser', { tenantId: 'ten_1', clawscaleUserId: 'csu_1', cokeAccountId: 'acc_1', channelId: 'ch_1' });
      await next();
    });
    app.route('/user/wechat-channel', userWechatChannelRouter);

    const res = await app.request('/user/wechat-channel/connect', { method: 'POST' });
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.data.status).toBe('pending');
    expect(body.data.qr_url).toBe('https://liteapp.weixin.qq.com/q/1');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir gateway/packages/api exec vitest run src/routes/user-wechat-channel.test.ts src/adapters/wechat.test.ts`
Expected: FAIL with missing router and missing personal-channel-aware adapter semantics.

- [ ] **Step 3: Implement the minimal internal router**

```ts
import { Hono } from 'hono';
import {
  archivePersonalWeChatChannel,
  createOrReusePersonalWeChatChannel,
  disconnectPersonalWeChatChannel,
} from '../lib/personal-wechat-channel.js';
import { getWeixinQR, getWeixinStatus, startWeixinQR, stopWeixinBot } from '../adapters/wechat.js';

export const userWechatChannelRouter = new Hono()
  .post('/', async (c) => {
    const auth = c.get('bridgeUser');
    const channel = await createOrReusePersonalWeChatChannel({
      tenantId: auth.tenantId,
      clawscaleUserId: auth.clawscaleUserId,
    });
    return c.json({ ok: true, data: { channel_id: channel.id, status: channel.status } });
  })
  .post('/connect', async (c) => {
    const auth = c.get('bridgeUser');
    const channel = await createOrReusePersonalWeChatChannel({
      tenantId: auth.tenantId,
      clawscaleUserId: auth.clawscaleUserId,
    });
    await startWeixinQR(channel.id);
    const qr = getWeixinQR(channel.id);
    const status = getWeixinStatus(channel.id) ?? 'qr_pending';
    return c.json({
      ok: true,
      data: { channel_id: channel.id, status: status === 'connected' ? 'connected' : 'pending', qr: qr?.image ?? null, qr_url: qr?.url ?? null },
    });
  })
  .get('/status', async (c) => {
    const auth = c.get('bridgeUser');
    const channel = await createOrReusePersonalWeChatChannel({
      tenantId: auth.tenantId,
      clawscaleUserId: auth.clawscaleUserId,
    });
    const status = getWeixinStatus(channel.id) ?? channel.status;
    const qr = getWeixinQR(channel.id);
    return c.json({ ok: true, data: { channel_id: channel.id, status, qr: qr?.image ?? null, qr_url: qr?.url ?? null } });
  })
  .post('/disconnect', async (c) => {
    const auth = c.get('bridgeUser');
    const channel = await disconnectPersonalWeChatChannel({
      tenantId: auth.tenantId,
      clawscaleUserId: auth.clawscaleUserId,
    });
    await stopWeixinBot(channel.id);
    return c.json({ ok: true, data: { channel_id: channel.id, status: 'disconnected' } });
  })
  .delete('/', async (c) => {
    const auth = c.get('bridgeUser');
    const channel = await archivePersonalWeChatChannel({
      tenantId: auth.tenantId,
      clawscaleUserId: auth.clawscaleUserId,
    });
    return c.json({ ok: true, data: { channel_id: channel.id, status: 'archived' } });
  });
```

- [ ] **Step 4: Mount the router and update adapter state behavior**

```ts
// gateway/packages/api/src/index.ts
import { userWechatChannelRouter } from './routes/user-wechat-channel.js';

app.route('/api/internal/user/wechat-channel', userWechatChannelRouter);
```

```ts
// gateway/packages/api/src/adapters/wechat.ts
if (statusData.status === 'confirmed' && statusData.bot_token) {
  await db.channel.update({
    where: { id: channelId },
    data: {
      status: 'connected',
      config: {
        baseUrl: botBaseUrl,
        token,
        botId: statusData.ilink_bot_id ?? '',
      },
    },
  });
}

if (statusData.status === 'expired') {
  await db.channel.update({ where: { id: channelId }, data: { status: 'error' } });
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pnpm --dir gateway/packages/api exec vitest run src/routes/user-wechat-channel.test.ts src/adapters/wechat.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add gateway/packages/api/src/routes/user-wechat-channel.ts gateway/packages/api/src/routes/user-wechat-channel.test.ts gateway/packages/api/src/index.ts gateway/packages/api/src/adapters/wechat.ts gateway/packages/api/src/adapters/wechat.test.ts
git commit -m "feat(gateway): add personal wechat channel api"
```

## Task 3: Route personal WeChat traffic by channel owner and freeze shared WeChat ownership writes

**Files:**
- Modify: `gateway/packages/api/src/lib/route-message.ts`
- Modify: `gateway/packages/api/src/lib/route-message.test.ts`
- Modify: `connector/clawscale_bridge/identity_service.py`
- Modify: `connector/clawscale_bridge/wechat_bind_session_service.py`
- Modify: `dao/external_identity_dao.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_identity_service.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py`
- Modify: `tests/unit/dao/test_external_identity_dao.py`

- [ ] **Step 1: Write the failing owner-routing tests**

```ts
it('routes personal wechat inbound by channel owner metadata before legacy shared lookup', async () => {
  db.channel.findUnique.mockResolvedValueOnce({
    id: 'ch_1',
    tenantId: 'ten_1',
    type: 'wechat_personal',
    scope: 'personal',
    ownerClawscaleUserId: 'csu_1',
    ownerClawscaleUser: { cokeAccountId: 'acc_1' },
  });

  await routeInboundMessage({
    tenantId: 'ten_1',
    channelId: 'ch_1',
    externalId: 'wxid_123',
    senderName: 'Alice',
    text: 'hello',
    meta: { platform: 'wechat_personal' },
  });

  expect(mockBridgeSend).toHaveBeenCalledWith(
    expect.objectContaining({
      metadata: expect.objectContaining({
        cokeAccountId: 'acc_1',
        channelScope: 'personal',
      }),
    }),
  );
});
```

```python
def test_handle_inbound_uses_personal_channel_owner_before_external_identity_lookup():
    external_identity_dao = FakeExternalIdentityDAO()
    service = IdentityService(
        external_identity_dao=external_identity_dao,
        binding_ticket_dao=None,
        bind_session_service=None,
        message_gateway=FakeMessageGateway(),
        reply_waiter=FakeReplyWaiter(),
        bind_base_url='http://bind.local',
        target_character_id='char_1',
    )

    payload = {
        'metadata': {
            'platform': 'wechat_personal',
            'channelScope': 'personal',
            'cokeAccountId': 'acc_1',
        },
        'text': 'hello',
    }

    result = service.handle_inbound(payload)

    assert result['status'] == 'ok'
    assert external_identity_dao.find_active_identity_called is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir gateway/packages/api exec vitest run src/lib/route-message.test.ts && .venv/bin/pytest tests/unit/connector/clawscale_bridge/test_identity_service.py tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py tests/unit/dao/test_external_identity_dao.py -v`
Expected: FAIL because personal ownership metadata is not yet authoritative and the shared bind service still performs ownership writes.

- [ ] **Step 3: Implement owner-first routing and freeze ownership writes**

```ts
// gateway/packages/api/src/lib/route-message.ts
const channel = await db.channel.findUnique({
  where: { id: input.channelId },
  include: {
    ownerClawscaleUser: {
      select: { id: true, cokeAccountId: true },
    },
  },
});

const ownershipMeta =
  channel?.type === 'wechat_personal' && channel.scope === 'personal' && channel.ownerClawscaleUser
    ? {
        clawscaleUserId: channel.ownerClawscaleUser.id,
        cokeAccountId: channel.ownerClawscaleUser.cokeAccountId,
        channelScope: 'personal',
      }
    : undefined;
```

```python
# connector/clawscale_bridge/wechat_bind_session_service.py
# personal wechat flow no longer writes ownership through external_identities
return {
    'status': 'legacy_only',
}
```

```python
# dao/external_identity_dao.py
# keep legacy reads, but do not add any new helper for personal-channel ownership writes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir gateway/packages/api exec vitest run src/lib/route-message.test.ts && .venv/bin/pytest tests/unit/connector/clawscale_bridge/test_identity_service.py tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py tests/unit/dao/test_external_identity_dao.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/api/src/lib/route-message.ts gateway/packages/api/src/lib/route-message.test.ts connector/clawscale_bridge/identity_service.py connector/clawscale_bridge/wechat_bind_session_service.py dao/external_identity_dao.py tests/unit/connector/clawscale_bridge/test_identity_service.py tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py tests/unit/dao/test_external_identity_dao.py
git commit -m "refactor(bridge): route personal wechat by channel owner"
```

## Task 4: Replace bind-session bridge API with personal channel lifecycle service

**Files:**
- Create: `connector/clawscale_bridge/gateway_personal_channel_client.py`
- Create: `connector/clawscale_bridge/personal_wechat_channel_service.py`
- Create: `tests/unit/connector/clawscale_bridge/test_gateway_personal_channel_client.py`
- Create: `tests/unit/connector/clawscale_bridge/test_personal_wechat_channel_service.py`
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- Modify: `conf/config.json`

- [ ] **Step 1: Write the failing personal-channel client tests**

```python
def test_gateway_personal_channel_client_create_posts_expected_auth_and_path(requests_mock):
    from connector.clawscale_bridge.gateway_personal_channel_client import GatewayPersonalChannelClient

    requests_mock.post(
        'http://gateway.local/api/internal/user/wechat-channel',
        json={'ok': True, 'data': {'channel_id': 'ch_1', 'status': 'disconnected'}},
    )

    client = GatewayPersonalChannelClient(
        api_base_url='http://gateway.local/api/internal/user/wechat-channel',
        api_key='secret',
    )

    result = client.create_or_reuse_channel(tenant_id='ten_1', clawscale_user_id='csu_1', coke_account_id='acc_1')

    assert result['channel_id'] == 'ch_1'
```

```python
def test_personal_wechat_channel_service_translates_pending_status_into_ui_payload():
    from connector.clawscale_bridge.personal_wechat_channel_service import PersonalWechatChannelService

    class FakeClient:
        def connect_channel(self, **kwargs):
            return {
                'channel_id': 'ch_1',
                'status': 'pending',
                'qr_url': 'https://liteapp.weixin.qq.com/q/demo',
                'qr': 'data:image/png;base64,abc',
            }

    service = PersonalWechatChannelService(gateway_client=FakeClient())
    result = service.start_connect(tenant_id='ten_1', clawscale_user_id='csu_1', coke_account_id='acc_1')

    assert result['status'] == 'pending'
    assert result['connect_url'] == 'https://liteapp.weixin.qq.com/q/demo'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/unit/connector/clawscale_bridge/test_gateway_personal_channel_client.py tests/unit/connector/clawscale_bridge/test_personal_wechat_channel_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -v`
Expected: FAIL with missing modules and missing app wiring.

- [ ] **Step 3: Implement the new gateway client and service**

```python
import requests


class GatewayPersonalChannelClientError(RuntimeError):
    pass


class GatewayPersonalChannelClient:
    def __init__(self, api_base_url: str, api_key: str, timeout_seconds: float = 10.0):
        self.api_base_url = api_base_url.rstrip('/')
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def _headers(self):
        return {'Authorization': f'Bearer {self.api_key}'}

    def create_or_reuse_channel(self, **payload):
        response = requests.post(self.api_base_url, json=payload, headers=self._headers(), timeout=self.timeout_seconds)
        body = response.json()
        if not response.ok or not body.get('ok'):
            raise GatewayPersonalChannelClientError('create_failed')
        return body['data']

    def connect_channel(self, **payload):
        response = requests.post(f'{self.api_base_url}/connect', json=payload, headers=self._headers(), timeout=self.timeout_seconds)
        body = response.json()
        if not response.ok or not body.get('ok'):
            raise GatewayPersonalChannelClientError('connect_failed')
        return body['data']

    def get_status(self, **payload):
        response = requests.get(f'{self.api_base_url}/status', params=payload, headers=self._headers(), timeout=self.timeout_seconds)
        body = response.json()
        if not response.ok or not body.get('ok'):
            raise GatewayPersonalChannelClientError('status_failed')
        return body['data']
```

```python
class PersonalWechatChannelService:
    def __init__(self, gateway_client):
        self.gateway_client = gateway_client

    def ensure_channel(self, tenant_id: str, clawscale_user_id: str, coke_account_id: str):
        return self.gateway_client.create_or_reuse_channel(
            tenant_id=tenant_id,
            clawscale_user_id=clawscale_user_id,
            coke_account_id=coke_account_id,
        )

    def start_connect(self, tenant_id: str, clawscale_user_id: str, coke_account_id: str):
        result = self.gateway_client.connect_channel(
            tenant_id=tenant_id,
            clawscale_user_id=clawscale_user_id,
            coke_account_id=coke_account_id,
        )
        return {
            'status': result['status'],
            'channel_id': result['channel_id'],
            'connect_url': result.get('qr_url'),
            'qr': result.get('qr'),
        }
```

- [ ] **Step 4: Wire the Flask app to the new personal-channel service**

```python
# connector/clawscale_bridge/app.py
from connector.clawscale_bridge.gateway_personal_channel_client import GatewayPersonalChannelClient
from connector.clawscale_bridge.personal_wechat_channel_service import PersonalWechatChannelService


def _build_personal_wechat_channel_service():
    bridge_conf = CONF['clawscale_bridge']
    client = GatewayPersonalChannelClient(
        api_base_url=bridge_conf['identity_api_url'].replace('/coke-bindings', '/user/wechat-channel'),
        api_key=bridge_conf['identity_api_key'],
    )
    return PersonalWechatChannelService(gateway_client=client)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/unit/connector/clawscale_bridge/test_gateway_personal_channel_client.py tests/unit/connector/clawscale_bridge/test_personal_wechat_channel_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add connector/clawscale_bridge/gateway_personal_channel_client.py connector/clawscale_bridge/personal_wechat_channel_service.py tests/unit/connector/clawscale_bridge/test_gateway_personal_channel_client.py tests/unit/connector/clawscale_bridge/test_personal_wechat_channel_service.py connector/clawscale_bridge/app.py tests/unit/connector/clawscale_bridge/test_bridge_app.py conf/config.json
git commit -m "feat(bridge): add personal wechat channel lifecycle service"
```

## Task 5: Update Coke user web from bind flow to personal channel lifecycle

**Files:**
- Create: `gateway/packages/web/lib/coke-user-wechat-channel.ts`
- Create: `gateway/packages/web/lib/coke-user-wechat-channel.test.ts`
- Modify: `gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/register/page.tsx`
- Modify: `docs/clawscale_bridge.md`

- [ ] **Step 1: Write the failing web helper tests**

```ts
import { describe, expect, it, vi } from 'vitest';

const getMock = vi.fn();
const postMock = vi.fn();
const deleteMock = vi.fn();

vi.mock('@/lib/coke-user-api', () => ({
  cokeUserApi: {
    get: getMock,
    post: postMock,
    delete: deleteMock,
  },
}));

import { archiveWechatChannel, createWechatChannel, getWechatChannelStatus, startWechatConnect } from './coke-user-wechat-channel.js';

describe('coke-user-wechat-channel', () => {
  it('creates a personal wechat channel', async () => {
    postMock.mockResolvedValueOnce({ ok: true, data: { channel_id: 'ch_1', status: 'disconnected' } });
    const result = await createWechatChannel();
    expect(result.status).toBe('disconnected');
  });

  it('starts connect and returns qr info', async () => {
    postMock.mockResolvedValueOnce({ ok: true, data: { channel_id: 'ch_1', status: 'pending', connect_url: 'https://liteapp.weixin.qq.com/q/demo' } });
    const result = await startWechatConnect();
    expect(result.connect_url).toContain('liteapp.weixin.qq.com');
  });

  it('archives the channel', async () => {
    deleteMock.mockResolvedValueOnce({ ok: true, data: { channel_id: 'ch_1', status: 'archived' } });
    const result = await archiveWechatChannel();
    expect(result.status).toBe('archived');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir gateway/packages/web exec vitest run lib/coke-user-wechat-channel.test.ts`
Expected: FAIL with missing helper module.

- [ ] **Step 3: Implement the lifecycle helper and page state machine**

```ts
// gateway/packages/web/lib/coke-user-wechat-channel.ts
import type { ApiResponse } from '@clawscale/shared';
import { cokeUserApi } from '@/lib/coke-user-api';

export type WechatChannelState =
  | { status: 'missing' }
  | { status: 'disconnected'; channel_id: string }
  | { status: 'pending'; channel_id: string; connect_url: string | null; qr?: string | null }
  | { status: 'connected'; channel_id: string }
  | { status: 'error'; channel_id: string }
  | { status: 'archived'; channel_id: string };

export async function createWechatChannel() {
  const res = await cokeUserApi.post<ApiResponse<WechatChannelState>>('/user/wechat-channel');
  return res.data;
}

export async function startWechatConnect() {
  const res = await cokeUserApi.post<ApiResponse<WechatChannelState>>('/user/wechat-channel/connect');
  return res.data;
}

export async function getWechatChannelStatus() {
  const res = await cokeUserApi.get<ApiResponse<WechatChannelState>>('/user/wechat-channel/status');
  return res.data;
}

export async function disconnectWechatChannel() {
  const res = await cokeUserApi.post<ApiResponse<WechatChannelState>>('/user/wechat-channel/disconnect');
  return res.data;
}

export async function archiveWechatChannel() {
  const res = await cokeUserApi.delete<ApiResponse<WechatChannelState>>('/user/wechat-channel');
  return res.data;
}
```

```tsx
// gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.tsx
// Replace bind-session boot with:
// - show "Create my WeChat channel" when status is missing
// - show "Connect WeChat" when disconnected
// - show QR when pending
// - show connected card when connected
// - show reconnect / delete actions when error
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir gateway/packages/web exec vitest run lib/coke-user-wechat-channel.test.ts`
Expected: PASS

- [ ] **Step 5: Run focused web smoke tests**

Run: `pnpm --dir gateway/packages/web exec vitest run lib/coke-user-auth.test.ts lib/coke-user-api.test.ts lib/coke-user-wechat-channel.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add gateway/packages/web/lib/coke-user-wechat-channel.ts gateway/packages/web/lib/coke-user-wechat-channel.test.ts gateway/packages/web/app/'(coke-user)'/coke/bind-wechat/page.tsx gateway/packages/web/app/'(coke-user)'/coke/login/page.tsx gateway/packages/web/app/'(coke-user)'/coke/register/page.tsx docs/clawscale_bridge.md
git commit -m "feat(web): replace wechat bind ui with personal channel flow"
```

## Task 6: Document migration gate and final verification

**Files:**
- Modify: `connector/clawscale_bridge/backfill_clawscale_users.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_backfill_clawscale_users.py`
- Modify: `docs/clawscale_bridge.md`
- Modify: `docs/superpowers/specs/2026-04-07-wechat-personal-per-user-channel-design.md`

- [ ] **Step 1: Write the failing migration-gate test**

```python
def test_reset_shared_wechat_bindings_requires_explicit_confirmation(monkeypatch):
    from connector.clawscale_bridge.backfill_clawscale_users import require_personal_wechat_reset_confirmation

    monkeypatch.delenv('ALLOW_WECHAT_PERSONAL_RESET', raising=False)

    with pytest.raises(RuntimeError):
        require_personal_wechat_reset_confirmation()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/unit/connector/clawscale_bridge/test_backfill_clawscale_users.py -v`
Expected: FAIL with missing confirmation helper.

- [ ] **Step 3: Add the explicit operator gate and docs**

```python
# connector/clawscale_bridge/backfill_clawscale_users.py
import os


def require_personal_wechat_reset_confirmation():
    if os.getenv('ALLOW_WECHAT_PERSONAL_RESET') != 'yes':
        raise RuntimeError('personal_wechat_reset_confirmation_required')
```

Update `docs/clawscale_bridge.md` to document:

- shared WeChat onboarding is frozen
- new personal WeChat onboarding path
- operator confirmation required before destructive reset
- no rollback to legacy shared-bind ownership after reset

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/unit/connector/clawscale_bridge/test_backfill_clawscale_users.py -v`
Expected: PASS

- [ ] **Step 5: Run final verification for all touched suites**

Run:

```bash
./.venv/bin/pytest \
  tests/unit/dao/test_external_identity_dao.py \
  tests/unit/connector/clawscale_bridge/test_identity_service.py \
  tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py \
  tests/unit/connector/clawscale_bridge/test_gateway_personal_channel_client.py \
  tests/unit/connector/clawscale_bridge/test_personal_wechat_channel_service.py \
  tests/unit/connector/clawscale_bridge/test_bridge_app.py \
  tests/unit/connector/clawscale_bridge/test_backfill_clawscale_users.py -v

pnpm --dir gateway/packages/api exec vitest run \
  src/lib/personal-wechat-channel.test.ts \
  src/routes/user-wechat-channel.test.ts \
  src/lib/route-message.test.ts \
  src/adapters/wechat.test.ts

pnpm --dir gateway/packages/web exec vitest run \
  lib/coke-user-auth.test.ts \
  lib/coke-user-api.test.ts \
  lib/coke-user-wechat-channel.test.ts
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add connector/clawscale_bridge/backfill_clawscale_users.py tests/unit/connector/clawscale_bridge/test_backfill_clawscale_users.py docs/clawscale_bridge.md
git commit -m "docs(migration): gate shared wechat reset for personal channel rollout"
```
