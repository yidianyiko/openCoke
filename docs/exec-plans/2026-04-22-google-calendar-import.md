# Google Calendar Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a first-version Google Calendar import flow that lets a claimed Coke customer authorize Google, import their `primary` calendar into Coke-owned reminders, and guides shared WhatsApp users through email claim before the import starts.

**Architecture:** Gateway owns claim-entry, Google OAuth, Postgres audit state, and the customer-facing web/API flow. Coke runtime owns conversation resolution plus imported reminder creation, because the live reminder system is conversation-scoped and must write valid `deferred_actions` without triggering historical imports immediately. The bridge exposes two new internal routes: import preflight and import execution.

**Tech Stack:** Next.js App Router, Hono, Prisma/Postgres, TypeScript, `googleapis`, Flask bridge, Python reminder runtime, MongoDB, Vitest, pytest

---

## File Map

- Modify: `gateway/packages/api/package.json`
  Add the Google client dependency used by the gateway OAuth and Calendar fetch flow.
- Modify: `gateway/packages/api/prisma/schema.prisma`
  Add the `CalendarImportRun` model plus any supporting enums/indexes.
- Create: `gateway/packages/api/prisma/migrations/20260422120000_calendar_import_runs/migration.sql`
  Persist the `calendar_import_runs` table.
- Create: `gateway/packages/api/src/lib/google-calendar-import-runs.ts`
  Own import-run creation, status transitions, and latest-run lookup.
- Create: `gateway/packages/api/src/lib/google-calendar-oauth.ts`
  Own Google auth URL generation, signed `state`, PKCE verifier handling, callback exchange, and `primary` calendar fetch helpers.
- Create: `gateway/packages/api/src/lib/google-calendar-runtime-client.ts`
  Own server-to-server calls from gateway to Coke bridge internal import routes.
- Modify: `gateway/packages/api/src/lib/customer-email.ts`
  Add the claim email helper that sends users to `/auth/claim` with a validated continuation target.
- Modify: `gateway/packages/api/src/lib/claim-token.ts`
  Extend claim token issue/complete flow to carry a validated `continueTo` path.
- Modify: `gateway/packages/api/src/routes/customer-claim-routes.ts`
  Add `POST /request` and return `continueTo` on successful claim completion.
- Create: `gateway/packages/api/src/routes/customer-google-calendar-import-routes.ts`
  Add authenticated preflight/start/status routes.
- Create: `gateway/packages/api/src/routes/customer-google-calendar-import-callback-routes.ts`
  Add the Google OAuth callback route that marks runs and redirects back to web.
- Modify: `gateway/packages/api/src/index.ts`
  Mount the new routes.
- Create: `gateway/packages/api/src/routes/customer-google-calendar-import-routes.test.ts`
  Cover auth gating, preflight, start, status, and callback behavior.
- Modify: `gateway/packages/api/src/routes/customer-claim-routes.test.ts`
  Cover claim request and continuation handling.
- Create: `gateway/packages/web/lib/customer-google-calendar-import.ts`
  Own typed API calls for claim-entry request, calendar import preflight/start/status, and callback summary fetch.
- Create: `gateway/packages/web/app/(customer)/auth/claim-entry/page.tsx`
  Render the email-first claim-entry page for shared WhatsApp users.
- Create: `gateway/packages/web/app/(customer)/auth/claim-entry/page.test.tsx`
  Cover claim-entry rendering, submission, and error states.
- Modify: `gateway/packages/web/app/(customer)/auth/claim/page.tsx`
  Respect the server-validated `continueTo` response instead of always pushing `/channels/wechat-personal`.
- Modify: `gateway/packages/web/app/(customer)/auth/claim/page.test.tsx`
  Cover continuation redirect and fallback behavior.
- Create: `gateway/packages/web/app/(customer)/account/calendar-import/page.tsx`
  Render import preflight, “Connect Google Calendar”, and run summary states.
- Create: `gateway/packages/web/app/(customer)/account/calendar-import/page.test.tsx`
  Cover blocked, ready, importing, success, and partial-failure UI states.
- Modify: `dao/conversation_dao.py`
  Add a helper that resolves the most recent deliverable private conversation for a customer and the default Coke character.
- Create: `tests/unit/dao/test_conversation_dao_calendar_import.py`
  Cover conversation resolution for import target lookup.
