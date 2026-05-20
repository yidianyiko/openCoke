# Product Action Availability Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define a minimal backend-owned action availability DTO so frontend surfaces display allowed actions and blocked reasons without owning lifecycle-transition truth.

**Architecture:** Add a small shared DTO for action availability, then adopt it first on personal WeChat channel and Calendar Import customer status responses. Each product system still owns its own action names and blocked-reason taxonomy.

**Tech Stack:** TypeScript, shared DTOs, Hono route tests, Vitest, Next frontend API clients.

---

**Plan Status:** completed
**Status Date:** 2026-05-20
**Freshness Check:** Execute after canonical doc sync. This plan may run before the route registry when earlier API DTO adoption is useful.

## Scope

Included:

- Add a generic DTO shape for allowed actions, blocked reasons, and recommended next action.
- Adopt the DTO for personal WeChat channel status.
- Add Calendar Import response shape only if existing route already exposes lifecycle status.
- Keep frontend behavior display-only.

Excluded:

- Generic capability framework.
- Full Reminder/Memo adoption.
- New UI workflows.

## File Map

- `gateway/packages/shared/src/types/action-availability.ts`: new DTO types.
- `gateway/packages/shared/src/index.ts`: export DTO.
- `gateway/packages/api/src/routes/user-wechat-channel.ts`: include action availability in personal channel state responses.
- `gateway/packages/web/lib/customer-wechat-channel.ts`: consume DTO as data, not derive transitions.
- `gateway/packages/api/src/routes/customer-google-calendar-import-routes.ts`: add DTO where status response exists.

## Work Breakdown

### Task 1: Add Shared DTO

**Files:**
- Create: `gateway/packages/shared/src/types/action-availability.ts`
- Modify: `gateway/packages/shared/src/index.ts`

- [x] **Step 1: Add DTO file**

Create `gateway/packages/shared/src/types/action-availability.ts`:

```ts
export interface ProductActionAvailability<Action extends string = string, Reason extends string = string> {
  allowedActions: Action[];
  blockedReasons: Reason[];
  recommendedNextAction?: Action;
}
```

- [x] **Step 2: Export DTO**

Add to `gateway/packages/shared/src/index.ts`:

```ts
export * from './types/action-availability.js';
```

- [x] **Step 3: Build shared package**

Run:

```bash
pnpm --dir gateway/packages/shared build
```

Expected: TypeScript build passes.

### Task 2: Adopt For Personal WeChat Channel

**Files:**
- Modify: `gateway/packages/api/src/routes/user-wechat-channel.ts`
- Modify: `gateway/packages/web/lib/customer-wechat-channel.ts`
- Test: relevant existing personal channel tests.

- [x] **Step 1: Add typed channel action availability**

In `user-wechat-channel.ts`, define:

```ts
type PersonalWechatCustomerAction = 'create' | 'connect' | 'disconnect' | 'archive' | 'refresh';
type PersonalWechatBlockedReason =
  | 'account_suspended'
  | 'email_not_verified'
  | 'subscription_required'
  | 'channel_missing'
  | 'channel_connected'
  | 'channel_archived';
```

Add an `actionAvailability` field to the customer channel state response using `ProductActionAvailability<PersonalWechatCustomerAction, PersonalWechatBlockedReason>`.

- [x] **Step 2: Compute backend-owned action availability**

Add a helper in `user-wechat-channel.ts`:

```ts
function buildPersonalWechatActionAvailability(input: {
  status: string;
  accessDeniedReason?: PersonalWechatBlockedReason | null;
}): ProductActionAvailability<PersonalWechatCustomerAction, PersonalWechatBlockedReason> {
  if (input.accessDeniedReason) {
    return {
      allowedActions: ['refresh'],
      blockedReasons: [input.accessDeniedReason],
      recommendedNextAction: 'refresh',
    };
  }
  if (input.status === 'connected') {
    return {
      allowedActions: ['disconnect', 'archive', 'refresh'],
      blockedReasons: [],
      recommendedNextAction: 'disconnect',
    };
  }
  if (input.status === 'missing' || input.status === 'archived') {
    return {
      allowedActions: ['create', 'refresh'],
      blockedReasons: [],
      recommendedNextAction: 'create',
    };
  }
  return {
    allowedActions: ['connect', 'archive', 'refresh'],
    blockedReasons: [],
    recommendedNextAction: 'connect',
  };
}
```

The exact statuses are `missing`, `disconnected`, `pending`, `connected`,
`error`, and `archived`; keep those names aligned with
`CustomerWechatChannelStatus`.

- [x] **Step 3: Update frontend type only**

In `customer-wechat-channel.ts`, import the DTO type and add:

```ts
actionAvailability?: ProductActionAvailability<
  'create' | 'connect' | 'disconnect' | 'archive' | 'refresh',
  string
>;
```

Do not move lifecycle decision logic into the frontend.

### Task 3: Backend Unit Tests For Action Availability Computation

**Files:**
- Create: `gateway/packages/api/src/routes/user-wechat-channel.test.ts` (or extend existing test file)

- [x] **Step 1: Exhaustively test buildPersonalWechatActionAvailability**

`buildPersonalWechatActionAvailability` is now the backend source of truth for allowed actions, blocked reasons, and the next recommended action. It must be exercised against the full status space `missing | disconnected | pending | connected | error | archived` and against every possible `accessDeniedReason`:

```ts
import { describe, it, expect } from 'vitest';
import { buildPersonalWechatActionAvailability } from './user-wechat-channel.js';

describe('buildPersonalWechatActionAvailability', () => {
  it.each([
    ['account_suspended'],
    ['email_not_verified'],
    ['subscription_required'],
  ] as const)('when access is denied for %s, only refresh is allowed', (reason) => {
    const result = buildPersonalWechatActionAvailability({
      status: 'connected',
      accessDeniedReason: reason,
    });
    expect(result.allowedActions).toEqual(['refresh']);
    expect(result.blockedReasons).toEqual([reason]);
    expect(result.recommendedNextAction).toBe('refresh');
  });

  it.each(['connected'] as const)('status=%s exposes disconnect/archive/refresh', (status) => {
    const result = buildPersonalWechatActionAvailability({ status });
    expect(result.allowedActions).toEqual(['disconnect', 'archive', 'refresh']);
    expect(result.blockedReasons).toEqual([]);
    expect(result.recommendedNextAction).toBe('disconnect');
  });

  it.each(['missing', 'archived'] as const)('status=%s exposes create/refresh', (status) => {
    const result = buildPersonalWechatActionAvailability({ status });
    expect(result.allowedActions).toEqual(['create', 'refresh']);
    expect(result.recommendedNextAction).toBe('create');
  });

  it.each(['disconnected', 'pending', 'error'] as const)('status=%s exposes connect/archive/refresh', (status) => {
    const result = buildPersonalWechatActionAvailability({ status });
    expect(result.allowedActions).toEqual(['connect', 'archive', 'refresh']);
    expect(result.recommendedNextAction).toBe('connect');
  });

  it('never claims a recommended action that is not in allowedActions', () => {
    for (const status of ['missing', 'disconnected', 'pending', 'connected', 'error', 'archived'] as const) {
      const result = buildPersonalWechatActionAvailability({ status });
      if (result.recommendedNextAction) {
        expect(result.allowedActions).toContain(result.recommendedNextAction);
      }
    }
  });
});
```

Expected: every status × accessDeniedReason combination is covered, and the test will catch any future drift where the recommended action is not one of the allowed actions.

### Task 4: Adopt For Calendar Import Status Response

**Files:**
- Modify: `gateway/packages/api/src/routes/customer-google-calendar-import-routes.ts`
- Test: existing or new calendar import route test

- [x] **Step 1: Add Calendar Import action availability**

Calendar Import already exposes lifecycle status. Add a typed `actionAvailability` field to the import status endpoint using the shared DTO:

```ts
type CalendarImportCustomerAction =
  | 'start_oauth'
  | 'continue_oauth'
  | 'run_import'
  | 'cancel_import'
  | 'reset';
type CalendarImportBlockedReason =
  | 'oauth_required'
  | 'oauth_in_progress'
  | 'import_in_progress'
  | 'subscription_required'
  | 'account_suspended';
```

Compute `actionAvailability: ProductActionAvailability<CalendarImportCustomerAction, CalendarImportBlockedReason>` from the existing import-run lifecycle. Do not introduce new lifecycle states; map existing states into the DTO only.

- [x] **Step 2: Backend unit tests for Calendar Import availability**

Add a `buildCalendarImportActionAvailability` helper (analogous to the WeChat one) and unit-test every (import_status, access_state) combination it supports. The test file must include at least: no-oauth, oauth-pending, idle-after-oauth, running-import, completed, failed, and each of the blocked-reason inputs.

Expected: Calendar Import status responses now include `actionAvailability`, frontend can display it, and backend tests exhaustively cover the computation.

### Task 5: Verify Product Action Availability Contract

**Files:**
- Read: changed API and frontend files

- [x] **Step 1: Run focused backend tests**

Run:

```bash
mkdir -p artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/product-action-availability-contract
pnpm --dir gateway/packages/api test user-wechat-channel customer-google-calendar-import \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/product-action-availability-contract/api.log
pnpm --dir gateway/packages/web test customer-wechat-channel \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/product-action-availability-contract/web.log
```

Expected: focused API and web tests pass. If no exact test filter exists, run full package tests.

- [x] **Step 2: Scan frontend for derived action truth**

Run:

```bash
rg -n "status === 'connected'|status === 'missing'|allowedActions|blockedReasons" \
  gateway/packages/web/app gateway/packages/web/lib/customer-wechat-channel.ts \
  | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/product-action-availability-contract/frontend-truth-scan.txt
```

Expected: `allowedActions`/`blockedReasons` may be displayed; lifecycle allowed-action truth should come from backend response or be documented as temporary display fallback.

### Task 6: E2E Action Availability Script

**Files:**
- Create: `scripts/e2e/product-action-availability-contract.sh`

- [x] **Step 1: Add e2e script**

Create `scripts/e2e/product-action-availability-contract.sh` (executable) that:

1. Boots the gateway API in test mode.
2. Fetches `/api/customer/channels/wechat-personal` with a fixture session at each known status (`missing`, `disconnected`, `pending`, `connected`, `error`, `archived`) and asserts the `actionAvailability.allowedActions`/`blockedReasons`/`recommendedNextAction` match the unit-test expectations.
3. Fetches the calendar import status endpoint for the same set of scenarios.
4. Writes per-request lines to `artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/product-action-availability-contract/e2e-action-availability.jsonl` with `{surface, scenario, status, allowedActions, blockedReasons, recommendedNextAction, ms}`.
5. Prints `[BEGIN]`/`[STEP]`/`[OK]`/`[FAIL]` structured log lines and exits non-zero on the first mismatch.

Expected: the script exits 0 and the evidence file documents every (surface × scenario) pair.
