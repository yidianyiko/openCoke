# User Link Scheduling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first-version user-link scheduling flow from public user link through service-link activation, bookable-window management, appointment request/confirmation/cancellation, and agent conversation notifications.

**Architecture:** Gateway/Postgres owns user links, link sessions, service links, availability, appointment state, notification intent, and audit events. Gateway Web owns the public `/u/:code` landing and QR route. Worker Runtime exposes agent tools as adapters over Gateway scheduling contracts; Bridge only normalizes scheduling notifications into the existing MongoDB `inputmessages` path.

**Tech Stack:** TypeScript, Hono, Prisma/Postgres, Next.js app router, Vitest, Python worker runtime, pytest, existing Bridge `/bridge/inbound`, MongoDB `inputmessages`.

---

## Scope And Execution Notes

This is one phased plan because the slices form one user path:

1. Gateway schema and domain contracts.
2. Gateway public/customer/internal APIs.
3. Gateway Web public user-link entry.
4. Bridge notification metadata normalization.
5. Worker Runtime scheduling tools.
6. Canonical docs and verification.

The repository has a nested `gateway/` checkout. Gateway commits are made from
`/data/projects/coke/gateway`; root docs and Python runtime commits are made
from `/data/projects/coke`. If the parent root records the gateway gitlink,
commit the nested gateway change first, then commit the parent gitlink together
with root files.

The design deliberately does **not** add automatic hold expiry. Pending
appointment requests hold their generated instance until A handles the request
or either party cancels. The design also allows the same B to hold multiple
independent pending requests with the same A, as long as each request occupies a
different generated instance.

## File Structure

### Gateway API

- Modify: `gateway/packages/api/prisma/schema.prisma`
  - Add scheduling enums and models.
  - Add shareable profile fields to `Customer`.
- Create: `gateway/packages/api/prisma/migrations/20260521090000_user_link_scheduling/migration.sql`
  - Add tables, enum types, indexes, and raw Postgres partial unique indexes.
- Create: `gateway/packages/api/src/scheduling/types.ts`
  - Shared TypeScript domain types, status enums, DTOs, stable error codes.
- Create: `gateway/packages/api/src/scheduling/time.ts`
  - IANA timezone validation, weekly/once recurrence validation, query range
    capping, generated instance tokens, timezone rendering.
- Create: `gateway/packages/api/src/scheduling/user-link-service.ts`
  - User link creation, reset, disable, QR URL data, link-session creation,
    link-session status, claim-session orchestration.
- Create: `gateway/packages/api/src/scheduling/service-link-service.ts`
  - Idempotent service-link creation, removed-link reactivation, block/unblock,
    remove, capability grant decisions.
- Create: `gateway/packages/api/src/scheduling/availability-service.ts`
  - Availability preview, confirmation, idempotent add, rule closure,
    per-instance exclusions, live-hold warning data.
- Create: `gateway/packages/api/src/scheduling/appointment-service.ts`
  - Query bookable instances, request appointment, confirm, reject, cancel,
    list pending requests, release reasons, appointment event writes.
- Create: `gateway/packages/api/src/scheduling/notification-service.ts`
  - Persist notification intent before Bridge calls, build synthetic inbound
    payloads, mark delivered on Bridge HTTP 2xx, retry pending notifications.
- Create: `gateway/packages/api/src/routes/public-user-link-routes.ts`
  - Public route backing for `/api/public/user-links/:code`,
    link-session open/status/claim APIs, and QR metadata.
- Create: `gateway/packages/api/src/routes/customer-scheduling-routes.ts`
  - Authenticated customer scheduling route surface for customer-owned actions.
- Create: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
  - Internal route surface used by Worker Runtime scheduling tools.
- Modify: `gateway/packages/api/src/index.ts`
  - Register public, customer, and internal scheduling routers.
- Create tests:
  - `gateway/packages/api/src/scheduling/time.test.ts`
  - `gateway/packages/api/src/scheduling/user-link-service.test.ts`
  - `gateway/packages/api/src/scheduling/service-link-service.test.ts`
  - `gateway/packages/api/src/scheduling/availability-service.test.ts`
  - `gateway/packages/api/src/scheduling/appointment-service.test.ts`
  - `gateway/packages/api/src/scheduling/notification-service.test.ts`
  - `gateway/packages/api/src/routes/public-user-link-routes.test.ts`
  - `gateway/packages/api/src/routes/customer-scheduling-routes.test.ts`
  - `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`

### Gateway Shared Package

- Modify: `gateway/packages/shared/src/index.ts`
  - Export scheduling DTOs.
- Create: `gateway/packages/shared/src/types/scheduling.ts`
  - Public-safe route response types used by Gateway Web.

### Gateway Web

- Create: `gateway/packages/web/lib/user-link-api.ts`
  - Fetch public user-link metadata, open link session, claim session.
- Create: `gateway/packages/web/app/u/[code]/page.tsx`
  - Public user-link landing page with A profile and state-specific actions.
- Create: `gateway/packages/web/app/u/[code]/qr/route.ts`
  - Server-side QR PNG route for `/u/:code/qr`.
- Create: `gateway/packages/web/app/u/[code]/page.test.tsx`
  - Landing-page state and link-session URL tests.
- Create: `gateway/packages/web/app/u/[code]/qr/route.test.ts`
  - QR route content-type and body tests.
- Modify: `gateway/packages/web/lib/customer-auth.ts`
  - Preserve safe `next` destinations that include `link_session` for login,
    register, and email verification return paths.
- Modify tests:
  - `gateway/packages/web/app/(customer)/auth/login/page.test.tsx`
  - `gateway/packages/web/app/(customer)/auth/register/page.test.tsx`
  - `gateway/packages/web/app/(customer)/auth/verify-email/page.test.tsx`

### Bridge And Worker Runtime

- Modify: `connector/clawscale_bridge/message_gateway.py`
  - Preserve `scheduling_notification` metadata from synthetic inbound payloads
    while keeping MongoDB `message_type` compatible with existing text
    processing.
- Modify tests:
  - `tests/unit/connector/clawscale_bridge/test_message_gateway.py`
  - `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- Create: `agent/agno_agent/capabilities/scheduling.py`
  - Python capability port and Gateway client for scheduling operations.
- Modify: `agent/agno_agent/capabilities/__init__.py`
  - Export `SchedulingCapabilityPort`.
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
  - Register logical scheduling tools from the spec and wire wrappers to the
    scheduling port.
- Modify: `agent/agno_agent/runtime/chat_response_instructions.py`
  - Add a scheduling tool boundary so the model uses scheduling tools only for
    explicit user-link, availability, appointment, and service-link requests.
- Create tests:
  - `tests/unit/agent/test_scheduling_capability.py`
  - `tests/unit/agent/test_agent_runtime_scheduling_tools.py`
  - `tests/unit/agent/test_chat_response_scheduling_instructions.py`

### Docs

- Modify: `docs/product-specs/FEATURE_TREE.md`
  - Add user-link scheduling route and runtime surfaces.
- Modify: `docs/design-docs/data-retention-policy.md`
  - Add scheduling retention policy rows.
- Modify: `docs/ARCHITECTURE.md`
  - Keep the single-Agent runtime tool list current after adding scheduling
    capability wrappers. This plan is based on `f7eb83c` (`Finish Agno
    migration cleanup`), where the architecture doc now names the active Agno
    runtime tools explicitly.
- Modify: `docs/superpowers/specs/2026-05-21-user-link-scheduling-design.md`
  - Only if implementation discovers a necessary contract correction.

## API Route Map

Gateway API routes:

- `GET /api/public/user-links/:code`
- `POST /api/public/user-links/:code/sessions`
- `GET /api/public/link-sessions/:token/status`
- `POST /api/public/link-sessions/:token/claim`
- `GET /api/customer/scheduling/user-link`
- `POST /api/customer/scheduling/user-link/reset`
- `POST /api/customer/scheduling/user-link/disable`
- `POST /api/customer/scheduling/bookable-windows/preview`
- `POST /api/customer/scheduling/bookable-windows/confirm`
- `GET /api/customer/scheduling/bookable-windows`
- `POST /api/customer/scheduling/appointments`
- `GET /api/customer/scheduling/appointments/pending`
- `POST /api/customer/scheduling/appointments/:id/confirm`
- `POST /api/customer/scheduling/appointments/:id/reject`
- `POST /api/customer/scheduling/appointments/:id/cancel`
- `POST /api/customer/scheduling/service-links/:otherAccountId/block`
- `POST /api/customer/scheduling/service-links/:otherAccountId/unblock`
- `DELETE /api/customer/scheduling/service-links/:otherAccountId`
- `POST /api/internal/scheduling/tools/:toolName`
- `POST /api/internal/scheduling/notifications/retry`

Gateway Web routes:

- `GET /u/[code]`
- `GET /u/[code]/qr`

## Task 1: Gateway Schema And Migration

**Files:**
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Create: `gateway/packages/api/prisma/migrations/20260521090000_user_link_scheduling/migration.sql`
- Test: `gateway/packages/api/src/scheduling/schema-contract.test.ts`

- [ ] **Step 1: Write the failing schema contract test**

Create `gateway/packages/api/src/scheduling/schema-contract.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const schemaPath = join(process.cwd(), 'prisma/schema.prisma');
const migrationPath = join(
  process.cwd(),
  'prisma/migrations/20260521090000_user_link_scheduling/migration.sql',
);