- Modify: `dao/deferred_action_dao.py`
  Add the imported-reminder metadata index and a best-effort duplicate lookup helper.
- Modify: `tests/unit/dao/test_deferred_action_dao.py`
  Cover the new metadata index and duplicate lookup query.
- Modify: `agent/agno_agent/tools/deferred_action/service.py`
  Add import-aware creation helpers for future one-shot, historical completed, and recurring imported reminders.
- Modify: `tests/unit/agent/test_deferred_action_service.py`
  Cover non-active historical imports and recurring imports seeded to the first future occurrence.
- Create: `connector/clawscale_bridge/google_calendar_import_service.py`
  Own runtime preflight resolution and Google event -> Coke reminder import mapping.
- Modify: `connector/clawscale_bridge/app.py`
  Mount `/bridge/internal/google-calendar-import/preflight` and `/bridge/internal/google-calendar-import/run`.
- Create: `tests/unit/connector/clawscale_bridge/test_google_calendar_import_service.py`
  Cover conversation resolution, Google reminder mapping, unsupported recurring exceptions, and import result counts.
- Modify: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
  Cover bridge auth and request validation for the new internal routes.
- Modify: `docs/architecture.md`
  Document the new calendar import capability and runtime boundary.
- Modify: `docs/fitness/coke-verification-matrix.md`
  Add verification commands for the gateway API/web and bridge/runtime import surfaces.
- Modify: `tasks/2026-04-22-google-calendar-import-design.md`
  Point to this implementation plan and mark the design phase handoff.

## Task 1: Add Gateway Persistence And Import-Run Domain Helpers

**Files:**
- Modify: `gateway/packages/api/package.json`
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Create: `gateway/packages/api/prisma/migrations/20260422120000_calendar_import_runs/migration.sql`
- Create: `gateway/packages/api/src/lib/google-calendar-import-runs.ts`
- Create: `gateway/packages/api/src/lib/google-calendar-import-runs.test.ts`

- [ ] **Step 1: Write the failing import-run helper tests**

```ts
import { describe, expect, it, vi } from 'vitest';
import {
  createCalendarImportRun,
  markCalendarImportRunImporting,
  markCalendarImportRunFinished,
} from './google-calendar-import-runs.js';

describe('google calendar import runs', () => {
  it('creates an authorizing run with target conversation identity', async () => {
    const db = {
      calendarImportRun: {
        create: vi.fn().mockResolvedValue({
          id: 'cir_1',
          status: 'authorizing',
          customerId: 'ck_1',
          identityId: 'idt_1',
          targetConversationId: 'conv_1',
          targetCharacterId: 'char_1',
        }),
      },
    };

    const result = await createCalendarImportRun(db as never, {
      customerId: 'ck_1',
      identityId: 'idt_1',
      targetConversationId: 'conv_1',
      targetCharacterId: 'char_1',
      triggerSource: 'manual_web',
    });

    expect(result.status).toBe('authorizing');
    expect(db.calendarImportRun.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          provider: 'google_calendar',
          targetConversationId: 'conv_1',
          targetCharacterId: 'char_1',
        }),
      }),
    );
  });
});
```

- [ ] **Step 2: Run the helper test to verify it fails**

Run: `cd gateway/packages/api && npm test -- src/lib/google-calendar-import-runs.test.ts`
Expected: FAIL with module not found or missing `calendarImportRun` model/types.

- [ ] **Step 3: Add the Prisma model, migration, dependency, and helper implementation**

```prisma
model CalendarImportRun {
  id                   String   @id @default(cuid())
  customerId           String   @map("customer_id")
  identityId           String   @map("identity_id")
  targetConversationId String   @map("target_conversation_id")
  targetCharacterId    String   @map("target_character_id")
  provider             String
  triggerSource        String   @map("trigger_source")
  status               String
  providerAccountEmail String?  @map("provider_account_email")
  importedCount        Int      @default(0) @map("imported_count")
  skippedCount         Int      @default(0) @map("skipped_count")
  failedCount          Int      @default(0) @map("failed_count")
  errorSummary         String?  @map("error_summary")
  startedAt            DateTime @default(now()) @map("started_at")
  finishedAt           DateTime? @map("finished_at")
  createdAt            DateTime @default(now()) @map("created_at")
  updatedAt            DateTime @updatedAt @map("updated_at")

  customer Customer @relation(fields: [customerId], references: [id], onDelete: Cascade)
  identity Identity @relation(fields: [identityId], references: [id], onDelete: Cascade)

  @@index([customerId, startedAt])
  @@index([identityId, startedAt])
  @@map("calendar_import_runs")
}
```

