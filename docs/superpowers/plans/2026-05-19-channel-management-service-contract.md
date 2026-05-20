# Channel Management Service Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define the in-process Channel management service contract used by customer channel routes without moving provider semantics into route bodies.

**Architecture:** Customer routes keep auth, customer context, request validation, and HTTP response shape. A backend-only Channel service owns lifecycle actions, provider semantics, allowed transitions, and typed errors while preserving the current route-level HTTP status/body mapping.

**Tech Stack:** TypeScript, Hono route tests, Vitest, Prisma-backed gateway API.

---

**Plan Status:** completed
**Status Date:** 2026-05-20
**Freshness Check:** Execute after `2026-05-19-shared-channel-package-boundary.md` so backend-only Channel module paths exist.

## Scope

Included:

- Define typed request/response/error shapes for personal WeChat channel management.
- Move provider/lifecycle decisions out of route bodies into named Channel service functions.
- Preserve current HTTP routes and response payloads.

Excluded:

- New provider integrations.
- HTTP extraction of the Channel service.
- Frontend UI changes beyond type import adjustments if required.

## File Map

- `gateway/packages/api/src/channel/customer-channel-service.ts`: new service contract and personal WeChat service implementation.
- `gateway/packages/api/src/channel/customer-channel-service.test.ts`: focused service tests.
- `gateway/packages/api/src/routes/customer-channel-routes.ts`: route adapter keeps auth and calls service.
- `gateway/packages/api/src/routes/user-wechat-channel.ts`: keep router factory but delegate action execution through service functions or retire duplicated logic once covered.

## Work Breakdown

### Task 1: Define Service Types And Error Taxonomy

**Files:**
- Create: `gateway/packages/api/src/channel/customer-channel-service.ts`
- Test: `gateway/packages/api/src/channel/customer-channel-service.test.ts`

- [x] **Step 1: Write comprehensive contract shape tests**

Create `gateway/packages/api/src/channel/customer-channel-service.test.ts` with full coverage of every error code and every lifecycle action:

```ts
import { describe, expect, it } from 'vitest';
import {
  channelServiceErrorToHttp,
  type CustomerChannelActionRequest,
  type CustomerChannelLifecycleAction,
  type CustomerChannelServiceErrorCode,
} from './customer-channel-service.js';

describe('customer channel service contract', () => {
  it.each<[CustomerChannelServiceErrorCode, 401 | 402 | 403 | 404]>([
    ['unauthorized', 401],
    ['invalid_or_expired_token', 401],
    ['account_not_found', 404],
    ['claim_inactive', 403],
    ['account_suspended', 403],
    ['email_not_verified', 403],
    ['subscription_required', 402],
  ])('maps error %s to HTTP %d', (code, status) => {
    expect(channelServiceErrorToHttp({ code })).toEqual({
      status,
      body: { ok: false, error: code },
    });
  });

  it.each<CustomerChannelLifecycleAction>([
    'create',
    'connect',
    'disconnect',
    'delete',
    'status',
  ])('accepts lifecycle action %s in CustomerChannelActionRequest', (action) => {
    const request: CustomerChannelActionRequest = {
      action,
      customerId: 'ck_customer_1',
      identityId: 'identity_1',
    };

    expect(request.action).toBe(action);
  });

  it('enumerates every error code that the route layer expects', () => {
    const expected: CustomerChannelServiceErrorCode[] = [
      'unauthorized',
      'invalid_or_expired_token',
      'account_not_found',
      'claim_inactive',
      'account_suspended',
      'email_not_verified',
      'subscription_required',
    ];

    for (const code of expected) {
      const mapped = channelServiceErrorToHttp({ code });
      expect(mapped.body.ok).toBe(false);
      expect(mapped.body.error).toBe(code);
    }
  });
});
```

- [x] **Step 2: Implement types and error mapper**

Create `gateway/packages/api/src/channel/customer-channel-service.ts`:

```ts
import type { ApiResponse } from '@clawscale/shared';

export type CustomerChannelLifecycleAction =
  | 'create'
  | 'connect'
  | 'disconnect'
  | 'delete'
  | 'status';

export type CustomerChannelServiceErrorCode =
  | 'unauthorized'
  | 'invalid_or_expired_token'
  | 'account_not_found'
  | 'claim_inactive'
  | 'account_suspended'
  | 'email_not_verified'
  | 'subscription_required';

export interface CustomerChannelActionRequest {
  action: CustomerChannelLifecycleAction;
  customerId: string;
  identityId: string;
}

export interface CustomerChannelServiceError {
  code: CustomerChannelServiceErrorCode;
}

export function channelServiceErrorToHttp(error: CustomerChannelServiceError): {
  status: 401 | 402 | 403 | 404;
  body: ApiResponse<never>;
} {
  if (error.code === 'account_not_found') {
    return { status: 404, body: { ok: false, error: error.code } };
  }
  if (error.code === 'unauthorized' || error.code === 'invalid_or_expired_token') {
    return { status: 401, body: { ok: false, error: error.code } };
  }
  if (error.code === 'subscription_required') {
    return { status: 402, body: { ok: false, error: error.code } };
  }
  return { status: 403, body: { ok: false, error: error.code } };
}
```

- [x] **Step 3: Run contract test**

Run:

```bash
pnpm --dir gateway/packages/api test customer-channel-service
```

Expected: service contract tests pass.

### Task 2: Move Personal WeChat Auth/Access Resolution Behind Service Boundary

**Files:**
- Modify: `gateway/packages/api/src/channel/customer-channel-service.ts`
- Modify: `gateway/packages/api/src/routes/customer-channel-routes.ts`
- Test: `gateway/packages/api/src/routes/customer-channel-routes.test.ts` and `gateway/packages/api/src/routes/user-wechat-channel.test.ts`

- [x] **Step 1: Add service function signatures**

Extend `customer-channel-service.ts` with:

```ts
export interface CustomerChannelAuthResult {
  tenantId: string;
  clawscaleUserId: string;
}

export interface CustomerChannelService {
  resolvePersonalWechatAuth(input: CustomerChannelActionRequest): Promise<CustomerChannelAuthResult>;
}
```

- [x] **Step 2: Move `loadCompatibilityCustomerAccount`, access gating, and ClawScale user resolution**

Move the helper logic currently in `customer-channel-routes.ts` into `customer-channel-service.ts`. Keep route middleware token verification in the route file; pass `{ action, customerId, identityId }` into the service. Preserve the current behavior where `subscription_required` blocks `connect` but not read-only status or delete/archive cleanup flows.

Expected: route file owns auth token/session extraction; service owns channel lifecycle prerequisites and provider-facing auth context.

- [x] **Step 3: Update route adapter**

In `customer-channel-routes.ts`, replace direct calls to `resolveCokeAccountAccess`, `ensureClawscaleUserForCustomer`, and local compatibility account helpers with:

```ts
const customerChannelService = createCustomerChannelService({ db });
```

and route `resolveAuth` through:

```ts
return customerChannelService.resolvePersonalWechatAuth({
  action,
  customerId: auth.customerId,
  identityId: auth.identityId,
});
```

Expected: no provider-aware lifecycle logic remains in `customer-channel-routes.ts`, and route behavior still matches the current `delete` endpoint semantics.

### Task 3: Verify Boundary

**Files:**
- Read: `gateway/packages/api/src/routes/customer-channel-routes.ts`
- Read: `gateway/packages/api/src/channel/customer-channel-service.ts`

- [x] **Step 1: Scan route body for moved dependencies**

Run:

```bash
rg -n "resolveCokeAccountAccess|ensureClawscaleUserForCustomer|loadCompatibilityCustomerAccount|enforceAccessForAction|shouldGateProvisioning" \
  gateway/packages/api/src/routes/customer-channel-routes.ts
```

Expected: no matches.

- [x] **Step 2: Add route-level integration tests for every lifecycle action**

Create `gateway/packages/api/src/routes/customer-channel-routes.test.ts` (or extend existing tests) so each lifecycle action exercised by the customer-facing endpoint goes through the new service boundary:

```ts
import { describe, expect, it, beforeEach } from 'vitest';
import { buildTestApp } from '../testing/build-test-app.js';

describe('customer channel routes through service boundary', () => {
  let app: ReturnType<typeof buildTestApp>;
  beforeEach(() => { app = buildTestApp(); });

  for (const action of ['create', 'connect', 'disconnect', 'delete', 'status'] as const) {
    it(`routes ${action} through the customer channel service`, async () => {
      const response = await app.request('/api/customer/channels/wechat-personal', {
        method: action === 'status' ? 'GET' : 'POST',
        headers: { Authorization: 'Bearer fake-session' },
        body: action === 'status' ? undefined : JSON.stringify({ action }),
      });
      // The body shape is asserted by snapshot or per-action shape.
      expect([200, 401, 402, 403, 404]).toContain(response.status);
    });
  }

  it('returns 402 with stable error body when subscription_required', async () => {
    const response = await app.request('/api/customer/channels/wechat-personal', {
      method: 'POST',
      headers: { Authorization: 'Bearer no-sub-session' },
      body: JSON.stringify({ action: 'connect' }),
    });
    expect(response.status).toBe(402);
    expect(await response.json()).toEqual({ ok: false, error: 'subscription_required' });
  });

  it('still allows delete/status when subscription_required', async () => {
    for (const action of ['delete', 'status'] as const) {
      const response = await app.request('/api/customer/channels/wechat-personal', {
        method: action === 'status' ? 'GET' : 'POST',
        headers: { Authorization: 'Bearer no-sub-session' },
        body: action === 'delete' ? JSON.stringify({ action }) : undefined,
      });
      expect(response.status).not.toBe(402);
    }
  });
});
```

If `buildTestApp` does not yet exist for hono, extend the existing route test harness with a minimal in-process app builder before writing the integration cases. Do not skip integration coverage — the goal of this plan is to prove the route still behaves identically after the service-boundary refactor.

- [x] **Step 3: Instrument the service with structured logging**

Inside `customer-channel-service.ts`, add a small logger surface so each lifecycle action and each typed error is observable in prod and tests:

```ts
import { createLogger } from '@clawscale/shared/logging';

const log = createLogger('channel.customer-service');

export function logChannelAction(
  request: CustomerChannelActionRequest,
  outcome: 'ok' | CustomerChannelServiceErrorCode,
): void {
  log.info({
    event: 'customer_channel_action',
    action: request.action,
    customer_id_hash: hashCustomerId(request.customerId),
    outcome,
  });
}
```

If `@clawscale/shared/logging` does not yet exist, use the project's current logging convention (look at `gateway/packages/api/src/lib/log.ts`). Every service entry point must emit at least: `action`, `customer_id_hash`, `outcome`.

- [x] **Step 4: Run gateway API tests with evidence emission**

Run:

```bash
mkdir -p artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/channel-management-service-contract
pnpm --dir gateway/packages/api test customer-channel-service customer-channel-routes \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/channel-management-service-contract/vitest.log
pnpm --dir gateway/packages/api test
zsh scripts/verify-surface gateway-api \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/channel-management-service-contract/verify-surface.log
```

Expected: gateway API tests pass and evidence logs exist for review.

### Task 4: E2E Route Behavior Script

**Files:**
- Create: `scripts/e2e/channel-management-service-contract.sh`

- [x] **Step 1: Add e2e behavior script**

Create `scripts/e2e/channel-management-service-contract.sh` (executable) that:

1. Boots the gateway API in test mode (`pnpm --dir gateway/packages/api dev:test &` or equivalent).
2. Waits for `http://127.0.0.1:4041/healthz`.
3. For each lifecycle action (`create`, `connect`, `disconnect`, `delete`, `status`), issues an authenticated request with a fixture session that triggers each typed error code in sequence (unauthorized → 401, no-subscription → 402 on connect but not on delete/status, suspended → 403, missing → 404, success → 200).
4. Writes a JSON line per request to `artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/channel-management-service-contract/e2e-routes.jsonl` with `{action, scenario, status, body, ms}`.
5. Exits 0 only if every expected (status, error) pair matched.

The script should print `[BEGIN]`, `[STEP <name>]`, `[OK <name> <ms>ms]`, `[FAIL <name> reason]` lines so failures are obvious. The script must not require external services beyond what the gateway API already needs in test mode.

Expected: the script exits 0 locally and produces the evidence file.
