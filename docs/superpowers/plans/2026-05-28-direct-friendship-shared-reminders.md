# Direct Friendship Shared Reminders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace friend-request and shared-reminder confirmation workflows with direct active friendships and direct active shared reminders, then deploy and production-smoke the real-account happy paths.

**Architecture:** Keep Scheduling hosted in the Gateway API and keep shared reminders as a center fact table plus per-user Reminder Runtime projections. Remove pending request semantics instead of preserving compatibility routes, and use a non-rolling deployment window because schema and route names are destructively changed.

**Tech Stack:** TypeScript, Hono, Prisma/Postgres, Vitest, Next.js, Python agent runtime tests, existing deploy script, production real-user-flow smoke skill.

---

## File Structure

- Modify `gateway/packages/api/prisma/schema.prisma`: remove `FriendRequest`, remove request status enums, rename `SharedReminderRequest` model/table semantics to `SharedReminder`, add direct friendship notification relation.
- Create `gateway/packages/api/prisma/migrations/20260528120000_direct_friendship_shared_reminders/migration.sql`: destructive data/schema migration with conversion counts and account-block absence assertion.
- Modify `gateway/packages/api/src/scheduling/schema-contract.test.ts`: assert removed schema and new active schema.
- Modify `gateway/packages/api/src/scheduling/types.ts`: replace request statuses/roles with `SharedReminderStatus` and `SharedReminderProjectionRole = creator | receiver`.
- Modify `gateway/packages/api/src/scheduling/notification-service.ts` and test: support `friendship` and `shared_reminder` notification resources only.
- Modify `gateway/packages/api/src/scheduling/user-link-service.ts` and test: replace friend request creation with direct friendship creation from link session/code.
- Modify `gateway/packages/api/src/scheduling/friendship-service.ts` and test: keep list/remove friend, delete friend-request APIs, ensure removal no longer cancels shared reminders.
- Modify `gateway/packages/api/src/scheduling/shared-reminder-service.ts` and test: active-only create/list/cancel, receiver conflict checks, actor-neutral cancel.
- Modify `gateway/packages/api/src/scheduling/domain-contract.ts`, `runtime-contract-fixtures.ts`, and route tests: remove pending tools, add `create_friendship_by_user_link_code`.
- Delete or empty `gateway/packages/api/src/scheduling/focus-binding-service.ts` and test if no active caller remains; otherwise reduce it to no pending invitation behavior.
- Modify `gateway/packages/api/src/routes/public-user-link-routes.ts` and test: replace `/friend-requests` with `/friendships`.
- Modify `gateway/packages/api/src/routes/customer-scheduling-routes.ts` and test: remove friend-request and pending shared-reminder routes.
- Modify `gateway/packages/api/src/routes/internal-scheduling-routes.ts` and test: remove pending tools through the domain contract.
- Modify `gateway/packages/api/src/lib/route-message.ts` and test: route product notifications by `friendship_id` and `shared_reminder_id`.
- Modify `gateway/packages/shared/src/types/scheduling.ts`: replace `FriendRequestResponse` with `DirectFriendshipResponse` and active shared-reminder types.
- Modify `gateway/packages/web/lib/user-link-api.ts` and test: rename `sendFriendRequest` to `createFriendship`.
- Modify `gateway/packages/web/lib/customer-friends.ts` and test: remove friend-request helpers.
- Modify `gateway/packages/web/app/(customer)/account/friends/page.tsx` and test: remove pending panels/buttons and use direct friendship copy.
- Modify `agent/agno_agent/capabilities/scheduling.py`, `agent/agno_agent/runtime/agent_runtime.py`, `agent/agno_agent/runtime/semantic_interpreter.py`, `agent/agno_agent/runtime/execution_agents.py`, `agent/agno_agent/runtime/chat_response_instructions.py`, `agent/agno_agent/runtime/focus.py`, `agent/agno_agent/runtime/scheduling_types.py`: remove pending/accept/reject/block tools and rename direct friend-link tool.
- Modify affected Python tests under `tests/unit/agent/`.
- Modify `docs/product-specs/FEATURE_TREE.md`, `docs/ARCHITECTURE.md` if it describes old active behavior, and `.agents/skills/production-real-user-flow-smoke/SKILL.md`.

## Task 1: Schema And Migration Contract

**Files:**
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Create: `gateway/packages/api/prisma/migrations/20260528120000_direct_friendship_shared_reminders/migration.sql`
- Modify: `gateway/packages/api/src/scheduling/schema-contract.test.ts`
- Modify: `gateway/packages/api/src/scheduling/types.ts`

- [ ] **Step 1: Write failing schema contract tests**

Add tests that assert the active schema no longer exposes request/blocking models and does expose current shared-reminder/friendship notification names:

```ts
it('removes friend request and pending shared reminder schema contracts', () => {
  const schema = readSchema();
  expect(schema).not.toContain('model FriendRequest');
  expect(schema).not.toContain('enum FriendRequestStatus');
  expect(schema).not.toContain('SharedReminderRequestStatus');
  expect(schema).not.toContain('pending_invitee_confirmation');
  expect(schema).not.toContain('friend_request_id');
  expect(schema).not.toContain('shared_reminder_request_id');
  expect(schema).not.toContain('model AccountBlock');
});

it('defines direct friendship and active shared reminder notification relations', () => {
  const schema = readSchema();
  expect(schema).toContain('model SharedReminder');
  expect(schema).toContain('@@map("shared_reminders")');
  expect(schema).toContain('friendshipId');
  expect(schema).toContain('sharedReminderId');
  expect(schema).toContain('enum SharedReminderStatus');
  expect(schema).toContain('active');
  expect(schema).toContain('cancelled');
  expect(schema).toContain('invalidated');
});
```

