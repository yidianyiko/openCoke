# Gateway Auth, Email, Stripe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Coke user auth, email verification, password reset, and Stripe payment from the Python Bridge into the Gateway, propagate account-access state into Bridge/Agent runtime, and update the Coke web app to the new `/api/coke/*` contract.

**Architecture:** Keep Gateway as the single source of truth for `CokeAccount`, `Subscription`, and `VerifyToken` in Postgres via Prisma. Bridge becomes a thin business-only adapter that receives precomputed access metadata from Gateway, blocks denied users before enqueue, and forwards enough Coke account metadata into Mongo input messages for the Agent identity adapter. Agent runtime stops resolving Coke users through Mongo `users._id` and instead uses a synthetic Coke-account context keyed by `CokeAccount.id`.

**Tech Stack:** Python 3.12, Flask, PyMongo, pytest, TypeScript, Hono, Prisma, PostgreSQL, Next.js, Vitest, pnpm, Stripe Checkout, bcryptjs, jsonwebtoken, Nodemailer

---

## Scope Check

This spec spans Gateway, Bridge, Agent, and web frontend, but it is one vertical feature slice: Coke account lifecycle and access gating. Keep it in one plan and execute in dependency order: Gateway data model first, public API second, message-path propagation third, Agent identity fourth, frontend last.

## File Structure

### New Gateway files

- `gateway/packages/api/src/lib/coke-auth.ts`
  Coke-only auth helpers: email normalization, bcrypt password helpers, JWT issue/verify, SHA-256 token hashing.
- `gateway/packages/api/src/lib/coke-auth.test.ts`
  Covers auth helpers and token hashing.
- `gateway/packages/api/src/lib/coke-subscription.ts`
  Shared helpers for latest subscription lookup, stacked expiry calculation, and checkout renewal URL building.
- `gateway/packages/api/src/lib/coke-subscription.test.ts`
  Covers active/expired subscription snapshots and stacking math.
- `gateway/packages/api/src/lib/coke-account-access.ts`
  Computes the combined access decision used by `/api/coke/*`, `route-message.ts`, and Bridge gating.
- `gateway/packages/api/src/lib/coke-account-access.test.ts`
  Covers normal, unverified, suspended, and expired-account access decisions.
- `gateway/packages/api/src/lib/email.ts`
  Mailgun-first, SMTP-fallback email sender plus concrete verification/reset email builders.
- `gateway/packages/api/src/middleware/coke-user-auth.ts`
  Hono middleware for Coke-user JWT auth, separate from member dashboard auth.
- `gateway/packages/api/src/routes/coke-auth-routes.ts`
  Public `/api/coke/register`, `/login`, `/verify-email`, `/resend-verification`, `/forgot-password`, `/reset-password`, `/me`.
- `gateway/packages/api/src/routes/coke-auth-routes.test.ts`
  Route tests for auth lifecycle and `/me`.
- `gateway/packages/api/src/routes/coke-payment-routes.ts`
  Public `/api/coke/checkout`, `/stripe-webhook`, `/subscription`.
- `gateway/packages/api/src/routes/coke-payment-routes.test.ts`
  Route tests for checkout, duplicate webhook handling, and subscription snapshot.
- `gateway/packages/api/src/routes/coke-wechat-routes.ts`
  Public `/api/coke/wechat-channel*` routes gated by combined Coke account access.
- `gateway/packages/api/src/routes/coke-wechat-routes.test.ts`
  Covers account-suspended, email-not-verified, subscription-required, and success paths.

### Modified Gateway files

- `gateway/packages/api/package.json`
  Add runtime deps for `stripe` and `nodemailer`.
- `gateway/packages/api/prisma/schema.prisma`
  Add `CokeAccountStatus`, `CokeAccount`, `Subscription`, `VerifyToken`, and `ClawscaleUser.account`.
- `gateway/packages/api/src/index.ts`
  Mount the new `/api/coke/*` routers.
- `gateway/packages/api/src/lib/clawscale-user.ts`
  Ensure provisioning works with `CokeAccount` rows and no longer depends on Bridge registration/login.
- `gateway/packages/api/src/lib/clawscale-user.test.ts`
  Update helper expectations for Gateway-owned account provisioning.
- `gateway/packages/api/src/lib/route-message.ts`
  Compute account-access metadata for personal Coke channels before calling the Bridge-backed custom backend.
- `gateway/packages/api/src/lib/route-message.test.ts`
  Assert the Bridge request metadata contains the new account-access envelope.
- `gateway/packages/api/src/lib/ai-backend.test.ts`
  Extend metadata-envelope assertions to the new access fields.
- `gateway/packages/web/lib/coke-user-api.ts`
  Point all Coke-user requests at `/api/coke/*`.
- `gateway/packages/web/lib/coke-user-auth.ts`
  Store the richer Coke-user profile returned by Gateway.
- `gateway/packages/web/lib/coke-user-wechat-channel.ts`
  Switch route paths from `/user/wechat-channel*` to `/api/coke/wechat-channel*`.
- `gateway/packages/web/lib/coke-user-wechat-channel.test.ts`
  Assert the new route paths.
- `gateway/packages/web/lib/coke-user-api-empty-body.test.ts`
  Keep the empty-body delete behavior covered after the route-path change.
- `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`
  Use `/api/coke/login`, surface verification/subscription status, and redirect correctly.
- `gateway/packages/web/app/(coke-user)/coke/register/page.tsx`
  Use `/api/coke/register` and show the verification-required next step.
- `gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.tsx`
  Enforce the new account-access states.
- `gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.test.tsx`
  Cover the new blocked states and the `/api/coke/wechat-channel` paths.

### New web app files

- `gateway/packages/web/app/(coke-user)/coke/verify-email/page.tsx`
- `gateway/packages/web/app/(coke-user)/coke/forgot-password/page.tsx`
- `gateway/packages/web/app/(coke-user)/coke/reset-password/page.tsx`
- `gateway/packages/web/app/(coke-user)/coke/payment-success/page.tsx`
- `gateway/packages/web/app/(coke-user)/coke/payment-cancel/page.tsx`
- `gateway/packages/web/app/(coke-user)/coke/renew/page.tsx`
- `gateway/packages/web/app/(coke-user)/coke/verify-email/page.test.tsx`
- `gateway/packages/web/app/(coke-user)/coke/renew/page.test.tsx`

### New Agent files

- `agent/runner/identity.py`
  Canonical Coke-account identity adapter for runner/context/message formatting.
- `tests/unit/runner/test_identity.py`
  Covers Mongo users, synthetic Coke-account users, and invalid nontrusted IDs.
- `tests/unit/runner/test_message_processor_identity.py`
  Covers `MessageAcquirer` with `CokeAccount.id` in `inputmessages.from_user`.
- `tests/unit/runner/test_dispatcher_without_gate.py`
  Proves `MessageDispatcher` no longer imports or instantiates `AccessGate`.

### Modified Agent files

- `agent/runner/message_processor.py`
  Resolve Coke accounts without `UserDAO.get_user_by_id`, persist metadata needed for synthetic users, and remove `AccessGate`.
- `agent/runner/context.py`
  Build relation keys from canonical IDs instead of raw Mongo `_id` assumptions.
- `agent/runner/agent_handler.py`
  Use canonical IDs in new-message checks and drop gate-denied/gate-expired branches.
- `agent/runner/agent_background_handler.py`
  Skip or safely handle synthetic Coke-account users where Mongo-only background flows still assume real `users` rows.
- `agent/util/message_util.py`
  Resolve talker labels from message metadata or synthetic user context for business messages.
- `agent/agno_agent/workflows/prepare_workflow.py`
- `agent/agno_agent/workflows/post_analyze_workflow.py`
- `agent/agno_agent/tools/reminder_tools.py`
- `agent/agno_agent/tools/reminder/service.py`
- `agent/agno_agent/tools/reminder/validator.py`
- `agent/agno_agent/tools/timezone_tools.py`
- `agent/agno_agent/tools/context_retrieve_tool.py`
- `agent/agno_agent/utils/usage_tracker.py`
  Read `session_state["user"]["id"]` instead of `_id`.

### Modified Bridge files

- `connector/clawscale_bridge/app.py`
  Remove `/user/*` routes, normalize the new access envelope from Gateway metadata, block denied users before enqueue, and forward the remaining Coke-account metadata to `message_gateway.enqueue`.
- `connector/clawscale_bridge/message_gateway.py`
  Persist Coke-account metadata on business input messages so Agent synthetic-user resolution has enough context.
