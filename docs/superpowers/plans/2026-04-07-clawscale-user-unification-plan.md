# Clawscale User Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tenant-scoped `ClawscaleUser` identity layer so one Coke account can own multiple channel-specific `EndUser` identities without changing Clawscale `Member` semantics.

**Architecture:** Make `ClawscaleUser` the canonical unified end-user record in the gateway Postgres schema and attach each `EndUser` to it. Keep Coke as the business-account owner by adding an internal gateway bind API that the Coke bridge calls after account binding, then update routing to prefer `clawscale_user_id` while keeping `linkedTo` as a temporary fallback for historical records.

**Tech Stack:** Python 3.12, Flask, requests, PyMongo, pytest, PostgreSQL, Prisma, TypeScript, Hono, Next.js, Vitest, pnpm

---

## File Structure

### New gateway files

- `gateway/packages/api/src/lib/clawscale-user.ts`
  Owns gateway-side `ClawscaleUser` upsert, bind conflict checks, and unified conversation lookup.
- `gateway/packages/api/src/lib/clawscale-user.test.ts`
  Covers gateway-side binding and unified-history helpers.
- `gateway/packages/api/src/routes/coke-bindings.ts`
  Internal authenticated route used by Coke bridge to bind `EndUser` to `ClawscaleUser`.
- `gateway/packages/api/src/routes/coke-bindings.test.ts`
  Verifies auth, success response, and conflict behavior for the internal bind route.
- `gateway/packages/api/src/routes/end-users.test.ts`
  Verifies the admin list API includes unified-user fields.

### Modified gateway files

- `gateway/packages/api/prisma/schema.prisma`
  Adds `ClawscaleUser`, adds `end_users.clawscale_user_id`, and keeps `linked_to` only for compatibility.
- `gateway/packages/api/src/index.ts`
  Mounts the new internal bind route.
- `gateway/packages/api/src/lib/route-message.ts`
  Resolves unified history via `clawscale_user_id` first, then falls back to `linkedTo`.
- `gateway/packages/api/src/lib/route-message.test.ts`
  Adds coverage for unified metadata and cross-channel history lookup.
- `gateway/packages/api/src/routes/end-users.ts`
  Returns `clawscaleUserId` and `clawscaleUser.cokeAccountId` for dashboard inspection.
- `gateway/packages/shared/src/types/conversation.ts`
  Adds unified-user fields to shared end-user types.
- `gateway/packages/web/app/(dashboard)/end-users/page.tsx`
  Replaces the current `Linked` UI with unified-user visibility.

### New Coke bridge files

- `connector/clawscale_bridge/gateway_identity_client.py`
  POST client for the gateway internal bind API.
- `connector/clawscale_bridge/backfill_clawscale_users.py`
  One-off operational backfill for existing active `external_identities`.
- `tests/unit/connector/clawscale_bridge/test_gateway_identity_client.py`
  Verifies gateway bind requests and failure handling.
- `tests/unit/connector/clawscale_bridge/test_backfill_clawscale_users.py`
  Verifies the backfill script skips already-synced records and updates unsynced ones.

### Modified Coke bridge files

- `dao/external_identity_dao.py`
  Stores `clawscale_user_id`, supports multi-identity lookups, and keeps primary push targeting.
- `tests/unit/dao/test_external_identity_dao.py`
  Covers the new index and sync update helper.
- `connector/clawscale_bridge/wechat_bind_session_service.py`
  Syncs gateway identity before local activation and stops rejecting additional identities for the same account.
- `tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py`
  Covers gateway sync and the new multi-identity behavior.
- `connector/clawscale_bridge/identity_service.py`
  Trusts `metadata.cokeAccountId` from the gateway when present and falls back to Mongo lookup otherwise.
- `tests/unit/connector/clawscale_bridge/test_identity_service.py`
  Covers direct gateway-bound routing and legacy fallback.
- `connector/clawscale_bridge/app.py`
  Wires the gateway identity client into the bind-session service.
- `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
  Verifies app wiring for the new gateway sync dependency.
- `conf/config.json`
  Adds bridge config for the gateway identity API.

### Docs

- `docs/clawscale_bridge.md`
  Documents the new env vars, migration steps, and backfill command.

## Compatibility Rules

- `Member` remains the dashboard/operator identity. Do not reuse or rename it.
- `EndUser.linkedTo` remains readable during migration, but no new feature logic should depend on it when `clawscale_user_id` is present.
- `external_identities.is_primary_push_target` stays in place for outbound delivery. The newest successful bind remains the primary push target unless product requirements change later.
- Gateway events should start sending both `clawscaleUserId` and `cokeAccountId` when a bind exists, but the Coke bridge must continue to support legacy metadata that only has the external tuple.

### Task 1: Add The Gateway `ClawscaleUser` Model And Internal Bind API

**Files:**
- Create: `gateway/packages/api/src/lib/clawscale-user.ts`
- Create: `gateway/packages/api/src/lib/clawscale-user.test.ts`
- Create: `gateway/packages/api/src/routes/coke-bindings.ts`
- Create: `gateway/packages/api/src/routes/coke-bindings.test.ts`
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Modify: `gateway/packages/api/src/index.ts`

- [ ] **Step 1: Write the failing gateway binding tests**

```ts
// gateway/packages/api/src/lib/clawscale-user.test.ts
import { beforeEach, describe, expect, it, vi } from 'vitest';

const db = vi.hoisted(() => ({
  clawscaleUser: {
    upsert: vi.fn(),
  },
  endUser: {
    findUnique: vi.fn(),
    update: vi.fn(),
  },
  conversation: {
    findMany: vi.fn(),
  },
}));

vi.mock('../db/index.js', () => ({ db }));

import { bindEndUserToCokeAccount, getUnifiedConversationIds } from './clawscale-user.js';

describe('bindEndUserToCokeAccount', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    db.endUser.findUnique.mockResolvedValue({
      id: 'eu_1',
      tenantId: 'ten_1',
      channelId: 'ch_1',
      externalId: 'wxid_123',
      clawscaleUserId: null,
    });
    db.clawscaleUser.upsert.mockResolvedValue({
      id: 'csu_1',
      tenantId: 'ten_1',
      cokeAccountId: 'acc_1',
    });
    db.endUser.update.mockResolvedValue({
      id: 'eu_1',
      clawscaleUserId: 'csu_1',
    });
  });

  it('upserts a tenant-scoped clawscale user and attaches the end user', async () => {
    const result = await bindEndUserToCokeAccount({
      tenantId: 'ten_1',
      channelId: 'ch_1',
      externalId: 'wxid_123',
      cokeAccountId: 'acc_1',
    });

    expect(db.clawscaleUser.upsert).toHaveBeenCalledWith(
      expect.objectContaining({
        where: {
          tenantId_cokeAccountId: {
            tenantId: 'ten_1',
            cokeAccountId: 'acc_1',
          },
        },
      }),
    );
    expect(db.endUser.update).toHaveBeenCalledWith({
      where: { id: 'eu_1' },
      data: { clawscaleUserId: 'csu_1' },
    });
    expect(result).toEqual({
      clawscaleUserId: 'csu_1',
      endUserId: 'eu_1',
      cokeAccountId: 'acc_1',
    });
  });

  it('throws a conflict when the end user already belongs to another clawscale user', async () => {
    db.endUser.findUnique.mockResolvedValueOnce({
      id: 'eu_1',
      tenantId: 'ten_1',
      channelId: 'ch_1',
      externalId: 'wxid_123',
      clawscaleUserId: 'csu_other',
    });
    db.clawscaleUser.upsert.mockResolvedValueOnce({
      id: 'csu_1',
      tenantId: 'ten_1',
      cokeAccountId: 'acc_1',
    });

    await expect(
      bindEndUserToCokeAccount({
        tenantId: 'ten_1',
        channelId: 'ch_1',
        externalId: 'wxid_123',
        cokeAccountId: 'acc_1',
      }),
    ).rejects.toThrow('end_user_already_bound');
  });
});