- [ ] **Step 2: Run schema contract tests and verify failure**

Run: `cd gateway && pnpm --filter @clawscale/api test -- src/scheduling/schema-contract.test.ts`

Expected: FAIL because current schema still contains `FriendRequest`, `SharedReminderRequest`, and old request foreign keys.

- [ ] **Step 3: Update Prisma schema and local TS types**

Implement these schema changes:

```prisma
model Friendship {
  id                  String                @id @default(cuid())
  accountAId          String                @map("account_a_id")
  accountBId          String                @map("account_b_id")
  source              String?               @default("direct_link")
  sourceUserLinkId    String?               @map("source_user_link_id")
  sourceLinkSessionId String?               @map("source_link_session_id")
  status              FriendshipStatus      @default(active)
  removedAt           DateTime?             @map("removed_at")
  createdAt           DateTime              @default(now()) @map("created_at")
  updatedAt           DateTime              @updatedAt @map("updated_at")
  accountA            Customer              @relation("FriendshipAccountA", fields: [accountAId], references: [id], onDelete: Cascade)
  accountB            Customer              @relation("FriendshipAccountB", fields: [accountBId], references: [id], onDelete: Cascade)
  sharedReminders     SharedReminder[]
  notifications       ProductNotification[]
  @@unique([accountAId, accountBId])
  @@index([accountAId, status])
  @@index([accountBId, status])
  @@map("friendships")
}

model SharedReminder {
  id                 String                @id @default(cuid())
  creatorAccountId   String                @map("creator_account_id")
  receiverAccountId  String                @map("receiver_account_id")
  friendshipId       String                @map("friendship_id")
  title              String                @db.VarChar(200)
  fireAt             DateTime              @map("fire_at")
  timezone           String
  durationMinutes    Int?                  @map("duration_minutes")
  idempotencyKey     String?               @map("idempotency_key")
  status             SharedReminderStatus  @default(active)
  creatorReminderId  String                @map("creator_reminder_id")
  receiverReminderId String                @map("receiver_reminder_id")
  cancelledAt        DateTime?             @map("cancelled_at")
  invalidatedAt      DateTime?             @map("invalidated_at")
  createdAt          DateTime              @default(now()) @map("created_at")
  updatedAt          DateTime              @updatedAt @map("updated_at")
  creator            Customer              @relation("CreatorSharedReminders", fields: [creatorAccountId], references: [id], onDelete: Cascade)
  receiver           Customer              @relation("ReceiverSharedReminders", fields: [receiverAccountId], references: [id], onDelete: Cascade)
  friendship         Friendship            @relation(fields: [friendshipId], references: [id], onDelete: Restrict)
  events             SharedReminderEvent[]
  projections        ReminderProjection[]
  notifications      ProductNotification[]
  @@unique([creatorAccountId, receiverAccountId, idempotencyKey])
  @@index([creatorAccountId, status])
  @@index([receiverAccountId, status])
  @@index([fireAt, status])
  @@map("shared_reminders")
}
```

Also update `types.ts`:

```ts
export type SharedReminderStatus = 'active' | 'cancelled' | 'invalidated';
export type SharedReminderProjectionRole = 'creator' | 'receiver';
export type SharedReminderActorRole = 'creator' | 'receiver' | 'system';
```

- [ ] **Step 4: Write migration**

Create `migration.sql` with explicit comments and data-shape conversion. Use SQL that:

```sql
-- Convert legacy shared_reminder_requests to shared_reminders.
-- Convert FriendRequest rows into friendships before dropping friend_requests.
-- Rename shared_reminder_request_id columns to shared_reminder_id.
-- Add product_notifications.friendship_id.
-- Assert account_blocks is absent by leaving no references and not creating it.
```

The migration must drop old enums after dependent columns are migrated. If production data needs a more complex backfill than one SQL migration can safely express, create a migration helper script in `gateway/packages/api/src/scripts/` and call it from the deploy window before dropping old tables.

- [ ] **Step 5: Run schema verification**

Run:

```bash
cd gateway
pnpm --filter @clawscale/api db:generate
pnpm --filter @clawscale/api test -- src/scheduling/schema-contract.test.ts
```

Expected: Prisma generation succeeds and schema contract tests pass.

- [ ] **Step 6: Commit**

```bash
git add gateway/packages/api/prisma/schema.prisma gateway/packages/api/prisma/migrations/20260528120000_direct_friendship_shared_reminders/migration.sql gateway/packages/api/src/scheduling/schema-contract.test.ts gateway/packages/api/src/scheduling/types.ts
git commit -m "feat: migrate scheduling schema to direct sharing"
```

## Task 2: Direct Friendship Service And Notifications

**Files:**
- Modify: `gateway/packages/api/src/scheduling/user-link-service.ts`
- Modify: `gateway/packages/api/src/scheduling/user-link-service.test.ts`
- Modify: `gateway/packages/api/src/scheduling/notification-service.ts`
- Modify: `gateway/packages/api/src/scheduling/notification-service.test.ts`
- Modify: `gateway/packages/api/src/scheduling/friendship-service.ts`
- Modify: `gateway/packages/api/src/scheduling/friendship-service.test.ts`