```ts
export async function createCalendarImportRun(client: CalendarImportRunClient, input: {
  customerId: string;
  identityId: string;
  targetConversationId: string;
  targetCharacterId: string;
  triggerSource: 'manual_web' | 'whatsapp_claim_redirect';
}) {
  return client.calendarImportRun.create({
    data: {
      customerId: input.customerId,
      identityId: input.identityId,
      targetConversationId: input.targetConversationId,
      targetCharacterId: input.targetCharacterId,
      provider: 'google_calendar',
      triggerSource: input.triggerSource,
      status: 'authorizing',
    },
  });
}
```

- [ ] **Step 4: Run the focused gateway API tests again**

Run:
- `cd gateway/packages/api && npm test -- src/lib/google-calendar-import-runs.test.ts`
- `cd gateway/packages/api && npm run db:generate`

Expected: PASS for the helper test and successful Prisma client generation.

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/api/package.json \
  gateway/packages/api/prisma/schema.prisma \
  gateway/packages/api/prisma/migrations/20260422120000_calendar_import_runs/migration.sql \
  gateway/packages/api/src/lib/google-calendar-import-runs.ts \
  gateway/packages/api/src/lib/google-calendar-import-runs.test.ts
git commit -m "feat(gateway): add calendar import run persistence"
```

## Task 2: Add Claim-Entry Request And Safe Claim Continuation

**Files:**
- Modify: `gateway/packages/api/src/lib/customer-email.ts`
- Modify: `gateway/packages/api/src/lib/claim-token.ts`
- Modify: `gateway/packages/api/src/routes/customer-claim-routes.ts`
- Modify: `gateway/packages/api/src/routes/customer-claim-routes.test.ts`
- Create: `gateway/packages/web/app/(customer)/auth/claim-entry/page.tsx`
- Create: `gateway/packages/web/app/(customer)/auth/claim-entry/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/claim/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/claim/page.test.tsx`
- Create: `gateway/packages/web/lib/customer-google-calendar-import.ts`

- [ ] **Step 1: Write the failing route and page tests for claim request plus continuation**

```ts
it('issues a claim email that preserves a safe continuation target', async () => {
  const res = await app.request('/api/auth/claim/request', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      entryToken: 'entry-token',
      email: 'alice@example.com',
      next: '/account/calendar-import',
    }),
  });

  expect(res.status).toBe(200);
  expect(sendCustomerClaimEmail).toHaveBeenCalledWith(
    expect.objectContaining({
      to: 'alice@example.com',
      continueTo: '/account/calendar-import',
    }),
  );
});
```

```tsx
it('routes to the server-validated continuation target after a successful claim', async () => {
  vi.mocked(customerApi.post).mockResolvedValueOnce({
    ok: true,
    data: {
      token: 'customer-token',
      customerId: 'ck_1',
      identityId: 'idt_1',
      email: 'alice@example.com',
      claimStatus: 'active',
      membershipRole: 'owner',
      continueTo: '/account/calendar-import',
    },
  });

  // render, submit, then:
  expect(pushMock).toHaveBeenCalledWith('/account/calendar-import');
});
```

- [ ] **Step 2: Run the claim route and page tests to verify they fail**

Run:
- `cd gateway/packages/api && npm test -- src/routes/customer-claim-routes.test.ts`
- `cd gateway/packages/web && npm test -- app/(customer)/auth/claim/page.test.tsx app/(customer)/auth/claim-entry/page.test.tsx`

Expected: FAIL because `/request`, claim email sending, `continueTo`, and the claim-entry page do not exist.

- [ ] **Step 3: Implement claim-entry request, signed continuation, and the new page**

```ts
interface ClaimTokenPayload {
  sub: string;
  identityId: string;
  email: string;
  tokenType: 'action';
  purpose: 'claim';
  continueTo?: string;
  stateFingerprint?: string;
}

function sanitizeContinueTo(value: string | undefined): string | undefined {
  return value && value.startsWith('/') && !value.startsWith('//') ? value : undefined;
}

