# WhatsApp Public Checkout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let shared WhatsApp users renew paid access directly from a signed payment link in the hard access-denied reply, without requiring website login.

**Architecture:** Keep the existing Stripe webhook and subscription stacking model intact, but add a new signed public checkout entrypoint that resolves directly to `customer_id`. Normalize shared WhatsApp access checks onto `customer_id` as well, so trial expiry reliably becomes `subscription_required` and can carry a dynamic renewal URL.

**Tech Stack:** TypeScript, Hono, Prisma, Vitest, Stripe, Next.js, existing JWT-based action tokens

---

## File Structure

### Create

- `gateway/packages/api/src/lib/coke-public-checkout.ts`
  - Issue and verify purpose-bound public checkout tokens.
  - Build signed public renewal URLs from `DOMAIN_CLIENT`.
- `gateway/packages/api/src/lib/coke-public-checkout.test.ts`
  - Covers token issuance, verification, expiry failure, and URL generation.

### Modify

- `gateway/packages/api/src/lib/coke-account-access.ts`
  - Add an opt-out for email-verification gating so shared WhatsApp can be gated on subscription without requiring claimed website identity.
- `gateway/packages/api/src/lib/coke-account-access.test.ts`
  - Add coverage for shared WhatsApp semantics (`requireEmailVerified: false`).
- `gateway/packages/api/src/routes/coke-payment-routes.ts`
  - Add `GET /api/coke/public-checkout`.
  - Refactor owner-loading logic so public checkout can resolve a `customer_id` without requiring an email-bearing identity.
  - Keep `/api/coke/checkout` unchanged for logged-in web users.
- `gateway/packages/api/src/routes/coke-payment-routes.test.ts`
  - Add focused route tests for the public checkout entrypoint and preserve existing checkout/webhook coverage.
- `gateway/packages/api/src/lib/route-message.ts`
  - Resolve shared-channel access from `resolvedChannelCustomerId`.
  - Skip email-verification gating for shared WhatsApp.
  - Generate dynamic signed renewal URLs only when access is denied for `subscription_required`.
- `gateway/packages/api/src/lib/route-message.test.ts`
  - Add/extend coverage for shared WhatsApp access decisions and renewal-link metadata.

### Integration-only

- Root repo `gateway` submodule pointer
  - Commit the submodule SHA bump after the gateway task commits are complete.

---

### Task 1: Add Public Checkout Token Helper And Shared Access Override

**Files:**
- Create: `gateway/packages/api/src/lib/coke-public-checkout.ts`
- Test: `gateway/packages/api/src/lib/coke-public-checkout.test.ts`
- Modify: `gateway/packages/api/src/lib/coke-account-access.ts`
- Test: `gateway/packages/api/src/lib/coke-account-access.test.ts`