describe('user-link scheduling schema contract', () => {
  it('declares scheduling models and no hold expiry field', () => {
    const schema = readFileSync(schemaPath, 'utf8');
    expect(schema).toContain('model UserLink');
    expect(schema).toContain('model LinkSession');
    expect(schema).toContain('model ServiceLink');
    expect(schema).toContain('model BookableWindow');
    expect(schema).toContain('model BookableWindowExclusion');
    expect(schema).toContain('model AppointmentRequest');
    expect(schema).toContain('model AppointmentEvent');
    expect(schema).toContain('model SchedulingNotification');
    expect(schema).toContain('tagline     String?  @db.VarChar(120)');
    expect(schema).toContain('avatarUrl   String?  @map("avatar_url")');
    expect(schema).not.toContain('holdExpiresAt');
    expect(schema).not.toContain('expired');
  });

  it('adds database-level uniqueness for active links and occupied instances', () => {
    const sql = readFileSync(migrationPath, 'utf8');
    expect(sql).toContain('CREATE UNIQUE INDEX "user_links_one_active_per_account"');
    expect(sql).toContain('WHERE status = \\'active\\'');
    expect(sql).toContain('CREATE UNIQUE INDEX "appointment_instance_occupancy_uniq"');
    expect(sql).toContain("WHERE status IN ('pending_held', 'confirmed_shared')");
    expect(sql).toContain('CREATE UNIQUE INDEX "service_links_provider_consumer_uniq"');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/schema-contract.test.ts
```

Expected: FAIL because the schema models and migration file do not exist.

- [ ] **Step 3: Add Prisma enums and models**

Add these enums near the other enum declarations in
`gateway/packages/api/prisma/schema.prisma`:

```prisma
enum UserLinkStatus {
  active
  disabled
}

enum LinkSessionStatus {
  opened
  claimed
  abandoned
}

enum ServiceLinkStatus {
  active
  blocked
  removed
}

enum SchedulingCapability {
  appointment_request
}

enum BookableWindowStatus {
  active
  closed
}

enum BookableWindowType {
  weekly
  once
}

enum AppointmentRequestStatus {
  pending_held
  confirmed_shared
  released
}

enum AppointmentReleaseReason {
  rejected_by_a
  cancelled_by_a
  cancelled_by_b
}

enum AppointmentActorRole {
  provider
  consumer
  system
}

enum SchedulingNotificationStatus {
  pending_delivery
  delivered
  failed
}
```

Add these fields to `model Customer`:

```prisma
  tagline     String?  @db.VarChar(120)
  avatarUrl   String?  @map("avatar_url")

  userLinksAsProvider UserLink[] @relation("ProviderUserLinks")
  serviceLinksAsProvider ServiceLink[] @relation("ProviderServiceLinks")
  serviceLinksAsConsumer ServiceLink[] @relation("ConsumerServiceLinks")
  bookableWindows BookableWindow[] @relation("ProviderBookableWindows")
  appointmentRequestsAsProvider AppointmentRequest[] @relation("ProviderAppointmentRequests")
  appointmentRequestsAsConsumer AppointmentRequest[] @relation("ConsumerAppointmentRequests")
  schedulingNotifications SchedulingNotification[]
```

Add these models after `CalendarImportHandoffSession`:

```prisma
model UserLink {
  id                String         @id @default(cuid())
  providerAccountId String         @map("provider_account_id")
  code              String         @unique
  status            UserLinkStatus @default(active)
  createdAt         DateTime       @default(now()) @map("created_at")
  disabledAt        DateTime?      @map("disabled_at")
  updatedAt         DateTime       @updatedAt @map("updated_at")

  provider     Customer      @relation("ProviderUserLinks", fields: [providerAccountId], references: [id], onDelete: Cascade)
  linkSessions LinkSession[]

  @@index([providerAccountId])
  @@index([status])
  @@map("user_links")
}

model LinkSession {
  id                String            @id @default(cuid())
  tokenHash         String            @unique @map("token_hash")
  userLinkId        String            @map("user_link_id")
  providerAccountId String            @map("provider_account_id")
  consumerAccountId String?           @map("consumer_account_id")
  status            LinkSessionStatus @default(opened)
  openedAt          DateTime          @default(now()) @map("opened_at")
  claimedAt         DateTime?         @map("claimed_at")
  abandonedAt       DateTime?         @map("abandoned_at")
  expiresAt         DateTime          @map("expires_at")
  createdAt         DateTime          @default(now()) @map("created_at")
  updatedAt         DateTime          @updatedAt @map("updated_at")

  userLink UserLink @relation(fields: [userLinkId], references: [id], onDelete: Cascade)

  @@index([providerAccountId, status])
  @@index([consumerAccountId])
  @@index([expiresAt])
  @@map("link_sessions")
}

model ServiceLink {
  id                String              @id @default(cuid())
  providerAccountId String              @map("provider_account_id")
  consumerAccountId String              @map("consumer_account_id")
  status            ServiceLinkStatus   @default(active)
  capabilities      SchedulingCapability[]
  createdAt         DateTime            @default(now()) @map("created_at")
  removedAt         DateTime?           @map("removed_at")
  blockedAt         DateTime?           @map("blocked_at")
  updatedAt         DateTime            @updatedAt @map("updated_at")

  provider Customer @relation("ProviderServiceLinks", fields: [providerAccountId], references: [id], onDelete: Cascade)
  consumer Customer @relation("ConsumerServiceLinks", fields: [consumerAccountId], references: [id], onDelete: Cascade)
  appointmentRequests AppointmentRequest[]

  @@index([providerAccountId, status])
  @@index([consumerAccountId, status])
  @@map("service_links")
}

model BookableWindow {
  id                String             @id @default(cuid())
  providerAccountId String             @map("provider_account_id")
  capability        SchedulingCapability @default(appointment_request)
  type              BookableWindowType
  rule              Json
  ruleFingerprint   String             @map("rule_fingerprint")
  status            BookableWindowStatus @default(active)
  createdAt         DateTime           @default(now()) @map("created_at")
  closedAt          DateTime?          @map("closed_at")
  updatedAt         DateTime           @updatedAt @map("updated_at")

  provider Customer @relation("ProviderBookableWindows", fields: [providerAccountId], references: [id], onDelete: Cascade)
  exclusions BookableWindowExclusion[]
  appointmentRequests AppointmentRequest[]

  @@index([providerAccountId, status])
  @@index([ruleFingerprint])
  @@map("bookable_windows")
}

model BookableWindowExclusion {
  id               String   @id @default(cuid())
  bookableWindowId String   @map("bookable_window_id")
  instanceStart    DateTime @map("instance_start")
  instanceEnd      DateTime @map("instance_end")
  createdAt        DateTime @default(now()) @map("created_at")

  bookableWindow BookableWindow @relation(fields: [bookableWindowId], references: [id], onDelete: Cascade)

  @@unique([bookableWindowId, instanceStart, instanceEnd])
  @@map("bookable_window_exclusions")
}

model AppointmentRequest {
  id                String                   @id @default(cuid())
  providerAccountId String                   @map("provider_account_id")
  consumerAccountId String                   @map("consumer_account_id")
  serviceLinkId     String                   @map("service_link_id")
  bookableWindowId  String                   @map("bookable_window_id")
  instanceStart     DateTime                 @map("instance_start")
  instanceEnd       DateTime                 @map("instance_end")
  timezone          String
  status            AppointmentRequestStatus @default(pending_held)
  releaseReason     AppointmentReleaseReason? @map("release_reason")
  createdAt         DateTime                 @default(now()) @map("created_at")
  releasedAt        DateTime?                @map("released_at")
  updatedAt         DateTime                 @updatedAt @map("updated_at")

  provider Customer @relation("ProviderAppointmentRequests", fields: [providerAccountId], references: [id], onDelete: Cascade)
  consumer Customer @relation("ConsumerAppointmentRequests", fields: [consumerAccountId], references: [id], onDelete: Cascade)
  serviceLink ServiceLink @relation(fields: [serviceLinkId], references: [id], onDelete: Restrict)
  bookableWindow BookableWindow @relation(fields: [bookableWindowId], references: [id], onDelete: Restrict)
  events AppointmentEvent[]
  notifications SchedulingNotification[]

  @@index([providerAccountId, status])
  @@index([consumerAccountId, status])
  @@index([bookableWindowId, instanceStart, instanceEnd])
  @@map("appointment_requests")
}

model AppointmentEvent {
  id             String                @id @default(cuid())
  appointmentId  String                @map("appointment_id")
  fromState      AppointmentRequestStatus? @map("from_state")
  toState        AppointmentRequestStatus  @map("to_state")
  actorAccountId String                @map("actor_account_id")
  actorRole      AppointmentActorRole  @map("actor_role")
  reason         String?
  createdAt      DateTime              @default(now()) @map("created_at")

  appointment AppointmentRequest @relation(fields: [appointmentId], references: [id], onDelete: Cascade)

  @@index([appointmentId, createdAt])
  @@index([actorAccountId, createdAt])
  @@map("appointment_events")
}

model SchedulingNotification {
  id             String                       @id @default(cuid())
  appointmentId  String                       @map("appointment_id")
  recipientAccountId String                   @map("recipient_account_id")
  idempotencyKey String                       @unique @map("idempotency_key")
  kind           String
  payload        Json
  status         SchedulingNotificationStatus @default(pending_delivery)
  attempts       Int                          @default(0)
  lastError      String?                      @map("last_error")
  deliveredAt    DateTime?                    @map("delivered_at")
  createdAt      DateTime                     @default(now()) @map("created_at")
  updatedAt      DateTime                     @updatedAt @map("updated_at")

  appointment AppointmentRequest @relation(fields: [appointmentId], references: [id], onDelete: Cascade)
  recipient Customer @relation(fields: [recipientAccountId], references: [id], onDelete: Cascade)

  @@index([status, createdAt])
  @@index([recipientAccountId, createdAt])
  @@map("scheduling_notifications")
}
```

- [ ] **Step 4: Add the raw migration SQL**

Create `gateway/packages/api/prisma/migrations/20260521090000_user_link_scheduling/migration.sql`.
The migration must include the generated Prisma table DDL plus these raw
indexes:

```sql
CREATE UNIQUE INDEX "user_links_one_active_per_account"
ON "user_links" ("provider_account_id")
WHERE status = 'active';

CREATE UNIQUE INDEX "service_links_provider_consumer_uniq"
ON "service_links" ("provider_account_id", "consumer_account_id");

CREATE UNIQUE INDEX "bookable_windows_active_fingerprint_uniq"
ON "bookable_windows" ("provider_account_id", "capability", "rule_fingerprint")
WHERE status = 'active';

CREATE UNIQUE INDEX "appointment_instance_occupancy_uniq"
ON "appointment_requests" (
  "provider_account_id",
  "bookable_window_id",
  "instance_start",
  "instance_end"
)
WHERE status IN ('pending_held', 'confirmed_shared');
```

- [ ] **Step 5: Run schema tests**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/schema-contract.test.ts
pnpm --dir gateway/packages/api db:generate
pnpm --dir gateway/packages/api build
```

Expected: tests pass, Prisma client generation succeeds, TypeScript build
succeeds.

- [ ] **Step 6: Commit gateway schema**

```bash
cd /data/projects/coke/gateway
git add packages/api/prisma/schema.prisma \
  packages/api/prisma/migrations/20260521090000_user_link_scheduling/migration.sql \
  packages/api/src/scheduling/schema-contract.test.ts
git commit -m "feat: add user link scheduling schema"
```

## Task 2: Scheduling Domain Types And Time Rules

**Files:**
- Create: `gateway/packages/api/src/scheduling/types.ts`
- Create: `gateway/packages/api/src/scheduling/time.ts`
- Test: `gateway/packages/api/src/scheduling/time.test.ts`

- [ ] **Step 1: Write failing time-rule tests**

Create `gateway/packages/api/src/scheduling/time.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
  buildRuleFingerprint,
  capQueryRange,
  generateWindowInstances,
  renderWindowForViewer,
  validateBookableWindowRule,
} from './time.js';

describe('scheduling time rules', () => {
  it('validates first-version weekly rules without RRULE conversion', () => {
    const rule = validateBookableWindowRule({
      type: 'weekly',
      days_of_week: [2, 4],
      time_start: '19:00',
      time_end: '21:00',
      timezone: 'Asia/Shanghai',
      effective_from: '2026-06-01',
      effective_until: null,
    });

    expect(rule.type).toBe('weekly');
    expect(rule.days_of_week).toEqual([2, 4]);
    expect(JSON.stringify(rule)).not.toContain('RRULE');
    expect(buildRuleFingerprint(rule)).toBe(buildRuleFingerprint(rule));
  });

  it('rejects short, overlapping, and invalid timezone windows', () => {
    expect(() => validateBookableWindowRule({
      type: 'weekly',
      days_of_week: [2],
      time_start: '19:00',
      time_end: '19:05',
      timezone: 'Asia/Shanghai',
      effective_from: '2026-06-01',
      effective_until: null,
    })).toThrow('window_too_short');

    expect(() => validateBookableWindowRule({
      type: 'weekly',
      days_of_week: [2],
      time_start: '19:00',
      time_end: '21:00',
      timezone: 'Mars/Base',
      effective_from: '2026-06-01',
      effective_until: null,
    })).toThrow('invalid_timezone');
  });

  it('caps availability query lookahead to 90 days', () => {
    const range = capQueryRange('2026-06-01', '2027-06-01');
    expect(range.dateFrom).toBe('2026-06-01');
    expect(range.dateTo).toBe('2026-08-30');
  });

  it('generates specific weekly instances and renders viewer timezone labels', () => {
    const rule = validateBookableWindowRule({
      type: 'weekly',
      days_of_week: [2],
      time_start: '19:00',
      time_end: '21:00',
      timezone: 'Asia/Shanghai',
      effective_from: '2026-06-01',
      effective_until: null,
    });

    const instances = generateWindowInstances({
      bookableWindowId: 'bw_1',
      rule,
      dateFrom: '2026-06-01',
      dateTo: '2026-06-14',
      excluded: [],
      occupied: [],
    });

    expect(instances).toHaveLength(2);
    expect(instances[0]).toMatchObject({
      bookableWindowId: 'bw_1',
      instanceStart: '2026-06-02T11:00:00.000Z',
      instanceEnd: '2026-06-02T13:00:00.000Z',
    });

    const rendered = renderWindowForViewer(instances[0]!, 'America/Los_Angeles');
    expect(rendered.timezoneLabel).toMatch(/Pacific|GMT-7|GMT-8/);
    expect(rendered.localDate).toBe('2026-06-02');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/time.test.ts
```

Expected: FAIL because `time.ts` does not exist.

- [ ] **Step 3: Add domain type definitions**

Create `gateway/packages/api/src/scheduling/types.ts`:

```ts
export type SchedulingCapability = 'appointment_request';
export type UserLinkStatus = 'active' | 'disabled';
export type LinkSessionStatus = 'opened' | 'claimed' | 'abandoned';
export type ServiceLinkStatus = 'active' | 'blocked' | 'removed';
export type BookableWindowStatus = 'active' | 'closed';
export type AppointmentRequestStatus = 'pending_held' | 'confirmed_shared' | 'released';
export type AppointmentReleaseReason = 'rejected_by_a' | 'cancelled_by_a' | 'cancelled_by_b';
export type AppointmentActorRole = 'provider' | 'consumer' | 'system';

export interface WeeklyBookableWindowRule {
  type: 'weekly';
  days_of_week: number[];
  time_start: string;
  time_end: string;
  timezone: string;
  effective_from: string;
  effective_until: string | null;
}

export interface OnceBookableWindowRule {
  type: 'once';
  date: string;
  time_start: string;
  time_end: string;
  timezone: string;
}

export type BookableWindowRule = WeeklyBookableWindowRule | OnceBookableWindowRule;

export interface GeneratedWindowInstance {
  windowInstanceId: string;
  bookableWindowId: string;
  instanceStart: string;
  instanceEnd: string;
  providerTimezone: string;
}

export interface SchedulingErrorBody {
  ok: false;
  error:
    | 'invalid_body'
    | 'invalid_timezone'
    | 'window_too_short'
    | 'window_overlap'
    | 'service_link_required'
    | 'service_link_blocked'
    | 'slot_unavailable'
    | 'appointment_not_found'
    | 'not_allowed'
    | 'cooldown_active'
    | 'bridge_delivery_failed';
}
```

- [ ] **Step 4: Implement `time.ts`**

Create `gateway/packages/api/src/scheduling/time.ts` with these exported
functions:

```ts
import { createHash, createHmac } from 'node:crypto';
import type { BookableWindowRule, GeneratedWindowInstance } from './types.js';

const LOCAL_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const LOCAL_TIME_RE = /^\d{2}:\d{2}$/;
const MIN_DURATION_MINUTES = 15;
const MAX_LOOKAHEAD_DAYS = 90;
const INSTANCE_SECRET = process.env['SCHEDULING_INSTANCE_SECRET'] || 'dev-scheduling-instance-secret';

function assertLocalDate(value: unknown, code = 'invalid_date'): string {
  if (typeof value !== 'string' || !LOCAL_DATE_RE.test(value)) throw new Error(code);
  const date = new Date(`${value}T00:00:00.000Z`);
  if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value) throw new Error(code);
  return value;
}

function minutes(value: string): number {
  if (!LOCAL_TIME_RE.test(value)) throw new Error('invalid_time');
  const [hour, minute] = value.split(':').map(Number);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) throw new Error('invalid_time');
  return hour * 60 + minute;
}

export function isValidIanaTimezone(value: string): boolean {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: value }).format(new Date());
    return true;
  } catch {
    return false;
  }
}

export function validateBookableWindowRule(raw: unknown): BookableWindowRule {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) throw new Error('invalid_rule');
  const value = raw as Record<string, unknown>;
  const type = value.type;
  const timeStart = typeof value.time_start === 'string' ? value.time_start : '';
  const timeEnd = typeof value.time_end === 'string' ? value.time_end : '';
  const timezone = typeof value.timezone === 'string' ? value.timezone : '';
  if (!isValidIanaTimezone(timezone)) throw new Error('invalid_timezone');
  if (minutes(timeEnd) - minutes(timeStart) < MIN_DURATION_MINUTES) throw new Error('window_too_short');

  if (type === 'weekly') {
    const days = Array.isArray(value.days_of_week) ? value.days_of_week : [];
    if (days.length === 0 || days.some((day) => typeof day !== 'number' || day < 1 || day > 7)) {
      throw new Error('invalid_weekday');
    }
    return {
      type: 'weekly',
      days_of_week: [...new Set(days)].sort((a, b) => a - b),
      time_start: timeStart,
      time_end: timeEnd,
      timezone,
      effective_from: assertLocalDate(value.effective_from),
      effective_until: value.effective_until === null ? null : assertLocalDate(value.effective_until),
    };
  }

  if (type === 'once') {
    return {
      type: 'once',
      date: assertLocalDate(value.date),
      time_start: timeStart,
      time_end: timeEnd,
      timezone,
    };
  }

  throw new Error('invalid_rule_type');
}

export function buildRuleFingerprint(rule: BookableWindowRule): string {
  return createHash('sha256').update(JSON.stringify(rule)).digest('hex');
}

export function capQueryRange(dateFrom: string, dateTo?: string): { dateFrom: string; dateTo: string } {
  const start = new Date(`${assertLocalDate(dateFrom)}T00:00:00.000Z`);
  const requestedEnd = dateTo ? new Date(`${assertLocalDate(dateTo)}T00:00:00.000Z`) : new Date(start);
  if (!dateTo) requestedEnd.setUTCDate(requestedEnd.getUTCDate() + 14);
  const maxEnd = new Date(start);
  maxEnd.setUTCDate(maxEnd.getUTCDate() + MAX_LOOKAHEAD_DAYS);
  const end = requestedEnd > maxEnd ? maxEnd : requestedEnd;
  return { dateFrom: start.toISOString().slice(0, 10), dateTo: end.toISOString().slice(0, 10) };
}

function utcDateForLocal(date: string, localMinutes: number): Date {
  const base = new Date(`${date}T00:00:00.000Z`);
  base.setUTCMinutes(base.getUTCMinutes() + localMinutes);
  return base;
}

export function encodeWindowInstanceId(input: {
  bookableWindowId: string;
  instanceStart: string;
  instanceEnd: string;
}): string {
  const payload = `${input.bookableWindowId}|${input.instanceStart}|${input.instanceEnd}`;
  const sig = createHmac('sha256', INSTANCE_SECRET).update(payload).digest('base64url').slice(0, 16);
  return Buffer.from(`${payload}|${sig}`).toString('base64url');
}

export function generateWindowInstances(input: {
  bookableWindowId: string;
  rule: BookableWindowRule;
  dateFrom: string;
  dateTo: string;
  excluded: Array<{ instanceStart: string; instanceEnd: string }>;
  occupied: Array<{ instanceStart: string; instanceEnd: string }>;
}): GeneratedWindowInstance[] {
  const from = new Date(`${assertLocalDate(input.dateFrom)}T00:00:00.000Z`);
  const to = new Date(`${assertLocalDate(input.dateTo)}T00:00:00.000Z`);
  const blocked = new Set([...input.excluded, ...input.occupied].map((item) => `${item.instanceStart}|${item.instanceEnd}`));
  const out: GeneratedWindowInstance[] = [];
  for (const cursor = new Date(from); cursor <= to; cursor.setUTCDate(cursor.getUTCDate() + 1)) {
    const date = cursor.toISOString().slice(0, 10);
    const weekday = cursor.getUTCDay() === 0 ? 7 : cursor.getUTCDay();
    if (input.rule.type === 'weekly' && !input.rule.days_of_week.includes(weekday)) continue;
    if (input.rule.type === 'weekly' && date < input.rule.effective_from) continue;
    if (input.rule.type === 'weekly' && input.rule.effective_until && date > input.rule.effective_until) continue;
    if (input.rule.type === 'once' && date !== input.rule.date) continue;

    const instanceStart = utcDateForLocal(date, minutes(input.rule.time_start)).toISOString();
    const instanceEnd = utcDateForLocal(date, minutes(input.rule.time_end)).toISOString();
    if (blocked.has(`${instanceStart}|${instanceEnd}`)) continue;
    out.push({
      windowInstanceId: encodeWindowInstanceId({ bookableWindowId: input.bookableWindowId, instanceStart, instanceEnd }),
      bookableWindowId: input.bookableWindowId,
      instanceStart,
      instanceEnd,
      providerTimezone: input.rule.timezone,
    });
  }
  return out;
}

export function renderWindowForViewer(instance: GeneratedWindowInstance, viewerTimezone: string) {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: viewerTimezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
    hour12: false,
  });
  const parts = formatter.formatToParts(new Date(instance.instanceStart));
  const byType = new Map(parts.map((part) => [part.type, part.value]));
  return {
    localDate: `${byType.get('year')}-${byType.get('month')}-${byType.get('day')}`,
    localTime: `${byType.get('hour')}:${byType.get('minute')}`,
    timezoneLabel: byType.get('timeZoneName') || viewerTimezone,
  };
}
```

- [ ] **Step 5: Run the time-rule tests**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/time.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit time rules**

```bash
cd /data/projects/coke/gateway
git add packages/api/src/scheduling/types.ts \
  packages/api/src/scheduling/time.ts \
  packages/api/src/scheduling/time.test.ts
git commit -m "feat: add scheduling time rules"
```

## Task 3: User Link, Link Session, And Service Link Domain Services

**Files:**
- Create: `gateway/packages/api/src/scheduling/user-link-service.ts`
- Create: `gateway/packages/api/src/scheduling/service-link-service.ts`
- Test: `gateway/packages/api/src/scheduling/user-link-service.test.ts`
- Test: `gateway/packages/api/src/scheduling/service-link-service.test.ts`

- [ ] **Step 1: Write failing service tests**

Create `gateway/packages/api/src/scheduling/user-link-service.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  createLinkSession,
  getOrCreateActiveUserLink,
  resetUserLink,
} from './user-link-service.js';

const db = {
  userLink: { findFirst: vi.fn(), create: vi.fn(), updateMany: vi.fn() },
  linkSession: { create: vi.fn() },
  customer: { findUnique: vi.fn() },
};

describe('user link service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.DOMAIN_CLIENT = 'https://kap.example';
  });

  it('creates a first active user link with shareable profile fields', async () => {
    db.userLink.findFirst.mockResolvedValueOnce(null);
    db.customer.findUnique.mockResolvedValueOnce({
      id: 'ck_a',
      displayName: 'Coach A',
      tagline: 'Strength coaching',
      avatarUrl: 'https://img.example/a.png',
    });
    db.userLink.create.mockResolvedValueOnce({ id: 'ul_1', code: 'AbCdEfGhIjK_', status: 'active' });

    const result = await getOrCreateActiveUserLink(db as never, { providerAccountId: 'ck_a' });

    expect(result.url).toBe('https://kap.example/u/AbCdEfGhIjK_');
    expect(result.profile).toEqual({
      displayName: 'Coach A',
      tagline: 'Strength coaching',
      avatarUrl: 'https://img.example/a.png',
    });
    expect(db.userLink.create.mock.calls[0][0].data.code).toMatch(/^[A-Za-z0-9_-]{12}$/);
  });

  it('resets by disabling the old active code and creating a new one', async () => {
    db.customer.findUnique.mockResolvedValueOnce({ id: 'ck_a', displayName: 'Coach A', tagline: null, avatarUrl: null });
    db.userLink.create.mockResolvedValueOnce({ id: 'ul_2', code: 'NewCode123__', status: 'active' });

    await resetUserLink(db as never, { providerAccountId: 'ck_a' });

    expect(db.userLink.updateMany).toHaveBeenCalledWith({
      where: { providerAccountId: 'ck_a', status: 'active' },
      data: { status: 'disabled', disabledAt: expect.any(Date) },
    });
    expect(db.userLink.create).toHaveBeenCalled();
  });

  it('opens a link session with token hash and 24 hour expiry', async () => {
    db.userLink.findFirst.mockResolvedValueOnce({
      id: 'ul_1',
      code: 'AbCdEfGhIjK_',
      status: 'active',
      providerAccountId: 'ck_a',
    });
    db.linkSession.create.mockImplementation(async ({ data }) => ({ id: 'ls_1', ...data }));

    const result = await createLinkSession(db as never, { code: 'AbCdEfGhIjK_' });

    expect(result.token).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(result.nextUrl).toContain('/auth/login?next=');
    expect(db.linkSession.create.mock.calls[0][0].data.tokenHash).not.toBe(result.token);
    expect(db.linkSession.create.mock.calls[0][0].data.status).toBe('opened');
  });
});
```

Create `gateway/packages/api/src/scheduling/service-link-service.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  blockServiceLink,
  createOrActivateServiceLink,
  removeServiceLink,
} from './service-link-service.js';

const tx = {
  serviceLink: { findFirst: vi.fn(), create: vi.fn(), update: vi.fn() },
  appointmentRequest: { updateMany: vi.fn() },
  schedulingNotification: { createMany: vi.fn() },
};

describe('service link service', () => {
  beforeEach(() => vi.clearAllMocks());

  it('is idempotent when an active link already exists', async () => {
    tx.serviceLink.findFirst.mockResolvedValueOnce({
      id: 'sl_1',
      status: 'active',
      capabilities: ['appointment_request'],
    });

    const result = await createOrActivateServiceLink(tx as never, {
      providerAccountId: 'ck_a',
      consumerAccountId: 'ck_b',
    });

    expect(result.status).toBe('active');
    expect(tx.serviceLink.create).not.toHaveBeenCalled();
  });

  it('reactivates a removed link instead of creating a duplicate row', async () => {
    tx.serviceLink.findFirst.mockResolvedValueOnce({ id: 'sl_1', status: 'removed', capabilities: [] });
    tx.serviceLink.update.mockResolvedValueOnce({ id: 'sl_1', status: 'active', capabilities: ['appointment_request'] });

    await createOrActivateServiceLink(tx as never, {
      providerAccountId: 'ck_a',
      consumerAccountId: 'ck_b',
    });

    expect(tx.serviceLink.update).toHaveBeenCalledWith({
      where: { id: 'sl_1' },
      data: {
        status: 'active',
        removedAt: null,
        capabilities: ['appointment_request'],
      },
    });
    expect(tx.serviceLink.create).not.toHaveBeenCalled();
  });

  it('does not grant capability when a blocked link exists', async () => {
    tx.serviceLink.findFirst.mockResolvedValueOnce({ id: 'sl_1', status: 'blocked', capabilities: [] });

    const result = await createOrActivateServiceLink(tx as never, {
      providerAccountId: 'ck_a',
      consumerAccountId: 'ck_b',
    });

    expect(result.status).toBe('blocked');
    expect(tx.serviceLink.create).not.toHaveBeenCalled();
  });

  it('blocking releases pending requests without revealing block reason', async () => {
    tx.serviceLink.findFirst.mockResolvedValueOnce({ id: 'sl_1', status: 'active' });
    tx.serviceLink.update.mockResolvedValueOnce({ id: 'sl_1', status: 'blocked' });
    tx.appointmentRequest.updateMany.mockResolvedValueOnce({ count: 2 });

    await blockServiceLink(tx as never, {
      providerAccountId: 'ck_a',
      consumerAccountId: 'ck_b',
    });

    expect(tx.appointmentRequest.updateMany).toHaveBeenCalledWith({
      where: { providerAccountId: 'ck_a', consumerAccountId: 'ck_b', status: 'pending_held' },
      data: { status: 'released', releaseReason: 'cancelled_by_a', releasedAt: expect.any(Date) },
    });
  });

  it('removal is reversible and does not block future user-link flow', async () => {
    tx.serviceLink.update.mockResolvedValueOnce({ id: 'sl_1', status: 'removed' });
    await removeServiceLink(tx as never, { serviceLinkId: 'sl_1' });
    expect(tx.serviceLink.update).toHaveBeenCalledWith({
      where: { id: 'sl_1' },
      data: { status: 'removed', removedAt: expect.any(Date) },
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/scheduling/user-link-service.test.ts \
  src/scheduling/service-link-service.test.ts
```

Expected: FAIL because the services do not exist.

- [ ] **Step 3: Implement user-link service**

Create `gateway/packages/api/src/scheduling/user-link-service.ts` with:

```ts
import { createHash, randomBytes } from 'node:crypto';

const LINK_SESSION_TTL_MS = 24 * 60 * 60 * 1000;

function readDomainClient(): string {
  const value = process.env['DOMAIN_CLIENT']?.trim().replace(/\/$/, '');
  if (!value) throw new Error('DOMAIN_CLIENT is required');
  return value;
}

function newUserLinkCode(): string {
  return randomBytes(9).toString('base64url').slice(0, 12);
}

function newSessionToken(): string {
  return randomBytes(32).toString('base64url');
}

function tokenHash(token: string): string {
  return createHash('sha256').update(token.trim()).digest('hex');
}

async function readProviderProfile(client: any, providerAccountId: string) {
  const customer = await client.customer.findUnique({
    where: { id: providerAccountId },
    select: { id: true, displayName: true, tagline: true, avatarUrl: true },
  });
  if (!customer) throw new Error('provider_not_found');
  return {
    displayName: customer.displayName,
    tagline: customer.tagline ?? null,
    avatarUrl: customer.avatarUrl ?? null,
  };
}

export async function getOrCreateActiveUserLink(client: any, input: { providerAccountId: string }) {
  const existing = await client.userLink.findFirst({
    where: { providerAccountId: input.providerAccountId, status: 'active' },
    orderBy: { createdAt: 'desc' },
  });
  const link = existing ?? await client.userLink.create({
    data: {
      providerAccountId: input.providerAccountId,
      code: newUserLinkCode(),
      status: 'active',
    },
  });
  const profile = await readProviderProfile(client, input.providerAccountId);
  return {
    id: link.id,
    code: link.code,
    status: link.status,
    url: `${readDomainClient()}/u/${encodeURIComponent(link.code)}`,
    qrUrl: `${readDomainClient()}/u/${encodeURIComponent(link.code)}/qr`,
    profile,
  };
}

export async function readPublicUserLinkByCode(client: any, input: { code: string }) {
  const link = await client.userLink.findFirst({
    where: { code: input.code, status: 'active' },
  });
  if (!link) throw new Error('link_not_active');
  const profile = await readProviderProfile(client, link.providerAccountId);
  return {
    id: link.id,
    code: link.code,
    status: link.status,
    url: `${readDomainClient()}/u/${encodeURIComponent(link.code)}`,
    qrUrl: `${readDomainClient()}/u/${encodeURIComponent(link.code)}/qr`,
    profile,
  };
}

export async function resetUserLink(client: any, input: { providerAccountId: string }) {
  await client.userLink.updateMany({
    where: { providerAccountId: input.providerAccountId, status: 'active' },
    data: { status: 'disabled', disabledAt: new Date() },
  });
  const link = await client.userLink.create({
    data: { providerAccountId: input.providerAccountId, code: newUserLinkCode(), status: 'active' },
  });
  const profile = await readProviderProfile(client, input.providerAccountId);
  return {
    id: link.id,
    code: link.code,
    status: link.status,
    url: `${readDomainClient()}/u/${encodeURIComponent(link.code)}`,
    qrUrl: `${readDomainClient()}/u/${encodeURIComponent(link.code)}/qr`,
    profile,
  };
}

export async function disableUserLink(client: any, input: { providerAccountId: string }) {
  await client.userLink.updateMany({
    where: { providerAccountId: input.providerAccountId, status: 'active' },
    data: { status: 'disabled', disabledAt: new Date() },
  });
  return { disabled: true };
}

export async function createLinkSession(client: any, input: { code: string }) {
  const link = await client.userLink.findFirst({
    where: { code: input.code, status: 'active' },
  });
  if (!link) throw new Error('link_not_active');
  const token = newSessionToken();
  const session = await client.linkSession.create({
    data: {
      tokenHash: tokenHash(token),
      userLinkId: link.id,
      providerAccountId: link.providerAccountId,
      status: 'opened',
      expiresAt: new Date(Date.now() + LINK_SESSION_TTL_MS),
    },
  });
  const next = `/u/${encodeURIComponent(input.code)}?link_session=${encodeURIComponent(token)}`;
  return {
    token,
    session,
    nextUrl: `/auth/login?next=${encodeURIComponent(next)}`,
    registerUrl: `/auth/register?next=${encodeURIComponent(next)}`,
  };
}
```

- [ ] **Step 4: Implement service-link service**

Create `gateway/packages/api/src/scheduling/service-link-service.ts` with:

```ts
type ServiceLinkStatus = 'active' | 'blocked' | 'removed';

export async function createOrActivateServiceLink(
  client: any,
  input: { providerAccountId: string; consumerAccountId: string },
): Promise<{ id: string; status: ServiceLinkStatus; capabilities: string[] }> {
  const existing = await client.serviceLink.findFirst({
    where: {
      providerAccountId: input.providerAccountId,
      consumerAccountId: input.consumerAccountId,
    },
  });
  if (existing?.status === 'active' || existing?.status === 'blocked') {
    return existing;
  }
  if (existing?.status === 'removed') {
    return client.serviceLink.update({
      where: { id: existing.id },
      data: {
        status: 'active',
        removedAt: null,
        capabilities: ['appointment_request'],
      },
    });
  }
  return client.serviceLink.create({
    data: {
      providerAccountId: input.providerAccountId,
      consumerAccountId: input.consumerAccountId,
      status: 'active',
      capabilities: ['appointment_request'],
    },
  });
}

export async function blockServiceLink(
  client: any,
  input: { providerAccountId: string; consumerAccountId: string },
) {
  const existing = await client.serviceLink.findFirst({
    where: {
      providerAccountId: input.providerAccountId,
      consumerAccountId: input.consumerAccountId,
    },
  });
  if (!existing) throw new Error('service_link_not_found');
  const link = await client.serviceLink.update({
    where: { id: existing.id },
    data: { status: 'blocked', blockedAt: new Date() },
  });
  await client.appointmentRequest.updateMany({
    where: {
      providerAccountId: input.providerAccountId,
      consumerAccountId: input.consumerAccountId,
      status: 'pending_held',
    },
    data: {
      status: 'released',
      releaseReason: 'cancelled_by_a',
      releasedAt: new Date(),
    },
  });
  return link;
}

export async function unblockServiceLink(
  client: any,
  input: { providerAccountId: string; consumerAccountId: string },
) {
  const existing = await client.serviceLink.findFirst({
    where: {
      providerAccountId: input.providerAccountId,
      consumerAccountId: input.consumerAccountId,
    },
  });
  if (!existing) throw new Error('service_link_not_found');
  return client.serviceLink.update({
    where: { id: existing.id },
    data: { status: 'active', blockedAt: null, capabilities: ['appointment_request'] },
  });
}

export async function removeServiceLink(client: any, input: { serviceLinkId: string }) {
  return client.serviceLink.update({
    where: { id: input.serviceLinkId },
    data: { status: 'removed', removedAt: new Date() },
  });
}
```

- [ ] **Step 5: Run domain service tests**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/scheduling/user-link-service.test.ts \
  src/scheduling/service-link-service.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit domain services**

```bash
cd /data/projects/coke/gateway
git add packages/api/src/scheduling/user-link-service.ts \
  packages/api/src/scheduling/user-link-service.test.ts \
  packages/api/src/scheduling/service-link-service.ts \
  packages/api/src/scheduling/service-link-service.test.ts
git commit -m "feat: add user link and service link services"
```

## Task 4: Availability And Appointment State Services

**Files:**
- Create: `gateway/packages/api/src/scheduling/availability-service.ts`
- Create: `gateway/packages/api/src/scheduling/appointment-service.ts`
- Test: `gateway/packages/api/src/scheduling/availability-service.test.ts`
- Test: `gateway/packages/api/src/scheduling/appointment-service.test.ts`

- [ ] **Step 1: Write failing availability tests**

Create `gateway/packages/api/src/scheduling/availability-service.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  closeBookableWindow,
  confirmBookableWindowPreview,
  previewBookableWindows,
} from './availability-service.js';

const client = {
  bookableWindow: { findFirst: vi.fn(), create: vi.fn(), update: vi.fn() },
  appointmentRequest: { findMany: vi.fn(), updateMany: vi.fn() },
  appointmentEvent: { createMany: vi.fn() },
};

describe('availability service', () => {
  beforeEach(() => vi.clearAllMocks());

  it('previews parsed weekly windows and requires confirmation before commit', async () => {
    const preview = await previewBookableWindows({
      providerAccountId: 'ck_a',
      instruction: '每周二和周四晚上 7 点到 9 点可以约训练',
      timezone: 'Asia/Shanghai',
    });

    expect(preview.previewId).toMatch(/^bwp_/);
    expect(preview.windows[0].rule).toMatchObject({
      type: 'weekly',
      days_of_week: [2, 4],
      time_start: '19:00',
      time_end: '21:00',
      timezone: 'Asia/Shanghai',
    });
    expect(client.bookableWindow.create).not.toHaveBeenCalled();
  });

  it('deduplicates identical active window rules on confirm', async () => {
    client.bookableWindow.findFirst.mockResolvedValueOnce({ id: 'bw_existing', status: 'active' });

    const result = await confirmBookableWindowPreview(client as never, {
      providerAccountId: 'ck_a',
      preview: {
        previewId: 'bwp_1',
        windows: [{
          rule: {
            type: 'weekly',
            days_of_week: [2],
            time_start: '19:00',
            time_end: '21:00',
            timezone: 'Asia/Shanghai',
            effective_from: '2026-06-01',
            effective_until: null,
          },
        }],
      },
    });

    expect(result.createdIds).toEqual([]);
    expect(result.reusedIds).toEqual(['bw_existing']);
    expect(client.bookableWindow.create).not.toHaveBeenCalled();
  });

  it('warns before closing a rule that has pending held requests', async () => {
    client.appointmentRequest.findMany.mockResolvedValueOnce([{ id: 'ar_1' }, { id: 'ar_2' }]);

    const result = await closeBookableWindow(client as never, {
      providerAccountId: 'ck_a',
      bookableWindowId: 'bw_1',
      confirmCancelPending: false,
    });

    expect(result).toEqual({ ok: false, error: 'pending_requests_require_confirmation', pendingCount: 2 });
    expect(client.bookableWindow.update).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Write failing appointment tests**

Create `gateway/packages/api/src/scheduling/appointment-service.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  cancelAppointment,
  confirmAppointment,
  listPendingRequests,
  queryBookableWindows,
  rejectAppointment,
  requestAppointment,
} from './appointment-service.js';

const tx = {
  serviceLink: { findFirst: vi.fn() },
  bookableWindow: { findMany: vi.fn() },
  bookableWindowExclusion: { findMany: vi.fn() },
  appointmentRequest: { findMany: vi.fn(), create: vi.fn(), findFirst: vi.fn(), update: vi.fn() },
  appointmentEvent: { create: vi.fn() },
};

describe('appointment service', () => {
  beforeEach(() => vi.clearAllMocks());

  it('allows the same B to hold multiple independent instances with A', async () => {
    tx.serviceLink.findFirst.mockResolvedValue({ id: 'sl_1', status: 'active', capabilities: ['appointment_request'] });
    tx.appointmentRequest.create
      .mockResolvedValueOnce({ id: 'ar_1', status: 'pending_held', instanceStart: new Date('2026-06-02T11:00:00.000Z') })
      .mockResolvedValueOnce({ id: 'ar_2', status: 'pending_held', instanceStart: new Date('2026-06-09T11:00:00.000Z') });

    await requestAppointment(tx as never, {
      providerAccountId: 'ck_a',
      consumerAccountId: 'ck_b',
      bookableWindowId: 'bw_1',
      instanceStart: '2026-06-02T11:00:00.000Z',
      instanceEnd: '2026-06-02T13:00:00.000Z',
      timezone: 'Asia/Shanghai',
      idempotencyKey: 'msg_1',
    });
    await requestAppointment(tx as never, {
      providerAccountId: 'ck_a',
      consumerAccountId: 'ck_b',
      bookableWindowId: 'bw_1',
      instanceStart: '2026-06-09T11:00:00.000Z',
      instanceEnd: '2026-06-09T13:00:00.000Z',
      timezone: 'Asia/Shanghai',
      idempotencyKey: 'msg_2',
    });

    expect(tx.appointmentRequest.create).toHaveBeenCalledTimes(2);
    expect(JSON.stringify(tx.appointmentRequest.create.mock.calls)).not.toContain('holdExpiresAt');
  });

  it('maps Postgres unique conflicts to slot_unavailable', async () => {
    tx.serviceLink.findFirst.mockResolvedValue({ id: 'sl_1', status: 'active', capabilities: ['appointment_request'] });
    tx.appointmentRequest.create.mockRejectedValueOnce({ code: 'P2002' });

    await expect(requestAppointment(tx as never, {
      providerAccountId: 'ck_a',
      consumerAccountId: 'ck_c',
      bookableWindowId: 'bw_1',
      instanceStart: '2026-06-02T11:00:00.000Z',
      instanceEnd: '2026-06-02T13:00:00.000Z',
      timezone: 'Asia/Shanghai',
      idempotencyKey: 'msg_3',
    })).rejects.toThrow('slot_unavailable');
  });

  it('confirms, rejects, and cancels with release reasons and events', async () => {
    tx.appointmentRequest.findFirst.mockResolvedValueOnce({
      id: 'ar_1',
      providerAccountId: 'ck_a',
      consumerAccountId: 'ck_b',
      status: 'pending_held',
    });
    tx.appointmentRequest.update.mockResolvedValueOnce({ id: 'ar_1', status: 'confirmed_shared' });

    await confirmAppointment(tx as never, { actorAccountId: 'ck_a', requestId: 'ar_1', idempotencyKey: 'msg_4' });

    expect(tx.appointmentEvent.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        appointmentId: 'ar_1',
        fromState: 'pending_held',
        toState: 'confirmed_shared',
        actorRole: 'provider',
      }),
    });

    tx.appointmentRequest.findFirst.mockResolvedValueOnce({
      id: 'ar_2',
      providerAccountId: 'ck_a',
      consumerAccountId: 'ck_b',
      status: 'pending_held',
    });
    tx.appointmentRequest.update.mockResolvedValueOnce({ id: 'ar_2', status: 'released', releaseReason: 'rejected_by_a' });

    await rejectAppointment(tx as never, { actorAccountId: 'ck_a', requestId: 'ar_2', idempotencyKey: 'msg_5' });
    expect(tx.appointmentRequest.update).toHaveBeenLastCalledWith({
      where: { id: 'ar_2' },
      data: { status: 'released', releaseReason: 'rejected_by_a', releasedAt: expect.any(Date) },
    });
  });

  it('lists pending requests for A with hold age instead of TTL', async () => {
    tx.appointmentRequest.findMany.mockResolvedValueOnce([{
      id: 'ar_1',
      createdAt: new Date('2026-06-01T00:00:00.000Z'),
      consumer: { displayName: 'Student B' },
      instanceStart: new Date('2026-06-02T11:00:00.000Z'),
      instanceEnd: new Date('2026-06-02T13:00:00.000Z'),
    }]);

    const result = await listPendingRequests(tx as never, {
      providerAccountId: 'ck_a',
      now: new Date('2026-06-01T03:00:00.000Z'),
    });

    expect(result[0]).toMatchObject({ requesterDisplayName: 'Student B', holdAgeMinutes: 180 });
    expect(result[0]).not.toHaveProperty('expiresAt');
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/scheduling/availability-service.test.ts \
  src/scheduling/appointment-service.test.ts
```

Expected: FAIL because the services do not exist.

- [ ] **Step 4: Implement availability service**

Create `gateway/packages/api/src/scheduling/availability-service.ts` with:

```ts
import { buildRuleFingerprint, validateBookableWindowRule } from './time.js';
import type { BookableWindowRule } from './types.js';

export interface BookableWindowPreview {
  previewId: string;
  windows: Array<{ rule: BookableWindowRule; fingerprint: string }>;
}

export async function previewBookableWindows(input: {
  providerAccountId: string;
  instruction: string;
  timezone: string;
}): Promise<BookableWindowPreview> {
  const normalized = input.instruction.replace(/\s+/g, '');
  const days = [
    ...(normalized.includes('周二') || normalized.includes('星期二') ? [2] : []),
    ...(normalized.includes('周四') || normalized.includes('星期四') ? [4] : []),
  ];
  const rule = validateBookableWindowRule({
    type: 'weekly',
    days_of_week: days.length ? days : [2],
    time_start: normalized.includes('7点') || normalized.includes('七点') ? '19:00' : '09:00',
    time_end: normalized.includes('9点') || normalized.includes('九点') ? '21:00' : '10:00',
    timezone: input.timezone,
    effective_from: new Date().toISOString().slice(0, 10),
    effective_until: null,
  });
  return {
    previewId: `bwp_${Buffer.from(JSON.stringify(rule)).toString('base64url').slice(0, 24)}`,
    windows: [{ rule, fingerprint: buildRuleFingerprint(rule) }],
  };
}

export async function confirmBookableWindowPreview(client: any, input: {
  providerAccountId: string;
  preview: BookableWindowPreview;
}) {
  const createdIds: string[] = [];
  const reusedIds: string[] = [];
  for (const window of input.preview.windows) {
    const existing = await client.bookableWindow.findFirst({
      where: {
        providerAccountId: input.providerAccountId,
        capability: 'appointment_request',
        ruleFingerprint: window.fingerprint,
        status: 'active',
      },
    });
    if (existing) {
      reusedIds.push(existing.id);
      continue;
    }
    const created = await client.bookableWindow.create({
      data: {
        providerAccountId: input.providerAccountId,
        capability: 'appointment_request',
        type: window.rule.type,
        rule: window.rule,
        ruleFingerprint: window.fingerprint,
        status: 'active',
      },
    });
    createdIds.push(created.id);
  }
  return { createdIds, reusedIds };
}

export async function closeBookableWindow(client: any, input: {
  providerAccountId: string;
  bookableWindowId: string;
  confirmCancelPending: boolean;
}) {
  const pending = await client.appointmentRequest.findMany({
    where: {
      providerAccountId: input.providerAccountId,
      bookableWindowId: input.bookableWindowId,
      status: 'pending_held',
    },
    select: { id: true },
  });
  if (pending.length > 0 && !input.confirmCancelPending) {
    return { ok: false, error: 'pending_requests_require_confirmation', pendingCount: pending.length };
  }
  await client.bookableWindow.update({
    where: { id: input.bookableWindowId },
    data: { status: 'closed', closedAt: new Date() },
  });
  if (pending.length > 0) {
    await client.appointmentRequest.updateMany({
      where: { id: { in: pending.map((item: { id: string }) => item.id) } },
      data: { status: 'released', releaseReason: 'cancelled_by_a', releasedAt: new Date() },
    });
  }
  return { ok: true, cancelledPendingCount: pending.length };
}
```

- [ ] **Step 5: Implement appointment service**

Create `gateway/packages/api/src/scheduling/appointment-service.ts` with
functions matching the tests. Required behavior:

```ts
import type { BookableWindowRule } from './types.js';
import { capQueryRange, generateWindowInstances, renderWindowForViewer } from './time.js';

function isUniqueConflict(error: unknown): boolean {
  return typeof error === 'object' && error !== null && (error as { code?: unknown }).code === 'P2002';
}

async function requireActiveServiceLink(client: any, providerAccountId: string, consumerAccountId: string) {
  const serviceLink = await client.serviceLink.findFirst({
    where: {
      providerAccountId,
      consumerAccountId,
      status: 'active',
      capabilities: { has: 'appointment_request' },
    },
  });
  if (!serviceLink) throw new Error('service_link_required');
  return serviceLink;
}

export async function requestAppointment(client: any, input: {
  providerAccountId: string;
  consumerAccountId: string;
  bookableWindowId: string;
  instanceStart: string;
  instanceEnd: string;
  timezone: string;
  idempotencyKey: string;
}) {
  const serviceLink = await requireActiveServiceLink(client, input.providerAccountId, input.consumerAccountId);
  try {
    const request = await client.appointmentRequest.create({
      data: {
        providerAccountId: input.providerAccountId,
        consumerAccountId: input.consumerAccountId,
        serviceLinkId: serviceLink.id,
        bookableWindowId: input.bookableWindowId,
        instanceStart: new Date(input.instanceStart),
        instanceEnd: new Date(input.instanceEnd),
        timezone: input.timezone,
        status: 'pending_held',
      },
    });
    await client.appointmentEvent.create({
      data: {
        appointmentId: request.id,
        fromState: null,
        toState: 'pending_held',
        actorAccountId: input.consumerAccountId,
        actorRole: 'consumer',
        reason: 'requested',
      },
    });
    return request;
  } catch (error) {
    if (isUniqueConflict(error)) throw new Error('slot_unavailable');
    throw error;
  }
}

export async function confirmAppointment(client: any, input: { actorAccountId: string; requestId: string; idempotencyKey: string }) {
  const current = await client.appointmentRequest.findFirst({
    where: { id: input.requestId, providerAccountId: input.actorAccountId, status: 'pending_held' },
  });
  if (!current) throw new Error('appointment_not_found');
  const updated = await client.appointmentRequest.update({
    where: { id: current.id },
    data: { status: 'confirmed_shared' },
  });
  await client.appointmentEvent.create({
    data: {
      appointmentId: current.id,
      fromState: 'pending_held',
      toState: 'confirmed_shared',
      actorAccountId: input.actorAccountId,
      actorRole: 'provider',
      reason: 'confirmed_by_a',
    },
  });
  return updated;
}
```

Also add these four functions to `appointment-service.ts`:

```ts
export async function rejectAppointment(client: any, input: { actorAccountId: string; requestId: string; idempotencyKey: string }) {
  const current = await client.appointmentRequest.findFirst({
    where: { id: input.requestId, providerAccountId: input.actorAccountId, status: 'pending_held' },
  });
  if (!current) throw new Error('appointment_not_found');
  const updated = await client.appointmentRequest.update({
    where: { id: current.id },
    data: { status: 'released', releaseReason: 'rejected_by_a', releasedAt: new Date() },
  });
  await client.appointmentEvent.create({
    data: {
      appointmentId: current.id,
      fromState: 'pending_held',
      toState: 'released',
      actorAccountId: input.actorAccountId,
      actorRole: 'provider',
      reason: 'rejected_by_a',
    },
  });
  return updated;
}

export async function cancelAppointment(client: any, input: { actorAccountId: string; requestId: string; idempotencyKey: string }) {
  const current = await client.appointmentRequest.findFirst({
    where: {
      id: input.requestId,
      status: { in: ['pending_held', 'confirmed_shared'] },
      OR: [{ providerAccountId: input.actorAccountId }, { consumerAccountId: input.actorAccountId }],
    },
  });
  if (!current) throw new Error('appointment_not_found');
  const releaseReason = current.providerAccountId === input.actorAccountId ? 'cancelled_by_a' : 'cancelled_by_b';
  const actorRole = current.providerAccountId === input.actorAccountId ? 'provider' : 'consumer';
  const updated = await client.appointmentRequest.update({
    where: { id: current.id },
    data: { status: 'released', releaseReason, releasedAt: new Date() },
  });
  await client.appointmentEvent.create({
    data: {
      appointmentId: current.id,
      fromState: current.status,
      toState: 'released',
      actorAccountId: input.actorAccountId,
      actorRole,
      reason: releaseReason,
    },
  });
  return updated;
}

export async function listPendingRequests(client: any, input: { providerAccountId: string; now: Date }) {
  const requests = await client.appointmentRequest.findMany({
    where: { providerAccountId: input.providerAccountId, status: 'pending_held' },
    orderBy: { createdAt: 'asc' },
    include: { consumer: { select: { displayName: true } } },
  });
  return requests.map((r: any) => ({
    id: r.id,
    requesterDisplayName: r.consumer.displayName,
    instanceStart: r.instanceStart instanceof Date ? r.instanceStart.toISOString() : r.instanceStart,
    instanceEnd: r.instanceEnd instanceof Date ? r.instanceEnd.toISOString() : r.instanceEnd,
    createdAt: r.createdAt instanceof Date ? r.createdAt.toISOString() : r.createdAt,
    holdAgeMinutes: Math.floor((input.now.getTime() - new Date(r.createdAt).getTime()) / 60000),
  }));
}

export async function queryBookableWindows(client: any, input: {
  providerAccountId: string;
  consumerAccountId: string;
  dateFrom: string;
  dateTo?: string;
  viewerTimezone?: string;
}) {
  const serviceLink = await requireActiveServiceLink(client, input.providerAccountId, input.consumerAccountId);
  const { dateFrom, dateTo } = capQueryRange(input.dateFrom, input.dateTo);
  const windows = await client.bookableWindow.findMany({
    where: { providerAccountId: input.providerAccountId, capability: 'appointment_request', status: 'active' },
  });
  const exclusions = await client.bookableWindowExclusion.findMany({
    where: { bookableWindow: { providerAccountId: input.providerAccountId } },
    select: { instanceStart: true, instanceEnd: true },
  });
  const occupied = await client.appointmentRequest.findMany({
    where: { providerAccountId: input.providerAccountId, status: { in: ['pending_held', 'confirmed_shared'] } },
    select: { instanceStart: true, instanceEnd: true },
  });
  const viewerTimezone = input.viewerTimezone || 'UTC';
  const instances = windows.flatMap((w: any) =>
    generateWindowInstances({
      bookableWindowId: w.id,
      rule: w.rule as BookableWindowRule,
      dateFrom,
      dateTo,
      excluded: exclusions.map((e: any) => ({
        instanceStart: e.instanceStart instanceof Date ? e.instanceStart.toISOString() : e.instanceStart,
        instanceEnd: e.instanceEnd instanceof Date ? e.instanceEnd.toISOString() : e.instanceEnd,
      })),
      occupied: occupied.map((o: any) => ({
        instanceStart: o.instanceStart instanceof Date ? o.instanceStart.toISOString() : o.instanceStart,
        instanceEnd: o.instanceEnd instanceof Date ? o.instanceEnd.toISOString() : o.instanceEnd,
      })),
    }).map((inst) => ({ ...inst, ...renderWindowForViewer(inst, viewerTimezone) }))
  );
  return { serviceLinkId: serviceLink.id, instances };
}
```

- [ ] **Step 6: Run appointment and availability tests**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/scheduling/availability-service.test.ts \
  src/scheduling/appointment-service.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit availability and appointments**

```bash
cd /data/projects/coke/gateway
git add packages/api/src/scheduling/availability-service.ts \
  packages/api/src/scheduling/availability-service.test.ts \
  packages/api/src/scheduling/appointment-service.ts \
  packages/api/src/scheduling/appointment-service.test.ts
git commit -m "feat: add scheduling availability and appointments"
```

## Task 5: Notification Queue And Bridge Injection

**Files:**
- Create: `gateway/packages/api/src/scheduling/notification-service.ts`
- Test: `gateway/packages/api/src/scheduling/notification-service.test.ts`
- Modify: `connector/clawscale_bridge/message_gateway.py`
- Test: `tests/unit/connector/clawscale_bridge/test_message_gateway.py`

- [ ] **Step 1: Write failing Gateway notification tests**

Create `gateway/packages/api/src/scheduling/notification-service.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  enqueueSchedulingNotification,
  retryPendingSchedulingNotifications,
} from './notification-service.js';

const client = {
  schedulingNotification: {
    create: vi.fn(),
    findMany: vi.fn(),
    update: vi.fn(),
  },
};

describe('notification service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.COKE_BRIDGE_INBOUND_URL = 'http://127.0.0.1:8090/bridge/inbound';
    process.env.COKE_BRIDGE_API_KEY = 'bridge-key';
  });

  it('persists notification intent before calling Bridge', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, text: async () => '{"ok":true}' });
    global.fetch = fetchMock as never;
    client.schedulingNotification.create.mockResolvedValueOnce({
      id: 'sn_1',
      idempotencyKey: 'appt:ar_1:request:A',
      recipientAccountId: 'ck_a',
      payload: { text: 'Student B requested Tuesday 7 PM' },
      kind: 'appointment_request',
      appointmentId: 'ar_1',
    });
    client.schedulingNotification.update.mockResolvedValueOnce({ id: 'sn_1', status: 'delivered' });

    await enqueueSchedulingNotification(client as never, {
      appointmentId: 'ar_1',
      recipientAccountId: 'ck_a',
      idempotencyKey: 'appt:ar_1:request:A',
      kind: 'appointment_request',
      text: 'Student B requested Tuesday 7 PM',
      metadata: { requestId: 'ar_1' },
    });

    expect(client.schedulingNotification.create).toHaveBeenCalledBefore(fetchMock);
    expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8090/bridge/inbound', expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({ Authorization: 'Bearer bridge-key' }),
    }));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      customer_id: 'ck_a',
      message_type: 'scheduling_notification',
      text: 'Student B requested Tuesday 7 PM',
    });
  });

  it('retries pending notifications and marks 2xx responses delivered', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, text: async () => '{"ok":true}' });
    global.fetch = fetchMock as never;
    client.schedulingNotification.findMany.mockResolvedValueOnce([{
      id: 'sn_1',
      recipientAccountId: 'ck_a',
      payload: { text: 'A confirmed Tuesday 7 PM', metadata: { requestId: 'ar_1' } },
      idempotencyKey: 'appt:ar_1:confirmed:B',
      kind: 'appointment_confirmed',
    }]);

    const result = await retryPendingSchedulingNotifications(client as never, { limit: 10 });

    expect(result.delivered).toBe(1);
    expect(client.schedulingNotification.update).toHaveBeenCalledWith({
      where: { id: 'sn_1' },
      data: { status: 'delivered', deliveredAt: expect.any(Date), lastError: null },
    });
  });
});
```

- [ ] **Step 2: Write failing Bridge metadata test**

Append to `tests/unit/connector/clawscale_bridge/test_message_gateway.py`:

```python
def test_scheduling_notification_metadata_is_preserved(fake_mongo, fake_user_dao):
    gateway = CokeMessageGateway(fake_mongo, fake_user_dao)

    doc = gateway.build_input_message(
        account_id="ck_a",
        character_id="char_1",
        text="Student B requested Tuesday 7 PM. Reply CONFIRM or DECLINE.",
        causal_inbound_event_id="appt_ar_1_request",
        inbound={
            "timestamp": 1770000000,
            "customer_id": "ck_a",
            "message_type": "scheduling_notification",
            "scheduling": {"request_id": "ar_1", "allowed_actions": ["confirm", "reject"]},
        },
    )

    assert doc["message_type"] == "text"
    assert doc["metadata"]["business_protocol"]["message_type"] == "scheduling_notification"
    assert doc["metadata"]["scheduling"]["request_id"] == "ar_1"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/notification-service.test.ts