customerClaimRouter.post(
  '/request',
  zValidator('json', z.object({
    entryToken: z.string().trim().min(1),
    email: z.string().trim().email(),
    next: z.string().trim().optional(),
  })),
  async (c) => {
    const body = c.req.valid('json');
    const continueTo = sanitizeContinueTo(body.next);
    const issued = await issueClaimToken(db as never, {
      customerId: verified.customerId,
      identityId: verified.identityId,
      email: body.email,
      continueTo,
    });
    await sendCustomerClaimEmail({
      to: issued.email,
      token: issued.token,
      continueTo,
    });
    return c.json({ ok: true, data: { message: 'claim_email_sent' } });
  },
);
```

```tsx
export default function ClaimEntryPage() {
  const [email, setEmail] = useState('');
  const [entryToken, setEntryToken] = useState('');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setEntryToken(params.get('entry') ?? '');
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await customerApi.post('/api/auth/claim/request', {
      entryToken,
      email,
      next: '/account/calendar-import',
    });
  }
}
```

- [ ] **Step 4: Run the focused claim tests again**

Run:
- `cd gateway/packages/api && npm test -- src/routes/customer-claim-routes.test.ts`
- `cd gateway/packages/web && npm test -- app/(customer)/auth/claim/page.test.tsx app/(customer)/auth/claim-entry/page.test.tsx`

Expected: PASS with the claim request endpoint sending email and the claim page redirecting to `/account/calendar-import` when `continueTo` is returned.

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/api/src/lib/customer-email.ts \
  gateway/packages/api/src/lib/claim-token.ts \
  gateway/packages/api/src/routes/customer-claim-routes.ts \
  gateway/packages/api/src/routes/customer-claim-routes.test.ts \
  gateway/packages/web/lib/customer-google-calendar-import.ts \
  gateway/packages/web/app/'(customer)'/auth/claim-entry/page.tsx \
  gateway/packages/web/app/'(customer)'/auth/claim-entry/page.test.tsx \
  gateway/packages/web/app/'(customer)'/auth/claim/page.tsx \
  gateway/packages/web/app/'(customer)'/auth/claim/page.test.tsx
git commit -m "feat(auth): add claim entry and calendar import continuation"
```

## Task 3: Add Google OAuth, Primary Calendar Fetch, And Gateway Import Routes

**Files:**
- Create: `gateway/packages/api/src/lib/google-calendar-oauth.ts`
- Create: `gateway/packages/api/src/lib/google-calendar-runtime-client.ts`
- Create: `gateway/packages/api/src/routes/customer-google-calendar-import-routes.ts`
- Create: `gateway/packages/api/src/routes/customer-google-calendar-import-callback-routes.ts`
- Create: `gateway/packages/api/src/routes/customer-google-calendar-import-routes.test.ts`
- Modify: `gateway/packages/api/src/index.ts`

- [ ] **Step 1: Write the failing gateway import route tests**

```ts
it('blocks start when the customer email is not verified', async () => {
  const res = await app.request('/api/customer/google-calendar-import/start', {
    method: 'POST',
    headers: {
      Authorization: 'Bearer customer-token',
      'content-type': 'application/json',
    },
  });

  expect(res.status).toBe(403);
  await expect(res.json()).resolves.toEqual({
    ok: false,
    error: 'email_not_verified',
  });
});

it('returns a Google auth URL after bridge preflight resolves a target conversation', async () => {
  runtimeClient.preflightGoogleCalendarImport.mockResolvedValue({
    ok: true,
    data: {
      conversationId: 'conv_1',
      userId: 'ck_1',
      characterId: 'char_1',
      timezone: 'Asia/Tokyo',
    },
  });

  const res = await app.request('/api/customer/google-calendar-import/start', {
    method: 'POST',
    headers: {
      Authorization: 'Bearer customer-token',
      'content-type': 'application/json',
    },
  });

  expect(res.status).toBe(200);
  await expect(res.json()).resolves.toEqual({
    ok: true,
    data: {
      runId: expect.any(String),
      url: expect.stringContaining('accounts.google.com'),
    },
  });
});
```

- [ ] **Step 2: Run the new gateway import route tests to verify they fail**

Run: `cd gateway/packages/api && npm test -- src/routes/customer-google-calendar-import-routes.test.ts`
Expected: FAIL because the route, OAuth helper, runtime client, and callback flow are missing.

