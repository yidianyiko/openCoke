# ClawScale Identity Schema Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the new Postgres `Identity` / `Customer` / `Membership` / `AgentBinding` platform schema, backfill existing Coke users into it without rekeying `account_id`, and land dormant shared-channel fields needed by Phase 1.5.

**Architecture:** Keep the legacy `Tenant` / `Member` / `Session` / `ClawscaleUser` / `CokeAccount` graph live while introducing the new platform-owned identity graph in parallel. The migration preserves `Customer.id = CokeAccount.id`, derives deterministic UUIDs for migrated `Identity`/`Membership` rows so reruns stay idempotent, seeds existing users as `Identity.claim_status = 'active'`, creates one default `Agent` row for Coke plus one `AgentBinding` per migrated customer, and adds dormant `shared`-channel schema (`Channel.ownership_kind`, nullable `Channel.customer_id`, `Channel.agent_id`, `ExternalIdentity`) without wiring runtime behavior yet.

**Tech Stack:** TypeScript, Prisma, PostgreSQL, Hono, Vitest, pnpm, tsx, ripgrep

---

## Scope Check

The spec spans multiple independent follow-up plans. This plan covers **follow-up plan 1 only**:

- Postgres schema additions for the new identity/customer model
- dormant shared-channel schema required to make Phase 1.5 additive later
- deterministic audit / backfill / verify tooling for existing data

This plan intentionally does **not** implement:

- stranded-model resolution (`Conversation`, `Message`, `Workflow`, etc.)
- auth route migration
- frontend relocation
- admin UI rebuild
- shared-channel runtime or inbound auto-provisioning

Those need separate plans after this one lands.

## File Structure

### New API files

- `gateway/packages/api/src/lib/platformization-migration.ts`
  Pure helper functions for deterministic ID mapping, seed-shape construction, and baseline summaries.
- `gateway/packages/api/src/lib/platformization-migration.test.ts`
  Unit coverage for ID reuse, claim-status defaults, agent binding defaults, and baseline drift detection.
- `gateway/packages/api/src/lib/platformization-schema.test.ts`
  Schema guard that asserts the Prisma file contains the new models, enums, and dormant shared-channel fields.
- `gateway/packages/api/src/lib/platformization-backfill.ts`
  DB-backed orchestration for baseline audit, default-agent seeding, legacy backfill, and post-migration verification.
- `gateway/packages/api/src/lib/platformization-backfill.test.ts`
  Unit tests with mocked Prisma client covering agent seeding, legacy row backfill, and verification summaries.
- `gateway/packages/api/src/scripts/audit-platformization-baseline.ts`
  CLI that audits the legacy `CokeAccount` / `ClawscaleUser` baseline before migration.
- `gateway/packages/api/src/scripts/backfill-platformization-identity.ts`
  CLI that creates `Identity` / `Customer` / `Membership` / `AgentBinding` rows from legacy data.
- `gateway/packages/api/src/scripts/verify-platformization-migration.ts`
  CLI that verifies migrated row counts, default agent uniqueness, and missing graph edges after backfill.

### Modified API files

- `gateway/packages/api/package.json`
  Add explicit `platformization:*` script aliases for audit/backfill/verify commands.
- `gateway/packages/api/prisma/schema.prisma`
  Add new enums/models/relations while leaving legacy tables in place for later plans.

### Generated migration artifacts

- `gateway/packages/api/prisma/migrations/<timestamp>_platformization_identity_schema/migration.sql`
  DDL for new tables, dormant shared-channel columns, partial unique index on default agent, and raw check constraints Prisma cannot express.

### Existing files this plan reads but does not modify

- `gateway/packages/api/src/lib/clawscale-user.ts`
  Current personal Coke provisioning logic; use it to verify legacy assumptions during audit, but do not refactor it in this plan.
- `gateway/packages/api/src/routes/auth.ts`
  Legacy member auth remains live until the later auth-ownership plan.
- `dao/user_dao.py`
  Reference point for the later `account_id` audit; read-only in this plan.

---

## Task 1: Add deterministic platformization migration helpers

**Files:**
- Create: `gateway/packages/api/src/lib/platformization-migration.ts`
- Create: `gateway/packages/api/src/lib/platformization-migration.test.ts`

- [ ] **Step 1: Write the failing helper tests**