- [ ] **Step 1: Write the failing token-helper tests**

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('coke-public-checkout helpers', () => {
  beforeEach(() => {
    vi.useRealTimers();
    process.env.CUSTOMER_JWT_SECRET = 'customer-secret';
    delete process.env.COKE_JWT_SECRET;
    process.env.DOMAIN_CLIENT = 'https://coke.example';
  });

  it('issues and verifies a public checkout token for one customer', () => {
    const token = issuePublicCheckoutToken({ customerId: 'ck_shared_1' });

    expect(verifyPublicCheckoutToken(token)).toMatchObject({
      sub: 'ck_shared_1',
      customerId: 'ck_shared_1',
      tokenType: 'action',
      purpose: 'public_checkout',
    });
  });

  it('rejects an expired public checkout token', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-04-20T00:00:00.000Z'));
    const token = issuePublicCheckoutToken({ customerId: 'ck_shared_1' });

    vi.setSystemTime(new Date('2026-04-21T00:00:01.000Z'));

    expect(() => verifyPublicCheckoutToken(token)).toThrow('invalid_or_expired_token');
  });

  it('builds a renewal URL from DOMAIN_CLIENT', () => {
    const token = 'signed-token';

    expect(buildPublicCheckoutUrl(token)).toBe(
      'https://coke.example/api/coke/public-checkout?token=signed-token',
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run src/lib/coke-public-checkout.test.ts
```

Expected:

- FAIL with `Cannot find module './coke-public-checkout.js'` or missing export errors.

- [ ] **Step 3: Write the minimal public-checkout helper**

```ts
import jwt from 'jsonwebtoken';

const PUBLIC_CHECKOUT_EXPIRES_IN: jwt.SignOptions['expiresIn'] = '24h';

export class PublicCheckoutTokenError extends Error {
  constructor(message: 'invalid_or_expired_token') {
    super(message);
    this.name = 'PublicCheckoutTokenError';
  }
}

interface PublicCheckoutTokenPayload {
  sub: string;
  customerId: string;
  tokenType: 'action';
  purpose: 'public_checkout';
  iat?: number;
  exp?: number;
}

function readCustomerJwtSecret(): string {
  const secret =
    process.env['CUSTOMER_JWT_SECRET']?.trim() ?? process.env['COKE_JWT_SECRET']?.trim();

  if (!secret) {
    throw new Error('CUSTOMER_JWT_SECRET or COKE_JWT_SECRET is required');
  }

  return secret;
}

export function issuePublicCheckoutToken(input: { customerId: string }): string {
  return jwt.sign(
    {
      sub: input.customerId,
      customerId: input.customerId,
      tokenType: 'action',
      purpose: 'public_checkout',
    },
    readCustomerJwtSecret(),
    { expiresIn: PUBLIC_CHECKOUT_EXPIRES_IN },
  );
}

export function verifyPublicCheckoutToken(token: string): PublicCheckoutTokenPayload {
  try {
    const payload = jwt.verify(token, readCustomerJwtSecret()) as PublicCheckoutTokenPayload;

    if (payload.tokenType !== 'action' || payload.purpose !== 'public_checkout') {
      throw new PublicCheckoutTokenError('invalid_or_expired_token');
    }

    return payload;
  } catch {
    throw new PublicCheckoutTokenError('invalid_or_expired_token');
  }
}

export function buildPublicCheckoutUrl(token: string): string {
  const domainClient = process.env['DOMAIN_CLIENT']?.trim().replace(/\/$/, '') ?? '';
  const path = `/api/coke/public-checkout?token=${encodeURIComponent(token)}`;
  return domainClient ? `${domainClient}${path}` : path;
}
```

- [ ] **Step 4: Write the failing shared-access override test**

```ts
it('skips email verification gating when explicitly disabled', async () => {
  db.subscription.findFirst.mockResolvedValue({
    expiresAt: new Date('2026-04-01T00:00:00.000Z'),
  });

  await expect(
    resolveCokeAccountAccess({
      account: {
        id: 'ck_shared_1',
        status: 'normal',
        emailVerified: false,
        displayName: 'Alice',
      },
      now: new Date('2026-04-10T00:00:00.000Z'),
      requireEmailVerified: false,
      renewalUrl: 'https://coke.app/api/coke/public-checkout?token=signed',
    }),
  ).resolves.toMatchObject({
    accountAccessAllowed: false,
    accountAccessDeniedReason: 'subscription_required',
    renewalUrl: 'https://coke.app/api/coke/public-checkout?token=signed',
  });
});
```

- [ ] **Step 5: Run the focused access-helper test to verify it fails**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run src/lib/coke-account-access.test.ts
```

Expected:

- FAIL because `requireEmailVerified` is not part of the input type or `email_not_verified` still wins.

- [ ] **Step 6: Add the minimal access-helper override**

```ts
export interface ResolveCokeAccountAccessInput {
  account: {
    id: string;
    status: 'normal' | 'suspended';
    emailVerified: boolean;
    displayName?: string | null;
  };
  now?: Date;
  renewalUrl?: string;
  requireEmailVerified?: boolean;
}

export async function resolveCokeAccountAccess(
  input: ResolveCokeAccountAccessInput,
): Promise<CokeAccountAccessDecision> {
  const snapshot = await getSubscriptionSnapshot(input.account.id, input.now ?? new Date());
  const renewalUrl = input.renewalUrl ?? buildRenewalUrl();
  const requireEmailVerified = input.requireEmailVerified ?? true;

  if (input.account.status !== 'normal') {
    return {
      accountStatus: input.account.status,
      emailVerified: input.account.emailVerified,
      ...snapshot,
      accountAccessAllowed: false,
      accountAccessDeniedReason: 'account_suspended',
      renewalUrl,
    };
  }

  if (requireEmailVerified && !input.account.emailVerified) {
    return {
      accountStatus: input.account.status,
      emailVerified: input.account.emailVerified,
      ...snapshot,
      accountAccessAllowed: false,
      accountAccessDeniedReason: 'email_not_verified',
      renewalUrl,
    };
  }

  if (!snapshot.subscriptionActive) {
    return {
      accountStatus: input.account.status,
      emailVerified: input.account.emailVerified,
      ...snapshot,
      accountAccessAllowed: false,
      accountAccessDeniedReason: 'subscription_required',
      renewalUrl,
    };
  }

  return {
    accountStatus: input.account.status,
    emailVerified: input.account.emailVerified,
    ...snapshot,
    accountAccessAllowed: true,
    accountAccessDeniedReason: null,
    renewalUrl,
  };
}
```

- [ ] **Step 7: Run the helper tests and verify they pass**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run \
  src/lib/coke-public-checkout.test.ts \
  src/lib/coke-account-access.test.ts
```

Expected:

- PASS for both files.

- [ ] **Step 8: Commit the helper layer**

```bash
git -C gateway add \
  packages/api/src/lib/coke-public-checkout.ts \
  packages/api/src/lib/coke-public-checkout.test.ts \
  packages/api/src/lib/coke-account-access.ts \
  packages/api/src/lib/coke-account-access.test.ts
git -C gateway commit -m "feat(gateway): add public checkout token helpers"
```

### Task 2: Add The Signed Public Checkout Route

**Files:**
- Modify: `gateway/packages/api/src/routes/coke-payment-routes.ts`
- Test: `gateway/packages/api/src/routes/coke-payment-routes.test.ts`

- [ ] **Step 1: Write the failing public-checkout route tests**

```ts
it('redirects a valid public checkout token straight to Stripe', async () => {
  verifyPublicCheckoutToken.mockReturnValue({
    sub: 'ck_shared_1',
    customerId: 'ck_shared_1',
    tokenType: 'action',
    purpose: 'public_checkout',
  });
  db.membership.findFirst.mockResolvedValue({
    role: 'owner',
    customer: { id: 'ck_shared_1', displayName: 'Alice' },
    identity: { id: 'idt_1', email: null, claimStatus: 'unclaimed' },
  });
  resolveCokeAccountAccess.mockResolvedValue({
    accountStatus: 'normal',
    emailVerified: false,
    subscriptionActive: false,
    subscriptionExpiresAt: '2026-04-08T00:00:00.000Z',
    accountAccessAllowed: false,
    accountAccessDeniedReason: 'subscription_required',
    renewalUrl: 'https://coke.example/api/coke/public-checkout?token=signed',
  });
  stripeCheckoutSessionsCreate.mockResolvedValue({
    url: 'https://stripe.example/checkout/session_public_123',
  });

  const app = new Hono();
  app.route('/api/coke', cokePaymentRouter);

  const res = await app.request('/api/coke/public-checkout?token=signed');

  expect(res.status).toBe(302);
  expect(res.headers.get('location')).toBe('https://stripe.example/checkout/session_public_123');
  expect(stripeCheckoutSessionsCreate).toHaveBeenCalledWith(
    expect.objectContaining({
      metadata: { customerId: 'ck_shared_1' },
    }),
  );
});

it('returns an invalid-link HTML page when the token cannot be verified', async () => {
  verifyPublicCheckoutToken.mockImplementation(() => {
    throw new PublicCheckoutTokenError('invalid_or_expired_token');
  });

  const app = new Hono();
  app.route('/api/coke', cokePaymentRouter);

  const res = await app.request('/api/coke/public-checkout?token=bad');

  expect(res.status).toBe(400);
  await expect(res.text()).resolves.toContain('payment link is invalid or expired');
});

it('returns an unavailable HTML page when Stripe checkout creation fails', async () => {
  verifyPublicCheckoutToken.mockReturnValue({
    sub: 'ck_shared_1',
    customerId: 'ck_shared_1',
    tokenType: 'action',
    purpose: 'public_checkout',
  });
  db.membership.findFirst.mockResolvedValue({
    role: 'owner',
    customer: { id: 'ck_shared_1', displayName: 'Alice' },
    identity: { id: 'idt_1', email: null, claimStatus: 'unclaimed' },
  });
  resolveCokeAccountAccess.mockResolvedValue({
    accountStatus: 'normal',
    emailVerified: false,
    subscriptionActive: false,
    subscriptionExpiresAt: '2026-04-08T00:00:00.000Z',
    accountAccessAllowed: false,
    accountAccessDeniedReason: 'subscription_required',
    renewalUrl: 'https://coke.example/api/coke/public-checkout?token=signed',
  });
  stripeCheckoutSessionsCreate.mockRejectedValue(new Error('stripe offline'));

  const app = new Hono();
  app.route('/api/coke', cokePaymentRouter);

  const res = await app.request('/api/coke/public-checkout?token=signed');

  expect(res.status).toBe(503);
  await expect(res.text()).resolves.toContain('checkout could not be prepared right now');
});
```

- [ ] **Step 2: Run the route test to verify it fails**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run src/routes/coke-payment-routes.test.ts
```

Expected:

- FAIL because `GET /api/coke/public-checkout` does not exist and helper mocks are unused.

- [ ] **Step 3: Implement the minimal public-checkout route**

```ts
import {
  PublicCheckoutTokenError,
  verifyPublicCheckoutToken,
} from '../lib/coke-public-checkout.js';

async function loadCompatibilityCustomerAccount(
  customerId: string,
  options?: { requireEmail?: boolean },
): Promise<{
  id: string;
  displayName: string;
  email: string | null;
  emailVerified: boolean;
  status: 'normal';
} | null> {
  const membership = await db.membership.findFirst({
    where: {
      customerId,
      role: 'owner',
    },
    include: {
      customer: {
        select: {
          id: true,
          displayName: true,
        },
      },
      identity: {
        select: {
          email: true,
          claimStatus: true,
        },
      },
    },
  });

  if (!membership || !membership.customer.id.startsWith('ck_')) {
    return null;
  }

  const email = membership.identity.email?.trim() ?? null;
  if ((options?.requireEmail ?? true) && !email) {
    return null;
  }

  return {
    id: membership.customer.id,
    displayName: membership.customer.displayName,
    email,
    emailVerified: membership.identity.claimStatus === 'active',
    status: 'normal',
  };
}

function htmlPage(title: string, body: string): string {
  return `<!DOCTYPE html><html><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /><title>${title}</title></head><body><main><h1>${title}</h1><p>${body}</p></main></body></html>`;
}

export const cokePaymentRouter = new Hono()
  .get('/public-checkout', async (c) => {
    const token = c.req.query('token')?.trim() ?? '';

    let customerId: string;
    try {
      customerId = verifyPublicCheckoutToken(token).customerId;
    } catch (error) {
      if (error instanceof PublicCheckoutTokenError) {
        return c.html(
          htmlPage(
            'Payment link unavailable',
            'This payment link is invalid or expired. Go back to WhatsApp and send another message to get a new link.',
          ),
          400,
        );
      }
      throw error;
    }

    const account = await loadCompatibilityCustomerAccount(customerId, { requireEmail: false });
    if (!account) {
      return c.html(
        htmlPage(
          'Payment link unavailable',
          'This payment link is invalid or expired. Go back to WhatsApp and send another message to get a new link.',
        ),
        404,
      );
    }

    const access = await resolveCokeAccountAccess({
      account: {
        id: account.id,
        status: account.status,
        emailVerified: account.emailVerified,
        displayName: account.displayName,
      },
      requireEmailVerified: false,
    });

    if (access.accountAccessDeniedReason === 'account_suspended') {
      return c.html(
        htmlPage(
          'Account unavailable',
          'This account is currently unavailable for renewal.',
        ),
        403,
      );
    }

    try {
      const session = await stripe.checkout.sessions.create({
        mode: 'payment',
        payment_method_types: ['card'],
        line_items: [
          {
            price: readPriceId(),
            quantity: 1,
          },
        ],
        success_url: buildSuccessUrl(),
        cancel_url: buildCancelUrl(),
        metadata: {
          customerId: account.id,
        },
      });

      return c.redirect(session.url!, 302);
    } catch {
      return c.html(
        htmlPage(
          'Checkout unavailable',
          'Checkout could not be prepared right now. Please return to WhatsApp and try again later.',
        ),
        503,
      );
    }
  })
```

- [ ] **Step 4: Re-run the route tests and verify they pass**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run src/routes/coke-payment-routes.test.ts
```

Expected:

- PASS, including the new public-checkout cases and the pre-existing logged-in checkout/webhook cases.

- [ ] **Step 5: Commit the public route**

```bash
git -C gateway add \
  packages/api/src/routes/coke-payment-routes.ts \
  packages/api/src/routes/coke-payment-routes.test.ts
git -C gateway commit -m "feat(gateway): add signed public coke checkout"
```

### Task 3: Switch Shared WhatsApp Renewal Metadata To Signed Public Checkout Links

**Files:**
- Modify: `gateway/packages/api/src/lib/route-message.ts`
- Test: `gateway/packages/api/src/lib/route-message.test.ts`

- [ ] **Step 1: Write the failing shared-renewal routing tests**

```ts
it('resolves shared whatsapp access against the provisioned customer and skips email verification gating', async () => {
  provisionSharedChannelCustomer.mockResolvedValueOnce({
    customerId: 'ck_shared_1',
    created: false,
    parked: false,
    provisionStatus: 'ready',
  });
  db.membership.findFirst.mockResolvedValueOnce({
    customer: { id: 'ck_shared_1', displayName: 'Alice' },
    identity: { claimStatus: 'unclaimed' },
  });

  await routeInboundMessage({
    channelId: 'ch_1',
    externalId: '8617807028761@s.whatsapp.net',
    displayName: 'Alice',
    text: 'hello',
    meta: { platform: 'whatsapp_evolution' },
  });

  expect(resolveCokeAccountAccess).toHaveBeenCalledWith({
    account: {
      id: 'ck_shared_1',
      displayName: 'Alice',
      emailVerified: false,
      status: 'normal',
    },
    requireEmailVerified: false,
  });
});

it('injects a signed public renewal link into shared whatsapp metadata when subscription is required', async () => {
  resolveCokeAccountAccess.mockResolvedValueOnce({
    accountStatus: 'normal',
    emailVerified: false,
    subscriptionActive: false,
    subscriptionExpiresAt: '2026-04-08T00:00:00.000Z',
    accountAccessAllowed: false,
    accountAccessDeniedReason: 'subscription_required',
    renewalUrl: 'https://coke.example/coke/renew',
  });
  issuePublicCheckoutToken.mockReturnValueOnce('signed-public-token');
  buildPublicCheckoutUrl.mockReturnValueOnce(
    'https://coke.example/api/coke/public-checkout?token=signed-public-token',
  );

  await routeInboundMessage({
    channelId: 'ch_1',
    externalId: '8617807028761@s.whatsapp.net',
    displayName: 'Alice',
    text: 'hello',
    meta: { platform: 'whatsapp_evolution' },
  });

  expect(generateReply).toHaveBeenCalledWith(
    expect.objectContaining({
      metadata: expect.objectContaining({
        customerId: 'ck_shared_1',
        accountAccessDeniedReason: 'subscription_required',
        renewalUrl: 'https://coke.example/api/coke/public-checkout?token=signed-public-token',
      }),
    }),
  );
});
```

- [ ] **Step 2: Run the routing tests to verify they fail**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run src/lib/route-message.test.ts
```

Expected:

- FAIL because shared channels still call `resolveCokeAccountAccess` through the old owner path or keep the legacy renewal URL.

- [ ] **Step 3: Implement the minimal shared-channel access normalization**

```ts
import {
  buildPublicCheckoutUrl,
  issuePublicCheckoutToken,
} from './coke-public-checkout.js';

const accessCustomerId =
  channel.ownershipKind === 'shared' ? resolvedChannelCustomerId : resolvedCokeAccountId;

const accessCustomerOwner = accessCustomerId
  ? await db.membership.findFirst({
      where: {
        customerId: accessCustomerId,
        role: 'owner',
      },
      include: {
        customer: {
          select: {
            id: true,
            displayName: true,
          },
        },
        identity: {
          select: {
            claimStatus: true,
          },
        },
      },
    })
  : null;

const resolvedAccessAccount = accessCustomerId && accessCustomerOwner
  ? {
      id: accessCustomerId,
      displayName: accessCustomerOwner.customer.displayName,
      emailVerified: accessCustomerOwner.identity.claimStatus === 'active',
      status: 'normal' as const,
    }
  : null;

let resolvedCokeAccountAccess = resolvedAccessAccount
  ? await resolveCokeAccountAccess({
      account: {
        id: resolvedAccessAccount.id,
        emailVerified: resolvedAccessAccount.emailVerified,
        displayName: resolvedAccessAccount.displayName,
        status: resolvedAccessAccount.status,
      },
      ...(channel.ownershipKind === 'shared' ? { requireEmailVerified: false } : {}),
    })
  : null;

if (
  channel.ownershipKind === 'shared' &&
  resolvedCokeAccountAccess?.accountAccessDeniedReason === 'subscription_required' &&
  resolvedChannelCustomerId
) {
  const token = issuePublicCheckoutToken({ customerId: resolvedChannelCustomerId });
  resolvedCokeAccountAccess = {
    ...resolvedCokeAccountAccess,
    renewalUrl: buildPublicCheckoutUrl(token),
  };
}
```

- [ ] **Step 4: Re-run the shared routing tests and verify they pass**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run src/lib/route-message.test.ts
```

Expected:

- PASS, including the new shared WhatsApp access and renewal-link assertions.

- [ ] **Step 5: Run the cross-file gateway regression suite**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run \
  src/lib/coke-public-checkout.test.ts \
  src/lib/coke-account-access.test.ts \
  src/routes/coke-payment-routes.test.ts \
  src/lib/route-message.test.ts
pnpm --dir gateway/packages/api build
```

Expected:

- All focused Vitest files PASS.
- `build` succeeds.

- [ ] **Step 6: Commit the shared renewal integration**

```bash
git -C gateway add \
  packages/api/src/lib/route-message.ts \
  packages/api/src/lib/route-message.test.ts
git -C gateway commit -m "feat(gateway): route shared whatsapp renewals to public checkout"
```

### Task 4: Integrate The Gateway Commits Back Into The Root Worktree

**Files:**
- Modify: root `gateway` submodule pointer
- Verify: root `docs/superpowers/specs/2026-04-20-whatsapp-public-checkout-design.md`
- Verify: root `docs/superpowers/plans/2026-04-20-whatsapp-public-checkout.md`

- [ ] **Step 1: Update the root worktree to the new gateway commit**

Run:

```bash
git -C gateway rev-parse HEAD
git add gateway
git status --short
```

Expected:

- root repo shows only the `gateway` submodule pointer change plus the committed plan/spec docs.

- [ ] **Step 2: Verify both repos are clean except for the intended pointer update**

Run:

```bash
git -C gateway status --short --branch
git status --short --branch
```

Expected:

- `gateway` is clean on the implementation branch.
- root repo shows the `gateway` SHA update and no unrelated edits.

- [ ] **Step 3: Commit the root submodule bump**

```bash
git add gateway
git commit -m "chore(gateway): update whatsapp public checkout flow"
```

- [ ] **Step 4: Final verification before branch wrap-up**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run \
  src/lib/coke-public-checkout.test.ts \
  src/lib/coke-account-access.test.ts \
  src/routes/coke-payment-routes.test.ts \
  src/lib/route-message.test.ts
git -C gateway status --short --branch
git status --short --branch
```

Expected:

- Focused API tests PASS.
- both repos are clean on the feature branch.

---

## Self-Review

- Spec coverage:
  - Shared WhatsApp access moves onto `customer_id`: Task 1 + Task 3
  - Signed public checkout token: Task 1
  - Public checkout route + Stripe redirect: Task 2
  - Hard reply renewal URL becomes actionable: Task 3
  - Existing webhook/subscription path preserved: Task 2 regression coverage
  - Root integration and clean pointer update: Task 4
- Placeholder scan:
  - No `TODO`, `TBD`, or “implement later” markers remain.
- Type consistency:
  - The plan uses one helper name set throughout: `issuePublicCheckoutToken`, `verifyPublicCheckoutToken`, `buildPublicCheckoutUrl`, and `requireEmailVerified`.