- [ ] **Step 3: Implement OAuth helpers, runtime client, and the gateway routes**

```ts
export async function buildGoogleCalendarAuthUrl(input: {
  runId: string;
  customerId: string;
  identityId: string;
  redirectUri: string;
}) {
  const oauth = new google.auth.OAuth2(
    process.env['GOOGLE_CALENDAR_CLIENT_ID'],
    process.env['GOOGLE_CALENDAR_CLIENT_SECRET'],
    input.redirectUri,
  );
  const codeVerifier = generators.codeVerifier();
  const codeChallenge = generators.codeChallenge(codeVerifier);
  const state = signGoogleCalendarState({
    runId: input.runId,
    customerId: input.customerId,
    identityId: input.identityId,
    codeVerifier,
  });

  return oauth.generateAuthUrl({
    access_type: 'online',
    scope: ['https://www.googleapis.com/auth/calendar.events.readonly'],
    include_granted_scopes: true,
    state,
    code_challenge_method: 'S256',
    code_challenge: codeChallenge,
  });
}
```

```ts
customerGoogleCalendarImportRouter.post('/start', requireCustomerImportAuth, async (c) => {
  const auth = c.get('customerImportAuth');
  const target = await preflightGoogleCalendarImport({
    customerId: auth.customerId,
    identityId: auth.identityId,
  });
  const run = await createCalendarImportRun(db as never, {
    customerId: auth.customerId,
    identityId: auth.identityId,
    targetConversationId: target.conversationId,
    targetCharacterId: target.characterId,
    triggerSource: 'manual_web',
  });
  const url = await buildGoogleCalendarAuthUrl({
    runId: run.id,
    customerId: auth.customerId,
    identityId: auth.identityId,
    redirectUri: readGoogleCalendarRedirectUri(),
  });
  return c.json({ ok: true, data: { runId: run.id, url } });
});
```

- [ ] **Step 4: Run the focused gateway API tests again**

Run: `cd gateway/packages/api && npm test -- src/routes/customer-google-calendar-import-routes.test.ts src/routes/customer-claim-routes.test.ts`
Expected: PASS for start/preflight/status/callback route coverage and no regressions in claim flow.

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/api/src/lib/google-calendar-oauth.ts \
  gateway/packages/api/src/lib/google-calendar-runtime-client.ts \
  gateway/packages/api/src/routes/customer-google-calendar-import-routes.ts \
  gateway/packages/api/src/routes/customer-google-calendar-import-callback-routes.ts \
  gateway/packages/api/src/routes/customer-google-calendar-import-routes.test.ts \
  gateway/packages/api/src/index.ts
git commit -m "feat(gateway): add google calendar oauth and import routes"
```

## Task 4: Add Runtime Preflight Resolution And Import-Aware Reminder Writers

**Files:**
- Modify: `dao/conversation_dao.py`
- Create: `tests/unit/dao/test_conversation_dao_calendar_import.py`
- Modify: `dao/deferred_action_dao.py`
- Modify: `tests/unit/dao/test_deferred_action_dao.py`
- Modify: `agent/agno_agent/tools/deferred_action/service.py`
- Modify: `tests/unit/agent/test_deferred_action_service.py`

- [ ] **Step 1: Write the failing Python tests for conversation resolution and import-aware reminder creation**

```python
def test_resolve_latest_private_conversation_by_db_user_ids_prefers_recent_conversation():
    from dao.conversation_dao import ConversationDAO

    dao = ConversationDAO.__new__(ConversationDAO)
    dao.collection = MagicMock()
    dao.collection.find.return_value.sort.return_value.limit.return_value = [
        {"_id": "conv-2", "platform": "wechat", "chatroom_name": None, "talkers": []}
    ]

    conversation = ConversationDAO.find_latest_private_conversation_by_db_user_ids(
        dao,
        db_user_id1="ck_1",
        db_user_id2="char_1",
    )

    assert str(conversation["_id"]) == "conv-2"
```

```python
def test_create_imported_historical_reminder_uses_completed_lifecycle():
    action_dao = Mock(create_action=Mock(return_value="action-1"))
    scheduler = Mock()
    service = service_module.DeferredActionService(
        action_dao=action_dao,
        scheduler=scheduler,
        now_provider=lambda: datetime(2026, 4, 22, 8, 0, tzinfo=UTC),
    )

    action = service.create_imported_historical_reminder(
        user_id="ck_1",
        character_id="char_1",
        conversation_id="conv_1",
        title="Yesterday meeting",
        dtstart=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
        timezone="UTC",
    )

    assert action["lifecycle_state"] == "completed"
    assert action["next_run_at"] is None
    scheduler.register_action.assert_not_called()