- [ ] **Step 1: Write failing direct friendship service tests**

Replace friend-request tests with direct friendship cases:

```ts
it('creates an active friendship from a link session and notifies only the link owner', async () => {
  const result = await createFriendshipFromLinkSession(db as never, {
    token: 'session-token',
    openerAccountId: 'ck_opener',
    idempotencyKey: 'friendship:ck_opener:session-token',
  });
  expect(result).toMatchObject({
    id: 'friendship_1',
    status: 'active',
    friendAccountId: 'ck_owner',
    created: true,
  });
  expect(db.friendship.upsert).toHaveBeenCalled();
  expect(db.productNotification.create).toHaveBeenCalledWith(expect.objectContaining({
    data: expect.objectContaining({
      friendshipId: 'friendship_1',
      recipientAccountId: 'ck_owner',
      kind: 'direct_friendship_created',
    }),
  }));
  expect(db.friendRequest).toBeUndefined();
});

it('reuses an existing active friendship without duplicate notification', async () => {
  db.friendship.findFirst.mockResolvedValueOnce({
    id: 'friendship_existing',
    accountAId: 'ck_opener',
    accountBId: 'ck_owner',
    status: 'active',
  });
  const result = await createFriendshipFromLinkSession(db as never, {
    token: 'session-token',
    openerAccountId: 'ck_opener',
    idempotencyKey: 'friendship:ck_opener:session-token',
  });
  expect(result).toMatchObject({ id: 'friendship_existing', status: 'active', created: false });
  expect(db.productNotification.create).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd gateway && pnpm --filter @clawscale/api test -- src/scheduling/user-link-service.test.ts src/scheduling/notification-service.test.ts src/scheduling/friendship-service.test.ts`

Expected: FAIL because direct friendship functions and notification resources do not exist yet.

- [ ] **Step 3: Implement service**

Rename exports:

```ts
export async function createFriendshipFromLinkSession(
  client: UserLinkClient,
  input: {
    token: string;
    openerAccountId: string;
    idempotencyKey: string;
  },
): Promise<DirectFriendshipResult>;

export async function createFriendshipByUserLinkCode(
  client: UserLinkClient,
  input: {
    openerAccountId: string;
    code: string;
    idempotencyKey: string;
  },
): Promise<DirectFriendshipResult>;
```

Implementation rules:

```ts
function canonicalPair(a: string, b: string): { accountAId: string; accountBId: string } {
  return a < b ? { accountAId: a, accountBId: b } : { accountAId: b, accountBId: a };
}
```

Use `friendship.findFirst` for active idempotency, reactivate removed rows with `status: active`, and create only if no row exists. Remove `findPendingFriendRequest`, `createFriendRequestWithConflictRead`, and all friend-request notification helpers.

Update `enqueueProductNotification` input:

```ts
type ProductNotificationResource =
  | { resourceType: 'friendship'; friendshipId: string }
  | { resourceType: 'shared_reminder'; sharedReminderId: string };
```

Map `friendship` to `{ friendshipId }` and `shared_reminder` to `{ sharedReminderId }`.

- [ ] **Step 4: Remove request cancellation side effects from friend removal**

`removeFriendship` must mark only the friendship removed. It must not invalidate or cancel active shared reminders. Delete old pending shared-reminder cleanup helpers from `friendship-service.ts`.

- [ ] **Step 5: Run tests**

Run: `cd gateway && pnpm --filter @clawscale/api test -- src/scheduling/user-link-service.test.ts src/scheduling/notification-service.test.ts src/scheduling/friendship-service.test.ts`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gateway/packages/api/src/scheduling/user-link-service.ts gateway/packages/api/src/scheduling/user-link-service.test.ts gateway/packages/api/src/scheduling/notification-service.ts gateway/packages/api/src/scheduling/notification-service.test.ts gateway/packages/api/src/scheduling/friendship-service.ts gateway/packages/api/src/scheduling/friendship-service.test.ts
git commit -m "feat: create friendships directly from user links"
```

## Task 3: Public Routes, Shared Types, And Web Link API

**Files:**
- Modify: `gateway/packages/api/src/routes/public-user-link-routes.ts`
- Modify: `gateway/packages/api/src/routes/public-user-link-routes.test.ts`
- Modify: `gateway/packages/shared/src/types/scheduling.ts`
- Modify: `gateway/packages/web/lib/user-link-api.ts`
- Modify: `gateway/packages/web/lib/user-link-api.test.ts`

- [ ] **Step 1: Write failing route/type tests**

Add route-not-found and replacement route tests:

```ts
it('does not expose the old friend request link route', async () => {
  const res = await createApp().request('/api/public/link-sessions/session-token/friend-requests', {
    method: 'POST',
    headers: authHeaders(),
  });
  expect(res.status).toBe(404);
});