.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_message_gateway.py -k scheduling_notification -v
```

Expected: both tests fail.

- [ ] **Step 4: Implement Gateway notification service**

Create `gateway/packages/api/src/scheduling/notification-service.ts`:

```ts
function readBridgeInboundUrl(): string {
  return process.env['COKE_BRIDGE_INBOUND_URL']?.trim() || 'http://127.0.0.1:8090/bridge/inbound';
}

function bridgeHeaders(): Record<string, string> {
  const apiKey = process.env['COKE_BRIDGE_API_KEY']?.trim();
  return {
    'Content-Type': 'application/json',
    ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
  };
}

async function deliver(notification: {
  id: string;
  recipientAccountId: string;
  idempotencyKey: string;
  kind: string;
  payload: unknown;
}, client: any) {
  const payload = notification.payload as { text?: string; metadata?: Record<string, unknown> };
  const response = await fetch(readBridgeInboundUrl(), {
    method: 'POST',
    headers: bridgeHeaders(),
    body: JSON.stringify({
      customer_id: notification.recipientAccountId,
      inbound_event_id: notification.idempotencyKey,
      text: payload.text,
      timestamp: Math.floor(Date.now() / 1000),
      message_type: 'scheduling_notification',
      scheduling: {
        kind: notification.kind,
        ...(payload.metadata || {}),
      },
    }),
  });
  if (!response.ok) throw new Error(`bridge_http_${response.status}`);
  await client.schedulingNotification.update({
    where: { id: notification.id },
    data: { status: 'delivered', deliveredAt: new Date(), lastError: null },
  });
}