describe('getUnifiedConversationIds', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns all conversations for the same clawscale user', async () => {
    db.conversation.findMany.mockResolvedValue([
      { id: 'conv_1' },
      { id: 'conv_2' },
    ]);

    const ids = await getUnifiedConversationIds({
      tenantId: 'ten_1',
      endUserId: 'eu_1',
      clawscaleUserId: 'csu_1',
      linkedTo: null,
    });

    expect(db.conversation.findMany).toHaveBeenCalledWith({
      where: {
        endUser: {
          tenantId: 'ten_1',
          clawscaleUserId: 'csu_1',
        },
      },
      select: { id: true },
    });
    expect(ids).toEqual(['conv_1', 'conv_2']);
  });
});

// gateway/packages/api/src/routes/coke-bindings.test.ts
import { Hono } from 'hono';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const bindEndUserToCokeAccount = vi.hoisted(() => vi.fn());

vi.mock('../lib/clawscale-user.js', () => ({ bindEndUserToCokeAccount }));

import { cokeBindingsRouter } from './coke-bindings.js';

describe('cokeBindingsRouter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env['CLAWSCALE_IDENTITY_API_KEY'] = 'identity-test-key';
  });

  it('rejects missing auth', async () => {
    const app = new Hono().route('/api/internal/coke-bindings', cokeBindingsRouter);

    const res = await app.request('/api/internal/coke-bindings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant_id: 'ten_1',
        channel_id: 'ch_1',
        external_id: 'wxid_123',
        coke_account_id: 'acc_1',
      }),
    });

    expect(res.status).toBe(401);
  });

  it('returns the unified identity payload after a successful bind', async () => {
    bindEndUserToCokeAccount.mockResolvedValue({
      clawscaleUserId: 'csu_1',
      endUserId: 'eu_1',
      cokeAccountId: 'acc_1',
    });

    const app = new Hono().route('/api/internal/coke-bindings', cokeBindingsRouter);

    const res = await app.request('/api/internal/coke-bindings', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer identity-test-key',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        tenant_id: 'ten_1',
        channel_id: 'ch_1',
        external_id: 'wxid_123',
        coke_account_id: 'acc_1',
      }),
    });

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      ok: true,
      data: {
        clawscale_user_id: 'csu_1',
        end_user_id: 'eu_1',
        coke_account_id: 'acc_1',
      },
    });
  });
});
```

- [ ] **Step 2: Run the gateway binding tests to verify they fail**

Run: `pnpm --dir gateway/packages/api exec vitest run src/lib/clawscale-user.test.ts src/routes/coke-bindings.test.ts`

Expected: FAIL with `Cannot find module './clawscale-user.js'`, `Cannot find module './coke-bindings.js'`, and Prisma model/type failures because `clawscaleUser` does not exist yet.

- [ ] **Step 3: Add the gateway schema, helper, and route**

```prisma
// gateway/packages/api/prisma/schema.prisma
model Tenant {
  id        String     @id
  slug      String     @unique
  name      String
  settings  Json       @default("{}")
  createdAt DateTime   @default(now()) @map("created_at")
  updatedAt DateTime   @updatedAt @map("updated_at")

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

model ClawscaleUser {
  id            String   @id
  tenantId      String   @map("tenant_id")
  cokeAccountId String   @map("coke_account_id")
  status        String   @default("active")
  createdAt     DateTime @default(now()) @map("created_at")
  updatedAt     DateTime @updatedAt @map("updated_at")

  tenant   Tenant    @relation(fields: [tenantId], references: [id], onDelete: Cascade)
  endUsers EndUser[]

  @@unique([tenantId, cokeAccountId])
  @@index([tenantId])
  @@map("clawscale_users")
}

model EndUser {
  id              String        @id
  tenantId        String        @map("tenant_id")
  channelId       String        @map("channel_id")
  externalId      String        @map("external_id")
  name            String?
  email           String?
  metadata        Json          @default("{}")
  status          EndUserStatus @default(allowed)
  createdAt       DateTime      @default(now()) @map("created_at")
  updatedAt       DateTime      @updatedAt @map("updated_at")
  linkedTo        String?       @map("linked_to")
  clawscaleUserId String?       @map("clawscale_user_id")

  tenant          Tenant         @relation(fields: [tenantId], references: [id], onDelete: Cascade)
  channel         Channel        @relation(fields: [channelId], references: [id], onDelete: Cascade)
  linkedPrimary   EndUser?       @relation("EndUserLink", fields: [linkedTo], references: [id], onDelete: SetNull)
  linkedFrom      EndUser[]      @relation("EndUserLink")
  clawscaleUser   ClawscaleUser? @relation(fields: [clawscaleUserId], references: [id], onDelete: SetNull)
  conversations   Conversation[]
  activeBackends  EndUserBackend[]
  linkCodes       LinkCode[]

  @@unique([tenantId, channelId, externalId])
  @@index([tenantId])
  @@index([clawscaleUserId])
  @@map("end_users")
}
```

```ts
// gateway/packages/api/src/lib/clawscale-user.ts
import { db } from '../db/index.js';
import { generateId } from './id.js';

export async function bindEndUserToCokeAccount(input: {
  tenantId: string;
  channelId: string;
  externalId: string;
  cokeAccountId: string;
}) {
  const endUser = await db.endUser.findUnique({
    where: {
      tenantId_channelId_externalId: {
        tenantId: input.tenantId,
        channelId: input.channelId,
        externalId: input.externalId,
      },
    },
  });

  if (!endUser) {
    throw new Error('end_user_not_found');
  }

  const clawscaleUser = await db.clawscaleUser.upsert({
    where: {
      tenantId_cokeAccountId: {
        tenantId: input.tenantId,
        cokeAccountId: input.cokeAccountId,
      },
    },
    create: {
      id: generateId('csu'),
      tenantId: input.tenantId,
      cokeAccountId: input.cokeAccountId,
    },
    update: {},
  });

  if (endUser.clawscaleUserId && endUser.clawscaleUserId !== clawscaleUser.id) {
    throw new Error('end_user_already_bound');
  }

  const updated = await db.endUser.update({
    where: { id: endUser.id },
    data: { clawscaleUserId: clawscaleUser.id },
  });

  return {
    clawscaleUserId: clawscaleUser.id,
    endUserId: updated.id,
    cokeAccountId: clawscaleUser.cokeAccountId,
  };
}

export async function getUnifiedConversationIds(input: {
  tenantId: string;
  endUserId: string;
  clawscaleUserId: string | null;
  linkedTo: string | null;
}) {
  if (input.clawscaleUserId) {
    const rows = await db.conversation.findMany({
      where: {
        endUser: {
          tenantId: input.tenantId,
          clawscaleUserId: input.clawscaleUserId,
        },
      },
      select: { id: true },
    });
    return rows.map((row) => row.id);
  }

  const primaryId = input.linkedTo ?? input.endUserId;
  const rows = await db.conversation.findMany({
    where: {
      endUser: {
        tenantId: input.tenantId,
        OR: [{ id: primaryId }, { linkedTo: primaryId }],
      },
    },
    select: { id: true },
  });
  return rows.map((row) => row.id);
}
```

```ts
// gateway/packages/api/src/routes/coke-bindings.ts
import { Hono } from 'hono';
import { z } from 'zod';
import { bindEndUserToCokeAccount } from '../lib/clawscale-user.js';

const bodySchema = z.object({
  tenant_id: z.string().min(1),
  channel_id: z.string().min(1),
  external_id: z.string().min(1),
  coke_account_id: z.string().min(1),
});

export const cokeBindingsRouter = new Hono();

cokeBindingsRouter.post('/', async (c) => {
  const expected = process.env['CLAWSCALE_IDENTITY_API_KEY'] ?? '';
  if (c.req.header('Authorization') !== `Bearer ${expected}`) {
    return c.json({ ok: false, error: 'unauthorized' }, 401);
  }

  const body = bodySchema.parse(await c.req.json());

  try {
    const result = await bindEndUserToCokeAccount({
      tenantId: body.tenant_id,
      channelId: body.channel_id,
      externalId: body.external_id,
      cokeAccountId: body.coke_account_id,
    });
    return c.json({
      ok: true,
      data: {
        clawscale_user_id: result.clawscaleUserId,
        end_user_id: result.endUserId,
        coke_account_id: result.cokeAccountId,
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'unknown_error';
    if (message === 'end_user_not_found') {
      return c.json({ ok: false, error: message }, 404);
    }
    if (message === 'end_user_already_bound') {
      return c.json({ ok: false, error: message }, 409);
    }
    throw error;
  }
});
```

```ts
// gateway/packages/api/src/index.ts
import { cokeBindingsRouter } from './routes/coke-bindings.js';

app.route('/api/internal/coke-bindings', cokeBindingsRouter);
```

- [ ] **Step 4: Regenerate Prisma client and run the gateway binding tests**

Run: `pnpm --dir gateway/packages/api db:generate && pnpm --dir gateway/packages/api exec vitest run src/lib/clawscale-user.test.ts src/routes/coke-bindings.test.ts`

Expected: PASS for the new binding helper and route tests.

- [ ] **Step 5: Commit the gateway schema and bind API**

```bash
git add gateway/packages/api/prisma/schema.prisma \
  gateway/packages/api/src/lib/clawscale-user.ts \
  gateway/packages/api/src/lib/clawscale-user.test.ts \
  gateway/packages/api/src/routes/coke-bindings.ts \
  gateway/packages/api/src/routes/coke-bindings.test.ts \
  gateway/packages/api/src/index.ts
git commit -m "feat(gateway): add clawscale user binding model"
```

### Task 2: Switch Gateway Routing And Dashboard APIs To Unified Identity

**Files:**
- Modify: `gateway/packages/api/src/lib/clawscale-user.ts`
- Modify: `gateway/packages/api/src/lib/route-message.ts`
- Modify: `gateway/packages/api/src/lib/route-message.test.ts`
- Modify: `gateway/packages/api/src/routes/end-users.ts`
- Create: `gateway/packages/api/src/routes/end-users.test.ts`
- Modify: `gateway/packages/shared/src/types/conversation.ts`
- Modify: `gateway/packages/web/app/(dashboard)/end-users/page.tsx`

- [ ] **Step 1: Write the failing routing and admin API tests**

```ts
// gateway/packages/api/src/lib/route-message.test.ts
import { beforeEach, describe, expect, it, vi } from 'vitest';

const db = vi.hoisted(() => ({
  channel: { findUnique: vi.fn() },
  tenant: { findUnique: vi.fn() },
  endUser: { findUnique: vi.fn(), create: vi.fn(), update: vi.fn() },
  conversation: { findFirst: vi.fn(), create: vi.fn(), update: vi.fn(), findMany: vi.fn() },
  message: { create: vi.fn(), findMany: vi.fn() },
  aiBackend: { findMany: vi.fn() },
  endUserBackend: { upsert: vi.fn(), deleteMany: vi.fn() },
}));

const generateReply = vi.hoisted(() => vi.fn());

vi.mock('../db/index.js', () => ({ db }));
vi.mock('./ai-backend.js', () => ({ generateReply }));
vi.mock('./clawscale-agent.js', () => ({
  buildSelectionMenu: vi.fn(() => 'menu'),
  runClawscaleAgent: vi.fn(),
}));

import { routeInboundMessage } from './route-message.js';

describe('routeInboundMessage unified identity', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    db.channel.findUnique.mockResolvedValue({ id: 'ch_1', tenantId: 'ten_1', status: 'connected' });
    db.tenant.findUnique.mockResolvedValue({ id: 'ten_1', settings: {} });
    db.endUser.findUnique.mockResolvedValue({
      id: 'eu_1',
      tenantId: 'ten_1',
      channelId: 'ch_1',
      externalId: 'wxid_123',
      name: 'Alice',
      status: 'allowed',
      linkedTo: null,
      clawscaleUserId: 'csu_1',
      clawscaleUser: { id: 'csu_1', cokeAccountId: 'acc_1' },
      activeBackends: [],
    });
    db.conversation.findFirst.mockResolvedValue({
      id: 'conv_1',
      tenantId: 'ten_1',
      channelId: 'ch_1',
      endUserId: 'eu_1',
    });
    db.conversation.findMany.mockResolvedValue([{ id: 'conv_1' }, { id: 'conv_2' }]);
    db.message.create.mockResolvedValue({});
    db.message.findMany.mockResolvedValue([]);
    db.aiBackend.findMany.mockResolvedValue([
      {
        id: 'ab_1',
        tenantId: 'ten_1',
        name: 'Coke Bridge',
        type: 'custom',
        config: { baseUrl: 'http://127.0.0.1:8090/bridge/inbound', responseFormat: 'json-auto' },
        isActive: true,
        isDefault: true,
      },
    ]);
    db.endUserBackend.upsert.mockResolvedValue({});
    db.endUserBackend.deleteMany.mockResolvedValue({});
    db.conversation.update.mockResolvedValue({});
    generateReply.mockResolvedValue('bridge ok');
  });

  it('sends clawscale user metadata and uses unified history', async () => {
    await routeInboundMessage({
      channelId: 'ch_1',
      externalId: 'wxid_123',
      displayName: 'Alice',
      text: '在吗',
      meta: { platform: 'wechat_personal' },
    });

    expect(db.conversation.findMany).toHaveBeenCalledWith({
      where: {
        endUser: {
          tenantId: 'ten_1',
          clawscaleUserId: 'csu_1',
        },
      },
      select: { id: true },
    });
    expect(generateReply).toHaveBeenCalledWith(
      expect.objectContaining({
        metadata: expect.objectContaining({
          tenantId: 'ten_1',
          channelId: 'ch_1',
          endUserId: 'eu_1',
          externalId: 'wxid_123',
          clawscaleUserId: 'csu_1',
          cokeAccountId: 'acc_1',
        }),
      }),
    );
  });
});

// gateway/packages/api/src/routes/end-users.test.ts
import { Hono } from 'hono';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const db = vi.hoisted(() => ({
  endUser: {
    findMany: vi.fn(),
    count: vi.fn(),
  },
}));

vi.mock('../db/index.js', () => ({ db }));
vi.mock('../middleware/auth.js', () => ({
  requireAuth: async (c: any, next: any) => {
    c.set('auth', { tenantId: 'ten_1', userId: 'mem_1', role: 'admin' });
    await next();
  },
}));

import { endUsersRouter } from './end-users.js';

describe('endUsersRouter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    db.endUser.findMany.mockResolvedValue([
      {
        id: 'eu_1',
        tenantId: 'ten_1',
        channelId: 'ch_1',
        externalId: 'wxid_123',
        name: 'Alice',
        email: null,
        status: 'allowed',
        linkedTo: null,
        clawscaleUserId: 'csu_1',
        clawscaleUser: { id: 'csu_1', cokeAccountId: 'acc_1' },
        createdAt: '2026-04-07T00:00:00.000Z',
        updatedAt: '2026-04-07T00:00:00.000Z',
        channel: { name: 'WeChat Personal', type: 'wechat_personal' },
        _count: { conversations: 2 },
      },
    ]);
    db.endUser.count.mockResolvedValue(1);
  });

  it('returns unified identity fields for dashboard rows', async () => {
    const app = new Hono().route('/api/end-users', endUsersRouter);
    const res = await app.request('/api/end-users');
    const json = await res.json();

    expect(res.status).toBe(200);
    expect(json.data.rows[0]).toMatchObject({
      id: 'eu_1',
      clawscaleUserId: 'csu_1',
      clawscaleUser: { id: 'csu_1', cokeAccountId: 'acc_1' },
    });
  });
});
```

- [ ] **Step 2: Run the gateway routing tests to verify they fail**

Run: `pnpm --dir gateway/packages/api exec vitest run src/lib/route-message.test.ts src/routes/end-users.test.ts`

Expected: FAIL because `route-message.ts` does not yet include `clawscaleUserId` metadata or unified conversation lookup, and `end-users.ts` does not yet select unified-user fields.

- [ ] **Step 3: Implement unified routing and dashboard visibility**

```ts
// gateway/packages/api/src/lib/route-message.ts
import { getUnifiedConversationIds } from './clawscale-user.js';