it('creates a friendship through the direct friendship route', async () => {
  mocks.createFriendshipFromLinkSession.mockResolvedValueOnce({
    id: 'friendship_1',
    status: 'active',
    friendAccountId: 'ck_owner',
    created: true,
  });
  const res = await createApp().request('/api/public/link-sessions/session-token/friendships', {
    method: 'POST',
    headers: authHeaders(),
  });
  expect(res.status).toBe(201);
  await expect(res.json()).resolves.toEqual({
    ok: true,
    data: { id: 'friendship_1', status: 'active', friend_account_id: 'ck_owner', created: true },
  });
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd gateway && pnpm --filter @clawscale/api test -- src/routes/public-user-link-routes.test.ts && pnpm --filter @clawscale/web test -- lib/user-link-api.test.ts`

Expected: FAIL because the old route and `sendFriendRequest` still exist.

- [ ] **Step 3: Implement route and type rename**

Use `POST /api/public/link-sessions/:token/friendships` and map service output to:

```ts
type PublicDirectFriendshipResult = {
  id: string;
  status: 'active';
  friend_account_id: string;
  created: boolean;
};
```

In shared types:

```ts
export interface DirectFriendshipResponse {
  id: string;
  status: 'active';
  friend_account_id: string;
  created: boolean;
}
```

In web API:

```ts
export async function createFriendship(input: { token: string }): Promise<ApiResponse<DirectFriendshipResponse>> {
  const res = await fetch(`${getCustomerApiBase()}/api/public/link-sessions/${encodeURIComponent(input.token)}/friendships`, {
    method: 'POST',
    headers: customerJsonHeaders(),
  });
  return (await res.json()) as ApiResponse<DirectFriendshipResponse>;
}
```

- [ ] **Step 4: Run tests**

Run: `cd gateway && pnpm --filter @clawscale/api test -- src/routes/public-user-link-routes.test.ts && pnpm --filter @clawscale/web test -- lib/user-link-api.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/api/src/routes/public-user-link-routes.ts gateway/packages/api/src/routes/public-user-link-routes.test.ts gateway/packages/shared/src/types/scheduling.ts gateway/packages/web/lib/user-link-api.ts gateway/packages/web/lib/user-link-api.test.ts
git commit -m "feat: expose direct friendship link route"
```

## Task 4: Active Shared Reminder Service

**Files:**
- Modify: `gateway/packages/api/src/scheduling/shared-reminder-service.ts`
- Modify: `gateway/packages/api/src/scheduling/shared-reminder-service.test.ts`
- Modify: `gateway/packages/api/src/scheduling/domain-contract.ts`

- [ ] **Step 1: Write failing active-create tests**

Add tests for active direct creation:

```ts
it('creates an active shared reminder with both projections and receiver notification', async () => {
  reminderRuntime.listRuntimeCalendarFacts.mockResolvedValueOnce([]);
  reminderRuntime.createRuntimeReminder
    .mockResolvedValueOnce({ id: 'rem_creator' })
    .mockResolvedValueOnce({ id: 'rem_receiver' });
  const result = await createSharedReminder(client as never, reminderRuntime as never, {
    creatorAccountId: 'ck_creator',
    receiverAccountId: 'ck_receiver',
    title: 'Design review',
    fireAt: '2029-01-01T02:00:00.000Z',
    timezone: 'Asia/Shanghai',
    durationMinutes: 30,
    idempotencyKey: 'idem_1',
  });
  expect(result).toMatchObject({ status: 'active', creatorReminderId: 'rem_creator', receiverReminderId: 'rem_receiver' });
  expect(client.sharedReminder.create).toHaveBeenCalledWith(expect.objectContaining({
    data: expect.objectContaining({ status: 'active' }),
  }));
  expect(client.productNotification.create).toHaveBeenCalledWith(expect.objectContaining({
    data: expect.objectContaining({ recipientAccountId: 'ck_receiver', kind: 'shared_reminder_created' }),
  }));
});
```

Add conflict and compensation tests:

```ts
it('fails receiver duration conflict without center row, projections, or notification', async () => {
  reminderRuntime.listRuntimeCalendarFacts.mockResolvedValueOnce([{ startsAt: '2029-01-01T02:10:00.000Z', endsAt: '2029-01-01T02:20:00.000Z' }]);
  await expect(createSharedReminder(client as never, reminderRuntime as never, validInput())).rejects.toThrow('receiver_time_conflict');
  expect(client.sharedReminder.create).not.toHaveBeenCalled();
  expect(reminderRuntime.createRuntimeReminder).not.toHaveBeenCalled();
  expect(client.productNotification.create).not.toHaveBeenCalled();
});

it('cancels creator runtime reminder when receiver projection fails', async () => {
  reminderRuntime.listRuntimeCalendarFacts.mockResolvedValueOnce([]);
  reminderRuntime.createRuntimeReminder
    .mockResolvedValueOnce({ id: 'rem_creator' })
    .mockRejectedValueOnce(new Error('runtime_failed'));
  await expect(createSharedReminder(client as never, reminderRuntime as never, validInput())).rejects.toThrow('runtime_failed');
  expect(reminderRuntime.cancelRuntimeReminder).toHaveBeenCalledWith(expect.objectContaining({ runtimeReminderId: 'rem_creator' }));
  expect(client.sharedReminder.create).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Write failing cancel tests**

```ts
it.each([
  ['creator', 'ck_creator', 'ck_receiver'],
  ['receiver', 'ck_receiver', 'ck_creator'],
])('lets %s cancel and notifies only the other participant', async (_role, actorAccountId, recipientAccountId) => {
  client.sharedReminder.findFirst.mockResolvedValueOnce(activeSharedReminder());
  const result = await cancelSharedReminder(client as never, reminderRuntime as never, {
    actorAccountId,
    sharedReminderId: 'sr_1',
    idempotencyKey: `cancel-${actorAccountId}`,
  });
  expect(result.status).toBe('cancelled');
  expect(reminderRuntime.cancelRuntimeReminder).toHaveBeenCalledTimes(2);
  expect(client.productNotification.create).toHaveBeenCalledWith(expect.objectContaining({
    data: expect.objectContaining({ recipientAccountId, kind: 'shared_reminder_cancelled' }),
  }));
});
```

- [ ] **Step 3: Run tests and verify failure**

Run: `cd gateway && pnpm --filter @clawscale/api test -- src/scheduling/shared-reminder-service.test.ts`

Expected: FAIL because current service uses request/pending/accept/reject semantics.

- [ ] **Step 4: Implement active shared reminder service**

Rename record/client fields from request naming to fact naming. Keep exported functions:

```ts
export async function createSharedReminder(
  client: SharedReminderClient,
  reminderRuntime: ReminderRuntimePort,
  input: CreateSharedReminderInput,
): Promise<SharedReminderRecord>;

export async function cancelSharedReminder(
  client: SharedReminderClient,
  reminderRuntime: Pick<ReminderRuntimePort, 'cancelRuntimeReminder'>,
  input: CancelSharedReminderInput,
): Promise<SharedReminderRecord>;

export async function listSharedReminders(
  client: SharedReminderClient,
  input: ListSharedRemindersInput,
): Promise<SharedReminderRecord[]>;
```

Delete exports:

```ts
acceptSharedReminder
rejectSharedReminder
listPendingSharedReminders
acceptPendingSharedRemindersFrom
rejectPendingSharedRemindersFrom
cancelPendingSharedRemindersFor
```

Implementation details:

- `createSharedReminder` accepts `creatorAccountId` and `receiverAccountId`.
- It calls `listRuntimeCalendarFacts` only when `durationMinutes` is non-null.
- It treats busy intervals as overlap when `busyStart < requestedEnd && requestedStart < busyEnd`.
- It generates `sharedReminderId` before runtime creates.
- Runtime idempotency keys include `shared-reminder:<sharedReminderId>:creator` and `shared-reminder:<sharedReminderId>:receiver`.
- It writes center row and two projection rows in one transaction after both runtime reminders exist.
- On post-runtime DB failure it calls `cancelRuntimeReminder` for both runtime reminders.
- It enqueues `shared_reminder_created` to receiver only and without `allowed_actions`.

- [ ] **Step 5: Implement actor-neutral cancel**

Use active row lookup:

```ts
const shared = await client.sharedReminder.findFirst({
  where: {
    id: sharedReminderId,
    status: { in: ['active', 'cancelled'] },
    OR: [{ creatorAccountId: actorAccountId }, { receiverAccountId: actorAccountId }],
  },
});
```

If active, update to `cancelled`, cancel both runtime reminders, record event with actor role, and notify the other participant. If already cancelled, return it and do not duplicate notification.

- [ ] **Step 6: Run tests**

Run: `cd gateway && pnpm --filter @clawscale/api test -- src/scheduling/shared-reminder-service.test.ts`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add gateway/packages/api/src/scheduling/shared-reminder-service.ts gateway/packages/api/src/scheduling/shared-reminder-service.test.ts gateway/packages/api/src/scheduling/domain-contract.ts
git commit -m "feat: make shared reminders active on create"
```

## Task 5: Domain Contract, Routes, Focus Cleanup

**Files:**
- Modify: `gateway/packages/api/src/scheduling/domain-contract.ts`
- Modify: `gateway/packages/api/src/scheduling/runtime-contract-fixtures.ts`
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.ts`
- Modify: `gateway/packages/api/src/routes/internal-scheduling-routes.test.ts`
- Modify: `gateway/packages/api/src/routes/customer-scheduling-routes.ts`
- Modify: `gateway/packages/api/src/routes/customer-scheduling-routes.test.ts`
- Modify or delete: `gateway/packages/api/src/scheduling/focus-binding-service.ts`
- Modify or delete: `gateway/packages/api/src/scheduling/focus-binding-service.test.ts`
- Modify: `gateway/packages/api/src/scheduling/friend-target-resolver.ts`
- Modify: `gateway/packages/api/src/scheduling/friend-target-resolver.test.ts`

- [ ] **Step 1: Write failing unknown-tool and route-not-found tests**

```ts
it.each([
  'list_friend_requests',
  'accept_friend_request',
  'reject_friend_request',
  'cancel_friend_request',
  'list_pending_shared_reminders',
  'accept_shared_reminder',
  'reject_shared_reminder',
  'accept_pending_shared_reminders_from',
  'reject_pending_shared_reminders_from',
  'cancel_pending_shared_reminders_for',
])('returns unknown_tool for removed tool %s', async (toolName) => {
  const res = await createApp().request(`/api/internal/scheduling/tools/${toolName}`, {
    method: 'POST',
    headers: internalHeaders(),
    body: JSON.stringify({ customer_id: 'ck_a' }),
  });
  expect(res.status).toBe(404);
  await expect(res.json()).resolves.toMatchObject({ ok: false, error: 'unknown_tool' });
});
```

For customer routes:

```ts
it.each([
  '/api/customer/scheduling/friend-requests',
  '/api/customer/scheduling/friend-requests/fr_1/accept',
  '/api/customer/scheduling/friend-requests/fr_1/reject',
  '/api/customer/scheduling/friend-requests/fr_1/cancel',
  '/api/customer/scheduling/shared-reminders/pending',
])('does not expose retired route %s', async (path) => {
  const res = await createApp().request(path, { method: path.includes('/accept') ? 'POST' : 'GET', headers: authHeaders() });
  expect(res.status).toBe(404);
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd gateway && pnpm --filter @clawscale/api test -- src/routes/internal-scheduling-routes.test.ts src/routes/customer-scheduling-routes.test.ts src/scheduling/focus-binding-service.test.ts src/scheduling/friend-target-resolver.test.ts`

Expected: FAIL because removed tools/routes still exist.

- [ ] **Step 3: Remove pending tool handlers and focus behavior**

In `domain-contract.ts`, keep only:

```ts
get_user_link
reset_user_link
disable_user_link
create_friendship_by_user_link_code
list_friends
remove_friendship
list_friend_calendar_facts
create_shared_reminder
cancel_shared_reminder
list_shared_reminders
```

Delete `resolvedPendingRequestId`, `resolveSharedReminderRequestId` accept/reject logic, and imports for removed functions. If `focus-binding-service.ts` only resolves pending invitations, delete its active route usage and tests. If route files still need `resolveAgentFocus` for other focus behavior, make it return no pending invitation candidates.

- [ ] **Step 4: Remove customer pending routes**

Delete route handlers for `/friend-requests`, `/friend-requests/:id/accept`, `/friend-requests/:id/reject`, `/friend-requests/:id/cancel`, pending shared reminder list, and pending bulk actions.

- [ ] **Step 5: Run tests**

Run: `cd gateway && pnpm --filter @clawscale/api test -- src/routes/internal-scheduling-routes.test.ts src/routes/customer-scheduling-routes.test.ts src/scheduling/friend-target-resolver.test.ts`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gateway/packages/api/src/scheduling/domain-contract.ts gateway/packages/api/src/scheduling/runtime-contract-fixtures.ts gateway/packages/api/src/routes/internal-scheduling-routes.ts gateway/packages/api/src/routes/internal-scheduling-routes.test.ts gateway/packages/api/src/routes/customer-scheduling-routes.ts gateway/packages/api/src/routes/customer-scheduling-routes.test.ts gateway/packages/api/src/scheduling/focus-binding-service.ts gateway/packages/api/src/scheduling/focus-binding-service.test.ts gateway/packages/api/src/scheduling/friend-target-resolver.ts gateway/packages/api/src/scheduling/friend-target-resolver.test.ts
git commit -m "feat: remove scheduling confirmation tools"
```

## Task 6: Notification Routing And Message Delivery Contract

**Files:**
- Modify: `gateway/packages/api/src/lib/route-message.ts`
- Modify: `gateway/packages/api/src/lib/route-message.test.ts`
- Modify: `gateway/packages/api/src/scheduling/notification-service.ts`
- Modify: `gateway/packages/api/src/scheduling/notification-service.test.ts`

- [ ] **Step 1: Write failing route-message tests**

```ts
it('routes direct friendship notifications with friendship id metadata', async () => {
  const message = await buildRouteMessage({
    kind: 'direct_friendship_created',
    friendshipId: 'friendship_1',
    sharedReminderId: null,
    payload: { text: 'Kai added you as a friend', metadata: { friendship_id: 'friendship_1' } },
  } as never);
  expect(message.text).toContain('Kai');
});

it('does not require friendRequestId or sharedReminderRequestId', async () => {
  await expect(buildRouteMessage(notificationWithOldRequestIds() as never)).rejects.toThrow();
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd gateway && pnpm --filter @clawscale/api test -- src/lib/route-message.test.ts src/scheduling/notification-service.test.ts`

Expected: FAIL because current code still reads old request ids.

- [ ] **Step 3: Implement routing update**

Replace `friendRequestId` and `sharedReminderRequestId` reads with `friendshipId` and `sharedReminderId`. Product notification payloads remain text-first; metadata names should be snake_case for API payloads.

- [ ] **Step 4: Run tests**

Run: `cd gateway && pnpm --filter @clawscale/api test -- src/lib/route-message.test.ts src/scheduling/notification-service.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/api/src/lib/route-message.ts gateway/packages/api/src/lib/route-message.test.ts gateway/packages/api/src/scheduling/notification-service.ts gateway/packages/api/src/scheduling/notification-service.test.ts
git commit -m "feat: route direct scheduling notifications"
```

## Task 7: Agent Runtime Tool Cleanup

**Files:**
- Modify: `agent/agno_agent/capabilities/scheduling.py`
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
- Modify: `agent/agno_agent/runtime/semantic_interpreter.py`
- Modify: `agent/agno_agent/runtime/execution_agents.py`
- Modify: `agent/agno_agent/runtime/chat_response_instructions.py`
- Modify: `agent/agno_agent/runtime/focus.py`
- Modify: `agent/agno_agent/runtime/scheduling_types.py`
- Modify: `tests/unit/agent/test_scheduling_capability.py`
- Modify: `tests/unit/agent/test_agent_runtime_scheduling_tools.py`
- Modify: `tests/unit/agent/test_agent_runtime_construction.py`
- Modify: `tests/unit/agent/test_execution_agents.py`
- Modify: `tests/unit/agent/test_chat_response_scheduling_instructions.py`
- Modify: `tests/unit/agent/test_focus_channel.py`
- Modify: `tests/unit/agent/test_scheduling_types.py`

- [ ] **Step 1: Write failing agent contract tests**

Add tests that removed tools are absent and direct friendship is present:

```python
def test_scheduling_tools_remove_confirmation_flows():
    assert "create_friendship_by_user_link_code" in SCHEDULING_TOOL_NAMES
    for removed in [
        "send_friend_request_by_user_link_code",
        "list_pending_shared_reminders",
        "accept_shared_reminder",
        "reject_shared_reminder",
        "list_friend_requests",
        "accept_friend_request",
        "reject_friend_request",
        "cancel_friend_request",
    ]:
        assert removed not in SCHEDULING_TOOL_NAMES
```

Update visible summary tests:

```python
def test_create_friendship_by_link_visible_summary():
    result = SchedulingCapabilityResult(
        tool_name="create_friendship_by_user_link_code",
        ok=True,
        content={"id": "friendship_1", "status": "active", "friend_account_id": "ck_owner", "created": True},
    )
    assert "已添加好友" in result.visible_summary()
```

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_scheduling_tools.py tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_execution_agents.py tests/unit/agent/test_chat_response_scheduling_instructions.py tests/unit/agent/test_focus_channel.py tests/unit/agent/test_scheduling_types.py -q`

Expected: FAIL because old tools and prompt rules remain.

- [ ] **Step 3: Remove old tools and rename direct friend tool**

Replace `send_friend_request_by_user_link_code` with `create_friendship_by_user_link_code`. Remove accept/reject shared reminder aliases, Chinese confirmation keywords that route to accept, and block/unblock intent rules. Shared reminder creation success copy should say active/created, not pending invite.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_scheduling_tools.py tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_execution_agents.py tests/unit/agent/test_chat_response_scheduling_instructions.py tests/unit/agent/test_focus_channel.py tests/unit/agent/test_scheduling_types.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/agno_agent/capabilities/scheduling.py agent/agno_agent/runtime/agent_runtime.py agent/agno_agent/runtime/semantic_interpreter.py agent/agno_agent/runtime/execution_agents.py agent/agno_agent/runtime/chat_response_instructions.py agent/agno_agent/runtime/focus.py agent/agno_agent/runtime/scheduling_types.py tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_scheduling_tools.py tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_execution_agents.py tests/unit/agent/test_chat_response_scheduling_instructions.py tests/unit/agent/test_focus_channel.py tests/unit/agent/test_scheduling_types.py
git commit -m "feat: remove scheduling confirmation tools from agent"
```

## Task 8: Customer Web Friends Page Cleanup

**Files:**
- Modify: `gateway/packages/web/lib/customer-friends.ts`
- Modify: `gateway/packages/web/lib/customer-friends.test.ts`
- Modify: `gateway/packages/web/app/(customer)/account/friends/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/account/friends/page.test.tsx`

- [ ] **Step 1: Write failing web tests**

Assert the page no longer fetches or renders pending requests:

```tsx
it('does not render pending invitation panels or accept reject buttons', async () => {
  listFriendsMock.mockResolvedValue({ ok: true, data: [] });
  render(<FriendsPage />);
  expect(await screen.findByText(/好友链接|Friend link/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /接受|Accept/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /拒绝|Reject/i })).not.toBeInTheDocument();
});
```

Assert link submission calls `createFriendship`:

```tsx
it('creates friendship directly from invite token', async () => {
  createFriendshipMock.mockResolvedValue({ ok: true, data: { id: 'friendship_1', status: 'active', friend_account_id: 'ck_owner', created: true } });
  // fill token field and submit
  expect(createFriendshipMock).toHaveBeenCalledWith({ token: 'session-token' });
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd gateway && pnpm --filter @clawscale/web test -- lib/customer-friends.test.ts "app/(customer)/account/friends/page.test.tsx"`

Expected: FAIL because old friend-request helpers are still used.

- [ ] **Step 3: Implement cleanup**

Delete `CustomerFriendRequest`, `listCustomerFriendRequests`, `acceptCustomerFriendRequest`, `rejectCustomerFriendRequest`, and `cancelCustomerFriendRequest`. Keep `listCustomerFriends` and `removeCustomerFriend`. Update page state to only manage friends, link info, and direct link add status. Remove pending request panels and block/unblock copy.

- [ ] **Step 4: Run tests**

Run: `cd gateway && pnpm --filter @clawscale/web test -- lib/customer-friends.test.ts "app/(customer)/account/friends/page.test.tsx"`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/web/lib/customer-friends.ts gateway/packages/web/lib/customer-friends.test.ts "gateway/packages/web/app/(customer)/account/friends/page.tsx" "gateway/packages/web/app/(customer)/account/friends/page.test.tsx"
git commit -m "feat: simplify customer friends UI"
```

## Task 9: Docs, Product Index, And Production Smoke Skill

**Files:**
- Modify: `docs/product-specs/FEATURE_TREE.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `.agents/skills/production-real-user-flow-smoke/SKILL.md`
- Modify: any active docs found by `rg -n "friend request|pending shared|accept_shared|reject_shared|block/unblock|shared_reminder_requests" docs agent gateway .agents/skills/production-real-user-flow-smoke`

- [ ] **Step 1: Write failing documentation scan command**

Run:

```bash
rg -n "friend request|friend-request|pending shared|accept_shared_reminder|reject_shared_reminder|list_pending_shared_reminders|block/unblock|shared_reminder_requests|friend_requests" docs/product-specs docs/ARCHITECTURE.md .agents/skills/production-real-user-flow-smoke/SKILL.md
```

Expected: output shows stale active docs and smoke instructions.

- [ ] **Step 2: Update active docs**

`FEATURE_TREE.md` should list:

```text
POST /api/public/link-sessions/:token/friendships
POST /api/internal/scheduling/tools/create_friendship_by_user_link_code
POST /api/internal/scheduling/tools/create_shared_reminder
POST /api/internal/scheduling/tools/cancel_shared_reminder
```

It must not list friend-request routes, accept/reject shared reminder tools, pending bulk tools, or block/unblock behavior.

- [ ] **Step 3: Update production smoke skill**

Change the skill flow to:

1. Inspect production service health and delivery routes.
2. Use a real account friend link or canonical tool to create direct friendship.
3. Verify `friendships.status = active` and `product_notifications.friendship_id` notification to link owner.
4. Create direct shared reminder with duration and no conflict.
5. Verify `shared_reminders.status = active`, both runtime ids, both projections, receiver notification only.
6. Cancel by one participant.
7. Verify both runtime reminders cancelled and only the other participant notified.
8. Run a conflict create path and verify no center row, projection, or notification.
9. Clean up only exact marker rows.

- [ ] **Step 4: Run docs scan**

Run:

```bash
rg -n "friend request|friend-request|pending shared|accept_shared_reminder|reject_shared_reminder|list_pending_shared_reminders|block/unblock|shared_reminder_requests|friend_requests" docs/product-specs docs/ARCHITECTURE.md .agents/skills/production-real-user-flow-smoke/SKILL.md
```

Expected: no active-contract references remain. Historical `docs/issues/` and generated `artifacts/evidence/` are not part of this scan.

- [ ] **Step 5: Commit**

```bash
git add docs/product-specs/FEATURE_TREE.md docs/ARCHITECTURE.md .agents/skills/production-real-user-flow-smoke/SKILL.md
git commit -m "docs: update direct scheduling product surfaces"
```

## Task 10: Full Verification, Deploy, And Production Smoke

**Files:**
- Modify only if verification identifies a real bug in files touched above.
- Generated evidence under `artifacts/evidence/` if production smoke scripts write evidence.

- [ ] **Step 1: Run broad stale-reference scans**

Run:

```bash
rg -n "FriendRequest|friendRequest|friend_request_id|friend_requests|SharedReminderRequest|sharedReminderRequest|shared_reminder_request_id|shared_reminder_requests|pending_invitee_confirmation|accept_shared_reminder|reject_shared_reminder|list_pending_shared_reminders|send_friend_request_by_user_link_code|block_account|unblock_account|block/unblock" gateway agent tests docs/product-specs docs/ARCHITECTURE.md .agents/skills/production-real-user-flow-smoke
```

Expected: no active code/test/docs references except migration comments or intentionally dated historical issue records outside this scan.

- [ ] **Step 2: Run gateway API tests**

Run:

```bash
cd gateway
pnpm --filter @clawscale/api test
pnpm --filter @clawscale/api build
```

Expected: exit 0.

- [ ] **Step 3: Run web tests and build**

Run:

```bash
cd gateway
pnpm --filter @clawscale/web test
pnpm --filter @clawscale/web build
```

Expected: exit 0.

- [ ] **Step 4: Run Python agent tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_scheduling_tools.py tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_execution_agents.py tests/unit/agent/test_chat_response_scheduling_instructions.py tests/unit/agent/test_focus_channel.py tests/unit/agent/test_scheduling_types.py -q
```

Expected: exit 0.

- [ ] **Step 5: Run repo routing verification**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
zsh scripts/check
git diff --check
```

Expected: checks exit 0. `review-trigger` is a non-blocking risk report; address any real issue it surfaces.

- [ ] **Step 6: Commit verification fixes**

If any verification fix was needed:

```bash
git status --short
git add gateway agent tests docs .agents artifacts
git commit -m "fix: complete direct scheduling verification"
```

- [ ] **Step 7: Deploy with the repository script**

Run:

```bash
./scripts/deploy-compose-to-gcp.sh --restart
```

Expected: deploy script exits 0. If it fails, classify the failure as product/runtime bug, test/eval bug, environment instability, or plan gap, then fix the correct layer and rerun until deploy succeeds or a real blocker is recorded.

- [ ] **Step 8: Use the production real-user-flow smoke skill**

Follow `.agents/skills/production-real-user-flow-smoke/SKILL.md` after updating it. Use unique marker:

```bash
MARKER="direct-sharing-$(date -u +%Y%m%dT%H%M%SZ)"
```

Smoke must verify:

- direct friend-link add creates active friendship and link-owner notification
- repeated friend-link add is idempotent and does not duplicate notification
- direct shared-reminder create returns active with both runtime reminders/projections
- receiver gets informational creation notification
- cancel by either participant cancels both runtime reminders and notifies only the other participant
- receiver conflict returns `receiver_time_conflict` and creates no center row, projection, or notification
- cleanup deletes only exact marker data

- [ ] **Step 9: Final commit for smoke evidence**

If smoke generated repo evidence:

```bash
git add artifacts/evidence docs/issues
git commit -m "chore: record direct scheduling production smoke"
```

If no repo evidence was generated, do not create empty evidence just to commit.