export async function enqueueSchedulingNotification(client: any, input: {
  appointmentId: string;
  recipientAccountId: string;
  idempotencyKey: string;
  kind: string;
  text: string;
  metadata: Record<string, unknown>;
}) {
  const notification = await client.schedulingNotification.create({
    data: {
      appointmentId: input.appointmentId,
      recipientAccountId: input.recipientAccountId,
      idempotencyKey: input.idempotencyKey,
      kind: input.kind,
      payload: { text: input.text, metadata: input.metadata },
      status: 'pending_delivery',
    },
  });
  await deliver(notification, client);
  return notification;
}

export async function retryPendingSchedulingNotifications(client: any, input: { limit: number }) {
  const pending = await client.schedulingNotification.findMany({
    where: { status: 'pending_delivery' },
    orderBy: { createdAt: 'asc' },
    take: input.limit,
  });
  let delivered = 0;
  let failed = 0;
  for (const notification of pending) {
    try {
      await deliver(notification, client);
      delivered += 1;
    } catch (error) {
      failed += 1;
      await client.schedulingNotification.update({
        where: { id: notification.id },
        data: { attempts: { increment: 1 }, lastError: error instanceof Error ? error.message : String(error) },
      });
    }
  }
  return { delivered, failed };
}
```

- [ ] **Step 5: Preserve scheduling metadata in Bridge**

Modify `connector/clawscale_bridge/message_gateway.py`:

```python
        inbound_message_type = _read_clean_string(inbound.get("message_type"))
        if inbound_message_type:
            business_protocol["message_type"] = inbound_message_type
