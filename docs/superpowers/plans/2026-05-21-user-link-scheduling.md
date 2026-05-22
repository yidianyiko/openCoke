# Friend Link And Shared Reminder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the appointment-oriented user-link scheduling slice with the first-version friend-link, friendship, and shared-reminder request flow defined in `docs/superpowers/specs/2026-05-21-user-link-scheduling-design.md`.

**Architecture:** Gateway/Postgres owns user links, link sessions, friend requests, friendships, blocks, shared reminder requests, notification intents, and audit transitions. Reminder Runtime remains owner-scoped; Gateway creates and cancels participant reminder projections only through the existing Bridge reminder-management API. Web and agent entry points call the same Gateway transitions, and Bridge only carries notification metadata into the existing agent conversation path.

**Tech Stack:** TypeScript, Hono, Prisma/Postgres, Next.js app router, Vitest, Python worker runtime, pytest, Bridge `/bridge/internal/reminders`, Bridge `/bridge/inbound`, MongoDB Reminder Runtime.

---

## Scope And Execution Notes

This plan intentionally replaces the current appointment model names and agent tools. Do not preserve appointment/bookable-window/service-link behavior as a compatibility path unless the spec is revised first.

The repository has a nested `gateway/` checkout. Gateway commits are made from `/data/projects/coke/gateway`; root docs and Python runtime commits are made from `/data/projects/coke`. Commit the nested gateway change first, then commit the parent gitlink together with root files when the parent records it.

Touched planning surfaces:

- `gateway-api`: product state, route handlers, Prisma schema, notification intent, Reminder Runtime projection calls.
- `gateway-web`: public user-link page, QR route, link-session handoff, friend-request actions.
- `bridge`: notification metadata preservation only.
- `worker-runtime`: scheduling domain tool names and instructions.
- `repo-os`: feature tree, architecture, retention policy, and this plan.

## File Structure

### Gateway API

- Modify: `gateway/packages/api/prisma/schema.prisma`
  - Keep `UserLink` and `LinkSession`, but change link-session TTL expectation from 1 day to 30 days.
  - Remove `ServiceLink`, `BookableWindow`, `BookableWindowExclusion`, `AppointmentRequest`, and `AppointmentEvent`.
  - Add `FriendRequest`, `Friendship`, `AccountBlock`, `SharedReminderRequest`, `SharedReminderEvent`, `ReminderProjection`, and generic `ProductNotification`.
- Create: `gateway/packages/api/prisma/migrations/20260522100000_friend_link_shared_reminders/migration.sql`
  - Apply enum/table changes and partial indexes.
- Modify: `gateway/packages/api/src/scheduling/types.ts`
  - Replace appointment DTOs with friend/shared-reminder DTOs.
- Modify: `gateway/packages/api/src/scheduling/user-link-service.ts`
  - Keep link creation/reset/disable/open-session.
  - Add `sendFriendRequestFromLinkSession`.
  - Remove automatic service-link creation on link-session claim.
- Delete: `gateway/packages/api/src/scheduling/service-link-service.ts`
- Delete: `gateway/packages/api/src/scheduling/availability-service.ts`
- Delete: `gateway/packages/api/src/scheduling/appointment-service.ts`
- Create: `gateway/packages/api/src/scheduling/friendship-service.ts`
  - Friend request accept/reject/cancel, friendship list/remove, block/unblock.
- Create: `gateway/packages/api/src/scheduling/shared-reminder-service.ts`
  - Shared reminder create/accept/reject/cancel/expire/invalidate.
- Modify: `gateway/packages/api/src/scheduling/notification-service.ts`
  - Rename the data contract from appointment-specific scheduling notifications to generic product notifications.
- Modify: `gateway/packages/api/src/lib/reminder-runtime-client.ts`
  - Allow shared-reminder projection metadata to pass through reminder create requests.
- Modify: `gateway/packages/api/src/routes/public-user-link-routes.ts`
  - Public link read/open-session and authenticated friend-request claim.
- Modify: `gateway/packages/api/src/routes/customer-scheduling-routes.ts`
  - Customer routes for user-link, friend requests, friendships, blocks, and shared reminders.
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
  - Agent tool route dispatch for friend/shared-reminder operations.
- Modify: `gateway/packages/api/src/index.ts`
  - Keep route registration current after route exports change.
- Modify tests under `gateway/packages/api/src/scheduling/` and `gateway/packages/api/src/routes/`.

### Gateway Shared And Web

- Modify: `gateway/packages/shared/src/types/scheduling.ts`
  - Export public-safe friend/shared-reminder DTOs.
- Modify: `gateway/packages/shared/src/index.ts`
  - Re-export scheduling DTOs.
- Modify: `gateway/packages/web/lib/user-link-api.ts`
  - Fetch public user-link data, open link sessions, send friend requests.
- Modify: `gateway/packages/web/app/u/[code]/page.tsx`
  - Public profile page with login/register or send-friend-request action.
- Modify: `gateway/packages/web/app/u/[code]/claim-handoff.tsx`
  - Authenticated claim form for sending a friend request.
- Modify: `gateway/packages/web/app/u/[code]/qr/route.ts`
  - Keep QR generation pointed at `/u/:code`.
- Modify auth tests in `gateway/packages/web/app/(customer)/auth/`.

### Bridge And Worker Runtime

- Modify: `connector/clawscale_bridge/message_gateway.py`
  - Preserve `product_notification` metadata while keeping text-compatible processing.
- Modify: `agent/agno_agent/capabilities/scheduling.py`
  - Replace appointment tool names with friend/shared-reminder tool names.
- Modify: `agent/agno_agent/runtime/scheduling_types.py`
  - Replace bookable-window preview types with shared-reminder argument models.
- Modify: `agent/agno_agent/runtime/execution_agents.py`
  - Update scheduling worker instructions and tool signature.
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
  - Update the scheduling domain docstring.
- Modify: `agent/agno_agent/runtime/chat_response_instructions.py`
  - Update model policy so ordinary personal reminders still use Reminder Runtime, while shared reminders require an active friend.
- Modify unit tests under `tests/unit/agent/` and `tests/unit/connector/clawscale_bridge/`.

### Docs

- Modify: `docs/product-specs/FEATURE_TREE.md`
- Modify: `docs/design-docs/data-retention-policy.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/superpowers/specs/2026-05-21-user-link-scheduling-design.md` only if implementation reveals a product-contract correction.

## Route Map

Gateway API routes:

- `GET /api/public/user-links/:code`
- `POST /api/public/user-links/:code/sessions`
- `GET /api/public/link-sessions/:token/status`
- `POST /api/public/link-sessions/:token/friend-requests`
- `GET /api/customer/scheduling/user-link`
- `POST /api/customer/scheduling/user-link/reset`
- `POST /api/customer/scheduling/user-link/disable`
- `GET /api/customer/scheduling/friend-requests`
- `POST /api/customer/scheduling/friend-requests/:id/accept`
- `POST /api/customer/scheduling/friend-requests/:id/reject`
- `POST /api/customer/scheduling/friend-requests/:id/cancel`
- `GET /api/customer/scheduling/friends`
- `DELETE /api/customer/scheduling/friends/:friendshipId`
- `POST /api/customer/scheduling/blocks`
- `DELETE /api/customer/scheduling/blocks/:blockedAccountId`
- `POST /api/customer/scheduling/shared-reminders`
- `GET /api/customer/scheduling/shared-reminders/pending`
- `POST /api/customer/scheduling/shared-reminders/:id/accept`
- `POST /api/customer/scheduling/shared-reminders/:id/reject`
- `POST /api/customer/scheduling/shared-reminders/:id/cancel`
- `POST /api/internal/scheduling/tools/:toolName`
- `POST /api/internal/scheduling/notifications/retry`

Worker scheduling tool names:

- `get_user_link`
- `reset_user_link`
- `disable_user_link`
- `list_friend_requests`
- `accept_friend_request`
- `reject_friend_request`
- `cancel_friend_request`
- `list_friends`
- `remove_friendship`
- `block_account`
- `unblock_account`
- `create_shared_reminder`
- `list_pending_shared_reminders`
- `accept_shared_reminder`
- `reject_shared_reminder`
- `cancel_shared_reminder`

## Task 1: Gateway Schema And Migration

**Files:**
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Create: `gateway/packages/api/prisma/migrations/20260522100000_friend_link_shared_reminders/migration.sql`
- Modify: `gateway/packages/api/src/scheduling/schema-contract.test.ts`

- [ ] **Step 1: Write the failing schema contract test**

Replace `gateway/packages/api/src/scheduling/schema-contract.test.ts` with:

```ts
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const schemaPath = join(process.cwd(), 'prisma/schema.prisma');
const migrationPath = join(
  process.cwd(),
  'prisma/migrations/20260522100000_friend_link_shared_reminders/migration.sql',
);

describe('friend-link and shared-reminder schema contract', () => {
  it('declares first-version product-state models', () => {
    const schema = readFileSync(schemaPath, 'utf8');
    expect(schema).toContain('model UserLink');
    expect(schema).toContain('model LinkSession');
    expect(schema).toContain('model FriendRequest');
    expect(schema).toContain('model Friendship');
    expect(schema).toContain('model AccountBlock');
    expect(schema).toContain('model SharedReminderRequest');
    expect(schema).toContain('model SharedReminderEvent');
    expect(schema).toContain('model ReminderProjection');
    expect(schema).toContain('model ProductNotification');
  });

  it('removes appointment-only product models', () => {
    const schema = readFileSync(schemaPath, 'utf8');
    expect(schema).not.toContain('model ServiceLink');
    expect(schema).not.toContain('model BookableWindow');
    expect(schema).not.toContain('model BookableWindowExclusion');
    expect(schema).not.toContain('model AppointmentRequest');
    expect(schema).not.toContain('model AppointmentEvent');
    expect(schema).not.toContain('enum AppointmentRequestStatus');
    expect(schema).not.toContain('enum BookableWindowStatus');
  });

  it('keeps database constraints for active links and account pairs', () => {
    const sql = readFileSync(migrationPath, 'utf8');
    expect(sql).toContain('CREATE UNIQUE INDEX "user_links_one_active_per_account"');
    expect(sql).toContain("WHERE status = 'active'");
    expect(sql).toContain('CREATE UNIQUE INDEX "friend_requests_one_pending_pair"');
    expect(sql).toContain("WHERE status = 'pending'");
    expect(sql).toContain('CREATE UNIQUE INDEX "friendships_one_active_pair"');
    expect(sql).toContain("WHERE status = 'active'");
    expect(sql).toContain('CREATE UNIQUE INDEX "account_blocks_direction_uniq"');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/schema-contract.test.ts
```

Expected: FAIL because the new migration and models are not present.

- [ ] **Step 3: Replace scheduling enums**

In `gateway/packages/api/prisma/schema.prisma`, keep `UserLinkStatus` and `LinkSessionStatus`, remove appointment/bookable-window/service-link enums, and add:

```prisma
enum FriendRequestStatus {
  pending
  accepted
  rejected
  cancelled
}

enum FriendshipStatus {
  active
  removed
}

enum SharedReminderRequestStatus {
  pending_invitee_confirmation
  accepted
  rejected
  expired
  cancelled
  invalidated
}

enum SharedReminderProjectionRole {
  requester
  invitee
}

enum SharedReminderActorRole {
  requester
  invitee
  system
}

enum ProductNotificationStatus {
  pending_delivery
  delivered
  failed
}
```

- [ ] **Step 4: Replace appointment models with friend/shared-reminder models**

In `gateway/packages/api/prisma/schema.prisma`, remove `ServiceLink`, `BookableWindow`, `BookableWindowExclusion`, `AppointmentRequest`, `AppointmentEvent`, and `SchedulingNotification`. Add:

```prisma
model FriendRequest {
  id                 String              @id @default(cuid())
  requesterAccountId String              @map("requester_account_id")
  targetAccountId    String              @map("target_account_id")
  linkSessionId      String?             @map("link_session_id")
  message            String?             @db.VarChar(500)
  idempotencyKey     String?             @map("idempotency_key")
  status             FriendRequestStatus @default(pending)
  resolvedAt         DateTime?           @map("resolved_at")
  createdAt          DateTime            @default(now()) @map("created_at")
  updatedAt          DateTime            @updatedAt @map("updated_at")

  requester   Customer     @relation("RequesterFriendRequests", fields: [requesterAccountId], references: [id], onDelete: Cascade)
  target      Customer     @relation("TargetFriendRequests", fields: [targetAccountId], references: [id], onDelete: Cascade)
  linkSession LinkSession? @relation(fields: [linkSessionId], references: [id], onDelete: SetNull)

  @@index([requesterAccountId, status])
  @@index([targetAccountId, status])
  @@unique([requesterAccountId, targetAccountId, idempotencyKey])
  @@map("friend_requests")
}

model Friendship {
  id              String           @id @default(cuid())
  accountAId      String           @map("account_a_id")
  accountBId      String           @map("account_b_id")
  friendRequestId String?          @map("friend_request_id")
  status          FriendshipStatus @default(active)
  removedAt       DateTime?        @map("removed_at")
  createdAt       DateTime         @default(now()) @map("created_at")
  updatedAt       DateTime         @updatedAt @map("updated_at")

  accountA      Customer       @relation("FriendshipAccountA", fields: [accountAId], references: [id], onDelete: Cascade)
  accountB      Customer       @relation("FriendshipAccountB", fields: [accountBId], references: [id], onDelete: Cascade)
  friendRequest FriendRequest? @relation(fields: [friendRequestId], references: [id], onDelete: SetNull)

  @@index([accountAId, status])
  @@index([accountBId, status])
  @@map("friendships")
}

model AccountBlock {
  id               String   @id @default(cuid())
  blockerAccountId String   @map("blocker_account_id")
  blockedAccountId String   @map("blocked_account_id")
  createdAt        DateTime @default(now()) @map("created_at")

  blocker Customer @relation("BlockerAccountBlocks", fields: [blockerAccountId], references: [id], onDelete: Cascade)
  blocked Customer @relation("BlockedAccountBlocks", fields: [blockedAccountId], references: [id], onDelete: Cascade)

  @@index([blockerAccountId])
  @@index([blockedAccountId])
  @@map("account_blocks")
}

model SharedReminderRequest {
  id                    String                      @id @default(cuid())
  requesterAccountId    String                      @map("requester_account_id")
  inviteeAccountId      String                      @map("invitee_account_id")
  friendshipId          String                      @map("friendship_id")
  title                 String                      @db.VarChar(200)
  fireAt                DateTime                    @map("fire_at")
  timezone              String
  idempotencyKey        String?                     @map("idempotency_key")
  status                SharedReminderRequestStatus @default(pending_invitee_confirmation)
  requesterReminderId   String?                     @map("requester_reminder_id")
  inviteeReminderId     String?                     @map("invitee_reminder_id")
  resolvedAt            DateTime?                   @map("resolved_at")
  createdAt             DateTime                    @default(now()) @map("created_at")
  updatedAt             DateTime                    @updatedAt @map("updated_at")

  requester Customer     @relation("RequesterSharedReminders", fields: [requesterAccountId], references: [id], onDelete: Cascade)
  invitee   Customer     @relation("InviteeSharedReminders", fields: [inviteeAccountId], references: [id], onDelete: Cascade)
  friendship Friendship  @relation(fields: [friendshipId], references: [id], onDelete: Restrict)
  events    SharedReminderEvent[]
  projections ReminderProjection[]
  notifications ProductNotification[]

  @@index([requesterAccountId, status])
  @@index([inviteeAccountId, status])
  @@index([fireAt, status])
  @@unique([requesterAccountId, inviteeAccountId, idempotencyKey])
  @@map("shared_reminder_requests")
}

model SharedReminderEvent {
  id                     String                      @id @default(cuid())
  sharedReminderRequestId String                     @map("shared_reminder_request_id")
  fromState              SharedReminderRequestStatus? @map("from_state")
  toState                SharedReminderRequestStatus @map("to_state")
  actorAccountId         String?                     @map("actor_account_id")
  actorRole              SharedReminderActorRole     @map("actor_role")
  idempotencyKey         String?                     @unique @map("idempotency_key")
  reason                 String?
  createdAt              DateTime                    @default(now()) @map("created_at")

  sharedReminderRequest SharedReminderRequest @relation(fields: [sharedReminderRequestId], references: [id], onDelete: Cascade)

  @@index([sharedReminderRequestId, createdAt])
  @@map("shared_reminder_events")
}

model ReminderProjection {
  id                     String                       @id @default(cuid())
  sharedReminderRequestId String                      @map("shared_reminder_request_id")
  ownerAccountId          String                      @map("owner_account_id")
  runtimeReminderId       String                      @map("runtime_reminder_id")
  role                    SharedReminderProjectionRole
  createdAt               DateTime                    @default(now()) @map("created_at")

  sharedReminderRequest SharedReminderRequest @relation(fields: [sharedReminderRequestId], references: [id], onDelete: Cascade)
  owner                 Customer              @relation(fields: [ownerAccountId], references: [id], onDelete: Cascade)

  @@unique([sharedReminderRequestId, role])
  @@index([ownerAccountId])
  @@map("reminder_projections")
}

model ProductNotification {
  id                     String                    @id @default(cuid())
  sharedReminderRequestId String?                  @map("shared_reminder_request_id")
  friendRequestId         String?                  @map("friend_request_id")
  recipientAccountId      String                   @map("recipient_account_id")
  idempotencyKey          String                   @unique @map("idempotency_key")
  kind                    String
  payload                 Json
  status                  ProductNotificationStatus @default(pending_delivery)
  attempts                Int                       @default(0)
  lastError               String?                   @map("last_error")
  deliveredAt             DateTime?                 @map("delivered_at")
  createdAt               DateTime                  @default(now()) @map("created_at")
  updatedAt               DateTime                  @updatedAt @map("updated_at")

  sharedReminderRequest SharedReminderRequest? @relation(fields: [sharedReminderRequestId], references: [id], onDelete: Cascade)
  friendRequest         FriendRequest?         @relation(fields: [friendRequestId], references: [id], onDelete: Cascade)
  recipient             Customer               @relation(fields: [recipientAccountId], references: [id], onDelete: Cascade)

  @@index([status, createdAt])
  @@index([recipientAccountId, createdAt])
  @@map("product_notifications")
}
```