```

- [ ] **Step 2: Run the Python tests to verify they fail**

Run:
- `pytest tests/unit/dao/test_conversation_dao_calendar_import.py -v`
- `pytest tests/unit/agent/test_deferred_action_service.py -v`

Expected: FAIL because the DAO helper and import-aware reminder methods do not exist yet.

- [ ] **Step 3: Implement the new DAO helpers, metadata index, and import-aware reminder creation**

```python
def find_latest_private_conversation_by_db_user_ids(
    self,
    db_user_id1: str,
    db_user_id2: str,
) -> Optional[Dict]:
    query = {
        "chatroom_name": None,
        "talkers.db_user_id": {"$all": [db_user_id1, db_user_id2]},
        "$where": "this.talkers.length === 2",
    }
    conversation = (
        self.collection.find(query)
        .sort([("_id", -1)])
        .limit(1)
    )
    rows = list(conversation)
    if not rows:
        return None
    return self.ensure_conversation_info_structure(rows[0])
```

```python
def create_imported_historical_reminder(self, *, user_id, character_id, conversation_id, title, dtstart, timezone, metadata=None):
    now = self.now_provider()
    action = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "character_id": character_id,
        "kind": "user_reminder",
        "source": "google_calendar_import",
        "visibility": "visible",
        "lifecycle_state": "completed",
        "revision": 0,
        "title": title,
        "payload": {"prompt": title, "metadata": metadata or {}},
        "timezone": timezone,
        "dtstart": dtstart,
        "rrule": None,
        "next_run_at": None,
        "last_run_at": None,
        "run_count": 0,
        "max_runs": None,
        "expires_at": None,
        "retry_policy": dict(DEFAULT_RETRY_POLICY),
        "lease": {"token": None, "leased_at": None, "lease_expires_at": None},
        "last_error": None,
        "created_at": now,
        "updated_at": now,
    }
    action["_id"] = self.action_dao.create_action(action)
    return action
```

- [ ] **Step 4: Run the focused Python tests again**

Run:
- `pytest tests/unit/dao/test_conversation_dao_calendar_import.py -v`
- `pytest tests/unit/dao/test_deferred_action_dao.py -v`
- `pytest tests/unit/agent/test_deferred_action_service.py -v`

Expected: PASS with the conversation lookup helper, metadata index, duplicate lookup, and import-aware reminder writes in place.

- [ ] **Step 5: Commit**

```bash
git add dao/conversation_dao.py \
  tests/unit/dao/test_conversation_dao_calendar_import.py \
  dao/deferred_action_dao.py \
  tests/unit/dao/test_deferred_action_dao.py \
  agent/agno_agent/tools/deferred_action/service.py \
  tests/unit/agent/test_deferred_action_service.py
git commit -m "feat(runtime): add import-aware reminder write path"
```

## Task 5: Add Bridge Internal Import Routes And Google Event Mapping

**Files:**
- Create: `connector/clawscale_bridge/google_calendar_import_service.py`
- Modify: `connector/clawscale_bridge/app.py`
- Create: `tests/unit/connector/clawscale_bridge/test_google_calendar_import_service.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`

- [ ] **Step 1: Write the failing bridge service and route tests**

```python
def test_preflight_returns_target_conversation_identity(monkeypatch):
    from connector.clawscale_bridge.google_calendar_import_service import GoogleCalendarImportService

    conversation_dao = MagicMock(
        find_latest_private_conversation_by_db_user_ids=MagicMock(
            return_value={
                "_id": "conv-1",
                "talkers": [
                    {"db_user_id": "ck_1", "nickname": "Alice"},
                    {"db_user_id": "char_1", "nickname": "coke"},
                ],
                "conversation_info": {},
            }
        )
    )

    service = GoogleCalendarImportService(
        conversation_dao=conversation_dao,
        deferred_action_service=MagicMock(),
        character_id_provider=lambda: "char_1",
    )

    result = service.preflight(customer_id="ck_1")

    assert result["conversation_id"] == "conv-1"
    assert result["user_id"] == "ck_1"
    assert result["character_id"] == "char_1"