```

Add this before the `metadata` dictionary is constructed:

```python
        scheduling = inbound.get("scheduling")
```

Add this immediately after the `metadata` dictionary is constructed:

```python
        if isinstance(scheduling, dict):
            metadata["scheduling"] = scheduling
```

Keep the top-level MongoDB `message_type` field as `_resolve_message_type(attachments)`
so existing text processing remains compatible.

- [ ] **Step 6: Run notification tests**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/notification-service.test.ts
.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_message_gateway.py -k scheduling_notification -v
```

Expected: PASS.

- [ ] **Step 7: Commit notification slice**

```bash
cd /data/projects/coke/gateway
git add packages/api/src/scheduling/notification-service.ts \
  packages/api/src/scheduling/notification-service.test.ts
git commit -m "feat: add scheduling notification delivery"

cd /data/projects/coke
git add connector/clawscale_bridge/message_gateway.py \
  tests/unit/connector/clawscale_bridge/test_message_gateway.py
git commit -m "feat: preserve scheduling notification metadata"
```

## Task 6: Gateway Scheduling Routes

**Files:**
- Create: `gateway/packages/api/src/routes/public-user-link-routes.ts`
- Create: `gateway/packages/api/src/routes/customer-scheduling-routes.ts`
- Create: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
- Modify: `gateway/packages/api/src/index.ts`
- Test: `gateway/packages/api/src/routes/public-user-link-routes.test.ts`
- Test: `gateway/packages/api/src/routes/customer-scheduling-routes.test.ts`
- Test: `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`

- [ ] **Step 1: Write failing public route test**

Create `gateway/packages/api/src/routes/public-user-link-routes.test.ts`:

```ts
import { Hono } from 'hono';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  readPublicUserLinkByCode: vi.fn(),
  createLinkSession: vi.fn(),
  claimLinkSession: vi.fn(),
  getLinkSessionStatus: vi.fn(),
}));

vi.mock('../scheduling/user-link-service.js', () => mocks);
vi.mock('../db/index.js', () => ({ db: {} }));

import { publicUserLinkRouter } from './public-user-link-routes.js';

describe('public user link routes', () => {
  beforeEach(() => vi.clearAllMocks());

  it('returns public profile for an active code without private data', async () => {
    mocks.readPublicUserLinkByCode.mockResolvedValueOnce({
      code: 'AbCdEfGhIjK_',
      url: 'https://kap.example/u/AbCdEfGhIjK_',
      qrUrl: 'https://kap.example/u/AbCdEfGhIjK_/qr',
      profile: { displayName: 'Coach A', tagline: 'Strength', avatarUrl: null },
    });
    const app = new Hono();
    app.route('/api/public/user-links', publicUserLinkRouter);

    const res = await app.request('/api/public/user-links/AbCdEfGhIjK_');

    expect(res.status).toBe(200);
    await expect(res.json()).resolves.toEqual({
      ok: true,
      data: expect.objectContaining({
        code: 'AbCdEfGhIjK_',
        profile: { displayName: 'Coach A', tagline: 'Strength', avatarUrl: null },
      }),
    });
  });

  it('opens a link session and returns auth next URLs containing link_session', async () => {
    mocks.createLinkSession.mockResolvedValueOnce({
      token: 'session-token',
      nextUrl: '/auth/login?next=%2Fu%2FAbCdEfGhIjK_%3Flink_session%3Dsession-token',
      registerUrl: '/auth/register?next=%2Fu%2FAbCdEfGhIjK_%3Flink_session%3Dsession-token',
    });
    const app = new Hono();
    app.route('/api/public/user-links', publicUserLinkRouter);

    const res = await app.request('/api/public/user-links/AbCdEfGhIjK_/sessions', { method: 'POST' });

    expect(res.status).toBe(201);
    const body = await res.json();
    expect(body.data.nextUrl).toContain('link_session');
  });
});
```

- [ ] **Step 2: Write failing customer and internal route tests**

Create `gateway/packages/api/src/routes/customer-scheduling-routes.test.ts`
with tests for:

```ts
it('requires customer auth before returning A user link', async () => {
  const app = new Hono();
  app.route('/api/customer/scheduling', customerSchedulingRouter);
  const res = await app.request('/api/customer/scheduling/user-link');
  expect(res.status).toBe(401);
});
```

Create `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`
with:

```ts
it('requires the internal bearer token', async () => {
  process.env.CLAWSCALE_IDENTITY_API_KEY = 'internal-key';
  const app = new Hono();
  app.route('/api/internal/scheduling', internalSchedulingRouter);
  const res = await app.request('/api/internal/scheduling/tools/get_user_link', { method: 'POST' });
  expect(res.status).toBe(401);
});
```

- [ ] **Step 3: Run route tests to verify they fail**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/routes/public-user-link-routes.test.ts \
  src/routes/customer-scheduling-routes.test.ts \
  src/routes/internal-scheduling-routes.test.ts
```

Expected: FAIL because routers do not exist.

- [ ] **Step 4: Implement public router**

Create `gateway/packages/api/src/routes/public-user-link-routes.ts`:

```ts
import { Hono } from 'hono';
import { db } from '../db/index.js';
import {
  createLinkSession,
  readPublicUserLinkByCode,
} from '../scheduling/user-link-service.js';

export const publicUserLinkRouter = new Hono();

publicUserLinkRouter.get('/:code', async (c) => {
  try {
    const result = await readPublicUserLinkByCode(db as never, { code: c.req.param('code') });
    return c.json({ ok: true, data: result });
  } catch {
    return c.json({ ok: false, error: 'link_not_active' }, 404);
  }
});

publicUserLinkRouter.post('/:code/sessions', async (c) => {
  try {
    const result = await createLinkSession(db as never, { code: c.req.param('code') });
    return c.json({ ok: true, data: result }, 201);
  } catch {
    return c.json({ ok: false, error: 'link_not_active' }, 404);
  }
});
```

The public read path must call `readPublicUserLinkByCode`; it must not create a
new user link or treat the code as `providerAccountId`.

- [ ] **Step 5: Implement customer and internal routers**

Create `gateway/packages/api/src/routes/customer-scheduling-routes.ts`:

```ts
import type { Context, Next } from 'hono';
import { Hono } from 'hono';
import { db } from '../db/index.js';
import { getCustomerSession, verifyCustomerToken, type CustomerSession } from '../lib/customer-auth.js';
import { closeBookableWindow, confirmBookableWindowPreview, previewBookableWindows } from '../scheduling/availability-service.js';
import { cancelAppointment, confirmAppointment, listPendingRequests, queryBookableWindows, rejectAppointment, requestAppointment } from '../scheduling/appointment-service.js';
import { blockServiceLink, removeServiceLink, unblockServiceLink } from '../scheduling/service-link-service.js';
import { disableUserLink, getOrCreateActiveUserLink, resetUserLink } from '../scheduling/user-link-service.js';

declare module 'hono' {
  interface ContextVariableMap { customerSchedulingAuth: CustomerSession; }
}

export const customerSchedulingRouter = new Hono();

async function requireCustomerSchedulingAuth(c: Context, next: Next): Promise<Response | void> {
  const header = c.req.header('Authorization');
  const token = header?.startsWith('Bearer ') ? header.slice(7).trim() : null;
  if (!token) return c.json({ ok: false, error: 'unauthorized' }, 401);
  try {
    const payload = verifyCustomerToken(token);
    const session = await getCustomerSession(db as never, { customerId: payload.sub, identityId: payload.identityId });
    if (!session) return c.json({ ok: false, error: 'account_not_found' }, 404);
    if (session.claimStatus !== 'active') return c.json({ ok: false, error: 'claim_inactive' }, 403);
    c.set('customerSchedulingAuth', session);
    await next();
    return;
  } catch {
    return c.json({ ok: false, error: 'invalid_or_expired_token' }, 401);
  }
}

customerSchedulingRouter.use('*', requireCustomerSchedulingAuth);

customerSchedulingRouter.get('/user-link', async (c) => {
  const session = c.get('customerSchedulingAuth');
  return c.json({ ok: true, data: await getOrCreateActiveUserLink(db as never, { providerAccountId: session.customerId }) });
});

customerSchedulingRouter.post('/user-link/reset', async (c) => {
  const session = c.get('customerSchedulingAuth');
  return c.json({ ok: true, data: await resetUserLink(db as never, { providerAccountId: session.customerId }) });
});

customerSchedulingRouter.post('/user-link/disable', async (c) => {
  const session = c.get('customerSchedulingAuth');
  return c.json({ ok: true, data: await disableUserLink(db as never, { providerAccountId: session.customerId }) });
});

customerSchedulingRouter.post('/bookable-windows/preview', async (c) => {
  const session = c.get('customerSchedulingAuth');
  const body = await c.req.json().catch(() => null);
  if (!body) return c.json({ ok: false, error: 'invalid_body' }, 400);
  try {
    return c.json({ ok: true, data: await previewBookableWindows({ providerAccountId: session.customerId, instruction: String(body.instruction || ''), timezone: String(body.timezone || 'UTC') }) });
  } catch (error) {
    return c.json({ ok: false, error: error instanceof Error ? error.message : 'preview_failed' }, 400);
  }
});

customerSchedulingRouter.post('/bookable-windows/confirm', async (c) => {
  const session = c.get('customerSchedulingAuth');
  const body = await c.req.json().catch(() => null);
  if (!body?.preview) return c.json({ ok: false, error: 'invalid_body' }, 400);
  return c.json({ ok: true, data: await confirmBookableWindowPreview(db as never, { providerAccountId: session.customerId, preview: body.preview }) });
});

customerSchedulingRouter.get('/bookable-windows', async (c) => {
  const session = c.get('customerSchedulingAuth');
  const windows = await (db as any).bookableWindow.findMany({
    where: { providerAccountId: session.customerId, status: 'active' },
    orderBy: { createdAt: 'desc' },
  });
  return c.json({ ok: true, data: windows });
});

customerSchedulingRouter.post('/appointments', async (c) => {
  const session = c.get('customerSchedulingAuth');
  const body = await c.req.json().catch(() => null);
  if (!body) return c.json({ ok: false, error: 'invalid_body' }, 400);
  try {
    const result = await requestAppointment(db as never, {
      providerAccountId: String(body.providerAccountId || ''),
      consumerAccountId: session.customerId,
      bookableWindowId: String(body.bookableWindowId || ''),
      instanceStart: String(body.instanceStart || ''),
      instanceEnd: String(body.instanceEnd || ''),
      timezone: String(body.timezone || 'UTC'),
      idempotencyKey: String(body.idempotencyKey || `${session.customerId}:${body.bookableWindowId}:${body.instanceStart}`),
    });
    return c.json({ ok: true, data: result }, 201);
  } catch (error) {
    return c.json({ ok: false, error: error instanceof Error ? error.message : 'request_failed' }, 400);
  }
});

customerSchedulingRouter.get('/appointments/pending', async (c) => {
  const session = c.get('customerSchedulingAuth');
  return c.json({ ok: true, data: await listPendingRequests(db as never, { providerAccountId: session.customerId, now: new Date() }) });
});

customerSchedulingRouter.post('/appointments/:id/confirm', async (c) => {
  const session = c.get('customerSchedulingAuth');
  const body = await c.req.json().catch(() => ({})) as Record<string, unknown>;
  try {
    return c.json({ ok: true, data: await confirmAppointment(db as never, { actorAccountId: session.customerId, requestId: c.req.param('id'), idempotencyKey: String(body?.idempotencyKey || `confirm:${session.customerId}:${c.req.param('id')}`) }) });
  } catch (error) {
    return c.json({ ok: false, error: error instanceof Error ? error.message : 'confirm_failed' }, 400);
  }
});

customerSchedulingRouter.post('/appointments/:id/reject', async (c) => {
  const session = c.get('customerSchedulingAuth');
  const body = await c.req.json().catch(() => ({})) as Record<string, unknown>;
  try {
    return c.json({ ok: true, data: await rejectAppointment(db as never, { actorAccountId: session.customerId, requestId: c.req.param('id'), idempotencyKey: String(body?.idempotencyKey || `reject:${session.customerId}:${c.req.param('id')}`) }) });
  } catch (error) {
    return c.json({ ok: false, error: error instanceof Error ? error.message : 'reject_failed' }, 400);
  }
});

customerSchedulingRouter.post('/appointments/:id/cancel', async (c) => {
  const session = c.get('customerSchedulingAuth');
  const body = await c.req.json().catch(() => ({})) as Record<string, unknown>;
  try {
    return c.json({ ok: true, data: await cancelAppointment(db as never, { actorAccountId: session.customerId, requestId: c.req.param('id'), idempotencyKey: String(body?.idempotencyKey || `cancel:${session.customerId}:${c.req.param('id')}`) }) });
  } catch (error) {
    return c.json({ ok: false, error: error instanceof Error ? error.message : 'cancel_failed' }, 400);
  }
});

customerSchedulingRouter.post('/service-links/:otherAccountId/block', async (c) => {
  const session = c.get('customerSchedulingAuth');
  try {
    return c.json({ ok: true, data: await blockServiceLink(db as never, { providerAccountId: session.customerId, consumerAccountId: c.req.param('otherAccountId') }) });
  } catch (error) {
    return c.json({ ok: false, error: error instanceof Error ? error.message : 'block_failed' }, 400);
  }
});

customerSchedulingRouter.post('/service-links/:otherAccountId/unblock', async (c) => {
  const session = c.get('customerSchedulingAuth');
  try {
    return c.json({ ok: true, data: await unblockServiceLink(db as never, { providerAccountId: session.customerId, consumerAccountId: c.req.param('otherAccountId') }) });
  } catch (error) {
    return c.json({ ok: false, error: error instanceof Error ? error.message : 'unblock_failed' }, 400);
  }
});

customerSchedulingRouter.delete('/service-links/:otherAccountId', async (c) => {
  const session = c.get('customerSchedulingAuth');
  try {
    const existing = await (db as any).serviceLink.findFirst({
      where: { providerAccountId: session.customerId, consumerAccountId: c.req.param('otherAccountId') },
    });
    if (!existing) return c.json({ ok: false, error: 'service_link_not_found' }, 404);
    return c.json({ ok: true, data: await removeServiceLink(db as never, { serviceLinkId: existing.id }) });
  } catch (error) {
    return c.json({ ok: false, error: error instanceof Error ? error.message : 'remove_failed' }, 400);
  }
});
```

Create `gateway/packages/api/src/routes/internal-scheduling-routes.ts`:

```ts
import { Hono } from 'hono';
import { db } from '../db/index.js';
import { getOrCreateActiveUserLink, resetUserLink } from '../scheduling/user-link-service.js';
import { queryBookableWindows, requestAppointment, confirmAppointment, rejectAppointment, cancelAppointment, listPendingRequests } from '../scheduling/appointment-service.js';
import { blockServiceLink, unblockServiceLink, removeServiceLink } from '../scheduling/service-link-service.js';

export const internalSchedulingRouter = new Hono();

function isAuthorized(header: string | undefined): boolean {
  const expected = process.env['CLAWSCALE_IDENTITY_API_KEY'] ?? '';
  return Boolean(expected) && header === `Bearer ${expected}`;
}

internalSchedulingRouter.post('/tools/:toolName', async (c) => {
  if (!isAuthorized(c.req.header('Authorization'))) {
    return c.json({ ok: false, error: 'unauthorized' }, 401);
  }
  const toolName = c.req.param('toolName');
  const body = await c.req.json().catch(() => null) as Record<string, unknown> | null;
  if (!body) return c.json({ ok: false, error: 'invalid_body' }, 400);

  const customerId = String(body.customer_id || '');
  const consumerAccountId = String(body.consumer_account_id || '');
  try {
    if (toolName === 'get_user_link') return c.json({ ok: true, data: await getOrCreateActiveUserLink(db as never, { providerAccountId: customerId }) });
    if (toolName === 'reset_user_link') return c.json({ ok: true, data: await resetUserLink(db as never, { providerAccountId: customerId }) });
    if (toolName === 'list_pending_requests') return c.json({ ok: true, data: await listPendingRequests(db as never, { providerAccountId: customerId, now: new Date() }) });
    if (toolName === 'query_bookable_windows') return c.json({ ok: true, data: await queryBookableWindows(db as never, { providerAccountId: customerId, consumerAccountId, dateFrom: String(body.date_from || ''), dateTo: body.date_to ? String(body.date_to) : undefined, viewerTimezone: body.viewer_timezone ? String(body.viewer_timezone) : undefined }) });
    if (toolName === 'request_appointment') return c.json({ ok: true, data: await requestAppointment(db as never, { providerAccountId: customerId, consumerAccountId, bookableWindowId: String(body.bookable_window_id || ''), instanceStart: String(body.instance_start || ''), instanceEnd: String(body.instance_end || ''), timezone: String(body.timezone || 'UTC'), idempotencyKey: String(body.idempotency_key || '') }) }, 201);
    if (toolName === 'confirm_appointment') return c.json({ ok: true, data: await confirmAppointment(db as never, { actorAccountId: customerId, requestId: String(body.request_id || ''), idempotencyKey: String(body.idempotency_key || '') }) });
    if (toolName === 'reject_appointment') return c.json({ ok: true, data: await rejectAppointment(db as never, { actorAccountId: customerId, requestId: String(body.request_id || ''), idempotencyKey: String(body.idempotency_key || '') }) });
    if (toolName === 'cancel_appointment') return c.json({ ok: true, data: await cancelAppointment(db as never, { actorAccountId: customerId, requestId: String(body.request_id || ''), idempotencyKey: String(body.idempotency_key || '') }) });
    if (toolName === 'block_service_link') return c.json({ ok: true, data: await blockServiceLink(db as never, { providerAccountId: customerId, consumerAccountId }) });
    if (toolName === 'unblock_service_link') return c.json({ ok: true, data: await unblockServiceLink(db as never, { providerAccountId: customerId, consumerAccountId }) });
    if (toolName === 'remove_service_link') {
      const existing = await (db as any).serviceLink.findFirst({ where: { providerAccountId: customerId, consumerAccountId } });
      if (!existing) return c.json({ ok: false, error: 'service_link_not_found' }, 404);
      return c.json({ ok: true, data: await removeServiceLink(db as never, { serviceLinkId: existing.id }) });
    }
    return c.json({ ok: false, error: 'unknown_tool' }, 404);
  } catch (error) {
    return c.json({ ok: false, error: error instanceof Error ? error.message : 'scheduling_failed' }, 400);
  }
});
```

- [ ] **Step 6: Register routers in API index**

Modify `gateway/packages/api/src/index.ts`:

```ts
import { publicUserLinkRouter } from './routes/public-user-link-routes.js';
import { customerSchedulingRouter } from './routes/customer-scheduling-routes.js';
import { internalSchedulingRouter } from './routes/internal-scheduling-routes.js';
```

Register:

```ts
app.route('/api/public/user-links', publicUserLinkRouter);
app.route('/api/customer/scheduling', customerSchedulingRouter);
app.route('/api/internal/scheduling', internalSchedulingRouter);
```

- [ ] **Step 7: Run route tests and API build**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/routes/public-user-link-routes.test.ts \
  src/routes/customer-scheduling-routes.test.ts \
  src/routes/internal-scheduling-routes.test.ts
pnpm --dir gateway/packages/api build
```

Expected: tests and build pass.

- [ ] **Step 8: Commit route slice**

```bash
cd /data/projects/coke/gateway
git add packages/api/src/routes/public-user-link-routes.ts \
  packages/api/src/routes/public-user-link-routes.test.ts \
  packages/api/src/routes/customer-scheduling-routes.ts \
  packages/api/src/routes/customer-scheduling-routes.test.ts \
  packages/api/src/routes/internal-scheduling-routes.ts \
  packages/api/src/routes/internal-scheduling-routes.test.ts \
  packages/api/src/index.ts
git commit -m "feat: expose scheduling gateway routes"
```

## Task 7: Gateway Web User Link Entry And QR

**Files:**
- Create: `gateway/packages/shared/src/types/scheduling.ts`
- Modify: `gateway/packages/shared/src/index.ts`
- Create: `gateway/packages/web/lib/user-link-api.ts`
- Create: `gateway/packages/web/app/u/[code]/page.tsx`
- Create: `gateway/packages/web/app/u/[code]/claim-handoff.tsx`
  - Complete preserved `link_session` tokens after customer auth returns to
    `/u/:code?link_session=...`.