// inside routeInboundMessage, when loading or creating the end user
let endUser = await db.endUser.findUnique({
  where: {
    tenantId_channelId_externalId: {
      tenantId,
      channelId,
      externalId,
    },
  },
  include: {
    activeBackends: true,
    clawscaleUser: {
      select: {
        id: true,
        cokeAccountId: true,
      },
    },
  },
});

if (!endUser) {
  endUser = await db.endUser.create({
    data: {
      id: generateId('eu'),
      tenantId,
      channelId,
      externalId,
      name: displayName ?? null,
    },
    include: {
      activeBackends: true,
      clawscaleUser: {
        select: {
          id: true,
          cokeAccountId: true,
        },
      },
    },
  });
}

const historyConvIds = await getUnifiedConversationIds({
  tenantId,
  endUserId: endUser.id,
  clawscaleUserId: endUser.clawscaleUserId ?? null,
  linkedTo: endUser.linkedTo ?? null,
});

return generateReply({
  backend: {
    type: backend.type as AiBackendType,
    config: cfg,
    ...(backend.type === 'palmos' && palmosCtx ? { palmosCtx } : {}),
  },
  history,
  sender: meta?.sender,
  platform: meta?.platform,
  metadata: {
    ...metadata,
    ...(endUser.clawscaleUserId ? { clawscaleUserId: endUser.clawscaleUserId } : {}),
    ...(endUser.clawscaleUser?.cokeAccountId
      ? { cokeAccountId: endUser.clawscaleUser.cokeAccountId }
      : {}),
  },
});
```

```ts
// gateway/packages/api/src/routes/end-users.ts
const endUserSelect = {
  id: true,
  tenantId: true,
  channelId: true,
  externalId: true,
  name: true,
  email: true,
  status: true,
  linkedTo: true,
  clawscaleUserId: true,
  clawscaleUser: {
    select: {
      id: true,
      cokeAccountId: true,
    },
  },
  createdAt: true,
  updatedAt: true,
  channel: { select: { name: true, type: true } },
  _count: { select: { conversations: true } },
} as const;
```

```ts
// gateway/packages/shared/src/types/conversation.ts
export interface EndUser {
  id: string;
  tenantId: string;
  channelId: string;
  externalId: string;
  name: string | null;
  email: string | null;
  status: EndUserStatus;
  clawscaleUserId?: string | null;
  clawscaleUser?: {
    id: string;
    cokeAccountId: string;
  } | null;
  createdAt: string;
  updatedAt: string;
}
```

```tsx
// gateway/packages/web/app/(dashboard)/end-users/page.tsx
interface EndUser {
  id: string;
  tenantId: string;
  channelId: string;
  externalId: string;
  name: string | null;
  email: string | null;
  status: 'allowed' | 'blocked';
  linkedTo: string | null;
  clawscaleUserId: string | null;
  clawscaleUser: { id: string; cokeAccountId: string } | null;
  createdAt: string;
  updatedAt: string;
  channel: { name: string; type: string };
  _count: { conversations: number };
}