- [ ] **Step 5: Add relation fields to existing models**

Add these relation fields to `Customer`:

```prisma
requesterFriendRequests FriendRequest[] @relation("RequesterFriendRequests")
targetFriendRequests    FriendRequest[] @relation("TargetFriendRequests")
friendshipsAsA          Friendship[]    @relation("FriendshipAccountA")
friendshipsAsB          Friendship[]    @relation("FriendshipAccountB")
blocksCreated           AccountBlock[]  @relation("BlockerAccountBlocks")
blocksReceived          AccountBlock[]  @relation("BlockedAccountBlocks")
requesterSharedReminders SharedReminderRequest[] @relation("RequesterSharedReminders")
inviteeSharedReminders   SharedReminderRequest[] @relation("InviteeSharedReminders")
reminderProjections      ReminderProjection[]
productNotifications     ProductNotification[]
```

Add this relation field to `LinkSession`:

```prisma
friendRequests FriendRequest[]
```

- [ ] **Step 6: Write the migration SQL**

Create `gateway/packages/api/prisma/migrations/20260522100000_friend_link_shared_reminders/migration.sql` with SQL generated from the Prisma change, then add these raw indexes:

```sql
CREATE UNIQUE INDEX "user_links_one_active_per_account"
  ON "user_links" ("provider_account_id")
  WHERE status = 'active';

CREATE UNIQUE INDEX "friend_requests_one_pending_pair"
  ON "friend_requests" ("requester_account_id", "target_account_id")
  WHERE status = 'pending';

CREATE UNIQUE INDEX "friendships_one_active_pair"
  ON "friendships" (LEAST("account_a_id", "account_b_id"), GREATEST("account_a_id", "account_b_id"))
  WHERE status = 'active';

CREATE UNIQUE INDEX "account_blocks_direction_uniq"
  ON "account_blocks" ("blocker_account_id", "blocked_account_id");
```

- [ ] **Step 7: Run schema verification**

Run:

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/schema-contract.test.ts
pnpm --dir gateway/packages/api exec prisma validate
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git -C gateway add packages/api/prisma/schema.prisma packages/api/prisma/migrations/20260522100000_friend_link_shared_reminders/migration.sql packages/api/src/scheduling/schema-contract.test.ts
git -C gateway commit -m "feat: model friend links and shared reminders"
```

## Task 2: User Link Sessions And Friend Requests

**Files:**
- Modify: `gateway/packages/api/src/scheduling/types.ts`
- Modify: `gateway/packages/api/src/scheduling/user-link-service.ts`
- Modify: `gateway/packages/api/src/scheduling/user-link-service.test.ts`
- Modify: `gateway/packages/api/src/routes/public-user-link-routes.ts`
- Modify: `gateway/packages/api/src/routes/public-user-link-routes.test.ts`

- [ ] **Step 1: Write failing service tests**

Add these tests to `gateway/packages/api/src/scheduling/user-link-service.test.ts`:

```ts
it('opens a 30 day link session without notifying the target', async () => {
  const now = new Date('2026-05-22T00:00:00.000Z');
  vi.setSystemTime(now);
  const client = fakeUserLinkClient({
    userLink: { id: 'ul_1', code: 'abc', status: 'active', providerAccountId: 'acct_a' },
    customer: { id: 'acct_a', displayName: 'A', tagline: null, avatarUrl: null },
  });

  const result = await openLinkSession(client as never, { code: 'abc' });

  expect(result.targetAccountId).toBe('acct_a');
  expect(result.expiresAt).toBe('2026-06-21T00:00:00.000Z');
  expect(client.productNotification.create).not.toHaveBeenCalled();
});

it('creates a pending friend request when an authenticated visitor claims a link session', async () => {
  const client = fakeUserLinkClient({
    linkSession: {
      id: 'ls_1',
      providerAccountId: 'acct_a',
      consumerAccountId: null,
      status: 'opened',
      expiresAt: new Date('2026-06-21T00:00:00.000Z'),
    },
  });

  const result = await sendFriendRequestFromLinkSession(client as never, {
    token: 'session-token',
    requesterAccountId: 'acct_b',
    message: 'Let us connect',
    idempotencyKey: 'friend:req:1',
  });

  expect(result.status).toBe('pending');
  expect(client.friendRequest.create).toHaveBeenCalledWith({
    data: expect.objectContaining({
      requesterAccountId: 'acct_b',
      targetAccountId: 'acct_a',
      linkSessionId: 'ls_1',
      status: 'pending',
    }),
  });
  expect(client.productNotification.create).toHaveBeenCalledWith({
    data: expect.objectContaining({
      recipientAccountId: 'acct_a',
      kind: 'friend_request',
    }),
  });
});

it('rejects self-claiming a user link session', async () => {
  const client = fakeUserLinkClient({
    linkSession: {
      id: 'ls_1',
      providerAccountId: 'acct_a',
      consumerAccountId: null,
      status: 'opened',
      expiresAt: new Date('2026-06-21T00:00:00.000Z'),
    },
  });

  await expect(
    sendFriendRequestFromLinkSession(client as never, {
      token: 'session-token',
      requesterAccountId: 'acct_a',
      message: null,
      idempotencyKey: 'friend:req:self',
    }),
  ).rejects.toThrow('cannot_friend_self');
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/user-link-service.test.ts
```

Expected: FAIL because `sendFriendRequestFromLinkSession` and `productNotification` are not wired.

- [ ] **Step 3: Update scheduling types**

Replace appointment-oriented content in `gateway/packages/api/src/scheduling/types.ts` with:

```ts
export type UserLinkStatus = 'active' | 'disabled';
export type LinkSessionStatus = 'opened' | 'claimed' | 'abandoned';
export type FriendRequestStatus = 'pending' | 'accepted' | 'rejected' | 'cancelled';
export type FriendshipStatus = 'active' | 'removed';
export type SharedReminderRequestStatus =
  | 'pending_invitee_confirmation'
  | 'accepted'
  | 'rejected'
  | 'expired'
  | 'cancelled'
  | 'invalidated';
export type SharedReminderProjectionRole = 'requester' | 'invitee';

export interface SchedulingErrorBody {
  ok: false;
  error:
    | 'invalid_body'
    | 'invalid_user_link'
    | 'invalid_link_session'
    | 'link_session_expired'
    | 'cannot_friend_self'
    | 'friend_request_blocked'
    | 'friend_request_not_found'
    | 'friendship_required'
    | 'friendship_not_found'
    | 'shared_reminder_not_found'
    | 'shared_reminder_not_pending'
    | 'shared_reminder_due'
    | 'reminder_projection_failed'
    | 'bridge_delivery_failed'
    | 'not_allowed';
}
```

- [ ] **Step 4: Update link-session TTL and friend-request creation**

In `gateway/packages/api/src/scheduling/user-link-service.ts`, set:

```ts
const LINK_SESSION_TTL_MS = 30 * 24 * 60 * 60 * 1000;
```

Add client capabilities:

```ts
friendRequest: {
  findFirst(args: { where: Record<string, unknown> }): Promise<Record<string, unknown> | null>;
  create(args: { data: Record<string, unknown> }): Promise<Record<string, unknown>>;
};
accountBlock: {
  findFirst(args: { where: Record<string, unknown> }): Promise<Record<string, unknown> | null>;
};
productNotification: {
  create(args: { data: Record<string, unknown> }): Promise<Record<string, unknown>>;
};
```

Add this exported function:

```ts
export async function sendFriendRequestFromLinkSession(
  client: UserLinkClient,
  input: {
    token: string;
    requesterAccountId: string;
    message: string | null;
    idempotencyKey: string;
  },
): Promise<Record<string, unknown>> {
  const requesterAccountId = nonEmpty(input.requesterAccountId, 'invalid_account');
  const session = await client.linkSession.findUnique({
    where: { tokenHash: tokenHash(input.token) },
  });
  if (!session || session.status !== 'opened') {
    throw new Error('invalid_link_session');
  }
  if (new Date(session.expiresAt).getTime() <= Date.now()) {
    throw new Error('link_session_expired');
  }
  if (session.providerAccountId === requesterAccountId) {
    throw new Error('cannot_friend_self');
  }
  const block = await client.accountBlock.findFirst({
    where: {
      blockerAccountId: session.providerAccountId,
      blockedAccountId: requesterAccountId,
    },
  });
  if (block) {
    throw new Error('friend_request_blocked');
  }
  const existing = await client.friendRequest.findFirst({
    where: {
      requesterAccountId,
      targetAccountId: session.providerAccountId,
      status: 'pending',
    },
  });
  if (existing) {
    return existing;
  }
  const request = await client.friendRequest.create({
    data: {
      requesterAccountId,
      targetAccountId: session.providerAccountId,
      linkSessionId: session.id,
      message: input.message,
      idempotencyKey: input.idempotencyKey,
      status: 'pending',
    },
  });
  await client.linkSession.updateMany({
    where: { id: session.id, status: 'opened' },
    data: {
      status: 'claimed',
      consumerAccountId: requesterAccountId,
      claimedAt: new Date(),
    },
  });
  await client.productNotification.create({
    data: {
      friendRequestId: request['id'],
      recipientAccountId: session.providerAccountId,
      idempotencyKey: `friend-request:${request['id']}:target`,
      kind: 'friend_request',
      payload: {
        text: '你有一个新的好友请求，请确认或拒绝。',
        metadata: {
          request_id: request['id'],
          request_type: 'friend_request',
          actor_account_id: requesterAccountId,
          allowed_actions: ['accept', 'reject'],
        },
      },
      status: 'pending_delivery',
    },
  });
  return request;
}
```

- [ ] **Step 5: Update public routes**

In `gateway/packages/api/src/routes/public-user-link-routes.ts`, replace the link-session claim route with a friend-request route:

```ts
publicLinkSessionRouter.post('/:token/friend-requests', async (c) => {
  const session = readCustomerSession(c);
  if (!session) {
    return c.json({ ok: false, error: 'unauthorized' }, 401);
  }
  const body = await readJsonObject(c);
  if (!body) {
    return c.json({ ok: false, error: 'invalid_body' }, 400);
  }
  try {
    const result = await sendFriendRequestFromLinkSession(db as never, {
      token: c.req.param('token'),
      requesterAccountId: session.customerId,
      message: typeof body['message'] === 'string' ? body['message'] : null,
      idempotencyKey: requestIdempotencyKey(body, 'friend-request', session.customerId, c.req.param('token')),
    });
    return c.json({ ok: true, data: result }, 201);
  } catch (error) {
    return c.json({ ok: false, error: errorMessage(error, 'friend_request_failed') }, 400);
  }
});
```

- [ ] **Step 6: Run route and service tests**

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/user-link-service.test.ts src/routes/public-user-link-routes.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git -C gateway add packages/api/src/scheduling/types.ts packages/api/src/scheduling/user-link-service.ts packages/api/src/scheduling/user-link-service.test.ts packages/api/src/routes/public-user-link-routes.ts packages/api/src/routes/public-user-link-routes.test.ts
git -C gateway commit -m "feat: create friend requests from user links"
```

## Task 3: Friendships, Blocks, And Customer Routes

**Files:**
- Create: `gateway/packages/api/src/scheduling/friendship-service.ts`
- Create: `gateway/packages/api/src/scheduling/friendship-service.test.ts`
- Modify: `gateway/packages/api/src/routes/customer-scheduling-routes.ts`
- Modify: `gateway/packages/api/src/routes/customer-scheduling-routes.test.ts`
- Delete: `gateway/packages/api/src/scheduling/service-link-service.ts`
- Delete: `gateway/packages/api/src/scheduling/availability-service.ts`

- [ ] **Step 1: Write failing friendship service tests**

Create `gateway/packages/api/src/scheduling/friendship-service.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import {
  acceptFriendRequest,
  blockAccount,
  rejectFriendRequest,
  removeFriendship,
} from './friendship-service.js';

describe('friendship service', () => {
  it('accepts a pending friend request and creates an active friendship', async () => {
    const client = fakeFriendshipClient({
      friendRequest: {
        id: 'fr_1',
        requesterAccountId: 'acct_b',
        targetAccountId: 'acct_a',
        status: 'pending',
      },
    });

    const result = await acceptFriendRequest(client as never, {
      actorAccountId: 'acct_a',
      requestId: 'fr_1',
      idempotencyKey: 'accept-fr-1',
    });

    expect(result.status).toBe('active');
    expect(client.friendRequest.updateMany).toHaveBeenCalledWith({
      where: { id: 'fr_1', targetAccountId: 'acct_a', status: 'pending' },
      data: { status: 'accepted', resolvedAt: expect.any(Date) },
    });
    expect(client.friendship.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        accountAId: 'acct_a',
        accountBId: 'acct_b',
        friendRequestId: 'fr_1',
        status: 'active',
      }),
    });
  });

  it('rejects a pending request without creating a friendship', async () => {
    const client = fakeFriendshipClient({
      friendRequest: {
        id: 'fr_1',
        requesterAccountId: 'acct_b',
        targetAccountId: 'acct_a',
        status: 'pending',
      },
    });

    await rejectFriendRequest(client as never, {
      actorAccountId: 'acct_a',
      requestId: 'fr_1',
      idempotencyKey: 'reject-fr-1',
    });

    expect(client.friendship.create).not.toHaveBeenCalled();
    expect(client.friendRequest.updateMany).toHaveBeenCalledWith({
      where: { id: 'fr_1', targetAccountId: 'acct_a', status: 'pending' },
      data: { status: 'rejected', resolvedAt: expect.any(Date) },
    });
  });

  it('blocking an account removes active friendship and invalidates pending shared reminders', async () => {
    const client = fakeFriendshipClient({
      friendship: { id: 'fs_1', accountAId: 'acct_a', accountBId: 'acct_b', status: 'active' },
    });

    await blockAccount(client as never, {
      blockerAccountId: 'acct_a',
      blockedAccountId: 'acct_b',
    });

    expect(client.accountBlock.create).toHaveBeenCalledWith({
      data: { blockerAccountId: 'acct_a', blockedAccountId: 'acct_b' },
    });
    expect(client.friendship.updateMany).toHaveBeenCalledWith({
      where: expect.objectContaining({ id: 'fs_1', status: 'active' }),
      data: { status: 'removed', removedAt: expect.any(Date) },
    });
    expect(client.sharedReminderRequest.updateMany).toHaveBeenCalledWith({
      where: expect.objectContaining({ status: 'pending_invitee_confirmation' }),
      data: { status: 'invalidated', resolvedAt: expect.any(Date) },
    });
  });

  it('removing a friendship does not cancel already accepted shared reminders', async () => {
    const client = fakeFriendshipClient({
      friendship: { id: 'fs_1', accountAId: 'acct_a', accountBId: 'acct_b', status: 'active' },
    });

    await removeFriendship(client as never, {
      actorAccountId: 'acct_a',
      friendshipId: 'fs_1',
    });

    expect(client.sharedReminderRequest.updateMany).toHaveBeenCalledWith({
      where: { friendshipId: 'fs_1', status: 'pending_invitee_confirmation' },
      data: { status: 'invalidated', resolvedAt: expect.any(Date) },
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/friendship-service.test.ts
```

Expected: FAIL because `friendship-service.ts` does not exist.

- [ ] **Step 3: Implement friendship service**

Create `gateway/packages/api/src/scheduling/friendship-service.ts` with these exports:

```ts
function canonicalPair(a: string, b: string): { accountAId: string; accountBId: string } {
  return a < b ? { accountAId: a, accountBId: b } : { accountAId: b, accountBId: a };
}

export async function acceptFriendRequest(client: FriendshipClient, input: {
  actorAccountId: string;
  requestId: string;
  idempotencyKey: string;
}): Promise<Record<string, unknown>> {
  const request = await client.friendRequest.findFirst({
    where: { id: input.requestId, targetAccountId: input.actorAccountId, status: 'pending' },
  });
  if (!request) throw new Error('friend_request_not_found');
  const pair = canonicalPair(request.requesterAccountId, request.targetAccountId);
  const friendship = await client.friendship.create({
    data: { ...pair, friendRequestId: request.id, status: 'active' },
  });
  await client.friendRequest.updateMany({
    where: { id: request.id, targetAccountId: input.actorAccountId, status: 'pending' },
    data: { status: 'accepted', resolvedAt: new Date() },
  });
  await client.productNotification.create({
    data: {
      friendRequestId: request.id,
      recipientAccountId: request.requesterAccountId,
      idempotencyKey: `friend-request:${request.id}:accepted`,
      kind: 'friend_request_accepted',
      payload: {
        text: '好友请求已通过。',
        metadata: { request_id: request.id, request_type: 'friend_request' },
      },
      status: 'pending_delivery',
    },
  });
  return friendship;
}

export async function rejectFriendRequest(client: FriendshipClient, input: {
  actorAccountId: string;
  requestId: string;
  idempotencyKey: string;
}): Promise<{ id: string; status: 'rejected' }> {
  const updated = await client.friendRequest.updateMany({
    where: { id: input.requestId, targetAccountId: input.actorAccountId, status: 'pending' },
    data: { status: 'rejected', resolvedAt: new Date() },
  });
  if (updated.count !== 1) throw new Error('friend_request_not_found');
  return { id: input.requestId, status: 'rejected' };
}
```

Add `cancelFriendRequest`, `listFriendRequests`, `listFriends`, `removeFriendship`, `blockAccount`, and `unblockAccount` in the same file. Use the same guard pattern: validate actor ownership, write one transition, enqueue one notification when the counterparty needs to know.

- [ ] **Step 4: Update customer routes**

In `gateway/packages/api/src/routes/customer-scheduling-routes.ts`, remove imports from `availability-service`, `appointment-service`, and `service-link-service`. Add routes that call the friendship service:

```ts
customerSchedulingRouter.get('/friend-requests', async (c) => {
  const session = requireCustomerSession(c);
  const result = await listFriendRequests(db as never, { accountId: session.customerId });
  return c.json({ ok: true, data: result });
});

customerSchedulingRouter.post('/friend-requests/:id/accept', async (c) => {
  const session = requireCustomerSession(c);
  const requestId = c.req.param('id');
  const result = await acceptFriendRequest(db as never, {
    actorAccountId: session.customerId,
    requestId,
    idempotencyKey: `customer:${session.customerId}:friend-request:${requestId}:accept`,
  });
  return c.json({ ok: true, data: result });
});

customerSchedulingRouter.post('/friend-requests/:id/reject', async (c) => {
  const session = requireCustomerSession(c);
  const requestId = c.req.param('id');
  const result = await rejectFriendRequest(db as never, {
    actorAccountId: session.customerId,
    requestId,
    idempotencyKey: `customer:${session.customerId}:friend-request:${requestId}:reject`,
  });
  return c.json({ ok: true, data: result });
});
```

- [ ] **Step 5: Run route and service tests**

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/friendship-service.test.ts src/routes/customer-scheduling-routes.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git -C gateway add packages/api/src/scheduling/friendship-service.ts packages/api/src/scheduling/friendship-service.test.ts packages/api/src/routes/customer-scheduling-routes.ts packages/api/src/routes/customer-scheduling-routes.test.ts
git -C gateway rm packages/api/src/scheduling/service-link-service.ts packages/api/src/scheduling/availability-service.ts
git -C gateway commit -m "feat: add friendship and block transitions"
```

## Task 4: Shared Reminder Requests And Projections

**Files:**
- Create: `gateway/packages/api/src/scheduling/shared-reminder-service.ts`
- Create: `gateway/packages/api/src/scheduling/shared-reminder-service.test.ts`
- Modify: `gateway/packages/api/src/lib/reminder-runtime-client.ts`
- Modify: `gateway/packages/api/src/lib/reminder-runtime-client.test.ts`
- Delete: `gateway/packages/api/src/scheduling/appointment-service.ts`
- Delete: `gateway/packages/api/src/scheduling/time.ts`

- [ ] **Step 1: Write failing shared-reminder tests**

Create `gateway/packages/api/src/scheduling/shared-reminder-service.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
  acceptSharedReminder,
  cancelSharedReminder,
  createSharedReminder,
  rejectSharedReminder,
} from './shared-reminder-service.js';

describe('shared reminder service', () => {
  it('creates requester projection immediately and notifies invitee', async () => {
    const client = fakeSharedReminderClient({
      friendship: { id: 'fs_1', accountAId: 'acct_a', accountBId: 'acct_b', status: 'active' },
    });
    const reminderRuntime = fakeReminderRuntime({
      create: { ok: true, data: { id: 'rem_req_1' } },
    });

    const result = await createSharedReminder(client as never, reminderRuntime, {
      requesterAccountId: 'acct_b',
      inviteeAccountId: 'acct_a',
      title: 'meeting',
      fireAt: '2026-05-22T07:00:00.000Z',
      timezone: 'Asia/Shanghai',
      idempotencyKey: 'shared:1',
    });

    expect(result.status).toBe('pending_invitee_confirmation');
    expect(reminderRuntime.createRuntimeReminder).toHaveBeenCalledWith(expect.objectContaining({
      customerId: 'acct_b',
      title: 'meeting',
      metadata: expect.objectContaining({
        projection_role: 'requester',
        counterparty_account_id: 'acct_a',
      }),
    }));
    expect(client.productNotification.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        recipientAccountId: 'acct_a',
        kind: 'shared_reminder_request',
      }),
    });
  });

  it('cancels the request when requester projection creation fails', async () => {
    const client = fakeSharedReminderClient({
      friendship: { id: 'fs_1', accountAId: 'acct_a', accountBId: 'acct_b', status: 'active' },
    });
    const reminderRuntime = fakeReminderRuntime({
      create: { ok: false, error: 'reminder_bridge_transport_failed' },
    });

    await expect(createSharedReminder(client as never, reminderRuntime, {
      requesterAccountId: 'acct_b',
      inviteeAccountId: 'acct_a',
      title: 'meeting',
      fireAt: '2026-05-22T07:00:00.000Z',
      timezone: 'Asia/Shanghai',
      idempotencyKey: 'shared:2',
    })).rejects.toThrow('reminder_projection_failed');

    expect(client.sharedReminderRequest.updateMany).toHaveBeenCalledWith({
      where: expect.objectContaining({ id: 'srr_1' }),
      data: { status: 'cancelled', resolvedAt: expect.any(Date) },
    });
  });

  it('accepts before fire time and creates invitee projection', async () => {
    const client = fakeSharedReminderClient({
      sharedReminderRequest: {
        id: 'srr_1',
        requesterAccountId: 'acct_b',
        inviteeAccountId: 'acct_a',
        title: 'meeting',
        fireAt: new Date('2026-05-22T07:00:00.000Z'),
        timezone: 'Asia/Shanghai',
        status: 'pending_invitee_confirmation',
      },
    });
    const reminderRuntime = fakeReminderRuntime({
      create: { ok: true, data: { id: 'rem_inv_1' } },
    });

    const result = await acceptSharedReminder(client as never, reminderRuntime, {
      actorAccountId: 'acct_a',
      requestId: 'srr_1',
      now: new Date('2026-05-22T06:00:00.000Z'),
      idempotencyKey: 'accept-srr-1',
    });

    expect(result.status).toBe('accepted');
    expect(reminderRuntime.createRuntimeReminder).toHaveBeenCalledWith(expect.objectContaining({
      customerId: 'acct_a',
      metadata: expect.objectContaining({ projection_role: 'invitee' }),
    }));
  });

  it('rejecting before fire time cancels requester projection', async () => {
    const client = fakeSharedReminderClient({
      sharedReminderRequest: {
        id: 'srr_1',
        requesterAccountId: 'acct_b',
        inviteeAccountId: 'acct_a',
        requesterReminderId: 'rem_req_1',
        fireAt: new Date('2026-05-22T07:00:00.000Z'),
        status: 'pending_invitee_confirmation',
      },
    });
    const reminderRuntime = fakeReminderRuntime({
      cancel: { ok: true, data: { id: 'rem_req_1' } },
    });

    await rejectSharedReminder(client as never, reminderRuntime, {
      actorAccountId: 'acct_a',
      requestId: 'srr_1',
      now: new Date('2026-05-22T06:00:00.000Z'),
      idempotencyKey: 'reject-srr-1',
    });

    expect(reminderRuntime.cancelRuntimeReminder).toHaveBeenCalledWith({
      customerId: 'acct_b',
      reminderId: 'rem_req_1',
    });
  });

  it('accepting after fire time marks the request expired and creates no invitee projection', async () => {
    const client = fakeSharedReminderClient({
      sharedReminderRequest: {
        id: 'srr_1',
        requesterAccountId: 'acct_b',
        inviteeAccountId: 'acct_a',
        fireAt: new Date('2026-05-22T07:00:00.000Z'),
        status: 'pending_invitee_confirmation',
      },
    });
    const reminderRuntime = fakeReminderRuntime({});

    await expect(acceptSharedReminder(client as never, reminderRuntime, {
      actorAccountId: 'acct_a',
      requestId: 'srr_1',
      now: new Date('2026-05-22T07:01:00.000Z'),
      idempotencyKey: 'accept-late-srr-1',
    })).rejects.toThrow('shared_reminder_due');

    expect(reminderRuntime.createRuntimeReminder).not.toHaveBeenCalled();
    expect(client.sharedReminderRequest.updateMany).toHaveBeenCalledWith({
      where: { id: 'srr_1', status: 'pending_invitee_confirmation' },
      data: { status: 'expired', resolvedAt: expect.any(Date) },
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/shared-reminder-service.test.ts
```

Expected: FAIL because `shared-reminder-service.ts` does not exist.

- [ ] **Step 3: Pass projection metadata through Reminder Runtime client**

Modify `gateway/packages/api/src/lib/reminder-runtime-client.ts`:

```ts
export interface CreateReminderInput {
  customerId: string;
  title: string;
  localDate: string;
  localTime: string;
  timezone: string;
  rrule?: string | null;
  businessConversationKey?: string | null;
  gatewayConversationId?: string | null;
  metadata?: Record<string, unknown>;
}
```

In `createRuntimeReminder`, add metadata to the body:

```ts
...(input.metadata ? { metadata: input.metadata } : {}),
```

- [ ] **Step 4: Implement shared-reminder service**

Create `gateway/packages/api/src/scheduling/shared-reminder-service.ts` with these core transitions:

```ts
function splitInstant(fireAt: string): { localDate: string; localTime: string } {
  const value = new Date(fireAt);
  if (Number.isNaN(value.getTime())) throw new Error('invalid_body');
  return {
    localDate: value.toISOString().slice(0, 10),
    localTime: value.toISOString().slice(11, 16),
  };
}

export async function createSharedReminder(
  client: SharedReminderClient,
  reminderRuntime: ReminderRuntimePort,
  input: {
    requesterAccountId: string;
    inviteeAccountId: string;
    title: string;
    fireAt: string;
    timezone: string;
    idempotencyKey: string;
  },
): Promise<Record<string, unknown>> {
  const friendship = await findActiveFriendship(client, input.requesterAccountId, input.inviteeAccountId);
  if (!friendship) throw new Error('friendship_required');
  const request = await client.sharedReminderRequest.create({
    data: {
      requesterAccountId: input.requesterAccountId,
      inviteeAccountId: input.inviteeAccountId,
      friendshipId: friendship.id,
      title: input.title,
      fireAt: new Date(input.fireAt),
      timezone: input.timezone,
      idempotencyKey: input.idempotencyKey,
      status: 'pending_invitee_confirmation',
    },
  });
  const when = splitInstant(input.fireAt);
  const projection = await reminderRuntime.createRuntimeReminder({
    customerId: input.requesterAccountId,
    title: input.title,
    localDate: when.localDate,
    localTime: when.localTime,
    timezone: input.timezone,
    metadata: {
      shared_reminder_request_id: request['id'],
      projection_role: 'requester',
      counterparty_account_id: input.inviteeAccountId,
    },
  });
  if (!projection.ok) {
    await client.sharedReminderRequest.updateMany({
      where: { id: request['id'] },
      data: { status: 'cancelled', resolvedAt: new Date() },
    });
    throw new Error('reminder_projection_failed');
  }
  const runtimeReminderId = String(projection.data['id']);
  await client.reminderProjection.create({
    data: {
      sharedReminderRequestId: request['id'],
      ownerAccountId: input.requesterAccountId,
      runtimeReminderId,
      role: 'requester',
    },
  });
  await client.sharedReminderRequest.updateMany({
    where: { id: request['id'], status: 'pending_invitee_confirmation' },
    data: { requesterReminderId: runtimeReminderId },
  });
  await enqueueSharedReminderNotification(client, {
    requestId: String(request['id']),
    recipientAccountId: input.inviteeAccountId,
    kind: 'shared_reminder_request',
    text: '你有一个共享提醒请求，请确认或拒绝。',
    allowedActions: ['accept', 'reject'],
  });
  return { ...request, requesterReminderId: runtimeReminderId };
}
```

Add `acceptSharedReminder`, `rejectSharedReminder`, `cancelSharedReminder`, `expireDueSharedReminders`, and `listPendingSharedReminders` in the same file. The late-accept branch must update pending requests to `expired` and must not call `createRuntimeReminder`.

- [ ] **Step 5: Run shared-reminder tests**

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/shared-reminder-service.test.ts src/lib/reminder-runtime-client.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git -C gateway add packages/api/src/scheduling/shared-reminder-service.ts packages/api/src/scheduling/shared-reminder-service.test.ts packages/api/src/lib/reminder-runtime-client.ts packages/api/src/lib/reminder-runtime-client.test.ts
git -C gateway rm packages/api/src/scheduling/appointment-service.ts packages/api/src/scheduling/time.ts
git -C gateway commit -m "feat: project shared reminders into personal reminders"
```

## Task 5: Product Notifications And Internal Routes

**Files:**
- Modify: `gateway/packages/api/src/scheduling/notification-service.ts`
- Modify: `gateway/packages/api/src/scheduling/notification-service.test.ts`
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`

- [ ] **Step 1: Write failing notification tests**

Replace appointment-specific tests in `gateway/packages/api/src/scheduling/notification-service.test.ts` with:

```ts
it('delivers product notification metadata to the bridge', async () => {
  const client = fakeNotificationClient();
  fetchMock.mockResponseOnce(JSON.stringify({ ok: true }));

  await enqueueProductNotification(client as never, {
    requestId: 'fr_1',
    requestType: 'friend_request',
    recipientAccountId: 'acct_a',
    idempotencyKey: 'friend-request:fr_1:target',
    kind: 'friend_request',
    text: '你有一个新的好友请求，请确认或拒绝。',
    metadata: {
      request_id: 'fr_1',
      request_type: 'friend_request',
      allowed_actions: ['accept', 'reject'],
    },
  });

  expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8090/bridge/inbound', expect.objectContaining({
    method: 'POST',
    body: JSON.stringify({
      customer_id: 'acct_a',
      inbound_event_id: 'friend-request:fr_1:target',
      text: '你有一个新的好友请求，请确认或拒绝。',
      timestamp: expect.any(Number),
      message_type: 'product_notification',
      product_notification: {
        request_id: 'fr_1',
        request_type: 'friend_request',
        allowed_actions: ['accept', 'reject'],
        kind: 'friend_request',
      },
    }),
  }));
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/notification-service.test.ts
```

Expected: FAIL because the service still uses appointment-specific fields and `scheduling_notification`.

- [ ] **Step 3: Rename notification service contract**

In `gateway/packages/api/src/scheduling/notification-service.ts`, rename exports and table access:

```ts
export interface EnqueueProductNotificationInput {
  requestId: string;
  requestType: 'friend_request' | 'shared_reminder_request';
  recipientAccountId: string;
  idempotencyKey: string;
  kind: string;
  text: string;
  metadata: Record<string, unknown>;
}
```

In delivery, send:

```ts
message_type: 'product_notification',
product_notification: {
  ...(payload.metadata || {}),
  kind: notification.kind,
},
```

Use `client.productNotification` instead of `client.schedulingNotification`.

- [ ] **Step 4: Update internal tool dispatch**

In `gateway/packages/api/src/routes/internal-scheduling-routes.ts`, remove appointment/bookable-window dispatch branches and add:

```ts
if (toolName === 'accept_friend_request') {
  const result = await acceptFriendRequest(db as never, {
    actorAccountId: customerId,
    requestId: stringField(body, 'request_id'),
    idempotencyKey: stringField(body, 'idempotency_key'),
  });
  return c.json({ ok: true, data: result });
}
if (toolName === 'create_shared_reminder') {
  const result = await createSharedReminder(db as never, reminderRuntimePort, {
    requesterAccountId: customerId,
    inviteeAccountId: stringField(body, 'invitee_account_id'),
    title: stringField(body, 'title'),
    fireAt: stringField(body, 'fire_at'),
    timezone: stringField(body, 'timezone', 'UTC'),
    idempotencyKey: stringField(body, 'idempotency_key'),
  });
  return c.json({ ok: true, data: result }, 201);
}
if (toolName === 'accept_shared_reminder') {
  const result = await acceptSharedReminder(db as never, reminderRuntimePort, {
    actorAccountId: customerId,
    requestId: stringField(body, 'request_id'),
    now: new Date(),
    idempotencyKey: stringField(body, 'idempotency_key'),
  });
  return c.json({ ok: true, data: result });
}
```

Add branches for the full tool list in the Route Map.

- [ ] **Step 5: Run internal route tests**

```bash
pnpm --dir gateway/packages/api test -- src/scheduling/notification-service.test.ts src/routes/internal-scheduling-routes.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git -C gateway add packages/api/src/scheduling/notification-service.ts packages/api/src/scheduling/notification-service.test.ts packages/api/src/routes/internal-scheduling-routes.ts packages/api/src/routes/internal-scheduling-routes.test.ts
git -C gateway commit -m "feat: route friend and shared reminder tools"
```

## Task 6: Worker Runtime Scheduling Tools

**Files:**
- Modify: `connector/clawscale_bridge/message_gateway.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_message_gateway.py`
- Modify: `agent/agno_agent/capabilities/scheduling.py`
- Modify: `agent/agno_agent/runtime/scheduling_types.py`
- Modify: `agent/agno_agent/runtime/execution_agents.py`
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
- Modify: `agent/agno_agent/runtime/chat_response_instructions.py`
- Modify tests under `tests/unit/agent/`

- [ ] **Step 1: Write failing Bridge metadata test**

Replace the scheduling notification test in `tests/unit/connector/clawscale_bridge/test_message_gateway.py` with:

```python
def test_product_notification_metadata_is_preserved():
    gateway = MessageGateway(
        mongo_client=FakeMongoClient(),
        redis_client=None,
        trigger_stream_key="triggers",
    )

    doc = gateway._build_input_document(
        {
            "customer_id": "acct_a",
            "text": "你有一个新的好友请求，请确认或拒绝。",
            "message_type": "product_notification",
            "product_notification": {
                "request_id": "fr_1",
                "request_type": "friend_request",
                "allowed_actions": ["accept", "reject"],
            },
        }
    )

    assert doc["metadata"]["message_type"] == "product_notification"
    assert doc["metadata"]["product_notification"] == {
        "request_id": "fr_1",
        "request_type": "friend_request",
        "allowed_actions": ["accept", "reject"],
    }
```

- [ ] **Step 2: Write failing worker tool-name tests**

Update `tests/unit/agent/test_scheduling_capability.py`:

```python
def test_create_shared_reminder_forwards_required_args():
    from agent.agno_agent.capabilities.scheduling import SchedulingCapabilityPort

    captured = {}

    def handler(tool_name, payload):
        captured["tool_name"] = tool_name
        captured["payload"] = payload
        return {"ok": True, "data": {"id": "srr_1", "status": "pending_invitee_confirmation"}}

    port = SchedulingCapabilityPort(tool_name="create_shared_reminder", handler=handler)
    result = port.run(
        "Help me and A remember the meeting",
        run_context=_run_context(user_id="acct_b"),
        args={
            "invitee_account_id": "acct_a",
            "title": "meeting",
            "fire_at": "2026-05-22T07:00:00.000Z",
            "timezone": "Asia/Shanghai",
            "idempotency_key": "shared-1",
        },
    )

    assert result.ok is True
    assert captured["tool_name"] == "create_shared_reminder"
    assert captured["payload"]["customer_id"] == "acct_b"
    assert captured["payload"]["invitee_account_id"] == "acct_a"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_message_gateway.py::test_product_notification_metadata_is_preserved tests/unit/agent/test_scheduling_capability.py::test_create_shared_reminder_forwards_required_args -q
```

Expected: FAIL because old names are still in use.

- [ ] **Step 4: Preserve product notification metadata**

In `connector/clawscale_bridge/message_gateway.py`, replace the old scheduling metadata block with:

```python
product_notification = inbound.get("product_notification")
if isinstance(product_notification, dict):
    metadata["product_notification"] = product_notification
```

Keep the existing `message_type` metadata assignment so the worker can see `product_notification`.

- [ ] **Step 5: Replace scheduling tool names**

In `agent/agno_agent/capabilities/scheduling.py`, replace `SCHEDULING_TOOL_NAMES` with the list from the Route Map and replace visible summaries with:

```python
_DURABLE_WRITE_VISIBLE_SUMMARIES = {
    "reset_user_link": "已重置用户链接。",
    "disable_user_link": "已停用用户链接。",
    "accept_friend_request": "已通过好友请求。",
    "reject_friend_request": "已拒绝好友请求。",
    "cancel_friend_request": "已取消好友请求。",
    "remove_friendship": "已移除好友关系。",
    "block_account": "已屏蔽该用户。",
    "unblock_account": "已解除屏蔽。",
    "create_shared_reminder": "已提交共享提醒请求。",
    "accept_shared_reminder": "已接受共享提醒。",
    "reject_shared_reminder": "已拒绝共享提醒并取消你的提醒。",
    "cancel_shared_reminder": "已取消共享提醒请求。",
}
```

Set read-only tools to:

```python
_READ_ONLY_TOOL_NAMES = {
    "get_user_link",
    "list_friend_requests",
    "list_friends",
    "list_pending_shared_reminders",
}
```

- [ ] **Step 6: Update scheduling execution agent instructions**

In `agent/agno_agent/runtime/execution_agents.py`, set:

```python
_SCHEDULING_SYSTEM_PROMPT = (
    "You are the friend-link and shared-reminder execution worker. "
    "Call exactly one scheduling tool that matches the intent. "
    "Do not create shared reminder state unless the named person resolves to "
    "one active friend. Ask for clarification when the name is ambiguous. "
    "Ordinary personal reminders are not scheduling-domain work. "
    "Do not treat an iLink QR as a public user-link QR."
)
```

Update `_make_scheduling_tool_fn` arguments so shared-reminder tools can pass `invitee_account_id`, `title`, `fire_at`, `timezone`, `request_id`, `friendship_id`, `blocked_account_id`, and `idempotency_key`.

- [ ] **Step 7: Update response instructions**

In `agent/agno_agent/runtime/chat_response_instructions.py`, replace the old appointment policy with:

```python
- Use scheduling_domain(intent=...) only for explicit user-link, friend-request, friendship/block, or shared-reminder actions.
- Ordinary one-person reminders must use the Reminder Runtime path, not scheduling_domain.
- A shared reminder requires one active friend. If the named person is not an active friend, explain that the user must add them as a friend first.
- If the friend name is ambiguous, ask the user to choose one friend and do not call scheduling_domain.
- Do not treat an iLink QR as a public friend-link QR. iLink is only for the current account's personal-channel binding.
- Ask for confirmation before reset/disable user link, accept/reject/cancel requests, remove friendship, block, or unblock unless the current turn explicitly confirms the exact action.
```

- [ ] **Step 8: Run worker tests**

```bash
.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_message_gateway.py tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_scheduling_tools.py tests/unit/agent/test_execution_agents.py tests/unit/agent/test_chat_response_scheduling_instructions.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add connector/clawscale_bridge/message_gateway.py tests/unit/connector/clawscale_bridge/test_message_gateway.py agent/agno_agent/capabilities/scheduling.py agent/agno_agent/runtime/scheduling_types.py agent/agno_agent/runtime/execution_agents.py agent/agno_agent/runtime/agent_runtime.py agent/agno_agent/runtime/chat_response_instructions.py tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_scheduling_tools.py tests/unit/agent/test_execution_agents.py tests/unit/agent/test_chat_response_scheduling_instructions.py
git commit -m "feat: expose friend and shared reminder tools"
```

## Task 7: Gateway Web User-Link Flow

**Files:**
- Modify: `gateway/packages/shared/src/types/scheduling.ts`
- Modify: `gateway/packages/shared/src/index.ts`
- Modify: `gateway/packages/web/lib/user-link-api.ts`
- Modify: `gateway/packages/web/app/u/[code]/page.tsx`
- Modify: `gateway/packages/web/app/u/[code]/claim-handoff.tsx`
- Modify: `gateway/packages/web/app/u/[code]/page.test.tsx`
- Modify auth return-path tests under `gateway/packages/web/app/(customer)/auth/`

- [ ] **Step 1: Write failing page tests**

Update `gateway/packages/web/app/u/[code]/page.test.tsx`:

```tsx
it('renders a public profile and starts login with preserved link session', async () => {
  mockFetchUserLink.mockResolvedValue({
    ok: true,
    data: {
      code: 'abc',
      status: 'active',
      profile: { displayName: 'Coach A', tagline: 'Strength coach', avatarUrl: null },
    },
  });
  mockOpenLinkSession.mockResolvedValue({
    ok: true,
    data: {
      token: 'session-token',
      targetAccountId: 'acct_a',
      expiresAt: '2026-06-21T00:00:00.000Z',
      loginUrl: '/auth/login?next=%2Fu%2Fabc%3Flink_session%3Dsession-token',
      registerUrl: '/auth/register?next=%2Fu%2Fabc%3Flink_session%3Dsession-token',
    },
  });

  render(await UserLinkPage({ params: Promise.resolve({ code: 'abc' }), searchParams: Promise.resolve({}) }));

  expect(screen.getByRole('heading', { name: 'Coach A' })).toBeInTheDocument();
  expect(screen.getByText('Strength coach')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Log in to add friend' })).toHaveAttribute(
    'href',
    '/auth/login?next=%2Fu%2Fabc%3Flink_session%3Dsession-token',
  );
});

it('renders the authenticated friend-request form for a preserved session', async () => {
  mockReadCustomerSession.mockResolvedValue({ customerId: 'acct_b' });
  mockFetchUserLink.mockResolvedValue({
    ok: true,
    data: {
      code: 'abc',
      status: 'active',
      profile: { displayName: 'Coach A', tagline: null, avatarUrl: null },
    },
  });

  render(await UserLinkPage({
    params: Promise.resolve({ code: 'abc' }),
    searchParams: Promise.resolve({ link_session: 'session-token' }),
  }));

  expect(screen.getByRole('button', { name: 'Send friend request' })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pnpm --dir gateway/packages/web test -- app/u/[code]/page.test.tsx
```

Expected: FAIL because the current page still uses claim/service-link copy.

- [ ] **Step 3: Update shared DTOs**

In `gateway/packages/shared/src/types/scheduling.ts`, export:

```ts
export interface PublicUserLinkResponse {
  code: string;
  status: 'active';
  profile: {
    displayName: string;
    tagline: string | null;
    avatarUrl: string | null;
  };
}

export interface PublicLinkSessionResponse {
  token: string;
  targetAccountId: string;
  expiresAt: string;
  loginUrl: string;
  registerUrl: string;
}

export interface FriendRequestResponse {
  id: string;
  status: 'pending' | 'accepted' | 'rejected' | 'cancelled';
}
```

- [ ] **Step 4: Update web API helpers**

In `gateway/packages/web/lib/user-link-api.ts`, expose:

```ts
export async function sendFriendRequest(input: {
  token: string;
  message: string;
}): Promise<{ ok: true; data: FriendRequestResponse } | { ok: false; error: string }> {
  return postCustomerJson(`/api/public/link-sessions/${encodeURIComponent(input.token)}/friend-requests`, {
    message: input.message,
  });
}
```

- [ ] **Step 5: Update public page copy and action**

In `gateway/packages/web/app/u/[code]/page.tsx`, make the primary states:

```tsx
{linkSession && !customerSession ? (
  <div className="actions">
    <a href={linkSession.loginUrl}>Log in to add friend</a>
    <a href={linkSession.registerUrl}>Create account to add friend</a>
  </div>
) : null}
{customerSession && linkSessionToken ? (
  <ClaimHandoff token={linkSessionToken} targetName={link.profile.displayName} />
) : null}
```

Keep the page focused on A's public profile and friend request. Do not mention appointments or bookable windows.

- [ ] **Step 6: Run web tests**

```bash
pnpm --dir gateway/packages/web test -- app/u/[code]/page.test.tsx app/u/[code]/qr/route.test.ts lib/user-link-api.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git -C gateway add packages/shared/src/types/scheduling.ts packages/shared/src/index.ts packages/web/lib/user-link-api.ts packages/web/app/u/[code]/page.tsx packages/web/app/u/[code]/claim-handoff.tsx packages/web/app/u/[code]/page.test.tsx packages/web/app/u/[code]/qr/route.test.ts packages/web/lib/user-link-api.test.ts
git -C gateway commit -m "feat: show friend-link public flow"
```

## Task 8: Docs, Surface Verification, And Final Commits

**Files:**
- Modify: `docs/product-specs/FEATURE_TREE.md`
- Modify: `docs/design-docs/data-retention-policy.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `tests/unit/test_data_retention_policy_consistency.py`

- [ ] **Step 1: Write failing repo docs consistency test**

Update `tests/unit/test_data_retention_policy_consistency.py` expected policy ids:

```python
EXPECTED_SCHEDULING_RETENTION_POLICIES = {
    "friend_link_session_retention",
    "disabled_user_link_retention",
    "friend_request_retention",
    "friendship_retention",
    "account_block_retention",
    "shared_reminder_request_retention",
    "product_notification_retention",
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/unit/test_data_retention_policy_consistency.py -q
```

Expected: FAIL because the retention policy doc still names appointment scheduling policies.

- [ ] **Step 3: Update feature tree**

In `docs/product-specs/FEATURE_TREE.md`, replace the `User Link Scheduling` section with:

```markdown
- Friend Link And Shared Reminders
  - public web entry: `gateway/packages/web/app/u/[code]/page.tsx`
  - public QR route: `gateway/packages/web/app/u/[code]/qr/route.ts`
  - public API: `gateway/packages/api/src/routes/public-user-link-routes.ts`
  - customer API: `gateway/packages/api/src/routes/customer-scheduling-routes.ts`
  - internal agent API: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
  - Gateway domain services: `gateway/packages/api/src/scheduling/`
  - Reminder Runtime projection client: `gateway/packages/api/src/lib/reminder-runtime-client.ts`
  - Worker agent tools: `agent/agno_agent/capabilities/scheduling.py`
```

- [ ] **Step 4: Update architecture**

In `docs/ARCHITECTURE.md`, replace the old scheduling tool list with:

```markdown
The runtime registers async tool wrappers (`reminder_intent`, `timezone`,
`calendar_import`, `url_context`, and the friend-link/shared-reminder tools:
`get_user_link`, `reset_user_link`, `disable_user_link`,
`list_friend_requests`, `accept_friend_request`, `reject_friend_request`,
`cancel_friend_request`, `list_friends`, `remove_friendship`, `block_account`,
`unblock_account`, `create_shared_reminder`,
`list_pending_shared_reminders`, `accept_shared_reminder`,
`reject_shared_reminder`, and `cancel_shared_reminder`) that capture typed
`CapabilityResult` objects for deterministic visible-output rules.
```

- [ ] **Step 5: Update retention policy**

In `docs/design-docs/data-retention-policy.md`, add rows for the ids in Step 1. Use 30 days for unclaimed link sessions, audit-retained disabled user links, account-lifetime friendships and blocks, and product-defined retention for shared reminder requests and notifications.

- [ ] **Step 6: Run diff-aware routing**

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: `suggest-verification` includes gateway, worker-runtime, bridge, and repo-OS surfaces. Expected `review-trigger` may request human review because this is a cross-boundary product-state migration.

- [ ] **Step 7: Run focused verification**

```bash
pnpm --dir gateway/packages/api test -- src/scheduling src/routes/public-user-link-routes.test.ts src/routes/customer-scheduling-routes.test.ts src/routes/internal-scheduling-routes.test.ts src/lib/reminder-runtime-client.test.ts
pnpm --dir gateway/packages/web test -- app/u/[code]/page.test.tsx app/u/[code]/qr/route.test.ts lib/user-link-api.test.ts
.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_message_gateway.py tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_scheduling_tools.py tests/unit/agent/test_execution_agents.py tests/unit/agent/test_chat_response_scheduling_instructions.py tests/unit/test_data_retention_policy_consistency.py -q
zsh scripts/check
```

Expected: PASS. If `review-trigger` asks for human review, record that as a required review gate rather than bypassing it.

- [ ] **Step 8: Commit root docs and parent gitlink**

```bash
git add docs/product-specs/FEATURE_TREE.md docs/design-docs/data-retention-policy.md docs/ARCHITECTURE.md tests/unit/test_data_retention_policy_consistency.py gateway
git commit -m "docs: align friend-link shared reminder surfaces"
```

## Self-Review

Spec coverage:

- Public user link and QR retrieval: Tasks 1, 2, and 7.
- Link-session context preservation with 30-day TTL: Task 2.
- Friend request confirmation, rejection, cancellation, friendship removal, and blocking: Task 3.
- Shared reminder request creation, requester projection, invitee acceptance/rejection, cancellation, due-before-accept expiry, and friendship invalidation: Task 4.
- Web and agent entry points calling the same Gateway transitions: Tasks 5, 6, and 7.
- Notification intent and Bridge metadata delivery: Tasks 5 and 6.
- Reminder Runtime as personal projection boundary: Task 4.
- Feature tree, architecture, and retention docs: Task 8.

Placeholder scan:

- No forbidden placeholder markers are present in task instructions.
- Every route, model, tool name, and verification command is named explicitly.

Type consistency:

- Tool names in the Route Map match Task 5 internal routes and Task 6 Python runtime changes.
- Shared reminder statuses match the design spec.
- `ProductNotification` replaces appointment-specific `SchedulingNotification`.
- `ReminderProjection.role` values match projection metadata roles.