- `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
  Cover the new account-access-denied replies and the absence of `/user/*` routes.
- `tests/unit/connector/clawscale_bridge/test_message_gateway.py`
  Assert Coke-account metadata is written into `inputmessages.metadata`.

### Files to delete during cleanup

- `connector/clawscale_bridge/user_auth.py`
- `connector/clawscale_bridge/gateway_user_provision_client.py`
- `agent/runner/access_gate.py`
- `agent/runner/payment/base.py`
- `agent/runner/payment/creem_provider.py`
- `agent/runner/payment/stripe_provider.py`
- `tests/unit/runner/test_access_gate.py`
- `tests/unit/runner/test_message_dispatcher_gate.py`
- `tests/unit/runner/payment/test_base.py`
- `tests/unit/runner/payment/test_creem_provider.py`
- `tests/unit/runner/payment/test_stripe_provider.py`
- `tests/unit/connector/clawscale_bridge/test_gateway_user_provision_client.py`

---

## Task 1: Add Gateway Coke account schema and core auth/access helpers

**Files:**
- Modify: `gateway/packages/api/package.json`
- Modify: `gateway/packages/api/prisma/schema.prisma`
- Create: `gateway/packages/api/src/lib/coke-auth.ts`
- Create: `gateway/packages/api/src/lib/coke-auth.test.ts`
- Create: `gateway/packages/api/src/lib/coke-subscription.ts`
- Create: `gateway/packages/api/src/lib/coke-subscription.test.ts`
- Create: `gateway/packages/api/src/lib/coke-account-access.ts`
- Create: `gateway/packages/api/src/lib/coke-account-access.test.ts`
- Create: `gateway/packages/api/src/lib/email.ts`

- [ ] **Step 1: Write the failing helper tests**

```ts
import { describe, expect, it, vi, beforeEach } from 'vitest';

const db = vi.hoisted(() => ({
  subscription: { findFirst: vi.fn() },
}));

vi.mock('../db/index.js', () => ({ db }));

import { normalizeEmail, sha256Hex } from './coke-auth.js';
import {
  calculateStackedAccessWindow,
  getSubscriptionSnapshot,
} from './coke-subscription.js';
import { resolveCokeAccountAccess } from './coke-account-access.js';

describe('coke-auth helpers', () => {
  it('normalizes email deterministically', () => {
    expect(normalizeEmail('  Alice@Example.COM ')).toBe('alice@example.com');
    expect(sha256Hex('token-123')).toHaveLength(64);
  });
});

describe('coke-subscription helpers', () => {
  beforeEach(() => vi.clearAllMocks());

  it('marks a future subscription as active', async () => {
    db.subscription.findFirst.mockResolvedValue({
      expiresAt: new Date('2026-05-10T00:00:00.000Z'),
    });

    await expect(getSubscriptionSnapshot('acct_1', new Date('2026-04-10T00:00:00.000Z'))).resolves.toEqual({
      subscriptionActive: true,
      subscriptionExpiresAt: '2026-05-10T00:00:00.000Z',
    });
  });

  it('stacks from the previous expiry when access is still active', () => {
    expect(
      calculateStackedAccessWindow({
        now: new Date('2026-04-10T00:00:00.000Z'),
        latestExpiresAt: new Date('2026-04-20T00:00:00.000Z'),
      }),
    ).toEqual({
      startsAt: '2026-04-20T00:00:00.000Z',
      expiresAt: '2026-05-20T00:00:00.000Z',
    });
  });
});

describe('resolveCokeAccountAccess', () => {
  beforeEach(() => vi.clearAllMocks());

  it('returns subscription_required when the account is normal and verified but expired', async () => {
    db.subscription.findFirst.mockResolvedValue({
      expiresAt: new Date('2026-04-01T00:00:00.000Z'),
    });

    await expect(
      resolveCokeAccountAccess({
        account: {
          id: 'acct_1',
          status: 'normal',
          emailVerified: true,
          displayName: 'Alice',
        },
        now: new Date('2026-04-10T00:00:00.000Z'),
        renewalUrl: 'https://coke.app/coke/renew',
      }),
    ).resolves.toMatchObject({
      accountAccessAllowed: false,
      accountAccessDeniedReason: 'subscription_required',
    });
  });
});
```

- [ ] **Step 2: Run the helper tests to confirm the missing modules fail**

Run: `pnpm --dir gateway/packages/api test -- src/lib/coke-auth.test.ts src/lib/coke-subscription.test.ts src/lib/coke-account-access.test.ts`

Expected: FAIL with module-not-found errors for the new Coke helper files.

- [ ] **Step 3: Add the Prisma models, install runtime deps, and implement the helper files**

Run:

```bash
pnpm --dir gateway/packages/api add stripe nodemailer
pnpm --dir gateway/packages/api add -D @types/nodemailer
```

```prisma
enum CokeAccountStatus {
  normal
  suspended
}

enum VerifyTokenType {
  email_verify
  password_reset
}

model CokeAccount {
  id            String            @id @default(cuid())
  email         String            @unique
  passwordHash  String            @map("password_hash")
  displayName   String            @map("display_name")
  emailVerified Boolean           @default(false) @map("email_verified")
  status        CokeAccountStatus @default(normal)
  createdAt     DateTime          @default(now()) @map("created_at")
  updatedAt     DateTime          @updatedAt @map("updated_at")

  clawscaleUser ClawscaleUser?
  subscriptions Subscription[]
  verifyTokens  VerifyToken[]

  @@map("coke_accounts")
}

model Subscription {
  id              String   @id @default(cuid())
  cokeAccountId   String   @map("coke_account_id")
  stripeSessionId String   @unique @map("stripe_session_id")
  amountPaid      Int      @map("amount_paid")
  currency        String   @default("usd")
  startsAt        DateTime @map("starts_at")
  expiresAt       DateTime @map("expires_at")
  createdAt       DateTime @default(now()) @map("created_at")

  account CokeAccount @relation(fields: [cokeAccountId], references: [id], onDelete: Cascade)

  @@index([cokeAccountId])
  @@index([cokeAccountId, expiresAt])
  @@map("subscriptions")
}

model VerifyToken {
  id            String          @id @default(cuid())
  cokeAccountId String          @map("coke_account_id")
  tokenHash     String          @unique @map("token_hash")
  type          VerifyTokenType
  expiresAt     DateTime        @map("expires_at")
  used          Boolean         @default(false)
  createdAt     DateTime        @default(now()) @map("created_at")

  account CokeAccount @relation(fields: [cokeAccountId], references: [id], onDelete: Cascade)

  @@index([cokeAccountId])
  @@map("verify_tokens")
}
```

```ts
import bcrypt from 'bcryptjs';
import crypto from 'node:crypto';
import jwt from 'jsonwebtoken';

const cokeJwtSecret = process.env['COKE_JWT_SECRET'] ?? 'dev-coke-secret-change-me';

export interface CokeJwtPayload {
  sub: string;
  email: string;
  iat?: number;
  exp?: number;
}

export function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

export async function hashPassword(password: string): Promise<string> {
  return bcrypt.hash(password, 10);
}

export async function verifyPassword(password: string, passwordHash: string): Promise<boolean> {
  return bcrypt.compare(password, passwordHash);
}

export function signCokeToken(payload: Omit<CokeJwtPayload, 'iat' | 'exp'>): string {
  return jwt.sign(payload, cokeJwtSecret, { expiresIn: '7d' });
}

export function verifyCokeToken(token: string): CokeJwtPayload {
  return jwt.verify(token, cokeJwtSecret) as CokeJwtPayload;
}

export function sha256Hex(value: string): string {
  return crypto.createHash('sha256').update(value).digest('hex');
}

export function issueVerifyToken(): { plainToken: string; tokenHash: string } {
  const plainToken = crypto.randomBytes(32).toString('hex');
  return { plainToken, tokenHash: sha256Hex(plainToken) };
}
```

```ts
import { db } from '../db/index.js';

export interface SubscriptionSnapshot {
  subscriptionActive: boolean;
  subscriptionExpiresAt: string | null;
}

export function calculateStackedAccessWindow(input: {
  now: Date;
  latestExpiresAt: Date | null;
}): { startsAt: string; expiresAt: string } {
  const startsAt = input.latestExpiresAt && input.latestExpiresAt > input.now
    ? input.latestExpiresAt
    : input.now;
  const expiresAt = new Date(startsAt.getTime() + 30 * 24 * 60 * 60 * 1000);
  return {
    startsAt: startsAt.toISOString(),
    expiresAt: expiresAt.toISOString(),
  };
}

export async function getSubscriptionSnapshot(
  cokeAccountId: string,
  now = new Date(),
): Promise<SubscriptionSnapshot> {
  const latest = await db.subscription.findFirst({
    where: { cokeAccountId },
    orderBy: [{ expiresAt: 'desc' }],
    select: { expiresAt: true },
  });
  const active = !!latest?.expiresAt && latest.expiresAt > now;
  return {
    subscriptionActive: active,
    subscriptionExpiresAt: latest?.expiresAt?.toISOString() ?? null,
  };
}

export function buildRenewalUrl(): string {
  return process.env['COKE_RENEWAL_URL']?.trim()
    || `${process.env['DOMAIN_CLIENT']?.replace(/\/$/, '')}/coke/renew`;
}
```

```ts
import { buildRenewalUrl, getSubscriptionSnapshot } from './coke-subscription.js';

export interface CokeAccountAccessDecision {
  accountStatus: 'normal' | 'suspended';
  emailVerified: boolean;
  subscriptionActive: boolean;
  subscriptionExpiresAt: string | null;
  accountAccessAllowed: boolean;
  accountAccessDeniedReason: 'email_not_verified' | 'subscription_required' | 'account_suspended' | null;
  renewalUrl: string;
}

export async function resolveCokeAccountAccess(input: {
  account: { id: string; status: 'normal' | 'suspended'; emailVerified: boolean; displayName: string };
  now?: Date;
  renewalUrl?: string;
}): Promise<CokeAccountAccessDecision> {
  const snapshot = await getSubscriptionSnapshot(input.account.id, input.now ?? new Date());
  if (input.account.status !== 'normal') {
    return {
      accountStatus: input.account.status,
      emailVerified: input.account.emailVerified,
      ...snapshot,
      accountAccessAllowed: false,
      accountAccessDeniedReason: 'account_suspended',
      renewalUrl: input.renewalUrl ?? buildRenewalUrl(),
    };
  }
  if (!input.account.emailVerified) {
    return {
      accountStatus: input.account.status,
      emailVerified: input.account.emailVerified,
      ...snapshot,
      accountAccessAllowed: false,
      accountAccessDeniedReason: 'email_not_verified',
      renewalUrl: input.renewalUrl ?? buildRenewalUrl(),
    };
  }
  if (!snapshot.subscriptionActive) {
    return {
      accountStatus: input.account.status,
      emailVerified: input.account.emailVerified,
      ...snapshot,
      accountAccessAllowed: false,
      accountAccessDeniedReason: 'subscription_required',
      renewalUrl: input.renewalUrl ?? buildRenewalUrl(),
    };
  }
  return {
    accountStatus: input.account.status,
    emailVerified: input.account.emailVerified,
    ...snapshot,
    accountAccessAllowed: true,
    accountAccessDeniedReason: null,
    renewalUrl: input.renewalUrl ?? buildRenewalUrl(),
  };
}
```

```ts
import nodemailer from 'nodemailer';

export async function sendCokeEmail(input: {
  to: string;
  subject: string;
  html: string;
}): Promise<void> {
  if (process.env['MAILGUN_API_KEY'] && process.env['MAILGUN_DOMAIN']) {
    const body = new URLSearchParams({
      from: process.env['EMAIL_FROM'] ?? 'noreply@keep4oforever.com',
      to: input.to,
      subject: input.subject,
      html: input.html,
    });
    const auth = Buffer.from(`api:${process.env['MAILGUN_API_KEY']}`).toString('base64');
    const res = await fetch(
      `https://api.mailgun.net/v3/${process.env['MAILGUN_DOMAIN']}/messages`,
      {
        method: 'POST',
        headers: { Authorization: `Basic ${auth}` },
        body,
      },
    );
    if (!res.ok) throw new Error(`mailgun_send_failed:${res.status}`);
    return;
  }

  const transporter = nodemailer.createTransport({
    host: process.env['EMAIL_HOST'],
    port: Number(process.env['EMAIL_PORT'] ?? 587),
    secure: Number(process.env['EMAIL_PORT'] ?? 587) === 465,
    auth: {
      user: process.env['EMAIL_USERNAME'],
      pass: process.env['EMAIL_PASSWORD'],
    },
  });

  await transporter.sendMail({
    from: process.env['EMAIL_FROM'] ?? 'noreply@keep4oforever.com',
    to: input.to,
    subject: input.subject,
    html: input.html,
  });
}
```

- [ ] **Step 4: Run the helper tests and generate Prisma client**

Run: `pnpm --dir gateway/packages/api test -- src/lib/coke-auth.test.ts src/lib/coke-subscription.test.ts src/lib/coke-account-access.test.ts`

Expected: PASS

Run: `pnpm --dir gateway/packages/api db:generate`

Expected: PASS with Prisma client generated for the new models.

Run: `pnpm --dir gateway/packages/api build`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/api/package.json gateway/packages/api/prisma/schema.prisma gateway/packages/api/src/lib/coke-auth.ts gateway/packages/api/src/lib/coke-auth.test.ts gateway/packages/api/src/lib/coke-subscription.ts gateway/packages/api/src/lib/coke-subscription.test.ts gateway/packages/api/src/lib/coke-account-access.ts gateway/packages/api/src/lib/coke-account-access.test.ts gateway/packages/api/src/lib/email.ts
git commit -m "feat(coke-api): add coke account auth and access core"
```

## Task 2: Add public Coke auth and payment routes on Gateway

**Files:**
- Create: `gateway/packages/api/src/middleware/coke-user-auth.ts`
- Create: `gateway/packages/api/src/routes/coke-auth-routes.ts`
- Create: `gateway/packages/api/src/routes/coke-auth-routes.test.ts`
- Create: `gateway/packages/api/src/routes/coke-payment-routes.ts`
- Create: `gateway/packages/api/src/routes/coke-payment-routes.test.ts`
- Modify: `gateway/packages/api/src/index.ts`
- Modify: `gateway/packages/api/src/lib/clawscale-user.ts`
- Modify: `gateway/packages/api/src/lib/clawscale-user.test.ts`

- [ ] **Step 1: Write failing route tests for `/api/coke/register`, `/me`, `/checkout`, and `/stripe-webhook`**

```ts
import { Hono } from 'hono';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const db = vi.hoisted(() => ({
  cokeAccount: {
    findUnique: vi.fn(),
    findFirst: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
  },
  verifyToken: {
    create: vi.fn(),
    findFirst: vi.fn(),
    update: vi.fn(),
  },
  subscription: {
    findFirst: vi.fn(),
    create: vi.fn(),
  },
  $transaction: vi.fn(async (fn: (tx: typeof db) => Promise<unknown>) => fn(db)),
  $queryRaw: vi.fn(),
}));

const ensureClawscaleUserForCokeAccount = vi.hoisted(() => vi.fn());
const sendCokeEmail = vi.hoisted(() => vi.fn());
const stripeCheckoutCreate = vi.hoisted(() => vi.fn());
const constructEvent = vi.hoisted(() => vi.fn());

vi.mock('../db/index.js', () => ({ db }));
vi.mock('../lib/clawscale-user.js', () => ({ ensureClawscaleUserForCokeAccount }));
vi.mock('../lib/email.js', () => ({ sendCokeEmail }));
vi.mock('stripe', () => ({
  default: class Stripe {
    checkout = { sessions: { create: stripeCheckoutCreate } };
    webhooks = { constructEvent };
  },
}));

import { cokeAuthRouter } from './coke-auth-routes.js';
import { cokePaymentRouter } from './coke-payment-routes.js';

describe('coke auth routes', () => {
  beforeEach(() => vi.clearAllMocks());

  it('registers a new account and provisions a personal tenant', async () => {
    const app = new Hono();
    app.route('/api/coke', cokeAuthRouter);
    db.cokeAccount.findUnique.mockResolvedValue(null);
    db.cokeAccount.create.mockResolvedValue({
      id: 'acct_1',
      email: 'alice@example.com',
      displayName: 'Alice',
      emailVerified: false,
      status: 'normal',
    });
    ensureClawscaleUserForCokeAccount.mockResolvedValue({
      tenantId: 'ten_1',
      clawscaleUserId: 'csu_1',
      created: true,
      ready: true,
    });

    const res = await app.request('/api/coke/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ displayName: 'Alice', email: 'Alice@example.com', password: 'password123' }),
    });

    expect(res.status).toBe(201);
    expect(sendCokeEmail).toHaveBeenCalledOnce();
    expect(ensureClawscaleUserForCokeAccount).toHaveBeenCalledWith({
      cokeAccountId: 'acct_1',
      displayName: 'Alice',
    });
  });
});

describe('coke payment routes', () => {
  beforeEach(() => vi.clearAllMocks());

  it('rejects checkout when email is not verified', async () => {
    const app = new Hono();
    app.route('/api/coke', cokePaymentRouter);
    const res = await app.request('/api/coke/checkout', {
      method: 'POST',
      headers: { Authorization: 'Bearer invalid' },
    });
    expect(res.status).toBe(401);
  });

  it('treats duplicate stripe sessions as already processed', async () => {
    const app = new Hono();
    app.route('/api/coke', cokePaymentRouter);
    constructEvent.mockReturnValue({
      type: 'checkout.session.completed',
      data: {
        object: {
          id: 'cs_test_1',
          payment_status: 'paid',
          amount_total: 900,
          currency: 'usd',
          metadata: { cokeAccountId: 'acct_1' },
        },
      },
    });
    db.subscription.create.mockRejectedValue({ code: 'P2002' });

    const res = await app.request('/api/coke/stripe-webhook', {
      method: 'POST',
      headers: { 'stripe-signature': 'sig_1' },
      body: '{}',
    });

    expect(res.status).toBe(200);
  });
});
```

- [ ] **Step 2: Run the route tests to verify the routers do not exist yet**

Run: `pnpm --dir gateway/packages/api test -- src/routes/coke-auth-routes.test.ts src/routes/coke-payment-routes.test.ts`

Expected: FAIL with module-not-found errors for `coke-auth-routes.ts`, `coke-payment-routes.ts`, and `coke-user-auth.ts`.

- [ ] **Step 3: Implement the Coke-user auth middleware and the public auth/payment routers**

```ts
import type { Context, Next } from 'hono';
import { verifyCokeToken, type CokeJwtPayload } from '../lib/coke-auth.js';

export interface CokeUserAuthContext {
  accountId: string;
  email: string;
}

declare module 'hono' {
  interface ContextVariableMap {
    cokeAuth: CokeUserAuthContext;
  }
}

export async function requireCokeUserAuth(c: Context, next: Next): Promise<Response | void> {
  const header = c.req.header('Authorization');
  if (!header?.startsWith('Bearer ')) {
    return c.json({ ok: false, error: 'unauthorized' }, 401);
  }
  let payload: CokeJwtPayload;
  try {
    payload = verifyCokeToken(header.slice(7));
  } catch {
    return c.json({ ok: false, error: 'invalid_or_expired_token' }, 401);
  }
  c.set('cokeAuth', { accountId: payload.sub, email: payload.email });
  await next();
}
```

```ts
import { Hono } from 'hono';
import { z } from 'zod';
import { zValidator } from '@hono/zod-validator';
import { db } from '../db/index.js';
import {
  hashPassword,
  issueVerifyToken,
  normalizeEmail,
  sha256Hex,
  signCokeToken,
  verifyPassword,
} from '../lib/coke-auth.js';
import { resolveCokeAccountAccess } from '../lib/coke-account-access.js';
import { sendCokeEmail } from '../lib/email.js';
import { requireCokeUserAuth } from '../middleware/coke-user-auth.js';
import { ensureClawscaleUserForCokeAccount } from '../lib/clawscale-user.js';

const registerSchema = z.object({
  displayName: z.string().min(1),
  email: z.string().email(),
  password: z.string().min(8),
});

export const cokeAuthRouter = new Hono()
  .post('/register', zValidator('json', registerSchema), async (c) => {
    const input = c.req.valid('json');
    const email = normalizeEmail(input.email);
    const existing = await db.cokeAccount.findUnique({ where: { email } });
    if (existing) return c.json({ ok: false, error: 'email_already_exists' }, 409);

    const created = await db.cokeAccount.create({
      data: {
        email,
        displayName: input.displayName.trim(),
        passwordHash: await hashPassword(input.password),
      },
    });
    await ensureClawscaleUserForCokeAccount({
      cokeAccountId: created.id,
      displayName: created.displayName,
    });
    const { plainToken, tokenHash } = issueVerifyToken();
    await db.verifyToken.create({
      data: {
        cokeAccountId: created.id,
        tokenHash,
        type: 'email_verify',
        expiresAt: new Date(Date.now() + 15 * 60 * 1000),
      },
    });
    await sendCokeEmail({
      to: created.email,
      subject: 'Verify your Coke email',
      html: `<a href="${process.env['DOMAIN_CLIENT']}/coke/verify-email?token=${plainToken}&email=${created.email}">Verify</a>`,
    });
    const token = signCokeToken({ sub: created.id, email: created.email });
    return c.json({
      ok: true,
      data: {
        token,
        user: {
          id: created.id,
          email: created.email,
          display_name: created.displayName,
          email_verified: created.emailVerified,
          status: created.status,
        },
      },
    }, 201);
  })
  .post('/login', zValidator('json', z.object({ email: z.string().email(), password: z.string().min(1) })), async (c) => {
    const input = c.req.valid('json');
    const account = await db.cokeAccount.findUnique({ where: { email: normalizeEmail(input.email) } });
    if (!account || !(await verifyPassword(input.password, account.passwordHash))) {
      return c.json({ ok: false, error: 'invalid_credentials' }, 401);
    }
    if (account.status !== 'normal') {
      return c.json({ ok: false, error: 'account_suspended' }, 403);
    }
    const access = await resolveCokeAccountAccess({ account });
    return c.json({
      ok: true,
      data: {
        token: signCokeToken({ sub: account.id, email: account.email }),
        user: {
          id: account.id,
          email: account.email,
          display_name: account.displayName,
          email_verified: account.emailVerified,
          status: account.status,
          subscription_active: access.subscriptionActive,
          subscription_expires_at: access.subscriptionExpiresAt,
        },
      },
    });
  })
  .get('/me', requireCokeUserAuth, async (c) => {
    const auth = c.get('cokeAuth');
    const account = await db.cokeAccount.findUnique({ where: { id: auth.accountId } });
    if (!account) return c.json({ ok: false, error: 'account_not_found' }, 404);
    const access = await resolveCokeAccountAccess({ account });
    return c.json({
      ok: true,
      data: {
        id: account.id,
        email: account.email,
        display_name: account.displayName,
        email_verified: account.emailVerified,
        status: account.status,
        subscription_active: access.subscriptionActive,
        subscription_expires_at: access.subscriptionExpiresAt,
      },
    });
  });
```

```ts
import { Hono } from 'hono';
import Stripe from 'stripe';
import { db } from '../db/index.js';
import { requireCokeUserAuth } from '../middleware/coke-user-auth.js';
import { resolveCokeAccountAccess } from '../lib/coke-account-access.js';
import { calculateStackedAccessWindow } from '../lib/coke-subscription.js';

const stripe = new Stripe(process.env['STRIPE_SECRET_KEY'] ?? '');

export const cokePaymentRouter = new Hono()
  .post('/checkout', requireCokeUserAuth, async (c) => {
    const auth = c.get('cokeAuth');
    const account = await db.cokeAccount.findUnique({ where: { id: auth.accountId } });
    if (!account) return c.json({ ok: false, error: 'account_not_found' }, 404);
    if (account.status !== 'normal') return c.json({ ok: false, error: 'account_suspended' }, 403);
    if (!account.emailVerified) return c.json({ ok: false, error: 'email_not_verified' }, 403);

    const session = await stripe.checkout.sessions.create({
      mode: 'payment',
      payment_method_types: ['card'],
      line_items: [{ price: process.env['STRIPE_PRICE_ID'] ?? '', quantity: 1 }],
      success_url: `${process.env['DOMAIN_CLIENT']}/coke/payment-success`,
      cancel_url: `${process.env['DOMAIN_CLIENT']}/coke/payment-cancel`,
      metadata: { cokeAccountId: account.id },
    });

    return c.json({ ok: true, data: { url: session.url } });
  })
  .get('/subscription', requireCokeUserAuth, async (c) => {
    const auth = c.get('cokeAuth');
    const account = await db.cokeAccount.findUnique({ where: { id: auth.accountId } });
    if (!account) return c.json({ ok: false, error: 'account_not_found' }, 404);
    return c.json({ ok: true, data: await resolveCokeAccountAccess({ account }) });
  })
  .post('/stripe-webhook', async (c) => {
    const rawBody = await c.req.text();
    const event = stripe.webhooks.constructEvent(
      rawBody,
      c.req.header('stripe-signature') ?? '',
      process.env['STRIPE_WEBHOOK_SECRET'] ?? '',
    );
    if (event.type !== 'checkout.session.completed') {
      return c.json({ ok: true });
    }
    const session = event.data.object as Stripe.Checkout.Session;
    if (session.payment_status !== 'paid') return c.json({ ok: true });

    await db.$transaction(async (tx) => {
      const cokeAccountId = String(session.metadata?.cokeAccountId ?? '');
      await tx.$queryRaw`SELECT id FROM coke_accounts WHERE id = ${cokeAccountId} FOR UPDATE`;
      const latest = await tx.subscription.findFirst({
        where: { cokeAccountId },
        orderBy: [{ expiresAt: 'desc' }],
        select: { expiresAt: true },
      });
      const window = calculateStackedAccessWindow({
        now: new Date(),
        latestExpiresAt: latest?.expiresAt ?? null,
      });
      try {
        await tx.subscription.create({
          data: {
            cokeAccountId,
            stripeSessionId: session.id,
            amountPaid: session.amount_total ?? 0,
            currency: session.currency ?? 'usd',
            startsAt: new Date(window.startsAt),
            expiresAt: new Date(window.expiresAt),
          },
        });
      } catch (error) {
        if ((error as { code?: string }).code !== 'P2002') throw error;
      }
    });

    return c.json({ ok: true });
  });
```

```ts
app.route('/api/coke', cokeAuthRouter);
app.route('/api/coke', cokePaymentRouter);
```

- [ ] **Step 4: Run the route tests and the API build**

Run: `pnpm --dir gateway/packages/api test -- src/routes/coke-auth-routes.test.ts src/routes/coke-payment-routes.test.ts src/lib/clawscale-user.test.ts`

Expected: PASS

Run: `pnpm --dir gateway/packages/api build`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/api/src/middleware/coke-user-auth.ts gateway/packages/api/src/routes/coke-auth-routes.ts gateway/packages/api/src/routes/coke-auth-routes.test.ts gateway/packages/api/src/routes/coke-payment-routes.ts gateway/packages/api/src/routes/coke-payment-routes.test.ts gateway/packages/api/src/index.ts gateway/packages/api/src/lib/clawscale-user.ts gateway/packages/api/src/lib/clawscale-user.test.ts
git commit -m "feat(coke-api): add public coke auth and payment routes"
```

## Task 3: Add public Coke WeChat routes gated by account access

**Files:**
- Create: `gateway/packages/api/src/routes/coke-wechat-routes.ts`
- Create: `gateway/packages/api/src/routes/coke-wechat-routes.test.ts`
- Modify: `gateway/packages/api/src/index.ts`
- Modify: `gateway/packages/api/src/routes/user-wechat-channel.ts`

- [ ] **Step 1: Write the failing WeChat-route tests**

```ts
import { Hono } from 'hono';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const db = vi.hoisted(() => ({
  cokeAccount: { findUnique: vi.fn() },
}));
const ensureClawscaleUserForCokeAccount = vi.hoisted(() => vi.fn());
const createOrReusePersonalWeChatChannel = vi.hoisted(() => vi.fn());
const startWeixinQR = vi.hoisted(() => vi.fn());

vi.mock('../db/index.js', () => ({ db }));
vi.mock('../lib/clawscale-user.js', () => ({ ensureClawscaleUserForCokeAccount }));
vi.mock('../lib/personal-wechat-channel.js', () => ({
  createOrReusePersonalWeChatChannel,
}));
vi.mock('../adapters/wechat.js', () => ({
  startWeixinQR,
  getWeixinQR: vi.fn(),
  getWeixinStatus: vi.fn(() => 'disconnected'),
  getWeixinRestoreState: vi.fn(() => 'idle'),
  stopWeixinBot: vi.fn(),
}));

import { cokeWechatRouter } from './coke-wechat-routes.js';

describe('coke-wechat-routes', () => {
  beforeEach(() => vi.clearAllMocks());

  it('returns email_not_verified before provisioning the channel', async () => {
    const app = new Hono();
    app.route('/api/coke/wechat-channel', cokeWechatRouter);
    const res = await app.request('/api/coke/wechat-channel', {
      method: 'POST',
      headers: { Authorization: 'Bearer invalid' },
    });
    expect(res.status).toBe(401);
  });

  it('returns subscription_required for connect when the account has no active access', async () => {
    const app = new Hono();
    app.route('/api/coke/wechat-channel', cokeWechatRouter);
    db.cokeAccount.findUnique.mockResolvedValue({
      id: 'acct_1',
      email: 'alice@example.com',
      displayName: 'Alice',
      emailVerified: true,
      status: 'normal',
    });
    const res = await app.request('/api/coke/wechat-channel/connect', {
      method: 'POST',
      headers: { Authorization: 'Bearer invalid' },
    });
    expect(res.status).toBe(401);
  });
});
```

- [ ] **Step 2: Run the WeChat-route tests**

Run: `pnpm --dir gateway/packages/api test -- src/routes/coke-wechat-routes.test.ts`

Expected: FAIL with module-not-found for `coke-wechat-routes.ts`.

- [ ] **Step 3: Implement the public WeChat router and reuse the existing lifecycle helpers**

```ts
import { Hono } from 'hono';
import { db } from '../db/index.js';
import { requireCokeUserAuth } from '../middleware/coke-user-auth.js';
import { resolveCokeAccountAccess } from '../lib/coke-account-access.js';
import { ensureClawscaleUserForCokeAccount } from '../lib/clawscale-user.js';
import {
  archivePersonalWeChatChannel,
  createOrReusePersonalWeChatChannel,
  disconnectPersonalWeChatChannel,
} from '../lib/personal-wechat-channel.js';
import {
  getWeixinQR,
  getWeixinRestoreState,
  getWeixinStatus,
  startWeixinQR,
  stopWeixinBot,
} from '../adapters/wechat.js';

async function loadAuthorizedCokeAccount(accountId: string) {
  const account = await db.cokeAccount.findUnique({ where: { id: accountId } });
  if (!account) throw new Error('account_not_found');
  const access = await resolveCokeAccountAccess({ account });
  return { account, access };
}

export const cokeWechatRouter = new Hono()
  .use('*', requireCokeUserAuth)
  .post('/', async (c) => {
    const auth = c.get('cokeAuth');
    const { account, access } = await loadAuthorizedCokeAccount(auth.accountId);
    if (account.status !== 'normal') return c.json({ ok: false, error: 'account_suspended' }, 403);
    if (!account.emailVerified) return c.json({ ok: false, error: 'email_not_verified' }, 403);

    const ensured = await ensureClawscaleUserForCokeAccount({
      cokeAccountId: account.id,
      displayName: account.displayName,
    });
    const channel = await createOrReusePersonalWeChatChannel({
      tenantId: ensured.tenantId,
      clawscaleUserId: ensured.clawscaleUserId,
    });
    return c.json({ ok: true, data: { channel_id: channel.id, status: channel.status } });
  })
  .post('/connect', async (c) => {
    const auth = c.get('cokeAuth');
    const { account, access } = await loadAuthorizedCokeAccount(auth.accountId);
    if (account.status !== 'normal') return c.json({ ok: false, error: 'account_suspended' }, 403);
    if (!account.emailVerified) return c.json({ ok: false, error: 'email_not_verified' }, 403);
    if (!access.subscriptionActive) return c.json({ ok: false, error: 'subscription_required' }, 402);

    const ensured = await ensureClawscaleUserForCokeAccount({
      cokeAccountId: account.id,
      displayName: account.displayName,
    });
    const channel = await createOrReusePersonalWeChatChannel({
      tenantId: ensured.tenantId,
      clawscaleUserId: ensured.clawscaleUserId,
    });
    await startWeixinQR(channel.id);
    const qr = getWeixinQR(channel.id);
    return c.json({
      ok: true,
      data: {
        channel_id: channel.id,
        status: 'pending',
        qr: qr?.image ?? null,
        qr_url: qr?.url ?? null,
        connect_url: qr?.url ?? null,
      },
    });
  })
  .get('/status', async (c) => {
    const auth = c.get('cokeAuth');
    const { account } = await loadAuthorizedCokeAccount(auth.accountId);
    const ensured = await ensureClawscaleUserForCokeAccount({
      cokeAccountId: account.id,
      displayName: account.displayName,
    });
    const liveStatus = getWeixinStatus(ensured.clawscaleUserId);
    return c.json({
      ok: true,
      data: {
        channel_id: ensured.clawscaleUserId,
        status: liveStatus,
        restore_state: getWeixinRestoreState(ensured.clawscaleUserId),
      },
    });
  })
  .post('/disconnect', async (c) => {
    const auth = c.get('cokeAuth');
    const { account } = await loadAuthorizedCokeAccount(auth.accountId);
    const ensured = await ensureClawscaleUserForCokeAccount({
      cokeAccountId: account.id,
      displayName: account.displayName,
    });
    await stopWeixinBot(ensured.clawscaleUserId);
    await disconnectPersonalWeChatChannel({
      tenantId: ensured.tenantId,
      clawscaleUserId: ensured.clawscaleUserId,
    });
    return c.json({ ok: true, data: { status: 'disconnected' } });
  })
  .delete('/', async (c) => {
    const auth = c.get('cokeAuth');
    const { account } = await loadAuthorizedCokeAccount(auth.accountId);
    const ensured = await ensureClawscaleUserForCokeAccount({
      cokeAccountId: account.id,
      displayName: account.displayName,
    });
    await archivePersonalWeChatChannel({
      tenantId: ensured.tenantId,
      clawscaleUserId: ensured.clawscaleUserId,
    });
    return c.json({ ok: true, data: { status: 'archived' } });
  });
```

```ts
app.route('/api/coke/wechat-channel', cokeWechatRouter);
```

- [ ] **Step 4: Run the WeChat route tests**

Run: `pnpm --dir gateway/packages/api test -- src/routes/coke-wechat-routes.test.ts`

Expected: PASS

Run: `pnpm --dir gateway/packages/api build`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/api/src/routes/coke-wechat-routes.ts gateway/packages/api/src/routes/coke-wechat-routes.test.ts gateway/packages/api/src/index.ts gateway/packages/api/src/routes/user-wechat-channel.ts
git commit -m "feat(coke-api): add public coke wechat routes"
```

## Task 4: Propagate account-access metadata into Bridge and block denied users before enqueue

**Files:**
- Modify: `gateway/packages/api/src/lib/route-message.ts`
- Modify: `gateway/packages/api/src/lib/route-message.test.ts`
- Modify: `gateway/packages/api/src/lib/ai-backend.test.ts`
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `connector/clawscale_bridge/message_gateway.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_message_gateway.py`

- [ ] **Step 1: Write failing metadata and Bridge-gate tests**

```ts
it('passes coke account access metadata to the Bridge backend for personal channels', async () => {
  db.channel.findUnique.mockResolvedValue({
    id: 'ch_1',
    tenantId: 'ten_1',
    status: 'connected',
    scope: 'personal',
    ownerClawscaleUserId: 'csu_1',
    ownerClawscaleUser: { id: 'csu_1', cokeAccountId: 'acct_1' },
  });
  db.endUser.findUnique.mockResolvedValue({
    id: 'eu_1',
    tenantId: 'ten_1',
    channelId: 'ch_1',
    externalId: 'wxid_123',
    name: 'Alice',
    status: 'allowed',
    linkedTo: null,
    clawscaleUserId: null,
    clawscaleUser: null,
    activeBackends: [{ backendId: 'ab_1' }],
  });
  db.cokeAccount.findUnique.mockResolvedValue({
    id: 'acct_1',
    email: 'alice@example.com',
    displayName: 'Alice',
    emailVerified: true,
    status: 'normal',
  });
  db.subscription.findFirst.mockResolvedValue({
    expiresAt: new Date('2026-05-10T00:00:00.000Z'),
  });

  await routeInboundMessage({
    channelId: 'ch_1',
    externalId: 'wxid_123',
    displayName: 'Alice',
    text: 'hello',
    meta: { platform: 'wechat_personal' },
  });

  const firstGenerateCall = vi.mocked(generateReply).mock.calls[0]?.[0] as { metadata?: Record<string, unknown> };
  expect(firstGenerateCall.metadata).toMatchObject({
    cokeAccountId: 'acct_1',
    cokeAccountDisplayName: 'Alice',
    accountAccessAllowed: true,
    accountStatus: 'normal',
    emailVerified: true,
  });
});
```

```py
def test_bridge_inbound_returns_renewal_message_without_enqueue(monkeypatch):
    from connector.clawscale_bridge.app import create_app
    import connector.clawscale_bridge.app as bridge_app

    app = create_app(testing=True)
    message_gateway = MagicMock()
    reply_waiter = MagicMock()
    service = bridge_app.BusinessOnlyBridgeGateway(
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        target_character_id="char_1",
    )
    monkeypatch.setitem(app.config, "BRIDGE_GATEWAY", service)
    client = app.test_client()

    response = client.post(
        "/bridge/inbound",
        headers={"Authorization": "Bearer test-bridge-key"},
        json={
            "messages": [{"role": "user", "content": "hello"}],
            "metadata": {
                "tenantId": "ten_1",
                "channelId": "ch_1",
                "platform": "wechat_personal",
                "endUserId": "eu_1",
                "externalId": "wxid_123",
                "channelScope": "personal",
                "clawscaleUserId": "csu_1",
                "cokeAccountId": "acct_1",
                "accountAccessAllowed": False,
                "accountAccessDeniedReason": "subscription_required",
                "renewalUrl": "https://coke.app/coke/renew",
            },
        },
    )

    assert response.status_code == 200
    assert "renew" in response.get_json()["reply"]
    message_gateway.enqueue.assert_not_called()
```

```py
def test_message_gateway_persists_coke_account_metadata():
    from connector.clawscale_bridge.message_gateway import CokeMessageGateway

    gateway = CokeMessageGateway(mongo=MagicMock(), user_dao=MagicMock())
    doc = gateway.build_input_message(
        account_id="acct_1",
        character_id="char_1",
        text="hello",
        causal_inbound_event_id="in_evt_1",
        inbound={
            "timestamp": 1710000000,
            "coke_account_id": "acct_1",
            "coke_account_display_name": "Alice",
            "account_status": "normal",
            "email_verified": True,
            "account_access_allowed": True,
            "renewal_url": "https://coke.app/coke/renew",
        },
    )

    assert doc["metadata"]["coke_account"] == {
        "id": "acct_1",
        "display_name": "Alice",
        "account_status": "normal",
        "email_verified": True,
        "account_access_allowed": True,
        "renewal_url": "https://coke.app/coke/renew",
    }
```

- [ ] **Step 2: Run the targeted Gateway and Bridge tests**

Run: `pnpm --dir gateway/packages/api test -- src/lib/route-message.test.ts src/lib/ai-backend.test.ts`

Expected: FAIL because the account-access metadata is not yet present.

Run: `pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/connector/clawscale_bridge/test_message_gateway.py -v`

Expected: FAIL because Bridge still enqueues denied users and `message_gateway.py` does not persist Coke-account metadata.

- [ ] **Step 3: Implement the account-access envelope on the Gateway->Bridge path**

```ts
import { resolveCokeAccountAccess } from './coke-account-access.js';

const cokeAccount =
  resolvedCokeAccountId
    ? await db.cokeAccount.findUnique({
        where: { id: resolvedCokeAccountId },
        select: { id: true, email: true, displayName: true, emailVerified: true, status: true },
      })
    : null;

const cokeAccess = cokeAccount
  ? await resolveCokeAccountAccess({ account: cokeAccount })
  : null;

const backendReply = await runBackend(backend, historyConvIds, {
  tenantId,
  channelId,
  endUserId: endUser!.id,
  conversationId: conversation!.id,
  gatewayConversationId: conversation!.id,
  inboundEventId,
  externalId: endUser!.externalId,
  ...(resolvedClawscaleUserId ? { clawscaleUserId: resolvedClawscaleUserId } : {}),
  ...(resolvedCokeAccountId ? { cokeAccountId: resolvedCokeAccountId } : {}),
  ...(cokeAccount ? {
    cokeAccountDisplayName: cokeAccount.displayName,
    accountStatus: cokeAccount.status,
    emailVerified: cokeAccount.emailVerified,
  } : {}),
  ...(cokeAccess ?? {}),
  ...(personalChannelOwnership ?? {}),
}, palmosCtx, {
  sender: endUser!.name ?? displayName,
  platform,
});
```

```py
    def _normalize_inbound(self, inbound_payload: dict) -> dict:
        metadata = inbound_payload.get("metadata") or {}
        messages = inbound_payload.get("messages") or []
        last_message = messages[-1] if messages else {}
        return {
            "tenant_id": metadata.get("tenantId") or inbound_payload.get("tenant_id"),
            "channel_id": metadata.get("channelId") or inbound_payload.get("channel_id"),
            "platform": metadata.get("platform") or inbound_payload.get("platform"),
            "end_user_id": metadata.get("endUserId") or inbound_payload.get("end_user_id"),
            "external_id": metadata.get("externalId") or inbound_payload.get("external_id"),
            "channel_scope": metadata.get("channelScope") or inbound_payload.get("channel_scope"),
            "clawscale_user_id": metadata.get("clawscaleUserId") or inbound_payload.get("clawscale_user_id"),
            "coke_account_id": metadata.get("cokeAccountId") or inbound_payload.get("coke_account_id"),
            "coke_account_display_name": metadata.get("cokeAccountDisplayName"),
            "account_status": metadata.get("accountStatus"),
            "email_verified": metadata.get("emailVerified"),
            "subscription_active": metadata.get("subscriptionActive"),
            "subscription_expires_at": metadata.get("subscriptionExpiresAt"),
            "account_access_allowed": metadata.get("accountAccessAllowed"),
            "account_access_denied_reason": metadata.get("accountAccessDeniedReason"),
            "renewal_url": metadata.get("renewalUrl"),
            "input": inbound_payload.get("input") or last_message.get("content") or "",
        }

    def handle_inbound(self, inbound_payload: dict):
        inbound = self._normalize_inbound(inbound_payload)
        if inbound.get("account_access_allowed") is False:
            reason = inbound.get("account_access_denied_reason")
            if reason == "subscription_required":
                reply = f"Your subscription has expired. Please renew at {inbound.get('renewal_url')}"
            elif reason == "email_not_verified":
                reply = "Please verify your email in the Coke web app before chatting."
            elif reason == "account_suspended":
                reply = "This account cannot currently use Coke. Please contact support."
            else:
                reply = "Coke account access is not available right now."
            return {"status": "ok", "reply": reply}
        return self._enqueue_and_wait(
            account_id=inbound["coke_account_id"],
            inbound=inbound,
            now_ts=int(time.time()),
        )
```

```py
        return {
            "input_timestamp": inbound["timestamp"],
            "handled_timestamp": inbound["timestamp"],
            "status": "pending",
            "from_user": account_id,
            "platform": "business",
            "chatroom_name": None,
            "to_user": character_id,
            "message_type": "text",
            "message": text,
            "metadata": {
                "source": "clawscale",
                "business_protocol": business_protocol,
                "coke_account": {
                    "id": inbound.get("coke_account_id"),
                    "display_name": inbound.get("coke_account_display_name"),
                    "account_status": inbound.get("account_status"),
                    "email_verified": inbound.get("email_verified"),
                    "subscription_active": inbound.get("subscription_active"),
                    "subscription_expires_at": inbound.get("subscription_expires_at"),
                    "account_access_allowed": inbound.get("account_access_allowed"),
                    "account_access_denied_reason": inbound.get("account_access_denied_reason"),
                    "renewal_url": inbound.get("renewal_url"),
                },
            },
        }
```

- [ ] **Step 4: Run the targeted tests again**

Run: `pnpm --dir gateway/packages/api test -- src/lib/route-message.test.ts src/lib/ai-backend.test.ts`

Expected: PASS

Run: `pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/connector/clawscale_bridge/test_message_gateway.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/api/src/lib/route-message.ts gateway/packages/api/src/lib/route-message.test.ts gateway/packages/api/src/lib/ai-backend.test.ts connector/clawscale_bridge/app.py connector/clawscale_bridge/message_gateway.py tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/connector/clawscale_bridge/test_message_gateway.py
git commit -m "feat(bridge): gate inbound by coke account access"
```

## Task 5: Add Agent identity adapter and runner-level CokeAccount support

**Files:**
- Create: `agent/runner/identity.py`
- Create: `tests/unit/runner/test_identity.py`
- Create: `tests/unit/runner/test_message_processor_identity.py`
- Modify: `agent/runner/message_processor.py`
- Modify: `agent/runner/context.py`
- Modify: `agent/runner/agent_handler.py`
- Modify: `agent/runner/agent_background_handler.py`
- Modify: `agent/util/message_util.py`

- [ ] **Step 1: Write failing Agent identity tests**

```py
from unittest.mock import MagicMock


def test_resolve_agent_user_context_builds_synthetic_coke_account_user():
    from agent.runner.identity import resolve_agent_user_context

    user = resolve_agent_user_context(
        user_id="acct_cuid_1",
        input_message={
            "platform": "business",
            "metadata": {
                "source": "clawscale",
                "coke_account": {
                    "id": "acct_cuid_1",
                    "display_name": "Alice",
                    "account_access_allowed": True,
                },
            },
        },
        user_dao=MagicMock(),
    )

    assert user == {
        "id": "acct_cuid_1",
        "_id": "acct_cuid_1",
        "nickname": "Alice",
        "is_coke_account": True,
    }
```

```py
from unittest.mock import MagicMock


def test_message_acquirer_accepts_coke_account_id_without_mongo_lookup_failure(monkeypatch):
    from agent.runner.message_processor import MessageAcquirer

    acquirer = MessageAcquirer("[T]")
    acquirer.user_dao = MagicMock()
    acquirer.user_dao.find_characters.return_value = [{"_id": "char_object_id"}]
    acquirer.user_dao.get_user_by_id.side_effect = lambda user_id: {"_id": "char_object_id", "name": "coke"} if user_id == "char_object_id" else None
    monkeypatch.setattr(
        "agent.runner.message_processor.read_top_inputmessages",
        lambda **kwargs: [{
            "_id": "msg_1",
            "from_user": "acct_cuid_1",
            "to_user": "char_object_id",
            "status": "pending",
            "platform": "business",
            "metadata": {
                "source": "clawscale",
                "coke_account": {"id": "acct_cuid_1", "display_name": "Alice"},
                "business_protocol": {"delivery_mode": "request_response", "gateway_conversation_id": "conv_1"},
            },
        }],
    )

    assert acquirer.acquire() is not None
```

- [ ] **Step 2: Run the new Agent identity tests**

Run: `pytest tests/unit/runner/test_identity.py tests/unit/runner/test_message_processor_identity.py -v`

Expected: FAIL because `identity.py` does not exist and `MessageAcquirer` still hard-fails non-ObjectId users.

- [ ] **Step 3: Implement the synthetic Coke-account identity adapter and switch the runner to canonical IDs**

```py
from bson import ObjectId
from bson.errors import InvalidId


def is_mongo_object_id(value: str) -> bool:
    try:
        ObjectId(value)
        return True
    except (TypeError, ValueError, InvalidId):
        return False


def get_agent_entity_id(entity: dict | None) -> str:
    if not isinstance(entity, dict):
        return ""
    if entity.get("id"):
        return str(entity["id"])
    if entity.get("_id"):
        return str(entity["_id"])
    return ""


def resolve_agent_user_context(user_id: str, input_message: dict, user_dao) -> dict | None:
    if is_mongo_object_id(user_id):
        user = user_dao.get_user_by_id(user_id)
        if isinstance(user, dict):
            user.setdefault("id", str(user.get("_id") or ""))
        return user

    metadata = input_message.get("metadata") or {}
    coke_account = metadata.get("coke_account") or {}
    if input_message.get("platform") == "business" and metadata.get("source") == "clawscale":
        nickname = (
            coke_account.get("display_name")
            or metadata.get("sender")
            or f"user-{user_id[-6:]}"
        )
        return {
            "id": user_id,
            "_id": user_id,
            "nickname": nickname,
            "is_coke_account": True,
        }

    return None
```

```py
from agent.runner.identity import get_agent_entity_id, resolve_agent_user_context

        user = resolve_agent_user_context(top_message["from_user"], top_message, self.user_dao)
        character = self.user_dao.get_user_by_id(top_message["to_user"])

        if user is None:
            logger.warning(f"{self.worker_tag} 非法用户标识，跳过: {top_message['from_user']}")
            top_message["status"] = "failed"
            top_message["error"] = "invalid_user_id"
            save_inputmessage(top_message)
            return None

        if character is None:
            logger.warning(f"{self.worker_tag} 角色不存在，跳过: {top_message['to_user']}")
            top_message["status"] = "failed"
            top_message["error"] = "user_not_found"
            save_inputmessage(top_message)
            return None

        canonical_user_id = get_agent_entity_id(user)
        canonical_character_id = get_agent_entity_id(character)
        input_messages = read_all_inputmessages(
            canonical_user_id,
            canonical_character_id,
            platform,
            "pending",
        )
```

```py
from agent.runner.identity import get_agent_entity_id

    user_id = get_agent_entity_id(user)
    character_id = get_agent_entity_id(character)
    if not user_id or not character_id:
        raise ValueError("Invalid user or character ID")

    relation = mongo.find_one("relations", {"uid": user_id, "cid": character_id})
    if relation is None:
        realtion_id = mongo.insert_one(
            "relations", get_default_relation(user_id, character_id)
        )
```

```py
def get_default_relation(user_id, character_id):
    return {
        "uid": user_id,
        "cid": character_id,
        "user_info": {
            "realname": "",
            "hobbyname": "",
            "description": "在聊天里认识的朋友",
        },
        "character_info": {
            "longterm_purpose": "帮用户实现他们想实现的生活目标（比如日程管理，定期提醒等），在用户需要完成目标时督促他，关心并用户的生活（吃饭，喝水等），也在用户低落时给予鼓励.",
            "shortterm_purpose": "随便认识一下这位朋友，少量闲聊，不聊也行",
            "attitude": "略微好奇",
            "status": "空闲",
        },
        "relationship": {
            "description": "在聊天里认识的朋友",
            "closeness": 20,
            "trustness": 20,
            "dislike": 0,
        },
    }
```

```py
from agent.runner.identity import get_agent_entity_id

            if is_new_message_coming_in(
                get_agent_entity_id(user),
                get_agent_entity_id(character),
                current_platform,
                current_message_ids,
            ):
                is_rollback = True
```

```py
def _resolve_talker_name(talker, message):
    metadata = message.get("metadata") or {}
    coke_account = metadata.get("coke_account")
    if message.get("platform") == "business" and isinstance(coke_account, dict):
        if coke_account.get("display_name"):
            return coke_account["display_name"]
    platform = message.get("platform")
    default_name = message.get("from_user") or "未知用户"
    if not isinstance(talker, dict) or talker is None:
        return default_name
    return resolve_profile_label(talker, default_name)
```

- [ ] **Step 4: Run the Agent identity tests and runner regressions**

Run: `pytest tests/unit/runner/test_identity.py tests/unit/runner/test_message_processor_identity.py tests/unit/agent/test_agent_handler.py tests/unit/test_context_timezone.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/runner/identity.py tests/unit/runner/test_identity.py tests/unit/runner/test_message_processor_identity.py agent/runner/message_processor.py agent/runner/context.py agent/runner/agent_handler.py agent/runner/agent_background_handler.py agent/util/message_util.py
git commit -m "feat(agent): support coke account identities in runner"
```

## Task 6: Migrate session_state consumers and delete legacy Agent payment/gate code

**Files:**
- Modify: `agent/agno_agent/workflows/prepare_workflow.py`
- Modify: `agent/agno_agent/workflows/post_analyze_workflow.py`
- Modify: `agent/agno_agent/tools/reminder_tools.py`
- Modify: `agent/agno_agent/tools/reminder/service.py`
- Modify: `agent/agno_agent/tools/reminder/validator.py`
- Modify: `agent/agno_agent/tools/timezone_tools.py`
- Modify: `agent/agno_agent/tools/context_retrieve_tool.py`
- Modify: `agent/agno_agent/utils/usage_tracker.py`
- Modify: `agent/runner/message_processor.py`
- Modify: `agent/runner/agent_handler.py`
- Create: `tests/unit/runner/test_dispatcher_without_gate.py`
- Delete: `agent/runner/access_gate.py`
- Delete: `agent/runner/payment/base.py`
- Delete: `agent/runner/payment/creem_provider.py`
- Delete: `agent/runner/payment/stripe_provider.py`
- Delete: `tests/unit/runner/test_access_gate.py`
- Delete: `tests/unit/runner/test_message_dispatcher_gate.py`
- Delete: `tests/unit/runner/payment/test_base.py`
- Delete: `tests/unit/runner/payment/test_creem_provider.py`
- Delete: `tests/unit/runner/payment/test_stripe_provider.py`

- [ ] **Step 1: Write a failing regression test proving the dispatcher no longer imports `AccessGate`**

```py
import importlib
import sys


def test_message_dispatcher_imports_without_access_gate_module(monkeypatch):
    sys.modules.pop("agent.runner.message_processor", None)
    sys.modules.pop("agent.runner.access_gate", None)
    monkeypatch.setitem(sys.modules, "agent.runner.access_gate", None)

    module = importlib.import_module("agent.runner.message_processor")

    dispatcher = module.MessageDispatcher("[T]")
    assert hasattr(dispatcher, "access_gate") is False
```

- [ ] **Step 2: Run the regression test and the existing reminder/timezone tests**

Run: `pytest tests/unit/runner/test_dispatcher_without_gate.py tests/unit/test_timezone_tools.py tests/unit/test_reminder_tools_gtd.py tests/unit/test_reminder_tools_side_effect_guard.py tests/unit/reminder/test_service.py tests/unit/reminder/test_validator.py tests/unit/reminder/test_timezone_propagation.py tests/unit/test_prepare_workflow_web_search.py -v`

Expected: FAIL because `message_processor.py` still imports `AccessGate` and some workflow/tool code still reads `session_state["user"]["_id"]`.

- [ ] **Step 3: Remove `AccessGate` and switch all workflow/tool user-id reads to `session_state["user"]["id"]`**

```py
class MessageDispatcher:
    SUPPORTED_HARDCODE = ("/", "\\", "、")

    def __init__(self, worker_tag: str):
        self.worker_tag = worker_tag
        self.admin_user_id = CONF.get("admin_user_id", "")

    def dispatch(self, msg_ctx: MessageContext) -> Tuple[str, Optional[Dict]]:
        context = msg_ctx.context
        input_messages = msg_ctx.input_messages

        if context["relation"]["relationship"]["dislike"] >= 100:
            return ("blocked", None)

        if str(context["user"].get("id") or context["user"].get("_id")) == self.admin_user_id and str(
            input_messages[0]["message"]
        ).startswith(self.SUPPORTED_HARDCODE):
            return ("hardcode", {"command": input_messages[0]["message"]})

        if context["relation"]["character_info"].get("status", "空闲") not in ["空闲"]:
            return ("hold", None)

        return ("normal", None)
```

```py
USER_ID = session_state.get("user", {}).get("id", "")
```

Apply that exact `session_state["user"]["id"]` read in these files:

```py
# agent/agno_agent/workflows/prepare_workflow.py
# agent/agno_agent/workflows/post_analyze_workflow.py
# agent/agno_agent/tools/reminder_tools.py
# agent/agno_agent/tools/reminder/service.py
# agent/agno_agent/tools/reminder/validator.py
# agent/agno_agent/tools/timezone_tools.py
# agent/agno_agent/tools/context_retrieve_tool.py
# agent/agno_agent/utils/usage_tracker.py
```

Delete the `gate_denied` and `gate_expired` branches from `agent/runner/agent_handler.py`, then delete:

```text
agent/runner/access_gate.py
agent/runner/payment/base.py
agent/runner/payment/creem_provider.py
agent/runner/payment/stripe_provider.py
tests/unit/runner/test_access_gate.py
tests/unit/runner/test_message_dispatcher_gate.py
tests/unit/runner/payment/test_base.py
tests/unit/runner/payment/test_creem_provider.py
tests/unit/runner/payment/test_stripe_provider.py
```

- [ ] **Step 4: Run the regression and existing workflow/tool tests again**

Run: `pytest tests/unit/runner/test_dispatcher_without_gate.py tests/unit/test_timezone_tools.py tests/unit/test_reminder_tools_gtd.py tests/unit/test_reminder_tools_side_effect_guard.py tests/unit/reminder/test_service.py tests/unit/reminder/test_validator.py tests/unit/reminder/test_timezone_propagation.py tests/unit/test_prepare_workflow_web_search.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/agno_agent/workflows/prepare_workflow.py agent/agno_agent/workflows/post_analyze_workflow.py agent/agno_agent/tools/reminder_tools.py agent/agno_agent/tools/reminder/service.py agent/agno_agent/tools/reminder/validator.py agent/agno_agent/tools/timezone_tools.py agent/agno_agent/tools/context_retrieve_tool.py agent/agno_agent/utils/usage_tracker.py agent/runner/message_processor.py agent/runner/agent_handler.py tests/unit/runner/test_dispatcher_without_gate.py
git rm agent/runner/access_gate.py agent/runner/payment/base.py agent/runner/payment/creem_provider.py agent/runner/payment/stripe_provider.py tests/unit/runner/test_access_gate.py tests/unit/runner/test_message_dispatcher_gate.py tests/unit/runner/payment/test_base.py tests/unit/runner/payment/test_creem_provider.py tests/unit/runner/payment/test_stripe_provider.py
git commit -m "chore(agent): remove legacy gate and payment code"
```

## Task 7: Update the Coke web app for Gateway auth, verification, password reset, and renewal

**Files:**
- Modify: `gateway/packages/web/lib/coke-user-api.ts`
- Modify: `gateway/packages/web/lib/coke-user-auth.ts`
- Modify: `gateway/packages/web/lib/coke-user-wechat-channel.ts`
- Modify: `gateway/packages/web/lib/coke-user-wechat-channel.test.ts`
- Modify: `gateway/packages/web/lib/coke-user-api-empty-body.test.ts`
- Modify: `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/register/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.test.tsx`
- Create: `gateway/packages/web/app/(coke-user)/coke/verify-email/page.tsx`
- Create: `gateway/packages/web/app/(coke-user)/coke/verify-email/page.test.tsx`
- Create: `gateway/packages/web/app/(coke-user)/coke/forgot-password/page.tsx`
- Create: `gateway/packages/web/app/(coke-user)/coke/reset-password/page.tsx`
- Create: `gateway/packages/web/app/(coke-user)/coke/payment-success/page.tsx`
- Create: `gateway/packages/web/app/(coke-user)/coke/payment-cancel/page.tsx`
- Create: `gateway/packages/web/app/(coke-user)/coke/renew/page.tsx`
- Create: `gateway/packages/web/app/(coke-user)/coke/renew/page.test.tsx`

- [ ] **Step 1: Write the failing web tests for the new route paths and renewal flow**

```ts
import { describe, expect, it, vi } from 'vitest';
import {
  archiveCokeUserWechatChannel,
  connectCokeUserWechatChannel,
  createCokeUserWechatChannel,
  getCokeUserWechatChannelStatus,
} from './coke-user-wechat-channel';
import { cokeUserApi } from './coke-user-api';

vi.mock('./coke-user-api', () => ({
  cokeUserApi: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('coke-user-wechat-channel routes', () => {
  it('uses the new /api/coke/wechat-channel contract', async () => {
    await createCokeUserWechatChannel();
    await connectCokeUserWechatChannel();
    await getCokeUserWechatChannelStatus();
    await archiveCokeUserWechatChannel();

    expect(cokeUserApi.post).toHaveBeenNthCalledWith(1, '/api/coke/wechat-channel');
    expect(cokeUserApi.post).toHaveBeenNthCalledWith(2, '/api/coke/wechat-channel/connect');
    expect(cokeUserApi.get).toHaveBeenCalledWith('/api/coke/wechat-channel/status');
    expect(cokeUserApi.delete).toHaveBeenCalledWith('/api/coke/wechat-channel');
  });
});
```

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';

const pushMock = vi.hoisted(() => vi.fn());
const postMock = vi.hoisted(() => vi.fn());
const getTokenMock = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: pushMock }),
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('../../../../lib/coke-user-auth', () => ({
  getCokeUserToken: () => getTokenMock(),
}));
vi.mock('../../../../lib/coke-user-api', () => ({
  cokeUserApi: { post: (...args: unknown[]) => postMock(...args) },
}));

import RenewPage from './page';

describe('RenewPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    getTokenMock.mockReturnValue('token');
    postMock.mockResolvedValue({ ok: true, data: { url: 'https://checkout.stripe.com/pay/cs_test_1' } });
  });

  afterEach(() => {
    root.unmount();
    container.remove();
    vi.restoreAllMocks();
  });

  it('creates a checkout session and navigates to the returned url', async () => {
    flushSync(() => {
      root.render(<RenewPage />);
    });

    await Promise.resolve();

    expect(postMock).toHaveBeenCalledWith('/api/coke/checkout');
  });
});
```

- [ ] **Step 2: Run the web tests**

Run: `pnpm --dir gateway/packages/web test -- lib/coke-user-wechat-channel.test.ts lib/coke-user-api-empty-body.test.ts 'app/(coke-user)/coke/bind-wechat/page.test.tsx' 'app/(coke-user)/coke/renew/page.test.tsx'`

Expected: FAIL because the libs still call `/user/*`, the renewal page does not exist, and the login/register UX still targets Bridge semantics.

- [ ] **Step 3: Implement the frontend contract and the new pages**

```ts
export interface CokeUser {
  id: string;
  email: string;
  display_name: string;
  email_verified?: boolean;
  status?: 'normal' | 'suspended';
  subscription_active?: boolean;
  subscription_expires_at?: string | null;
}

export function storeCokeUserAuth(result: CokeAuthResult): void {
  localStorage.setItem(TOKEN_KEY, result.token);
  localStorage.setItem(USER_KEY, JSON.stringify(result.user));
}
```

```ts
export function createCokeUserWechatChannel() {
  return cokeUserApi.post('/api/coke/wechat-channel');
}

export function connectCokeUserWechatChannel() {
  return cokeUserApi.post('/api/coke/wechat-channel/connect');
}

export function getCokeUserWechatChannelStatus() {
  return cokeUserApi.get('/api/coke/wechat-channel/status');
}

export function disconnectCokeUserWechatChannel() {
  return cokeUserApi.post('/api/coke/wechat-channel/disconnect');
}

export function archiveCokeUserWechatChannel() {
  return cokeUserApi.delete('/api/coke/wechat-channel').then(normalizeEmptyArchiveResponse);
}
```

```tsx
const res = await cokeUserApi.post<ApiResponse<CokeAuthResult>>('/api/coke/register', {
  displayName,
  email,
  password,
});

if (res.ok) {
  storeCokeUserAuth(res.data);
  router.push('/coke/verify-email');
}
```

```tsx
const res = await cokeUserApi.post<ApiResponse<CokeAuthResult>>('/api/coke/login', {
  email,
  password,
});

if (res.ok) {
  storeCokeUserAuth(res.data);
  router.push('/coke/bind-wechat');
}
```

```tsx
if (channel.status === 'missing') {
  return 'Verify your email and renew your subscription before creating a WeChat channel.';
}
```

```tsx
'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getCokeUserToken } from '../../../../lib/coke-user-auth';
import { cokeUserApi } from '../../../../lib/coke-user-api';

export default function RenewPage() {
  const router = useRouter();
  const [error, setError] = useState('');

  useEffect(() => {
    if (!getCokeUserToken()) {
      router.replace('/coke/login?next=/coke/renew');
      return;
    }

    void cokeUserApi
      .post<{ ok: boolean; data: { url: string } }>('/api/coke/checkout')
      .then((res) => {
        if (!res.ok) {
          setError('Unable to start renewal right now.');
          return;
        }
        window.location.href = res.data.url;
      })
      .catch(() => setError('Unable to start renewal right now.'));
  }, [router]);

  return <section>{error || 'Preparing your renewal checkout...'}</section>;
}
```

- [ ] **Step 4: Run the web tests and the Next.js build**

Run: `pnpm --dir gateway/packages/web test -- lib/coke-user-wechat-channel.test.ts lib/coke-user-api-empty-body.test.ts 'app/(coke-user)/coke/bind-wechat/page.test.tsx' 'app/(coke-user)/coke/renew/page.test.tsx'`

Expected: PASS

Run: `pnpm --dir gateway/packages/web build`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/web/lib/coke-user-api.ts gateway/packages/web/lib/coke-user-auth.ts gateway/packages/web/lib/coke-user-wechat-channel.ts gateway/packages/web/lib/coke-user-wechat-channel.test.ts gateway/packages/web/lib/coke-user-api-empty-body.test.ts 'gateway/packages/web/app/(coke-user)/coke/login/page.tsx' 'gateway/packages/web/app/(coke-user)/coke/register/page.tsx' 'gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.tsx' 'gateway/packages/web/app/(coke-user)/coke/bind-wechat/page.test.tsx' 'gateway/packages/web/app/(coke-user)/coke/verify-email/page.tsx' 'gateway/packages/web/app/(coke-user)/coke/verify-email/page.test.tsx' 'gateway/packages/web/app/(coke-user)/coke/forgot-password/page.tsx' 'gateway/packages/web/app/(coke-user)/coke/reset-password/page.tsx' 'gateway/packages/web/app/(coke-user)/coke/payment-success/page.tsx' 'gateway/packages/web/app/(coke-user)/coke/payment-cancel/page.tsx' 'gateway/packages/web/app/(coke-user)/coke/renew/page.tsx' 'gateway/packages/web/app/(coke-user)/coke/renew/page.test.tsx'
git commit -m "feat(coke-web): add gateway auth and renewal flows"
```

## Task 8: Delete legacy Bridge auth surface and run end-to-end verification

**Files:**
- Modify: `connector/clawscale_bridge/app.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`
- Delete: `connector/clawscale_bridge/user_auth.py`
- Delete: `connector/clawscale_bridge/gateway_user_provision_client.py`
- Delete: `tests/unit/connector/clawscale_bridge/test_gateway_user_provision_client.py`

- [ ] **Step 1: Write failing cleanup tests for the removed `/user/*` routes**

```py
def test_bridge_user_auth_routes_are_not_registered():
    from connector.clawscale_bridge.app import create_app

    client = create_app(testing=True).test_client()

    assert client.post("/user/register").status_code == 404
    assert client.post("/user/login").status_code == 404
    assert client.post("/user/wechat-channel").status_code == 404
    assert client.post("/user/wechat-channel/connect").status_code == 404
    assert client.get("/user/wechat-channel/status").status_code == 404
    assert client.post("/user/wechat-channel/disconnect").status_code == 404
    assert client.delete("/user/wechat-channel").status_code == 404
```

- [ ] **Step 2: Run the cleanup test and a representative mixed verification set**

Run: `pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py -v`

Expected: FAIL because Bridge still registers `/user/*`.

- [ ] **Step 3: Remove the old `/user/*` routes and dead Bridge auth/provision files**

```py
    @app.post("/bridge/inbound")
    def inbound():
        from connector.clawscale_bridge.auth import require_bridge_auth

        ok, error = require_bridge_auth(app.config["COKE_BRIDGE_API_KEY"])
        if not ok:
            body, status = error
            return jsonify(body), status

        payload = request.get_json(force=True)
        gateway = app.config.get("BRIDGE_GATEWAY")
        if gateway is None:
            return jsonify({"ok": False, "error": "bridge service not wired"}), 500

        result = gateway.handle_inbound(payload)
        if result.get("status") != "ok":
            return jsonify({"ok": False, "error": result.get("error", "invalid_request")}), 400

        response = {"ok": True, "reply": result["reply"]}
        for key in ("business_conversation_key", "output_id", "causal_inbound_event_id"):
            if key in result and result[key]:
                response[key] = result[key]
        return jsonify(response)

    return app
```

Delete:

```text
connector/clawscale_bridge/user_auth.py
connector/clawscale_bridge/gateway_user_provision_client.py
tests/unit/connector/clawscale_bridge/test_gateway_user_provision_client.py
```

- [ ] **Step 4: Run the broader verification set**

Run: `pnpm --dir gateway/packages/api test`

Expected: PASS

Run: `pnpm --dir gateway/packages/api build`

Expected: PASS

Run: `pnpm --dir gateway/packages/web test`

Expected: PASS

Run: `pnpm --dir gateway/packages/web build`

Expected: PASS

Run: `pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/connector/clawscale_bridge/test_message_gateway.py tests/unit/agent/test_agent_handler.py tests/unit/runner/test_identity.py tests/unit/runner/test_message_processor_identity.py tests/unit/test_timezone_tools.py tests/unit/test_context_timezone.py tests/unit/test_reminder_tools_gtd.py tests/unit/test_reminder_tools_side_effect_guard.py tests/unit/reminder/test_service.py tests/unit/reminder/test_validator.py tests/unit/reminder/test_timezone_propagation.py tests/unit/test_prepare_workflow_web_search.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add connector/clawscale_bridge/app.py tests/unit/connector/clawscale_bridge/test_bridge_app.py
git rm connector/clawscale_bridge/user_auth.py connector/clawscale_bridge/gateway_user_provision_client.py tests/unit/connector/clawscale_bridge/test_gateway_user_provision_client.py
git commit -m "chore(bridge): remove legacy coke user auth surface"
```