// replace the "Linked" column
<th className="px-5 py-3 text-left font-medium text-gray-500">Unified User</th>

<td className="px-5 py-3.5">
  {u.clawscaleUserId ? (
    <div className="text-xs">
      <p className="font-mono text-gray-900">{u.clawscaleUserId}</p>
      <p className="text-gray-400 font-mono">{u.clawscaleUser?.cokeAccountId}</p>
    </div>
  ) : u.linkedTo ? (
    <span className="flex items-center gap-1 text-amber-600 text-xs">
      <Link2 className="h-3.5 w-3.5" /> Legacy link only
    </span>
  ) : (
    <span className="text-gray-400 text-xs">Unbound</span>
  )}
</td>
```

- [ ] **Step 4: Run the gateway routing and dashboard API tests**

Run: `pnpm --dir gateway/packages/api exec vitest run src/lib/route-message.test.ts src/routes/end-users.test.ts`

Expected: PASS, with backend metadata now including `clawscaleUserId` and `cokeAccountId`.

- [ ] **Step 5: Commit the gateway unified-routing changes**

```bash
git add gateway/packages/api/src/lib/clawscale-user.ts \
  gateway/packages/api/src/lib/route-message.ts \
  gateway/packages/api/src/lib/route-message.test.ts \
  gateway/packages/api/src/routes/end-users.ts \
  gateway/packages/api/src/routes/end-users.test.ts \
  gateway/packages/shared/src/types/conversation.ts \
  'gateway/packages/web/app/(dashboard)/end-users/page.tsx'