```

```python
def test_exception_bearing_series_is_skipped_with_warning():
    service = GoogleCalendarImportService(
        conversation_dao=MagicMock(),
        deferred_action_service=MagicMock(),
        character_id_provider=lambda: "char_1",
    )

    result = service.import_events(
        target={"conversation_id": "conv-1", "user_id": "ck_1", "character_id": "char_1", "timezone": "UTC"},
        calendar_defaults={"timezone": "UTC", "default_reminders": []},
        events=[
            {
                "id": "evt-series",
                "status": "confirmed",
                "recurrence": ["RRULE:FREQ=DAILY"],
                "recurringEventId": "evt-series",
                "originalStartTime": {"dateTime": "2026-04-22T09:00:00Z"},
            }
        ],
    )

    assert result["skipped_count"] == 1
    assert result["warnings"][0]["reason"] == "unsupported_recurring_exceptions"
```

- [ ] **Step 2: Run the bridge tests to verify they fail**

Run:
- `pytest tests/unit/connector/clawscale_bridge/test_google_calendar_import_service.py -v`
- `pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py -v`

Expected: FAIL because the service and internal routes do not exist.

- [ ] **Step 3: Implement the bridge service and internal endpoints**

```python
class GoogleCalendarImportService:
    def __init__(self, *, conversation_dao=None, deferred_action_service=None, character_id_provider=None):
        self.conversation_dao = conversation_dao or ConversationDAO()
        self.deferred_action_service = deferred_action_service or DeferredActionService()
        self.character_id_provider = character_id_provider or ensure_default_character_seeded

    def preflight(self, *, customer_id: str) -> dict[str, str]:
        character_id = self.character_id_provider()
        conversation = self.conversation_dao.find_latest_private_conversation_by_db_user_ids(
            db_user_id1=customer_id,
            db_user_id2=character_id,
        )
        if not conversation:
            raise ValueError("conversation_required")
        return {
            "conversation_id": str(conversation["_id"]),
            "user_id": customer_id,
            "character_id": character_id,
            "timezone": "Asia/Tokyo",
        }
```

```python
@app.post("/bridge/internal/google-calendar-import/preflight")
def google_calendar_import_preflight():
    ok, error = require_bridge_auth(app.config["COKE_BRIDGE_API_KEY"])
    if not ok:
        body, status = error
        return jsonify(body), status
    payload = request.get_json(force=True)
    result = app.config["GOOGLE_CALENDAR_IMPORT_SERVICE"].preflight(
        customer_id=payload["customer_id"],
    )
    return jsonify({"ok": True, "data": result})
```

- [ ] **Step 4: Run the bridge tests again**

Run:
- `pytest tests/unit/connector/clawscale_bridge/test_google_calendar_import_service.py -v`
- `pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py -v`

Expected: PASS with working preflight, import routing, reminder mapping, and unsupported recurring exception handling.

- [ ] **Step 5: Commit**

```bash
git add connector/clawscale_bridge/google_calendar_import_service.py \
  connector/clawscale_bridge/app.py \
  tests/unit/connector/clawscale_bridge/test_google_calendar_import_service.py \
  tests/unit/connector/clawscale_bridge/test_bridge_app.py
git commit -m "feat(bridge): add google calendar import runtime endpoints"
```

## Task 6: Add Customer Import UI, Run Summary, And Final Docs

**Files:**
- Create: `gateway/packages/web/app/(customer)/account/calendar-import/page.tsx`
- Create: `gateway/packages/web/app/(customer)/account/calendar-import/page.test.tsx`
- Modify: `docs/architecture.md`
- Modify: `docs/fitness/coke-verification-matrix.md`
- Modify: `tasks/2026-04-22-google-calendar-import-design.md`

- [ ] **Step 1: Write the failing account page test for import preflight and summary states**

```tsx
it('shows a blocked state when no Coke private conversation exists', async () => {
  vi.mocked(customerGoogleCalendarImportApi.getPreflight).mockResolvedValueOnce({
    ok: true,
    data: {
      ready: false,
      blockedReason: 'conversation_required',
    },
  });

  renderPage();
  await waitForEffects();

  expect(container.textContent).toContain('Start or resume a Coke conversation first');
});