- Create: `gateway/packages/web/app/u/[code]/qr/route.ts`
- Test: `gateway/packages/web/app/u/[code]/page.test.tsx`
- Test: `gateway/packages/web/app/u/[code]/qr/route.test.ts`
- Modify: `gateway/packages/api/src/routes/public-user-link-routes.ts`
  - Require authenticated customer bearer auth before claiming a link session;
    never trust a client-supplied `customer_id` for claim ownership.
- Modify: `gateway/packages/web/next.config.ts`
  - Remove static export mode because `/u/[code]` and `/u/[code]/qr` are
    arbitrary runtime routes.
- Modify: `gateway/packages/web/package.json`
  - Run production builds with webpack until the local worktree symlink layout
    no longer triggers Turbopack's node_modules-root panic.
- Modify: `gateway/Dockerfile`
  - Serve web through `next start` instead of static `out/` files so dynamic
    user-link and QR routes work in production.

- [ ] **Step 1: Write failing web page test**

Create `gateway/packages/web/app/u/[code]/page.test.tsx`:

```tsx
import { describe, expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';

vi.mock('../../../lib/user-link-api', () => ({
  readPublicUserLink: vi.fn().mockResolvedValue({
    ok: true,
    data: {
      code: 'AbCdEfGhIjK_',
      profile: { displayName: 'Coach A', tagline: 'Strength coaching', avatarUrl: null },
      session: {
        nextUrl: '/auth/login?next=%2Fu%2FAbCdEfGhIjK_%3Flink_session%3Dtok',
        registerUrl: '/auth/register?next=%2Fu%2FAbCdEfGhIjK_%3Flink_session%3Dtok',
      },
    },
  }),
}));

import UserLinkPage from './page';

describe('UserLinkPage', () => {
  it('shows provider profile and auth actions that preserve link_session', async () => {
    const html = renderToString(await UserLinkPage({ params: Promise.resolve({ code: 'AbCdEfGhIjK_' }) }));
    expect(html).toContain('Coach A');
    expect(html).toContain('Strength coaching');
    expect(html).toContain('/auth/login?next=');
    expect(html).toContain('link_session');
    expect(html).toContain('/u/AbCdEfGhIjK_/qr');
  });
});
```

- [ ] **Step 2: Write failing QR route test**

Create `gateway/packages/web/app/u/[code]/qr/route.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { GET } from './route';

describe('/u/[code]/qr', () => {
  it('returns a QR png for the absolute user link URL', async () => {
    process.env.NEXT_PUBLIC_COKE_WEB_URL = 'https://kap.example';
    const res = await GET(new Request('https://kap.example/u/AbCdEfGhIjK_/qr'), {
      params: Promise.resolve({ code: 'AbCdEfGhIjK_' }),
    });

    expect(res.headers.get('content-type')).toBe('image/png');
    expect((await res.arrayBuffer()).byteLength).toBeGreaterThan(100);
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  'app/u/[code]/page.test.tsx' \
  'app/u/[code]/qr/route.test.ts'
```

Expected: FAIL because web files do not exist.

- [ ] **Step 4: Add shared scheduling types and API client**

Create `gateway/packages/shared/src/types/scheduling.ts`:

```ts
export interface PublicUserLinkProfile {
  displayName: string;
  tagline: string | null;
  avatarUrl: string | null;
}

export interface PublicUserLinkResponse {
  code: string;
  url: string;
  qrUrl: string;
  profile: PublicUserLinkProfile;
  session?: {
    token?: string;
    nextUrl: string;
    registerUrl: string;
  };
}
```

Export it from `gateway/packages/shared/src/index.ts`:

```ts
export * from './types/scheduling.js';
```

Create `gateway/packages/web/lib/user-link-api.ts`:

```ts
import type { ApiResponse } from '../../shared/src/types/api';
import type { PublicUserLinkResponse } from '../../shared/src/types/scheduling';
import { getCustomerApiBase } from './customer-api';

export async function readPublicUserLink(code: string): Promise<ApiResponse<PublicUserLinkResponse>> {
  const base = getCustomerApiBase();
  const metaRes = await fetch(`${base}/api/public/user-links/${encodeURIComponent(code)}`, { cache: 'no-store' });
  if (!metaRes.ok) return { ok: false, error: 'link_not_active' } as ApiResponse<PublicUserLinkResponse>;
  const meta = await metaRes.json() as ApiResponse<PublicUserLinkResponse>;
  if (!meta.ok) return meta;

  const sessionRes = await fetch(`${base}/api/public/user-links/${encodeURIComponent(code)}/sessions`, {
    method: 'POST',
    cache: 'no-store',
  });
  if (!sessionRes.ok) return meta;
  const session = await sessionRes.json() as ApiResponse<PublicUserLinkResponse['session']>;
  return {
    ok: true,
    data: {
      ...meta.data,
      session: session.ok ? session.data : undefined,
    },
  };
}
```

- [ ] **Step 5: Add public page and QR route**

Create `gateway/packages/web/app/u/[code]/page.tsx`:

```tsx
import Image from 'next/image';
import Link from 'next/link';
import { readPublicUserLink } from '../../../lib/user-link-api';

export default async function UserLinkPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const result = await readPublicUserLink(code);
  if (!result.ok) {
    return (
      <main className="coke-site public-user-link">
        <section className="public-user-link__panel">
          <h1>Link no longer active</h1>
          <p>This user link cannot create new connection sessions.</p>
        </section>
      </main>
    );
  }

  const { profile, session } = result.data;
  return (
    <main className="coke-site public-user-link">
      <section className="public-user-link__panel">
        {profile.avatarUrl ? <Image src={profile.avatarUrl} alt="" width={72} height={72} /> : null}
        <h1>{profile.displayName}</h1>
        {profile.tagline ? <p>{profile.tagline}</p> : null}
        <img src={`/u/${encodeURIComponent(code)}/qr`} alt="" width={160} height={160} />
        <div className="public-user-link__actions">
          <Link href={session?.nextUrl || '/auth/login'}>Log in to connect</Link>
          <Link href={session?.registerUrl || '/auth/register'}>Create account to connect</Link>
        </div>
      </section>
    </main>
  );
}
```

Add `gateway/packages/web/app/u/[code]/claim-handoff.tsx` as a client-only
handoff that reads the stored customer auth token through the web API client,
calls `POST /api/public/link-sessions/:token/claim`, and redirects the customer
to the channel surface after the Service Link is activated. When
`searchParams.link_session` is present, the page must pass `openSession: false`
to `readPublicUserLink()` so the original auth-preserved token is not abandoned
and replaced by a fresh session.

Create `gateway/packages/web/app/u/[code]/qr/route.ts`:

```ts
import QRCode from 'qrcode';

function readWebBase(): string {
  return (process.env['NEXT_PUBLIC_COKE_WEB_URL'] || process.env['DOMAIN_CLIENT'] || 'http://localhost:4040').replace(/\/$/, '');
}

export async function GET(_req: Request, { params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const url = `${readWebBase()}/u/${encodeURIComponent(code)}`;
  const buffer = await QRCode.toBuffer(url, { type: 'png', margin: 1, width: 320 });
  return new Response(buffer, {
    headers: {
      'content-type': 'image/png',
      'cache-control': 'public, max-age=300',
    },
  });
}
```

- [ ] **Step 6: Add CSS**

Append scoped styles to `gateway/packages/web/app/public-site.css`:

```css
.coke-site.public-user-link {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px;
}

.coke-site .public-user-link__panel {
  width: min(100%, 420px);
  display: grid;
  gap: 16px;
  justify-items: center;
  text-align: center;
}

.coke-site .public-user-link__actions {
  display: grid;
  gap: 10px;
  width: 100%;
}

.coke-site .public-user-link__actions a {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  border: 1px solid var(--ink-20);
  border-radius: 8px;
  font-weight: 700;
}
```

- [ ] **Step 7: Run web tests and build**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  'app/u/[code]/page.test.tsx' \
  'app/u/[code]/qr/route.test.ts'
pnpm --dir gateway/packages/web build
```

Expected: tests and build pass. The build output should show `/u/[code]` and
`/u/[code]/qr` as dynamic server-rendered routes.

- [ ] **Step 8: Commit web entry**

```bash
cd /data/projects/coke/gateway
git add packages/shared/src/types/scheduling.ts \
  packages/shared/src/index.ts \
  packages/api/src/routes/public-user-link-routes.ts \
  packages/api/src/routes/public-user-link-routes.test.ts \
  packages/web/lib/user-link-api.ts \
  packages/web/app/u/[code]/claim-handoff.tsx \
  packages/web/app/u/[code]/page.tsx \
  packages/web/app/u/[code]/page.test.tsx \
  packages/web/app/u/[code]/qr/route.ts \
  packages/web/app/u/[code]/qr/route.test.ts \
  packages/web/app/public-site.css \
  packages/web/next.config.ts \
  packages/web/package.json \
  Dockerfile
git commit -m "feat: add public user link web entry"
```

## Task 8: Worker Runtime Scheduling Tools

**Files:**
- Create: `agent/agno_agent/capabilities/scheduling.py`
- Modify: `agent/agno_agent/capabilities/__init__.py`
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
- Modify: `agent/agno_agent/runtime/chat_response_instructions.py`
- Test: `tests/unit/agent/test_scheduling_capability.py`
- Test: `tests/unit/agent/test_agent_runtime_scheduling_tools.py`
- Test: `tests/unit/agent/test_chat_response_scheduling_instructions.py`

- [ ] **Step 1: Write failing capability tests**

Create `tests/unit/agent/test_scheduling_capability.py`:

```python
from datetime import UTC, datetime
from types import SimpleNamespace

from agent.agno_agent.runtime.context import AgentRunContext


def _run_context():
    return AgentRunContext(
        user=SimpleNamespace(id="ck_a", nickname="Coach A", timezone="Asia/Shanghai"),
        character=SimpleNamespace(id="char_1", nickname="Coke"),
        conversation=SimpleNamespace(id="conv_1", route_key="wechat_personal:primary"),
        platform="business",
        current_time=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
    )


def test_get_user_link_calls_gateway_tool(monkeypatch):
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    calls = []

    def handler(tool_name, payload):
      calls.append((tool_name, payload))
      return {"ok": True, "data": {"url": "https://kap.example/u/AbCdEfGhIjK_"}}

    port = SchedulingCapabilityPort(tool_name="get_user_link", handler=handler)
    result = port.run("", _run_context(), {})

    assert result.ok is True
    assert result.name == "get_user_link"
    assert result.content["url"] == "https://kap.example/u/AbCdEfGhIjK_"
    assert calls[0][0] == "get_user_link"
    assert calls[0][1]["customer_id"] == "ck_a"


def test_scheduling_gateway_client_uses_internal_auth(monkeypatch):
    from agent.agno_agent.capabilities.scheduling import SchedulingGatewayClient

    captured = {}

    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"ok": True, "data": {"pending": []}}

    class Session:
        def post(self, url, json, headers, timeout):
            captured.update({"url": url, "json": json, "headers": headers, "timeout": timeout})
            return Response()

    client = SchedulingGatewayClient(
        api_url="https://api.example",
        api_key="internal-key",
        session=Session(),
    )

    assert client.call_tool("list_pending_requests", {"customer_id": "ck_a"}) == {"ok": True, "data": {"pending": []}}
    assert captured["url"] == "https://api.example/api/internal/scheduling/tools/list_pending_requests"
    assert captured["headers"]["Authorization"] == "Bearer internal-key"
```

Create `tests/unit/agent/test_agent_runtime_scheduling_tools.py`:

```python
from datetime import UTC, datetime
from types import SimpleNamespace

from agent.agno_agent.runtime.agent_runtime import build_capability_tool_wrappers
from agent.agno_agent.runtime.context import AgentRunContext


class RecordingPort:
    def __init__(self):
        self.calls = []

    async def run(self, input_message, run_context, args):
        from agent.agno_agent.runtime.result import CapabilityResult
        self.calls.append((input_message, args))
        return CapabilityResult(name="get_user_link", ok=True, content={"url": "https://kap.example/u/AbCdEfGhIjK_"})


def test_runtime_exposes_get_user_link_tool():
    port = RecordingPort()
    context = AgentRunContext(
        user=SimpleNamespace(id="ck_a", nickname="Coach A", timezone="Asia/Shanghai"),
        character=SimpleNamespace(id="char_1", nickname="Coke"),
        conversation=SimpleNamespace(id="conv_1", route_key="wechat_personal:primary"),
        platform="business",
        current_time=datetime(2026, 6, 1, tzinfo=UTC),
    )

    wrappers = build_capability_tool_wrappers(
        ports={"get_user_link": port},
        run_context=context,
        input_message="show my link",
        tool_results=[],
    )

    assert "get_user_link" in wrappers
```

- [ ] **Step 2: Write failing instruction test**

Create `tests/unit/agent/test_chat_response_scheduling_instructions.py`:

```python
from datetime import UTC, datetime
from types import SimpleNamespace

from agent.agno_agent.runtime.chat_response_instructions import build_chat_response_instructions
from agent.agno_agent.runtime.inputs import AgentInput


def test_scheduling_tool_boundary_is_present():
    run_context = SimpleNamespace(
        current_time=datetime(2026, 6, 1, tzinfo=UTC),
        user=SimpleNamespace(id="ck_a", nickname="Coach A", timezone="Asia/Shanghai"),
        character=SimpleNamespace(id="char_1", nickname="Coke"),
        conversation=SimpleNamespace(id="conv_1", route_key="wechat_personal:primary"),
        platform="business",
    )
    text = build_chat_response_instructions(
        run_context,
        AgentInput(input_type="user.turn", message="show my user link", payload=None),
    )
    assert "Scheduling tool boundary:" in text
    assert "Do not create appointment state from ordinary calendar discussion" in text
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/agent/test_scheduling_capability.py \
  tests/unit/agent/test_agent_runtime_scheduling_tools.py \
  tests/unit/agent/test_chat_response_scheduling_instructions.py \
  -v
```

Expected: FAIL because scheduling capability files and instructions do not
exist.

- [ ] **Step 4: Implement scheduling capability port**

Create `agent/agno_agent/capabilities/scheduling.py`:

```python
from __future__ import annotations

import os
from typing import Any, Callable

import requests

from agent.agno_agent.runtime.context import AgentRunContext
from agent.agno_agent.runtime.result import CapabilityResult


class SchedulingGatewayClientError(RuntimeError):
    pass


class SchedulingGatewayClient:
    def __init__(
        self,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        session: Any | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.api_url = (api_url or os.environ.get("COKE_GATEWAY_API_URL") or os.environ.get("NEXT_PUBLIC_COKE_API_URL") or "http://127.0.0.1:4041").rstrip("/")
        self.api_key = api_key or os.environ.get("CLAWSCALE_IDENTITY_API_KEY", "")
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def call_tool(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.api_url}/api/internal/scheduling/tools/{tool_name}",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not data.get("ok"):
            raise SchedulingGatewayClientError(str(data.get("error", "scheduling_gateway_failed")) if isinstance(data, dict) else "invalid_scheduling_gateway_response")
        return data


class SchedulingCapabilityPort:
    def __init__(
        self,
        *,
        tool_name: str,
        handler: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        client: SchedulingGatewayClient | None = None,
    ) -> None:
        self.tool_name = tool_name
        self.handler = handler
        self.client = client or SchedulingGatewayClient()

    def run(
        self,
        input_message: str,
        run_context: AgentRunContext,
        args: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        payload = {
            "customer_id": run_context.user.id,
            "conversation_id": run_context.conversation.id,
            "platform": run_context.platform,
            "input_message": input_message,
            **(args or {}),
        }
        raw = self.handler(self.tool_name, payload) if self.handler else self.client.call_tool(self.tool_name, payload)
        data = raw.get("data", raw)
        if not isinstance(data, dict):
            data = {"value": data}
        return CapabilityResult(
            name=self.tool_name,
            ok=bool(raw.get("ok", True)),
            content=data,
            error=None if raw.get("ok", True) else str(raw.get("error", "scheduling_failed")),
            metadata={"durable_write": self.tool_name not in {"query_bookable_windows", "list_pending_requests"}},
        )
```

Update `agent/agno_agent/capabilities/__init__.py` incrementally. Add the
`SchedulingCapabilityPort` import and `__all__` entry while preserving the
existing exports from the current `f7eb83c` Agno runtime cleanup baseline:

```python
from agent.agno_agent.capabilities.album import AlbumCapabilityPort
from agent.agno_agent.capabilities.calendar_import_port import CalendarImportPort
from agent.agno_agent.capabilities.context_retrieve import ContextRetrieveCapabilityPort
from agent.agno_agent.capabilities.reminder_intent import ReminderIntentPort
from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort
from agent.agno_agent.capabilities.timezone import TimezoneCapabilityPort
from agent.agno_agent.capabilities.timezone_port import TimezonePort
from agent.agno_agent.capabilities.url_context_port import UrlContextPort
from agent.agno_agent.capabilities.usage import UsageCapabilityPort

__all__ = [
    "AlbumCapabilityPort",
    "CalendarImportPort",
    "ContextRetrieveCapabilityPort",
    "ReminderIntentPort",
    "SchedulingCapabilityPort",
    "TimezoneCapabilityPort",
    "TimezonePort",
    "UrlContextPort",
    "UsageCapabilityPort",
]
```

- [ ] **Step 5: Register scheduling tools in runtime**

Modify `_default_capability_ports()` in
`agent/agno_agent/runtime/agent_runtime.py`:

```python
from agent.agno_agent.capabilities import SchedulingCapabilityPort

scheduling_tool_names = (
    "get_user_link",
    "reset_user_link",
    "disable_user_link",
    "open_bookable_windows",
    "confirm_bookable_windows",
    "query_bookable_windows",
    "request_appointment",
    "confirm_appointment",
    "reject_appointment",
    "cancel_appointment",
    "list_pending_requests",
    "block_service_link",
    "unblock_service_link",
    "remove_service_link",
)
ports = {
    "reminder_intent": ReminderIntentPort(),
    "timezone": TimezoneCapabilityPort(),
    "calendar_import": CalendarImportPort(),
    "url_context": UrlContextPort(),
}
ports.update({
    name: SchedulingCapabilityPort(tool_name=name)
    for name in scheduling_tool_names
})
return ports
```

Add wrapper branches in `_build_capability_tool_wrapper` for scheduling tools:

```python
    if tool_name in {
        "get_user_link",
        "reset_user_link",
        "disable_user_link",
        "open_bookable_windows",
        "confirm_bookable_windows",
        "query_bookable_windows",
        "request_appointment",
        "confirm_appointment",
        "reject_appointment",
        "cancel_appointment",
        "list_pending_requests",
        "block_service_link",
        "unblock_service_link",
        "remove_service_link",
    }:

        async def scheduling_tool(**kwargs: Any) -> dict[str, Any]:
            """Use for explicit user-link, availability, appointment, or service-link scheduling requests."""
            return await _call(dict(kwargs))

        return scheduling_tool
```

- [ ] **Step 6: Add scheduling instruction boundary**

Modify `agent/agno_agent/runtime/chat_response_instructions.py`:

```python
_SCHEDULING_TOOL_BOUNDARY = """Scheduling tool boundary:
- Use scheduling tools only when the current user message explicitly asks to show/reset/disable a user link, manage bookable windows, query a linked provider's availability, request an appointment, confirm/reject/cancel an appointment, list pending appointment requests, or block/remove/unblock a service link.
- Do not create appointment state from ordinary calendar discussion, plans, or vague availability talk.
- Pending appointment holds do not expire automatically. If A asks about stale requests, list pending requests or cancel/reject them; do not invent a hidden timeout.
- If B has multiple active provider service links and does not name a provider, ask which provider instead of guessing."""
```

Include `_SCHEDULING_TOOL_BOUNDARY` in the `"\n\n".join` call after
`_REMINDER_TOOL_BOUNDARY`.

- [ ] **Step 7: Run agent tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/agent/test_scheduling_capability.py \
  tests/unit/agent/test_agent_runtime_scheduling_tools.py \
  tests/unit/agent/test_chat_response_scheduling_instructions.py \
  -v
```

Expected: PASS.

- [ ] **Step 8: Commit worker-runtime slice**

```bash
cd /data/projects/coke
git add agent/agno_agent/capabilities/scheduling.py \
  agent/agno_agent/capabilities/__init__.py \
  agent/agno_agent/runtime/agent_runtime.py \
  agent/agno_agent/runtime/chat_response_instructions.py \
  tests/unit/agent/test_scheduling_capability.py \
  tests/unit/agent/test_agent_runtime_scheduling_tools.py \
  tests/unit/agent/test_chat_response_scheduling_instructions.py
git commit -m "feat: add scheduling agent tools"
```

## Task 9: Documentation And Route Discoverability

**Files:**
- Modify: `docs/product-specs/FEATURE_TREE.md`
- Modify: `docs/design-docs/data-retention-policy.md`
- Modify: `docs/fitness/ownership-registry.yaml`
- Modify: `docs/ARCHITECTURE.md`
- Test: `tests/unit/test_data_retention_policy_consistency.py`

- [ ] **Step 1: Write failing retention consistency test extension**

Modify `tests/unit/test_data_retention_policy_consistency.py` to include the
new scheduling policy names from `docs/design-docs/data-retention-policy.md`
and the boundary spec. Add:

```python
SCHEDULING_SPEC = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-05-21-user-link-scheduling-design.md"
)


def test_scheduling_spec_retention_policies_are_documented():
    spec_names = _extract_policy_names(SCHEDULING_SPEC)
    doc_names = _extract_policy_names(POLICY_DOC)
    missing = spec_names - doc_names
    assert missing == set(), (
        "Retention policies named in scheduling spec are missing from policy doc: "
        f"{sorted(missing)}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_data_retention_policy_consistency.py -v
```

Expected: FAIL until the policy doc and spec use matching policy names.

- [ ] **Step 3: Update data retention policy**

Add rows to `docs/design-docs/data-retention-policy.md`:

```markdown
| `scheduling_link_session_retention` | 30 days after abandoned; claimed sessions follow account lifetime | Platform System | link session count by terminal state |
| `scheduling_service_link_retention` | 90 days after removed or blocked | Platform System | service link count by terminal state |
| `scheduling_appointment_request_retention` | 90 days after released | Platform System | appointment request count by terminal state |
| `scheduling_shared_appointment_retention` | 1 year after cancelled | Platform System | shared appointment count by terminal state |
| `scheduling_bookable_window_retention` | 90 days after closed | Platform System | bookable window count by status |
| `scheduling_disabled_user_link_retention` | indefinite, de-listed and not reused | Platform System | disabled user link count |
```

Update the scheduling spec data-retention section to name those policy ids.

- [ ] **Step 4: Update feature tree**

Add under `Platform / Gateway Surfaces` in
`docs/product-specs/FEATURE_TREE.md`:

```markdown
- User Link Scheduling
  - public web entry: `gateway/packages/web/app/u/[code]/page.tsx`
  - public QR route: `gateway/packages/web/app/u/[code]/qr/route.ts`
  - public API: `gateway/packages/api/src/routes/public-user-link-routes.ts`
  - customer API: `gateway/packages/api/src/routes/customer-scheduling-routes.ts`
  - internal agent API: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
  - Gateway domain services: `gateway/packages/api/src/scheduling/`
  - Worker agent tools: `agent/agno_agent/capabilities/scheduling.py`
```

- [ ] **Step 4a: Update architecture runtime tool inventory**

Update `docs/ARCHITECTURE.md` in the single-Agent runtime section so the
Agno-managed tool-wrapper list includes the scheduling tools added in Task 8.
Preserve the `f7eb83c` architecture wording about the shared `agent_sessions`
MongoDB session store, Agno-managed history context, raw input text, runner
responsibilities, post-analyze dispatch, and retired module-level Agno agent
singletons. Do not reintroduce retired prepare/chat workflow, legacy multi-agent
runtime, orchestrator, or memo-tool wording.

- [ ] **Step 4b: Update ownership registry**

Add the scheduling Gateway route files to `docs/fitness/ownership-registry.yaml`:

- `gateway/packages/api/src/routes/public-user-link-routes.ts`
- `gateway/packages/api/src/routes/customer-scheduling-routes.ts`
- `gateway/packages/api/src/routes/internal-scheduling-routes.ts`

Use Platform as the primary owner. Add Agent Runtime as secondary owner for
customer/internal scheduling routes that expose agent-facing scheduling
contracts.

- [ ] **Step 5: Run docs checks**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_data_retention_policy_consistency.py -v
zsh scripts/check
zsh scripts/verify-surface repo-os-docs
```

Expected: PASS.

- [ ] **Step 6: Commit docs**

```bash
cd /data/projects/coke
git add docs/product-specs/FEATURE_TREE.md \
  docs/design-docs/data-retention-policy.md \
  docs/fitness/ownership-registry.yaml \
  docs/ARCHITECTURE.md \
  docs/superpowers/specs/2026-05-21-user-link-scheduling-design.md \
  docs/superpowers/plans/2026-05-21-user-link-scheduling.md \
  tests/unit/test_data_retention_policy_consistency.py
git commit -m "docs: add scheduling route and retention surfaces"
```

## Task 10: End-To-End Verification And Final Integration

**Files:**
- No new source files.
- Evidence output: `artifacts/evidence/2026-05-21-user-link-scheduling-verification.md`

- [ ] **Step 1: Run Gateway API tests**

Run:

```bash
pnpm --dir gateway/packages/api test -- \
  src/scheduling/schema-contract.test.ts \
  src/scheduling/time.test.ts \
  src/scheduling/user-link-service.test.ts \
  src/scheduling/service-link-service.test.ts \
  src/scheduling/availability-service.test.ts \
  src/scheduling/appointment-service.test.ts \
  src/scheduling/notification-service.test.ts \
  src/routes/public-user-link-routes.test.ts \
  src/routes/customer-scheduling-routes.test.ts \
  src/routes/internal-scheduling-routes.test.ts
pnpm --dir gateway/packages/api build
```

Expected: all listed tests pass and the API package builds.

- [ ] **Step 2: Run Gateway Web tests**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  'app/u/[code]/page.test.tsx' \
  'app/u/[code]/qr/route.test.ts' \
  'app/(customer)/auth/login/page.test.tsx' \
  'app/(customer)/auth/register/page.test.tsx' \
  'app/(customer)/auth/verify-email/page.test.tsx'
pnpm --dir gateway/packages/web build
```

Expected: all listed tests pass and the Web package builds.

- [ ] **Step 3: Run Python bridge and worker tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/test_message_gateway.py \
  tests/unit/connector/clawscale_bridge/test_bridge_app.py \
  tests/unit/agent/test_scheduling_capability.py \
  tests/unit/agent/test_agent_runtime_scheduling_tools.py \
  tests/unit/agent/test_chat_response_scheduling_instructions.py \
  -v
```

Expected: all listed tests pass.

- [ ] **Step 4: Run diff-aware repository verification**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/verify-surface repo-os-docs gateway-api gateway-web bridge worker-runtime
zsh scripts/review-trigger --base HEAD~1
```

Expected:

- `suggest-verification` lists the touched surfaces.
- `verify-surface` passes.
- `review-trigger` may require human review for cross-boundary product work;
  record its exact output.

- [ ] **Step 5: Capture evidence**

Create `artifacts/evidence/2026-05-21-user-link-scheduling-verification.md`
with command names, exit codes, and the final 20 lines of each command output.
Use this command from `/data/projects/coke` after the verification commands
have run:

```bash
mkdir -p artifacts/evidence
{
  echo '# User Link Scheduling Verification'
  echo
  echo 'Date: 2026-05-21'
  echo
  echo '## Required Command Set'
  echo
  echo '- pnpm --dir gateway/packages/api test -- src/scheduling/schema-contract.test.ts src/scheduling/time.test.ts src/scheduling/user-link-service.test.ts src/scheduling/service-link-service.test.ts src/scheduling/availability-service.test.ts src/scheduling/appointment-service.test.ts src/scheduling/notification-service.test.ts src/routes/public-user-link-routes.test.ts src/routes/customer-scheduling-routes.test.ts src/routes/internal-scheduling-routes.test.ts'
  echo '- pnpm --dir gateway/packages/api build'
  echo '- pnpm --dir gateway/packages/web test -- app/u/[code]/page.test.tsx app/u/[code]/qr/route.test.ts app/(customer)/auth/login/page.test.tsx app/(customer)/auth/register/page.test.tsx app/(customer)/auth/verify-email/page.test.tsx'
  echo '- pnpm --dir gateway/packages/web build'
  echo '- .venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_message_gateway.py tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_scheduling_tools.py tests/unit/agent/test_chat_response_scheduling_instructions.py -v'
  echo '- zsh scripts/verify-surface repo-os-docs gateway-api gateway-web bridge worker-runtime'
  echo '- zsh scripts/review-trigger --base HEAD~1'
  echo
  echo '## Result Recording Rule'
  echo
  echo 'For each command above, record exit code 0 for pass or the exact nonzero exit code for failure, followed by the final 20 output lines.'
} > artifacts/evidence/2026-05-21-user-link-scheduling-verification.md
```

- [ ] **Step 6: Commit evidence**

```bash
cd /data/projects/coke
git add artifacts/evidence/2026-05-21-user-link-scheduling-verification.md
git commit -m "test: record user link scheduling verification"
```

## Self-Review Checklist

- [ ] Spec REQ-1 is covered by Tasks 3, 6, and 7.
- [ ] Spec REQ-2 is covered by Tasks 3, 6, and 7.
- [ ] Spec REQ-3 is covered by Tasks 6 and 7.
- [ ] Spec REQ-4 is covered by Tasks 3 and 6.
- [ ] Spec REQ-5 is covered by Tasks 2, 4, and 8.
- [ ] Spec REQ-6 is covered by Tasks 2, 4, and 8.
- [ ] Spec REQ-7 is covered by Tasks 4 and 5.
- [ ] Spec REQ-8 is covered by Tasks 4, 5, and 8.
- [ ] Spec REQ-9 is covered by Tasks 4 and 5.
- [ ] Spec REQ-10 is covered by Tasks 1 and 4.
- [ ] Spec REQ-11 is covered by Tasks 4 and 5.
- [ ] Spec REQ-12 is covered by Tasks 4, 6, and 8.
- [ ] Spec REQ-13 is covered by Tasks 3, 6, and 8.
- [ ] No implementation task adds automatic hold expiry.
- [ ] No implementation task adds a one-pending-request-per-A-B limit.
- [ ] Database-level per-instance occupancy is enforced by a partial unique
  index.
- [ ] Gateway route discoverability is updated in `FEATURE_TREE.md`.
- [ ] Agno single-Agent runtime tool inventory is updated in
  `docs/ARCHITECTURE.md` without reverting the `f7eb83c` architecture cleanup.
- [ ] Retention policy names are documented and tested.
- [ ] All route, domain, web, bridge, worker, repo-OS, and review-trigger
  commands have fresh evidence.