git commit -m "feat(gateway): route end users via unified clawscale users"
```

### Task 3: Sync Gateway Identity Into The Coke Bridge And Preserve Multi-Channel Bindings

**Files:**
- Create: `connector/clawscale_bridge/gateway_identity_client.py`
- Create: `tests/unit/connector/clawscale_bridge/test_gateway_identity_client.py`
- Modify: `dao/external_identity_dao.py`
- Modify: `tests/unit/dao/test_external_identity_dao.py`
- Modify: `connector/clawscale_bridge/wechat_bind_session_service.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py`
- Modify: `connector/clawscale_bridge/identity_service.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_identity_service.py`
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- Modify: `conf/config.json`

- [ ] **Step 1: Write the failing Coke bridge tests**

```python
# tests/unit/dao/test_external_identity_dao.py
from unittest.mock import MagicMock


def test_external_identity_indexes_include_clawscale_user_lookup():
    from dao.external_identity_dao import ExternalIdentityDAO

    dao = ExternalIdentityDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()

    dao.create_indexes()

    dao.collection.create_index.assert_any_call([("clawscale_user_id", 1)])


def test_set_clawscale_user_id_updates_existing_identity_tuple():
    from dao.external_identity_dao import ExternalIdentityDAO

    dao = ExternalIdentityDAO(mongo_uri="mongodb://example", db_name="test")
    dao.collection = MagicMock()

    dao.set_clawscale_user_id(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
        clawscale_user_id="csu_1",
        now_ts=1775472000,
    )

    dao.collection.update_one.assert_called_once_with(
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
        },
        {
            "$set": {
                "clawscale_user_id": "csu_1",
                "updated_at": 1775472000,
            }
        },
    )


# tests/unit/connector/clawscale_bridge/test_gateway_identity_client.py
from unittest.mock import MagicMock


def test_bind_end_user_posts_expected_payload_and_returns_data():
    from connector.clawscale_bridge.gateway_identity_client import GatewayIdentityClient

    session = MagicMock()
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "ok": True,
        "data": {
            "clawscale_user_id": "csu_1",
            "end_user_id": "eu_1",
            "coke_account_id": "acc_1",
        },
    }
    session.post.return_value = response

    client = GatewayIdentityClient(
        session=session,
        identity_api_url="https://gateway.local/api/internal/coke-bindings",
        identity_api_key="identity-key",
    )

    result = client.bind_end_user(
        tenant_id="ten_1",
        channel_id="ch_1",
        external_id="wxid_123",
        coke_account_id="acc_1",
    )

    assert result["clawscale_user_id"] == "csu_1"
    session.post.assert_called_once_with(
        "https://gateway.local/api/internal/coke-bindings",
        json={
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "external_id": "wxid_123",
            "coke_account_id": "acc_1",
        },
        headers={"Authorization": "Bearer identity-key"},
        timeout=15,
    )


# tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py
from unittest.mock import MagicMock


def test_consume_matching_session_syncs_gateway_before_local_identity_activation():
    from connector.clawscale_bridge.wechat_bind_session_service import WechatBindSessionService

    bind_session_dao = MagicMock()
    bind_session_dao.find_active_session_by_bind_token.return_value = {
        "session_id": "bs_1",
        "account_id": "acc_1",
        "bind_token": "ctx_bind_123",
        "status": "pending",
        "expires_at": 1775472600,
    }
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity.return_value = None
    external_identity_dao.activate_identity.return_value = {
        "account_id": "acc_1",
        "external_end_user_id": "wxid_123",
        "status": "active",
    }
    gateway_identity_client = MagicMock()
    gateway_identity_client.bind_end_user.return_value = {
        "clawscale_user_id": "csu_1",
        "end_user_id": "eu_1",
        "coke_account_id": "acc_1",
    }

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
        bind_base_url="https://bridge.coke.local",
        public_connect_url_template="https://placeholder.invalid/?bind_token={bind_token}",
        ttl_seconds=600,
    )

    identity = service.consume_matching_session(
        bind_token="ctx_bind_123",
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
        now_ts=1775472000,
    )

    assert identity["account_id"] == "acc_1"
    gateway_identity_client.bind_end_user.assert_called_once_with(
        tenant_id="ten_1",
        channel_id="ch_1",
        external_id="wxid_123",
        coke_account_id="acc_1",
    )
    external_identity_dao.set_clawscale_user_id.assert_called_once_with(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_1",
        platform="wechat_personal",
        external_end_user_id="wxid_123",
        clawscale_user_id="csu_1",
        now_ts=1775472000,
    )


def test_consume_matching_session_allows_another_identity_for_same_account():
    from connector.clawscale_bridge.wechat_bind_session_service import WechatBindSessionService

    bind_session_dao = MagicMock()
    bind_session_dao.find_active_session_by_bind_token.return_value = {
        "session_id": "bs_1",
        "account_id": "acc_1",
        "bind_token": "ctx_bind_123",
        "status": "pending",
        "expires_at": 1775472600,
    }
    external_identity_dao = MagicMock()
    external_identity_dao.find_active_identity.return_value = None
    external_identity_dao.find_active_identity_for_account.return_value = {
        "account_id": "acc_1",
        "external_end_user_id": "wxid_existing",
        "status": "active",
    }
    external_identity_dao.activate_identity.return_value = {
        "account_id": "acc_1",
        "external_end_user_id": "tg_456",
        "status": "active",
    }
    gateway_identity_client = MagicMock()
    gateway_identity_client.bind_end_user.return_value = {
      "clawscale_user_id": "csu_1",
      "end_user_id": "eu_2",
      "coke_account_id": "acc_1",
    }

    service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
        bind_base_url="https://bridge.coke.local",
        public_connect_url_template="https://placeholder.invalid/?bind_token={bind_token}",
        ttl_seconds=600,
    )

    identity = service.consume_matching_session(
        bind_token="ctx_bind_123",
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_tg",
        platform="telegram",
        external_end_user_id="tg_456",
        now_ts=1775472000,
    )

    assert identity["external_end_user_id"] == "tg_456"
    external_identity_dao.activate_identity.assert_called_once()


# tests/unit/connector/clawscale_bridge/test_identity_service.py
from unittest.mock import MagicMock


def test_handle_inbound_prefers_bound_coke_account_from_gateway_metadata():
    from connector.clawscale_bridge.identity_service import IdentityService

    message_gateway = MagicMock()
    message_gateway.enqueue.return_value = "req_1"
    reply_waiter = MagicMock()
    reply_waiter.wait_for_reply.return_value = "hi"

    service = IdentityService(
        external_identity_dao=MagicMock(),
        binding_ticket_dao=MagicMock(),
        bind_session_service=MagicMock(),
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        bind_base_url="https://coke.local",
        target_character_id="char_1",
    )

    result = service.handle_inbound(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "platform": "wechat_personal",
                "externalId": "wxid_123",
                "endUserId": "eu_1",
                "conversationId": "conv_1",
                "clawscaleUserId": "csu_1",
                "cokeAccountId": "acc_1",
            },
        }
    )

    assert result == {"status": "ok", "reply": "hi"}
    message_gateway.enqueue.assert_called_once_with(
        account_id="acc_1",
        character_id="char_1",
        text="hello",
        inbound={
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "conversation_id": "conv_1",
            "platform": "wechat_personal",
            "end_user_id": "eu_1",
            "external_id": "wxid_123",
            "external_message_id": "conv_1",
            "timestamp": message_gateway.enqueue.call_args.kwargs["inbound"]["timestamp"],
        },
    )
```

- [ ] **Step 2: Run the Coke bridge identity tests to verify they fail**

Run: `pytest tests/unit/dao/test_external_identity_dao.py tests/unit/connector/clawscale_bridge/test_gateway_identity_client.py tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py tests/unit/connector/clawscale_bridge/test_identity_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -v`

Expected: FAIL because `gateway_identity_client.py` and the new DAO methods do not exist yet, and the bind-session service still blocks a second identity.

- [ ] **Step 3: Implement gateway sync, multi-identity storage, and metadata short-circuiting**

```python
# connector/clawscale_bridge/gateway_identity_client.py
import requests


class GatewayIdentityClient:
    def __init__(
        self,
        identity_api_url: str,
        identity_api_key: str,
        session=None,
    ):
        self.identity_api_url = identity_api_url
        self.identity_api_key = identity_api_key
        self.session = session or requests.Session()

    def bind_end_user(
        self,
        tenant_id: str,
        channel_id: str,
        external_id: str,
        coke_account_id: str,
    ):
        response = self.session.post(
            self.identity_api_url,
            json={
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "external_id": external_id,
                "coke_account_id": coke_account_id,
            },
            headers={"Authorization": f"Bearer {self.identity_api_key}"},
            timeout=15,
        )
        data = response.json()
        if response.status_code != 200 or not data.get("ok"):
            raise ValueError(data.get("error", "gateway_identity_bind_failed"))
        return data["data"]
```

```python
# dao/external_identity_dao.py
from pymongo import MongoClient


class ExternalIdentityDAO:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db.get_collection("external_identities")

    def create_indexes(self) -> None:
        self.collection.create_index(
            [
                ("source", 1),
                ("tenant_id", 1),
                ("channel_id", 1),
                ("platform", 1),
                ("external_end_user_id", 1),
            ],
            unique=True,
        )
        self.collection.create_index(
            [("account_id", 1), ("tenant_id", 1), ("is_primary_push_target", 1)]
        )
        self.collection.create_index([("status", 1)])
        self.collection.create_index([("clawscale_user_id", 1)])

    def find_active_identity_for_account(self, account_id: str, platform: str | None = None):
        query = {
            "account_id": account_id,
            "source": "clawscale",
            "status": "active",
        }
        if platform is not None:
            query["platform"] = platform
        return self.collection.find_one(query)

    def set_clawscale_user_id(
        self,
        source: str,
        tenant_id: str,
        channel_id: str,
        platform: str,
        external_end_user_id: str,
        clawscale_user_id: str,
        now_ts: int,
    ) -> None:
        self.collection.update_one(
            {
                "source": source,
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "platform": platform,
                "external_end_user_id": external_end_user_id,
            },
            {
                "$set": {
                    "clawscale_user_id": clawscale_user_id,
                    "updated_at": now_ts,
                }
            },
        )

    def iter_active_clawscale_identities(self):
        return self.collection.find(
            {
                "source": "clawscale",
                "status": "active",
            }
        )
```

```python
# connector/clawscale_bridge/wechat_bind_session_service.py
class WechatBindSessionService:
    def __init__(
        self,
        bind_session_dao,
        external_identity_dao,
        bind_base_url: str,
        public_connect_url_template: str,
        ttl_seconds: int,
        gateway_identity_client=None,
    ):
        self.bind_session_dao = bind_session_dao
        self.external_identity_dao = external_identity_dao
        self.bind_base_url = bind_base_url.rstrip("/")
        self.public_connect_url_template = public_connect_url_template
        self.ttl_seconds = ttl_seconds
        self.gateway_identity_client = gateway_identity_client

    def _consume_session(
        self,
        session: dict,
        source: str,
        tenant_id: str,
        channel_id: str,
        platform: str,
        external_end_user_id: str,
        now_ts: int,
    ):
        current_identity = self.external_identity_dao.find_active_identity(
            source=source,
            tenant_id=tenant_id,
            channel_id=channel_id,
            platform=platform,
            external_end_user_id=external_end_user_id,
        )
        if current_identity:
            self.bind_session_dao.mark_bound(
                session_id=session["session_id"],
                masked_identity=self._mask_identity(external_end_user_id),
                external_end_user_id=external_end_user_id,
                now_ts=now_ts,
            )
            return current_identity

        bind_result = None
        if self.gateway_identity_client is not None:
            bind_result = self.gateway_identity_client.bind_end_user(
                tenant_id=tenant_id,
                channel_id=channel_id,
                external_id=external_end_user_id,
                coke_account_id=session["account_id"],
            )

        identity = self.external_identity_dao.activate_identity(
            source=source,
            tenant_id=tenant_id,
            channel_id=channel_id,
            platform=platform,
            external_end_user_id=external_end_user_id,
            account_id=session["account_id"],
            now_ts=now_ts,
        )

        if bind_result and bind_result.get("clawscale_user_id"):
            self.external_identity_dao.set_clawscale_user_id(
                source=source,
                tenant_id=tenant_id,
                channel_id=channel_id,
                platform=platform,
                external_end_user_id=external_end_user_id,
                clawscale_user_id=bind_result["clawscale_user_id"],
                now_ts=now_ts,
            )

        self.bind_session_dao.mark_bound(
            session_id=session["session_id"],
            masked_identity=self._mask_identity(external_end_user_id),
            external_end_user_id=external_end_user_id,
            now_ts=now_ts,
        )
        return identity
```

```python
# connector/clawscale_bridge/identity_service.py
import time


class IdentityService:
    def handle_inbound(self, inbound_payload: dict):
        metadata = inbound_payload["metadata"]
        now_ts = int(time.time())

        if metadata.get("cokeAccountId"):
            bridge_request_id = self.message_gateway.enqueue(
                account_id=metadata["cokeAccountId"],
                character_id=self.target_character_id,
                text=inbound_payload["messages"][-1]["content"],
                inbound={
                    "tenant_id": metadata["tenantId"],
                    "channel_id": metadata["channelId"],
                    "conversation_id": metadata["conversationId"],
                    "platform": metadata["platform"],
                    "end_user_id": metadata["endUserId"],
                    "external_id": metadata["externalId"],
                    "external_message_id": metadata["conversationId"],
                    "timestamp": now_ts,
                },
            )
            reply = self.reply_waiter.wait_for_reply(bridge_request_id)
            return {"status": "ok", "reply": reply}

        external_identity = self.external_identity_dao.find_active_identity(
            source="clawscale",
            tenant_id=metadata["tenantId"],
            channel_id=metadata["channelId"],
            platform=metadata["platform"],
            external_end_user_id=metadata["externalId"],
        )
        if not external_identity:
            bind_token = metadata.get("contextToken")
            if bind_token:
                external_identity = self.bind_session_service.consume_matching_session(
                    bind_token=bind_token,
                    source="clawscale",
                    tenant_id=metadata["tenantId"],
                    channel_id=metadata["channelId"],
                    platform=metadata["platform"],
                    external_end_user_id=metadata["externalId"],
                    now_ts=now_ts,
                )
            if not external_identity:
                external_identity = self.bind_session_service.consume_matching_session_from_text(
                    text=inbound_payload["messages"][-1]["content"],
                    source="clawscale",
                    tenant_id=metadata["tenantId"],
                    channel_id=metadata["channelId"],
                    platform=metadata["platform"],
                    external_end_user_id=metadata["externalId"],
                    now_ts=now_ts,
                )
        if not external_identity:
            ticket = self.issue_or_reuse_binding_ticket(metadata, now_ts=now_ts)
            return {
                "status": "bind_required",
                "reply": f"请先绑定账号: {ticket['bind_url']}",
                "bind_url": ticket["bind_url"],
            }

        bridge_request_id = self.message_gateway.enqueue(
            account_id=external_identity["account_id"],
            character_id=self.target_character_id,
            text=inbound_payload["messages"][-1]["content"],
            inbound={
                "tenant_id": metadata["tenantId"],
                "channel_id": metadata["channelId"],
                "conversation_id": metadata["conversationId"],
                "platform": metadata["platform"],
                "end_user_id": metadata["endUserId"],
                "external_id": metadata["externalId"],
                "external_message_id": metadata["conversationId"],
                "timestamp": now_ts,
            },
        )
        reply = self.reply_waiter.wait_for_reply(bridge_request_id)
        return {"status": "ok", "reply": reply}
```

```python
# connector/clawscale_bridge/app.py
from connector.clawscale_bridge.gateway_identity_client import GatewayIdentityClient


def _build_gateway_identity_client():
    bridge_conf = CONF["clawscale_bridge"]
    return GatewayIdentityClient(
        identity_api_url=bridge_conf["identity_api_url"],
        identity_api_key=bridge_conf["identity_api_key"],
    )


def _build_default_bridge_gateway():
    bridge_conf = CONF["clawscale_bridge"]
    mongo_uri = _mongo_uri()
    db_name = CONF["mongodb"]["mongodb_name"]

    user_dao = UserDAO(mongo_uri=mongo_uri, db_name=db_name)
    external_identity_dao = ExternalIdentityDAO(mongo_uri=mongo_uri, db_name=db_name)
    binding_ticket_dao = BindingTicketDAO(mongo_uri=mongo_uri, db_name=db_name)
    bind_session_dao = WechatBindSessionDAO(mongo_uri=mongo_uri, db_name=db_name)
    mongo = MongoDBBase(connection_string=mongo_uri, db_name=db_name)
    message_gateway = CokeMessageGateway(mongo=mongo, user_dao=user_dao)
    reply_waiter = ReplyWaiter(
        mongo=mongo,
        poll_interval_seconds=bridge_conf["poll_interval_seconds"],
        timeout_seconds=bridge_conf["reply_timeout_seconds"],
    )
    bind_session_service = WechatBindSessionService(
        bind_session_dao=bind_session_dao,
        external_identity_dao=external_identity_dao,
        gateway_identity_client=_build_gateway_identity_client(),
        bind_base_url=bridge_conf["bind_base_url"],
        public_connect_url_template=bridge_conf["wechat_public_connect_url_template"],
        ttl_seconds=bridge_conf["wechat_bind_session_ttl_seconds"],
    )
    return IdentityService(
        external_identity_dao=external_identity_dao,
        binding_ticket_dao=binding_ticket_dao,
        bind_session_service=bind_session_service,
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        bind_base_url=bridge_conf["bind_base_url"],
        target_character_id=_resolve_target_character_id(user_dao),
    )


def _build_user_bind_service():
    mongo_uri = _mongo_uri()
    db_name = CONF["mongodb"]["mongodb_name"]
    bridge_conf = CONF["clawscale_bridge"]
    return WechatBindSessionService(
        bind_session_dao=WechatBindSessionDAO(mongo_uri=mongo_uri, db_name=db_name),
        external_identity_dao=ExternalIdentityDAO(mongo_uri=mongo_uri, db_name=db_name),
        gateway_identity_client=_build_gateway_identity_client(),
        bind_base_url=bridge_conf["bind_base_url"],
        public_connect_url_template=bridge_conf["wechat_public_connect_url_template"],
        ttl_seconds=bridge_conf["wechat_bind_session_ttl_seconds"],
    )
```

```json
// conf/config.json
"clawscale_bridge": {
  "host": "0.0.0.0",
  "port": 8090,
  "api_key": "${COKE_BRIDGE_API_KEY}",
  "user_auth_secret": "${COKE_USER_AUTH_SECRET}",
  "user_auth_token_ttl_seconds": 604800,
  "bind_base_url": "${COKE_BIND_BASE_URL}",
  "wechat_public_connect_url_template": "${COKE_WECHAT_PUBLIC_CONNECT_URL_TEMPLATE}",
  "wechat_bind_session_ttl_seconds": 600,
  "web_allowed_origin": "${COKE_WEB_ALLOWED_ORIGIN}",
  "reply_timeout_seconds": 25,
  "poll_interval_seconds": 1,
  "outbound_api_url": "${CLAWSCALE_OUTBOUND_API_URL}",
  "outbound_api_key": "${CLAWSCALE_OUTBOUND_API_KEY}",
  "identity_api_url": "${CLAWSCALE_IDENTITY_API_URL}",
  "identity_api_key": "${CLAWSCALE_IDENTITY_API_KEY}"
}
```

- [ ] **Step 4: Run the Coke bridge identity test suite**

Run: `pytest tests/unit/dao/test_external_identity_dao.py tests/unit/connector/clawscale_bridge/test_gateway_identity_client.py tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py tests/unit/connector/clawscale_bridge/test_identity_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -v`

Expected: PASS, including the new gateway sync and direct `cokeAccountId` routing path.

- [ ] **Step 5: Commit the Coke bridge identity sync changes**

```bash
git add dao/external_identity_dao.py \
  tests/unit/dao/test_external_identity_dao.py \
  connector/clawscale_bridge/gateway_identity_client.py \
  connector/clawscale_bridge/wechat_bind_session_service.py \
  connector/clawscale_bridge/identity_service.py \
  connector/clawscale_bridge/app.py \
  tests/unit/connector/clawscale_bridge/test_gateway_identity_client.py \
  tests/unit/connector/clawscale_bridge/test_wechat_bind_session_service.py \
  tests/unit/connector/clawscale_bridge/test_identity_service.py \
  tests/unit/connector/clawscale_bridge/test_bridge_app.py \
  conf/config.json
git commit -m "feat(bind): sync clawscale unified users into coke bridge"
```

### Task 4: Backfill Existing Active Identities And Document The Rollout

**Files:**
- Create: `connector/clawscale_bridge/backfill_clawscale_users.py`
- Create: `tests/unit/connector/clawscale_bridge/test_backfill_clawscale_users.py`
- Modify: `docs/clawscale_bridge.md`

- [ ] **Step 1: Write the failing backfill test**

```python
# tests/unit/connector/clawscale_bridge/test_backfill_clawscale_users.py
from unittest.mock import MagicMock


def test_backfill_only_syncs_records_missing_clawscale_user_id():
    from connector.clawscale_bridge.backfill_clawscale_users import backfill_active_identities

    external_identity_dao = MagicMock()
    external_identity_dao.iter_active_clawscale_identities.return_value = [
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_1",
            "platform": "wechat_personal",
            "external_end_user_id": "wxid_123",
            "account_id": "acc_1",
            "clawscale_user_id": "csu_existing",
        },
        {
            "source": "clawscale",
            "tenant_id": "ten_1",
            "channel_id": "ch_2",
            "platform": "telegram",
            "external_end_user_id": "tg_456",
            "account_id": "acc_1",
        },
    ]
    gateway_identity_client = MagicMock()
    gateway_identity_client.bind_end_user.return_value = {
        "clawscale_user_id": "csu_1",
        "end_user_id": "eu_2",
        "coke_account_id": "acc_1",
    }

    summary = backfill_active_identities(
        external_identity_dao=external_identity_dao,
        gateway_identity_client=gateway_identity_client,
        now_ts=1775472000,
    )

    assert summary == {"scanned": 2, "updated": 1, "skipped": 1}
    gateway_identity_client.bind_end_user.assert_called_once_with(
        tenant_id="ten_1",
        channel_id="ch_2",
        external_id="tg_456",
        coke_account_id="acc_1",
    )
    external_identity_dao.set_clawscale_user_id.assert_called_once_with(
        source="clawscale",
        tenant_id="ten_1",
        channel_id="ch_2",
        platform="telegram",
        external_end_user_id="tg_456",
        clawscale_user_id="csu_1",
        now_ts=1775472000,
    )
```

- [ ] **Step 2: Run the backfill test to verify it fails**

Run: `pytest tests/unit/connector/clawscale_bridge/test_backfill_clawscale_users.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'connector.clawscale_bridge.backfill_clawscale_users'`.

- [ ] **Step 3: Implement the backfill script and document the rollout**

```python
# connector/clawscale_bridge/backfill_clawscale_users.py
import time

from conf.config import CONF
from connector.clawscale_bridge.gateway_identity_client import GatewayIdentityClient
from dao.external_identity_dao import ExternalIdentityDAO


def backfill_active_identities(external_identity_dao, gateway_identity_client, now_ts: int):
    scanned = 0
    updated = 0
    skipped = 0

    for identity in external_identity_dao.iter_active_clawscale_identities():
      scanned += 1
      if identity.get("clawscale_user_id"):
        skipped += 1
        continue

      bind_result = gateway_identity_client.bind_end_user(
          tenant_id=identity["tenant_id"],
          channel_id=identity["channel_id"],
          external_id=identity["external_end_user_id"],
          coke_account_id=identity["account_id"],
      )

      external_identity_dao.set_clawscale_user_id(
          source=identity["source"],
          tenant_id=identity["tenant_id"],
          channel_id=identity["channel_id"],
          platform=identity["platform"],
          external_end_user_id=identity["external_end_user_id"],
          clawscale_user_id=bind_result["clawscale_user_id"],
          now_ts=now_ts,
      )
      updated += 1

    return {"scanned": scanned, "updated": updated, "skipped": skipped}


def main():
    mongo_uri = (
        "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/"
    )
    dao = ExternalIdentityDAO(
        mongo_uri=mongo_uri,
        db_name=CONF["mongodb"]["mongodb_name"],
    )
    client = GatewayIdentityClient(
        identity_api_url=CONF["clawscale_bridge"]["identity_api_url"],
        identity_api_key=CONF["clawscale_bridge"]["identity_api_key"],
    )
    summary = backfill_active_identities(
        external_identity_dao=dao,
        gateway_identity_client=client,
        now_ts=int(time.time()),
    )
    print(summary)


if __name__ == "__main__":
    main()
```

```md
<!-- docs/clawscale_bridge.md -->
## Unified Identity Rollout

Required env vars:

- `CLAWSCALE_IDENTITY_API_URL`
- `CLAWSCALE_IDENTITY_API_KEY`

Gateway rollout:

1. Apply the Prisma schema change:
   `pnpm --dir gateway/packages/api db:migrate --name clawscale-user-unification`
2. Regenerate the Prisma client:
   `pnpm --dir gateway/packages/api db:generate`

Coke bridge rollout:

1. Deploy the bridge with the new `identity_api_url` and `identity_api_key` config.
2. Run the one-off backfill after both services are live:
   `python -m connector.clawscale_bridge.backfill_clawscale_users`

Manual smoke test:

1. Bind a new WeChat end user to a Coke account.
2. Confirm the matching gateway `end_users` row now has `clawscale_user_id`.
3. Confirm the matching Mongo `external_identities` row has the same `clawscale_user_id`.
4. Send a second message from the same user and verify the bridge inbound metadata now contains `cokeAccountId`.
```

- [ ] **Step 4: Run the backfill test and the relevant bridge tests**

Run: `pytest tests/unit/connector/clawscale_bridge/test_backfill_clawscale_users.py tests/unit/connector/clawscale_bridge/test_gateway_identity_client.py tests/unit/connector/clawscale_bridge/test_identity_service.py -v`

Expected: PASS, and the backfill summary should show skipped vs updated counts correctly.

- [ ] **Step 5: Commit the rollout tooling and docs**

```bash
git add connector/clawscale_bridge/backfill_clawscale_users.py \
  tests/unit/connector/clawscale_bridge/test_backfill_clawscale_users.py \
  docs/clawscale_bridge.md
git commit -m "docs(bind): add clawscale user migration runbook"
```

## Self-Review

### Spec coverage

- `ClawscaleUser` model: covered by Task 1.
- `EndUser -> ClawscaleUser` bind semantics: covered by Task 1 and Task 3.
- `cokeAccountId <-> ClawscaleUser` contract: covered by Task 1 route and Task 3 bridge sync.
- explicit binding only: preserved by Task 3.
- cross-channel unified history: covered by Task 2.
- backward compatibility and migration: covered by Task 2 fallback behavior and Task 4 backfill.

### Placeholder scan

- No `TODO`, `TBD`, or “handle appropriately” placeholders remain.
- Every code-change step includes concrete code or command examples.
- Every test step names exact test files and commands.

### Type consistency

- Gateway side uses `clawscaleUserId` in TypeScript and `clawscale_user_id` on wire/JSON payloads.
- Coke bridge side uses `clawscale_user_id` in Mongo and JSON payloads.
- `cokeAccountId` is only used inside gateway event metadata and TypeScript.
- `coke_account_id` is only used in gateway internal bind API payloads.
