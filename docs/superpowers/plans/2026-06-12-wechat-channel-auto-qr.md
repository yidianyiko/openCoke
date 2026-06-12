# WeChat Channel Auto QR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the personal-WeChat QR automatically when an eligible logged-in user opens the WeChat channel page with no channel.

**Architecture:** Keep the existing customer WeChat page state machine. Add a one-shot auto-create guard after a fresh `missing` status is loaded, reusing `createCustomerWechatChannel()` and the existing mutation failure path. Do not change backend endpoints or onboarding completion semantics.

**Tech Stack:** Next.js client component, React state/effects, Vitest page tests.

---

### Task 1: Red Tests For Auto QR

**Files:**
- Modify: `web/app/(customer)/channels/wechat-personal/page.test.tsx`

- [x] **Step 1: Replace the missing-channel layout test with an auto-create test**

Use this behavior in the existing branded-layout describe block:

```ts
it('auto-starts QR login when an eligible account has no WeChat channel', async () => {
  getCustomerWechatChannelStatusMock.mockResolvedValueOnce({
    ok: true,
    data: {
      status: 'missing',
    },
  });
  createCustomerWechatChannelMock.mockResolvedValueOnce({
    ok: true,
    data: {
      status: 'pending',
      session_id: 'session_1',
      qrcode_id: 'qr_1',
      qrcode_image: 'data:image/png;base64,QR1',
      connector_status: 'waiting_for_scan',
      instructions: "scan this QR code with this user's own WeChat account",
    },
  });

  renderWithLocale(root, 'en');
  await waitForText(container, 'Scan to connect WeChat');

  expect(createCustomerWechatChannelMock).toHaveBeenCalledTimes(1);
  expect(container.querySelector('.customer-channel-page__qr-image')?.getAttribute('src')).toBe(
    'data:image/png;base64,QR1',
  );
  expect(container.textContent).not.toContain('Create my WeChat channel');
});
```

- [x] **Step 2: Add a failed auto-create fallback test**

```ts
it('keeps the manual create action visible when automatic QR login fails', async () => {
  getCustomerWechatChannelStatusMock.mockResolvedValueOnce({
    ok: true,
    data: {
      status: 'missing',
    },
  });
  createCustomerWechatChannelMock.mockResolvedValueOnce({
    ok: false,
    error: 'provider_login_failed',
  });

  renderWithLocale(root, 'en');
  await waitForText(container, 'Create my WeChat channel');

  expect(createCustomerWechatChannelMock).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain('The last connect attempt failed. Retry or archive this channel.');
  expect(
    Array.from(container.querySelectorAll('button')).some((button) =>
      button.textContent?.includes('Create my WeChat channel'),
    ),
  ).toBe(true);
});
```

- [x] **Step 3: Run the focused tests and verify RED**

Run:

```bash
cd web && pnpm test -- app/\(customer\)/channels/wechat-personal/page.test.tsx
```

Expected: the new auto-start tests fail because the page still waits for a manual click.

### Task 2: Implement One-Shot Auto Start

**Files:**
- Modify: `web/app/(customer)/channels/wechat-personal/page.tsx`
- Modify: `web/app/(customer)/channels/wechat-personal/page.test.tsx`

- [x] **Step 1: Add refs for one-shot automatic create state**

Add refs near the existing channel/busy refs:

```ts
const autoCreateAttemptedRef = useRef(false);
const autoCreateInFlightRef = useRef(false);
```

- [x] **Step 2: Add an effect that auto-runs the existing create action once**

Add the effect after `runAction` and the action handlers are available:

```ts
useEffect(() => {
  if (channel?.status !== 'missing') {
    return;
  }
  if (autoCreateAttemptedRef.current || autoCreateInFlightRef.current) {
    return;
  }
  if (busyActionRef.current != null) {
    return;
  }

  autoCreateAttemptedRef.current = true;
  autoCreateInFlightRef.current = true;
  void runAction('create', () => createCustomerWechatChannel()).finally(() => {
    autoCreateInFlightRef.current = false;
  });
}, [channel?.status]);
```

If linting flags function order or dependency issues, wrap `runAction` in
`useCallback` with the existing `copy` dependency so the effect has an explicit,
stable dependency list.

- [x] **Step 3: Update the old manual click test**

The existing "stays on the QR scan screen after connect and polls the returned
session" test should no longer click "Create my WeChat channel". Let auto-start
produce the pending state, then keep the interval/poll assertions.

- [x] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
cd web && pnpm test -- app/\(customer\)/channels/wechat-personal/page.test.tsx
```

Expected: focused page tests pass.

### Task 3: Final Verification, Commit, Push

**Files:**
- Modified code/tests from Tasks 1-2.
- Plan: `docs/superpowers/plans/2026-06-12-wechat-channel-auto-qr.md`

- [x] **Step 1: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

- [x] **Step 2: Run relevant verification**

At minimum run:

```bash
cd web && pnpm test -- app/\(customer\)/channels/wechat-personal/page.test.tsx lib/customer-wechat-channel.test.ts
zsh scripts/verify-surface repo-os-docs
```

If routing identifies a required web surface command, run that command too.

- [ ] **Step 3: Commit only scoped files**

```bash
git add docs/superpowers/plans/2026-06-12-wechat-channel-auto-qr.md \
  web/app/\(customer\)/channels/wechat-personal/page.tsx \
  web/app/\(customer\)/channels/wechat-personal/page.test.tsx
git commit -m "feat(web): auto-start wechat qr setup"
```

- [ ] **Step 4: Push the current branch**

```bash
git push -u origin "$(git branch --show-current)"
```