Create `gateway/packages/api/src/lib/platformization-migration.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
  buildDefaultAgentSeed,
  buildLegacyAgentBindingSeed,
  buildLegacyCustomerGraph,
  deriveDeterministicPlatformId,
  deriveCustomerIdFromLegacyAccount,
  summarizeLegacyBaseline,
} from './platformization-migration.js';

describe('deriveCustomerIdFromLegacyAccount', () => {
  it('reuses the legacy CokeAccount id byte-for-byte', () => {
    expect(deriveCustomerIdFromLegacyAccount('ck_legacy_123')).toBe('ck_legacy_123');
  });
});

describe('deriveDeterministicPlatformId', () => {
  it('returns the same UUID for the same scope and legacy account id', () => {
    expect(
      deriveDeterministicPlatformId('identity', 'ck_legacy_123'),
    ).toBe(deriveDeterministicPlatformId('identity', 'ck_legacy_123'));
  });
});

describe('buildLegacyCustomerGraph', () => {
  it('marks migrated users as active and preserves account id as customer id', () => {
    const graph = buildLegacyCustomerGraph({
      cokeAccountId: 'ck_legacy_123',
      email: 'Alice@Example.COM',
      displayName: 'Alice',
      createdAt: new Date('2026-04-01T00:00:00.000Z'),
      updatedAt: new Date('2026-04-02T00:00:00.000Z'),
    });

    expect(graph.customer).toMatchObject({
      id: 'ck_legacy_123',
      kind: 'personal',
      displayName: 'Alice',
    });
    expect(graph.identity).toMatchObject({
      id: deriveDeterministicPlatformId('identity', 'ck_legacy_123'),
      email: 'alice@example.com',
      claimStatus: 'active',
    });
    expect(graph.membership).toMatchObject({
      id: deriveDeterministicPlatformId('membership', 'ck_legacy_123'),
      customerId: 'ck_legacy_123',
      role: 'owner',
    });
  });
});

describe('buildLegacyAgentBindingSeed', () => {
  it('creates a ready binding for migrated customers', () => {
    expect(
      buildLegacyAgentBindingSeed({
        customerId: 'ck_legacy_123',
        agentId: '33333333-3333-3333-3333-333333333333',
      }),
    ).toMatchObject({
      customerId: 'ck_legacy_123',
      agentId: '33333333-3333-3333-3333-333333333333',
      provisionStatus: 'ready',
      provisionAttempts: 0,
      provisionLastError: null,
    });
  });
});

describe('buildDefaultAgentSeed', () => {
  it('creates the default Coke agent row with isDefault=true', () => {
    expect(
      buildDefaultAgentSeed({
        id: '44444444-4444-4444-4444-444444444444',
        endpoint: 'https://coke.example.com/agent',
        authToken: 'secret-token',
      }),
    ).toMatchObject({
      id: '44444444-4444-4444-4444-444444444444',
      slug: 'coke',
      isDefault: true,
      endpoint: 'https://coke.example.com/agent',
      authToken: 'secret-token',
    });
  });
});

describe('summarizeLegacyBaseline', () => {
  it('reports missing clawscale users and drifted mongo account ids', () => {
    const summary = summarizeLegacyBaseline({
      cokeAccounts: [
        { cokeAccountId: 'ck_1', email: 'one@example.com' },
        { cokeAccountId: 'ck_2', email: 'two@example.com' },
      ],
      clawscaleUsers: [{ cokeAccountId: 'ck_1', tenantId: 'tnt_1' }],
      mongoAccountIds: ['ck_1', 'ck_orphan'],
    });

    expect(summary.errors).toEqual([
      'missing_clawscale_user:ck_2',
      'orphan_mongo_account_id:ck_orphan',
    ]);
    expect(summary.counts).toEqual({
      cokeAccounts: 2,
      clawscaleUsers: 1,
      mongoAccountIds: 2,
    });
  });
});
```

- [ ] **Step 2: Run the focused helper test to verify the red state**

Run: `pnpm --dir gateway/packages/api test -- src/lib/platformization-migration.test.ts`

Expected: FAIL with `Cannot find module './platformization-migration.js'` or missing export errors.

- [ ] **Step 3: Write the minimal migration helper implementation**

Create `gateway/packages/api/src/lib/platformization-migration.ts`:

```ts
import { createHash, randomUUID } from 'node:crypto';

export interface LegacyCokeAccountSeedInput {
  cokeAccountId: string;
  email: string;
  displayName: string | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface LegacyBaselineSummaryInput {
  cokeAccounts: Array<{ cokeAccountId: string; email: string }>;
  clawscaleUsers: Array<{ cokeAccountId: string; tenantId: string }>;
  mongoAccountIds: string[];
}

export function deriveCustomerIdFromLegacyAccount(cokeAccountId: string): string {
  return cokeAccountId;
}

export function deriveDeterministicPlatformId(scope: string, legacyAccountId: string): string {
  const hex = createHash('sha256')
    .update(scope)
    .update(':')
    .update(legacyAccountId)
    .digest('hex')
    .slice(0, 32);

  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    `5${hex.slice(13, 16)}`,
    `a${hex.slice(17, 20)}`,
    hex.slice(20, 32),
  ].join('-');
}

export function buildLegacyCustomerGraph(
  input: LegacyCokeAccountSeedInput,
) {
  const customerId = deriveCustomerIdFromLegacyAccount(input.cokeAccountId);
  const identityId = deriveDeterministicPlatformId('identity', input.cokeAccountId);
  const membershipId = deriveDeterministicPlatformId('membership', input.cokeAccountId);
  const normalizedEmail = input.email.trim().toLowerCase();
  const displayName = input.displayName?.trim() || normalizedEmail;

  return {
    identity: {
      id: identityId,
      email: normalizedEmail,
      displayName,
      claimStatus: 'active' as const,
      createdAt: input.createdAt,
      updatedAt: input.updatedAt,
    },
    customer: {
      id: customerId,
      kind: 'personal' as const,
      displayName,
      createdAt: input.createdAt,
      updatedAt: input.updatedAt,
    },
    membership: {
      id: membershipId,
      identityId,
      customerId,
      role: 'owner' as const,
      createdAt: input.createdAt,
      updatedAt: input.updatedAt,
    },
  };
}

export function buildLegacyAgentBindingSeed(input: {
  customerId: string;
  agentId: string;
}) {
  return {
    customerId: input.customerId,
    agentId: input.agentId,
    provisionStatus: 'ready' as const,
    provisionAttempts: 0,
    provisionLastError: null,
  };
}

export function buildDefaultAgentSeed(input: {
  id?: string;
  endpoint: string;
  authToken: string;
}) {
  return {
    id: input.id ?? randomUUID(),
    slug: 'coke',
    name: 'Coke',
    endpoint: input.endpoint,
    authToken: input.authToken,
    isDefault: true,
  };
}

export function summarizeLegacyBaseline(input: LegacyBaselineSummaryInput) {
  const clawscaleAccountIds = new Set(input.clawscaleUsers.map((row) => row.cokeAccountId));
  const cokeAccountIds = new Set(input.cokeAccounts.map((row) => row.cokeAccountId));
  const errors: string[] = [];

  for (const account of input.cokeAccounts) {
    if (!clawscaleAccountIds.has(account.cokeAccountId)) {
      errors.push(`missing_clawscale_user:${account.cokeAccountId}`);
    }
  }

  for (const accountId of input.mongoAccountIds) {
    if (!cokeAccountIds.has(accountId)) {
      errors.push(`orphan_mongo_account_id:${accountId}`);
    }
  }

  return {
    counts: {
      cokeAccounts: input.cokeAccounts.length,
      clawscaleUsers: input.clawscaleUsers.length,
      mongoAccountIds: input.mongoAccountIds.length,
    },
    errors,
  };
}
```

- [ ] **Step 4: Run the helper tests to verify the green state**

Run: `pnpm --dir gateway/packages/api test -- src/lib/platformization-migration.test.ts`

Expected: PASS with 6 tests passing in `platformization-migration.test.ts`.

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/api/src/lib/platformization-migration.ts \
        gateway/packages/api/src/lib/platformization-migration.test.ts
git commit -m "feat(gateway): add platformization migration helpers"
```

## Task 2: Extend the Prisma schema and generate the dormant platformization migration

**Files:**
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Create: `gateway/packages/api/src/lib/platformization-schema.test.ts`
- Create: `gateway/packages/api/prisma/migrations/<timestamp>_platformization_identity_schema/migration.sql`

- [ ] **Step 1: Write the failing schema guard test**

Create `gateway/packages/api/src/lib/platformization-schema.test.ts`:

```ts
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const schema = readFileSync(
  new URL('../../prisma/schema.prisma', import.meta.url),
  'utf8',
);

describe('platformization prisma schema', () => {
  it('declares the new identity/customer graph', () => {
    expect(schema).toContain('enum IdentityClaimStatus');
    expect(schema).toContain('model Identity');
    expect(schema).toContain('model Customer');
    expect(schema).toContain('model Membership');
    expect(schema).toContain('model Agent');
    expect(schema).toContain('model AgentBinding');
    expect(schema).toContain('model AdminAccount');
    expect(schema).toContain('mfaSecret');
    expect(schema).toContain('model ExternalIdentity');
  });

  it('adds dormant shared-channel fields to Channel', () => {
    expect(schema).toContain('enum ChannelOwnershipKind');
    expect(schema).toContain('ownershipKind');
    expect(schema).toContain('customerId');
    expect(schema).toContain('agentId');
  });
});
```

- [ ] **Step 2: Run the schema guard test to verify the red state**

Run: `pnpm --dir gateway/packages/api test -- src/lib/platformization-schema.test.ts`

Expected: FAIL because `schema.prisma` does not yet contain `IdentityClaimStatus`, `Customer`, `Membership`, `Agent`, `AgentBinding`, `AdminAccount`, `ExternalIdentity`, or `Channel.ownershipKind`.

- [ ] **Step 3: Modify the Prisma schema and create the SQL migration**

Update `gateway/packages/api/prisma/schema.prisma` with these additions:

```prisma
enum IdentityClaimStatus {
  active
  unclaimed
  pending
}

enum CustomerKind {
  personal
  organization
}

enum MembershipRole {
  owner
  member
  viewer
}

enum AgentBindingProvisionStatus {
  pending
  ready
  error
}

enum ChannelOwnershipKind {
  customer
  shared
}

model Identity {
  id           String              @id @default(uuid())
  email        String?             @unique
  phone        String?
  displayName  String              @map("display_name")
  passwordHash String?             @map("password_hash")
  claimStatus  IdentityClaimStatus @default(active) @map("claim_status")
  createdAt    DateTime            @default(now()) @map("created_at")
  updatedAt    DateTime            @updatedAt @map("updated_at")

  memberships Membership[]

  @@map("identities")
}

model Customer {
  id          String        @id
  kind        CustomerKind
  displayName String        @map("display_name")
  createdAt   DateTime      @default(now()) @map("created_at")
  updatedAt   DateTime      @updatedAt @map("updated_at")

  memberships        Membership[]
  channels           Channel[]
  agentBindings      AgentBinding[]
  externalIdentities ExternalIdentity[]

  @@map("customers")
}

model Membership {
  id         String         @id @default(uuid())
  identityId String         @map("identity_id")
  customerId String         @map("customer_id")
  role       MembershipRole @default(owner)
  createdAt  DateTime       @default(now()) @map("created_at")
  updatedAt  DateTime       @updatedAt @map("updated_at")

  identity Identity @relation(fields: [identityId], references: [id], onDelete: Cascade)
  customer Customer @relation(fields: [customerId], references: [id], onDelete: Cascade)

  @@unique([identityId, customerId])
  @@index([customerId])
  @@map("memberships")
}

model Agent {
  id        String   @id @default(uuid())
  slug      String   @unique
  name      String
  endpoint  String
  authToken String   @map("auth_token")
  isDefault Boolean  @default(false) @map("is_default")
  createdAt DateTime @default(now()) @map("created_at")
  updatedAt DateTime @updatedAt @map("updated_at")

  bindings       AgentBinding[]
  sharedChannels Channel[]

  @@map("agents")
}

model AgentBinding {
  id                String                       @id @default(uuid())
  customerId        String                       @map("customer_id")
  agentId           String                       @map("agent_id")
  provisionStatus   AgentBindingProvisionStatus  @default(pending) @map("provision_status")
  provisionAttempts Int                          @default(0) @map("provision_attempts")
  provisionLastError String?                     @map("provision_last_error")
  provisionUpdatedAt DateTime                    @default(now()) @map("provision_updated_at")
  createdAt         DateTime                     @default(now()) @map("created_at")
  updatedAt         DateTime                     @updatedAt @map("updated_at")

  customer Customer @relation(fields: [customerId], references: [id], onDelete: Cascade)
  agent    Agent    @relation(fields: [agentId], references: [id], onDelete: Restrict)

  @@unique([customerId])
  @@index([agentId])
  @@map("agent_bindings")
}

model AdminAccount {
  id           String   @id @default(uuid())
  email        String   @unique
  passwordHash String   @map("password_hash")
  mfaSecret    String?  @map("mfa_secret")
  isActive     Boolean  @default(true) @map("is_active")
  createdAt    DateTime @default(now()) @map("created_at")
  updatedAt    DateTime @updatedAt @map("updated_at")

  @@map("admin_accounts")
}

model ExternalIdentity {
  id                 String   @id @default(uuid())
  provider           String
  identityType       String   @map("identity_type")
  identityValue      String   @map("identity_value")
  customerId         String   @map("customer_id")
  firstSeenChannelId String   @map("first_seen_channel_id")
  firstSeenAt        DateTime @default(now()) @map("first_seen_at")
  lastSeenAt         DateTime @default(now()) @map("last_seen_at")
  createdAt          DateTime @default(now()) @map("created_at")
  updatedAt          DateTime @updatedAt @map("updated_at")

  customer         Customer @relation(fields: [customerId], references: [id], onDelete: Cascade)
  firstSeenChannel Channel  @relation(fields: [firstSeenChannelId], references: [id], onDelete: Restrict)

  @@unique([provider, identityType, identityValue])
  @@index([customerId])
  @@map("external_identities")
}
```

Patch `model Channel` to add the dormant fields while keeping the legacy relations intact:

```prisma
model Channel {
  id                   String             @id
  tenantId             String             @map("tenant_id")
  type                 ChannelType
  scope                ChannelScope       @default(tenant_shared)
  ownershipKind        ChannelOwnershipKind @default(customer) @map("ownership_kind")
  customerId           String?            @map("customer_id")
  agentId              String?            @map("agent_id")
  ownerClawscaleUserId String?            @map("owner_clawscale_user_id")
  activeLifecycleKey   String?            @unique @map("active_lifecycle_key")
  name                 String
  status               ChannelStatus      @default(disconnected)
  config               Json               @default("{}")
  createdAt            DateTime           @default(now()) @map("created_at")
  updatedAt            DateTime           @updatedAt @map("updated_at")

  tenant             Tenant          @relation(fields: [tenantId], references: [id], onDelete: Cascade)
  customer           Customer?       @relation(fields: [customerId], references: [id], onDelete: Restrict)
  sharedAgent        Agent?          @relation(fields: [agentId], references: [id], onDelete: Restrict)
  ownerClawscaleUser ClawscaleUser?  @relation(fields: [ownerClawscaleUserId], references: [id], onDelete: SetNull)
  conversations      Conversation[]
  endUsers           EndUser[]
  deliveryRoutes     DeliveryRoute[]
  externalIdentities ExternalIdentity[]

  @@index([tenantId])
  @@index([customerId])
  @@index([agentId])
  @@index([ownerClawscaleUserId])
  @@map("channels")
}
```

Then generate the migration:

Run: `pnpm --dir gateway/packages/api exec prisma migrate dev --name platformization_identity_schema`

After generation, ensure the generated `gateway/packages/api/prisma/migrations/<timestamp>_platformization_identity_schema/migration.sql` contains the raw SQL Prisma cannot express directly:

```sql
CREATE UNIQUE INDEX "agents_is_default_true_key"
ON "agents" ("is_default")
WHERE "is_default" = true;

ALTER TABLE "channels"
ADD CONSTRAINT "channels_customer_or_shared_check"
CHECK (
  ("ownership_kind" = 'customer' AND "customer_id" IS NOT NULL)
  OR
  ("ownership_kind" = 'shared' AND "customer_id" IS NULL AND "agent_id" IS NOT NULL)
);

CREATE UNIQUE INDEX "channels_customer_kind_active_key"
ON "channels" ("customer_id", "type")
WHERE "customer_id" IS NOT NULL AND "status" <> 'archived';
```

- [ ] **Step 4: Run schema validation and the guard test**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/platformization-schema.test.ts
pnpm --dir gateway/packages/api exec prisma validate
pnpm --dir gateway/packages/api db:generate
```

Expected:

- `platformization-schema.test.ts` PASS
- `prisma validate` prints `The schema at prisma/schema.prisma is valid`
- `db:generate` prints `✔ Generated Prisma Client`

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/api/prisma/schema.prisma \
        gateway/packages/api/prisma/migrations/*_platformization_identity_schema/migration.sql \
        gateway/packages/api/src/lib/platformization-schema.test.ts
git commit -m "feat(gateway): add platform identity schema"
```

## Task 3: Add audit, backfill, and post-migration verification tooling

**Files:**
- Modify: `gateway/packages/api/package.json`
- Create: `gateway/packages/api/src/lib/platformization-backfill.ts`
- Create: `gateway/packages/api/src/lib/platformization-backfill.test.ts`
- Create: `gateway/packages/api/src/scripts/audit-platformization-baseline.ts`
- Create: `gateway/packages/api/src/scripts/backfill-platformization-identity.ts`
- Create: `gateway/packages/api/src/scripts/verify-platformization-migration.ts`

- [ ] **Step 1: Write the failing backfill/orchestration tests**

Create `gateway/packages/api/src/lib/platformization-backfill.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';

const db = vi.hoisted(() => ({
  agent: {
    findFirst: vi.fn(),
    create: vi.fn(),
    count: vi.fn(),
  },
  cokeAccount: {
    findMany: vi.fn(),
  },
  clawscaleUser: {
    findMany: vi.fn(),
    count: vi.fn(),
  },
  identity: {
    count: vi.fn(),
    upsert: vi.fn(),
  },
  customer: {
    count: vi.fn(),
    upsert: vi.fn(),
  },
  membership: {
    count: vi.fn(),
    upsert: vi.fn(),
  },
  agentBinding: {
    count: vi.fn(),
    upsert: vi.fn(),
  },
  $transaction: vi.fn(async (callback) => callback(db)),
}));

vi.mock('../db/index.js', () => ({ db }));

import {
  auditLegacyBaseline,
  backfillLegacyCustomers,
  ensureDefaultAgent,
  verifyPlatformizationMigration,
} from './platformization-backfill.js';

describe('ensureDefaultAgent', () => {
  beforeEach(() => vi.clearAllMocks());

  it('creates the default Coke agent when one does not exist', async () => {
    db.agent.findFirst.mockResolvedValue(null);
    db.agent.create.mockResolvedValue({ id: 'agent_1' });

    await expect(
      ensureDefaultAgent({
        endpoint: 'https://coke.example.com/agent',
        authToken: 'secret-token',
      }),
    ).resolves.toBe('agent_1');

    expect(db.agent.create).toHaveBeenCalledTimes(1);
  });
});

describe('auditLegacyBaseline', () => {
  beforeEach(() => vi.clearAllMocks());

  it('summarizes legacy CokeAccount and ClawscaleUser rows', async () => {
    db.cokeAccount.findMany.mockResolvedValue([
      { id: 'ck_1', email: 'one@example.com' },
      { id: 'ck_2', email: 'two@example.com' },
    ]);
    db.clawscaleUser.findMany.mockResolvedValue([{ cokeAccountId: 'ck_1', tenantId: 'tnt_1' }]);

    await expect(auditLegacyBaseline({ mongoAccountIds: ['ck_1'] })).resolves.toMatchObject({
      counts: { cokeAccounts: 2, clawscaleUsers: 1, mongoAccountIds: 1 },
      errors: ['missing_clawscale_user:ck_2'],
    });
  });
});

describe('backfillLegacyCustomers', () => {
  beforeEach(() => vi.clearAllMocks());

  it('upserts the new graph for each legacy Coke account', async () => {
    db.cokeAccount.findMany.mockResolvedValue([
      {
        id: 'ck_1',
        email: 'one@example.com',
        displayName: 'One',
        createdAt: new Date('2026-04-01T00:00:00.000Z'),
        updatedAt: new Date('2026-04-02T00:00:00.000Z'),
      },
    ]);

    await backfillLegacyCustomers({
      agentId: 'agent_1',
      dryRun: false,
    });

    expect(db.identity.upsert).toHaveBeenCalledTimes(1);
    expect(db.customer.upsert).toHaveBeenCalledTimes(1);
    expect(db.membership.upsert).toHaveBeenCalledTimes(1);
    expect(db.agentBinding.upsert).toHaveBeenCalledTimes(1);
  });
});

describe('verifyPlatformizationMigration', () => {
  beforeEach(() => vi.clearAllMocks());

  it('reports matching graph counts after a successful backfill', async () => {
    db.cokeAccount.count.mockResolvedValue(2);
    db.identity.count.mockResolvedValue(2);
    db.customer.count.mockResolvedValue(2);
    db.membership.count.mockResolvedValue(2);
    db.agentBinding.count.mockResolvedValue(2);
    db.agent.count.mockResolvedValue(1);

    await expect(verifyPlatformizationMigration()).resolves.toEqual({
      counts: {
        cokeAccounts: 2,
        identities: 2,
        customers: 2,
        memberships: 2,
        agentBindings: 2,
        defaultAgents: 1,
      },
      errors: [],
    });
  });
});
```

- [ ] **Step 2: Run the focused backfill test to verify the red state**

Run: `pnpm --dir gateway/packages/api test -- src/lib/platformization-backfill.test.ts`

Expected: FAIL because `platformization-backfill.ts` and the CLI scripts do not exist yet.

- [ ] **Step 3: Implement the DB orchestration helpers, CLI scripts, and package aliases**

Create `gateway/packages/api/src/lib/platformization-backfill.ts`:

```ts
import { db } from '../db/index.js';
import {
  buildDefaultAgentSeed,
  buildLegacyAgentBindingSeed,
  buildLegacyCustomerGraph,
  summarizeLegacyBaseline,
} from './platformization-migration.js';

export async function ensureDefaultAgent(input: {
  endpoint: string;
  authToken: string;
}): Promise<string> {
  const existing = await db.agent.findFirst({
    where: { isDefault: true },
    select: { id: true },
  });
  if (existing) {
    return existing.id;
  }

  const created = await db.agent.create({
    data: buildDefaultAgentSeed({
      endpoint: input.endpoint,
      authToken: input.authToken,
    }),
    select: { id: true },
  });
  return created.id;
}

export async function auditLegacyBaseline(input: { mongoAccountIds: string[] }) {
  const cokeAccounts = await db.cokeAccount.findMany({
    select: { id: true, email: true },
    orderBy: { createdAt: 'asc' },
  });
  const clawscaleUsers = await db.clawscaleUser.findMany({
    select: { cokeAccountId: true, tenantId: true },
    orderBy: { createdAt: 'asc' },
  });

  return summarizeLegacyBaseline({
    cokeAccounts: cokeAccounts.map((row) => ({
      cokeAccountId: row.id,
      email: row.email,
    })),
    clawscaleUsers,
    mongoAccountIds: input.mongoAccountIds,
  });
}

export async function backfillLegacyCustomers(input: {
  agentId: string;
  dryRun: boolean;
}) {
  const legacyAccounts = await db.cokeAccount.findMany({
    select: {
      id: true,
      email: true,
      displayName: true,
      createdAt: true,
      updatedAt: true,
    },
    orderBy: { createdAt: 'asc' },
  });

  if (input.dryRun) {
    return { wouldBackfill: legacyAccounts.length };
  }

  return db.$transaction(async (tx) => {
    for (const account of legacyAccounts) {
      const graph = buildLegacyCustomerGraph({
        cokeAccountId: account.id,
        email: account.email,
        displayName: account.displayName,
        createdAt: account.createdAt,
        updatedAt: account.updatedAt,
      });

      await tx.identity.upsert({
        where: { id: graph.identity.id },
        create: graph.identity,
        update: {
          email: graph.identity.email,
          displayName: graph.identity.displayName,
          claimStatus: 'active',
        },
      });

      await tx.customer.upsert({
        where: { id: graph.customer.id },
        create: graph.customer,
        update: {
          kind: graph.customer.kind,
          displayName: graph.customer.displayName,
        },
      });

      await tx.membership.upsert({
        where: { identityId_customerId: { identityId: graph.membership.identityId, customerId: graph.membership.customerId } },
        create: graph.membership,
        update: { role: graph.membership.role },
      });

      const binding = buildLegacyAgentBindingSeed({
        customerId: graph.customer.id,
        agentId: input.agentId,
      });

      await tx.agentBinding.upsert({
        where: { customerId: binding.customerId },
        create: binding,
        update: {
          agentId: binding.agentId,
          provisionStatus: 'ready',
          provisionAttempts: 0,
          provisionLastError: null,
        },
      });
    }

    return { backfilled: legacyAccounts.length };
  });
}

export async function verifyPlatformizationMigration() {
  const [
    cokeAccounts,
    identities,
    customers,
    memberships,
    agentBindings,
    defaultAgents,
  ] = await Promise.all([
    db.cokeAccount.count(),
    db.identity.count(),
    db.customer.count(),
    db.membership.count(),
    db.agentBinding.count(),
    db.agent.count({ where: { isDefault: true } }),
  ]);

  const errors: string[] = [];
  if (identities !== cokeAccounts) errors.push(`identity_count_mismatch:${identities}:${cokeAccounts}`);
  if (customers !== cokeAccounts) errors.push(`customer_count_mismatch:${customers}:${cokeAccounts}`);
  if (memberships !== cokeAccounts) errors.push(`membership_count_mismatch:${memberships}:${cokeAccounts}`);
  if (agentBindings !== cokeAccounts) errors.push(`agent_binding_count_mismatch:${agentBindings}:${cokeAccounts}`);
  if (defaultAgents !== 1) errors.push(`default_agent_count:${defaultAgents}`);

  return {
    counts: {
      cokeAccounts,
      identities,
      customers,
      memberships,
      agentBindings,
      defaultAgents,
    },
    errors,
  };
}
```

Create `gateway/packages/api/src/scripts/audit-platformization-baseline.ts`:

```ts
import { db } from '../db/index.js';
import { auditLegacyBaseline } from '../lib/platformization-backfill.js';

const mongoAccountIds = (process.env['MONGO_ACCOUNT_IDS'] ?? '')
  .split(',')
  .map((value) => value.trim())
  .filter(Boolean);

const summary = await auditLegacyBaseline({ mongoAccountIds });
console.log(JSON.stringify(summary, null, 2));
await db.$disconnect();

if (summary.errors.length > 0) {
  process.exit(1);
}
```

Create `gateway/packages/api/src/scripts/backfill-platformization-identity.ts`:

```ts
import { db } from '../db/index.js';
import {
  backfillLegacyCustomers,
  ensureDefaultAgent,
} from '../lib/platformization-backfill.js';

const endpoint = process.env['COKE_AGENT_ENDPOINT']?.trim();
const authToken = process.env['COKE_AGENT_AUTH_TOKEN']?.trim();
const dryRun = process.argv.includes('--dry-run');

if (!endpoint || !authToken) {
  throw new Error('platformization_agent_config_missing');
}

const agentId = await ensureDefaultAgent({ endpoint, authToken });
const summary = await backfillLegacyCustomers({ agentId, dryRun });
console.log(JSON.stringify({ agentId, ...summary }, null, 2));
await db.$disconnect();
```

Create `gateway/packages/api/src/scripts/verify-platformization-migration.ts`:

```ts
import { db } from '../db/index.js';
import { verifyPlatformizationMigration } from '../lib/platformization-backfill.js';

const summary = await verifyPlatformizationMigration();
console.log(JSON.stringify(summary, null, 2));
await db.$disconnect();

if (summary.errors.length > 0) {
  process.exit(1);
}
```

Patch `gateway/packages/api/package.json`:

```json
{
  "scripts": {
    "platformization:audit": "tsx src/scripts/audit-platformization-baseline.ts",
    "platformization:backfill": "tsx src/scripts/backfill-platformization-identity.ts",
    "platformization:verify": "tsx src/scripts/verify-platformization-migration.ts"
  }
}
```

- [ ] **Step 4: Run tests and smoke the CLIs**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/lib/platformization-backfill.test.ts
pnpm --dir gateway/packages/api platformization:audit
COKE_AGENT_ENDPOINT=https://coke.example.com/agent \
COKE_AGENT_AUTH_TOKEN=secret-token \
pnpm --dir gateway/packages/api platformization:backfill -- --dry-run
pnpm --dir gateway/packages/api platformization:verify
```

Expected:

- `platformization-backfill.test.ts` PASS
- `platformization:audit` prints a JSON summary with `counts` and exits `0` on a clean baseline or `1` with explicit drift codes
- `platformization:backfill --dry-run` prints `wouldBackfill`
- `platformization:verify` prints `counts` plus `errors: []` after a successful backfill

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/api/package.json \
        gateway/packages/api/src/lib/platformization-backfill.ts \
        gateway/packages/api/src/lib/platformization-backfill.test.ts \
        gateway/packages/api/src/scripts/audit-platformization-baseline.ts \
        gateway/packages/api/src/scripts/backfill-platformization-identity.ts \
        gateway/packages/api/src/scripts/verify-platformization-migration.ts
git commit -m "feat(gateway): add platform identity migration tooling"
```

## Final Verification Checklist

- [ ] Run the helper and schema suites together:

```bash
pnpm --dir gateway/packages/api test -- \
  src/lib/platformization-migration.test.ts \
  src/lib/platformization-schema.test.ts \
  src/lib/platformization-backfill.test.ts
```

Expected: PASS for all three focused test files.

- [ ] Run the spec-mandated code audits before touching production data:

```bash
rg -n "csu_|ClawscaleUser" /data/projects/coke/gateway/packages/api/src -g '!**/*.test.ts'
rg -n "account_id" /data/projects/coke/agent /data/projects/coke/connector /data/projects/coke/dao /data/projects/coke/util -g '!**/__pycache__/**' -g '!tests/**'
```

Expected:

- First command returns the remaining legacy references that later plans must remove or rewrite.
- Second command returns the Mongo `account_id` touchpoints that must continue to carry byte-identical `Customer.id` values.

- [ ] Rehearse the migration on a disposable Postgres database:

```bash
pnpm --dir gateway/packages/api exec prisma migrate reset --force
pnpm --dir gateway/packages/api platformization:backfill
pnpm --dir gateway/packages/api platformization:verify
```

Expected:

- `migrate reset` recreates the schema cleanly
- `platformization:backfill` prints `{ "backfilled": <legacy_count> }`
- `platformization:verify` exits `0` with `errors: []`

- [ ] Tag the cutover candidate after verification:

```bash
git status --short
git log --oneline -3
```

Expected: clean working tree and the three commits from Tasks 1–3 visible at the top of history.