it('opens the Google authorization URL when import is ready', async () => {
  vi.mocked(customerGoogleCalendarImportApi.getPreflight).mockResolvedValueOnce({
    ok: true,
    data: { ready: true, latestRun: null },
  });
  vi.mocked(customerGoogleCalendarImportApi.start).mockResolvedValueOnce({
    ok: true,
    data: { runId: 'cir_1', url: 'https://accounts.google.com/o/oauth2/v2/auth?...' },
  });

  renderPage();
  await waitForEffects();
  container.querySelector('button[data-testid="start-google-import"]')?.dispatchEvent(
    new Event('click', { bubbles: true }),
  );

  expect(windowOpenMock).toHaveBeenCalledWith(
    'https://accounts.google.com/o/oauth2/v2/auth?...',
    '_self',
  );
});
```

- [ ] **Step 2: Run the web page test to verify it fails**

Run: `cd gateway/packages/web && npm test -- app/(customer)/account/calendar-import/page.test.tsx`
Expected: FAIL because the page and typed API client do not exist yet.

- [ ] **Step 3: Implement the page, finish docs, and wire the final task handoff**

```tsx
export default function CustomerCalendarImportPage() {
  const [preflight, setPreflight] = useState<CalendarImportPreflight | null>(null);
  const [run, setRun] = useState<CalendarImportRun | null>(null);

  useEffect(() => {
    void customerGoogleCalendarImportApi.getPreflight().then((res) => {
      if (res.ok) {
        setPreflight(res.data);
      }
    });
  }, []);

  async function handleStart() {
    const res = await customerGoogleCalendarImportApi.start();
    if (res.ok) {
      window.open(res.data.url, '_self');
    }
  }
}
```

```md
- `gateway` now exposes a first-version Google Calendar import flow.
- The gateway performs OAuth and calendar fetch.
- The Coke bridge resolves the target private conversation and writes imported reminders into `deferred_actions`.
- Historical imports are written as completed reminders and do not schedule future work.
```

- [ ] **Step 4: Run the final feature-focused verification commands**

Run:
- `cd gateway/packages/api && npm test -- src/routes/customer-claim-routes.test.ts src/routes/customer-google-calendar-import-routes.test.ts`
- `cd gateway/packages/web && npm test -- app/(customer)/auth/claim/page.test.tsx app/(customer)/auth/claim-entry/page.test.tsx app/(customer)/account/calendar-import/page.test.tsx`
- `pytest tests/unit/dao/test_conversation_dao_calendar_import.py tests/unit/dao/test_deferred_action_dao.py tests/unit/agent/test_deferred_action_service.py tests/unit/connector/clawscale_bridge/test_google_calendar_import_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -v`
- `pytest tests/unit/test_repo_os_structure.py -v`
- `zsh scripts/check`

Expected: PASS across gateway API, gateway web, bridge/runtime, and repo-OS checks.

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/web/app/'(customer)'/account/calendar-import/page.tsx \
  gateway/packages/web/app/'(customer)'/account/calendar-import/page.test.tsx \
  docs/architecture.md \
  docs/fitness/coke-verification-matrix.md \
  tasks/2026-04-22-google-calendar-import-design.md
git commit -m "feat(web): add google calendar import entry and summary"
```

## Self-Review

### Spec coverage

- Claim-entry link, email-first claim, and post-claim continuation are covered by Task 2.
- Google OAuth, `primary` calendar fetch, import-run audit, and callback handling are covered by Task 3.
- Conversation-scoped target resolution, historical import semantics, and recurring-import constraints are covered by Tasks 4 and 5.
- Customer-facing import screen and run summary are covered by Task 6.
- Batch-level verification and docs updates are covered by Task 6.

No spec requirement is intentionally left without a task.

### Placeholder scan

- No unfinished placeholder markers remain.
- Migration folder name, route paths, file paths, and commands are concrete.
- Every code-writing step includes an explicit code block.

### Type consistency

- `CalendarImportRun` consistently uses `targetConversationId` and `targetCharacterId`.
- Claim continuation consistently uses `continueTo`.
- Customer-facing route paths consistently use `/api/customer/google-calendar-import/*`.
- Bridge internal paths consistently use `/bridge/internal/google-calendar-import/*`.

## Execution Handoff

Plan complete and saved to `docs/exec-plans/2026-04-22-google-calendar-import.md`.

Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints
