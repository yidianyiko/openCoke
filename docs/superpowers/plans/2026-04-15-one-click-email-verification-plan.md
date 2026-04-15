# One-Click Email Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace manual token-entry email verification with an automatic link-driven flow and add resend recovery on the login page.

**Architecture:** Keep the existing backend verification POST contract, but turn the verify-email page into an automatic transition screen and move failed-link recovery into the login page. The frontend becomes responsible for redirecting invalid verification states into a resend path without exposing token entry UI.

**Tech Stack:** Next.js, React, TypeScript, Vitest, existing Coke user API helpers and locale copy

---

## File Structure

- Modify: `gateway/packages/web/app/(coke-user)/coke/verify-email/page.tsx`
  Convert the page from a form to an automatic verification transition screen.
- Modify: `gateway/packages/web/app/(coke-user)/coke/verify-email/page.test.tsx`
  Replace manual-form expectations with auto-submit and redirect behavior.
- Modify: `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`
  Add query-driven verification recovery UI and resend action.
- Modify: `gateway/packages/web/app/(coke-user)/coke/login/page.test.tsx`
  Cover email prefill, expired-link copy, and resend action.
- Modify: `gateway/packages/web/lib/i18n.ts`
  Update verify-email copy and add login recovery copy.

### Task 1: Auto-Verify the Email Link

**Files:**
- Modify: `gateway/packages/web/app/(coke-user)/coke/verify-email/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/verify-email/page.test.tsx`
- Modify: `gateway/packages/web/lib/i18n.ts`

- [ ] **Step 1: Write the failing verify-email page tests**

Update `gateway/packages/web/app/(coke-user)/coke/verify-email/page.test.tsx` so the page:

```tsx
it('automatically verifies from the query string and redirects without manual entry UI', async () => {
  window.history.pushState({}, '', '/coke/verify-email?token=verify-token&email=alice@example.com');

  flushSync(() => {
    root.render(
      <LocaleProvider initialLocale="en">
        <VerifyEmailPage />
      </LocaleProvider>,
    );
  });

  await flushTicks(2);

  expect(postMock).toHaveBeenCalledWith('/api/coke/verify-email', {
    token: 'verify-token',
    email: 'alice@example.com',
  });
  expect(container.querySelector('input#token')).toBeNull();
  expect(container.querySelector('input#email')).toBeNull();
  expect(pushMock).toHaveBeenCalledWith('/coke/bind-wechat');
});

it('redirects to login recovery when the verification link is missing email or token', async () => {
  window.history.pushState({}, '', '/coke/verify-email?token=verify-token');

  flushSync(() => {
    root.render(
      <LocaleProvider initialLocale="en">
        <VerifyEmailPage />
      </LocaleProvider>,
    );
  });

  await flushTicks(2);

  expect(postMock).not.toHaveBeenCalled();
  expect(pushMock).toHaveBeenCalledWith('/coke/login?verification=expired');
});

it('redirects to login recovery when verification fails', async () => {
  postMock.mockResolvedValue({ ok: false, error: 'invalid_or_expired_token' });
  window.history.pushState({}, '', '/coke/verify-email?token=verify-token&email=alice@example.com');

  flushSync(() => {
    root.render(
      <LocaleProvider initialLocale="en">
        <VerifyEmailPage />
      </LocaleProvider>,
    );
  });

  await flushTicks(2);

  expect(pushMock).toHaveBeenCalledWith(
    '/coke/login?email=alice%40example.com&verification=expired',
  );
});
```

- [ ] **Step 2: Run the verify-email page test to verify red**

Run: `pnpm -C gateway --filter @clawscale/web test -- 'app/(coke-user)/coke/verify-email/page.test.tsx'`

Expected: FAIL because the page still renders token/email inputs and requires manual submission.

- [ ] **Step 3: Implement the automatic verification page**

Refactor `gateway/packages/web/app/(coke-user)/coke/verify-email/page.tsx` to:

```tsx
useEffect(() => {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token')?.trim() ?? '';
  const email = params.get('email')?.trim() ?? '';

  if (!token || !email) {
    router.push(email
      ? `/coke/login?email=${encodeURIComponent(email)}&verification=expired`
      : '/coke/login?verification=expired');
    return;
  }

  let cancelled = false;

  async function verify() {
    setLoading(true);
    const res = await cokeUserApi.post<ApiResponse<CokeAuthResult>>('/api/coke/verify-email', {
      token,
      email,
    });

    if (cancelled) return;

    if (!res.ok) {
      router.push(`/coke/login?email=${encodeURIComponent(email)}&verification=expired`);
      return;
    }

    storeCokeUserAuth(res.data);
    router.push(res.data.user.subscription_active === false ? '/coke/renew' : '/coke/bind-wechat');
  }

  void verify().catch(() => {
    if (!cancelled) {
      router.push(`/coke/login?email=${encodeURIComponent(email)}&verification=expired`);
    }
  }).finally(() => {
    if (!cancelled) setLoading(false);
  });

  return () => {
    cancelled = true;
  };
}, [router]);
```

Render only a loading shell with updated copy:

```tsx
<h1>{copy.title}</h1>
<p>{loading ? copy.verifyingDescription : copy.description}</p>
```

- [ ] **Step 4: Update verify-email localized copy**

In `gateway/packages/web/lib/i18n.ts`, change the verify-email English copy from token pasting to automatic verification:

```ts
verifyEmail: {
  title: 'Verify your email',
  description: 'We are preparing your secure email verification.',
  verifyingDescription: 'Verifying your email link now...',
  verifiedMessage: 'Email verified.',
  genericError: 'Unable to verify your email right now.',
}
```

Also update the Chinese copy to remove token-entry wording.

- [ ] **Step 5: Run the verify-email page test to verify green**

Run: `pnpm -C gateway --filter @clawscale/web test -- 'app/(coke-user)/coke/verify-email/page.test.tsx'`

Expected: PASS

### Task 2: Add Login Recovery and Resend UI

**Files:**
- Modify: `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/login/page.test.tsx`
- Modify: `gateway/packages/web/lib/i18n.ts`

- [ ] **Step 1: Write the failing login recovery tests**

Expand `gateway/packages/web/app/(coke-user)/coke/login/page.test.tsx`:

```tsx
import { cokeUserApi } from '../../../../lib/coke-user-api';

it('prefills the email and shows resend recovery copy for expired verification links', async () => {
  window.history.pushState({}, '', '/coke/login?email=alice@example.com&verification=expired');

  flushSync(() => {
    root.render(
      <LocaleProvider initialLocale="en">
        <CokeLoginPage />
      </LocaleProvider>,
    );
  });

  await Promise.resolve();

  expect((container.querySelector('#email') as HTMLInputElement).value).toBe('alice@example.com');
  expect(container.textContent).toContain('Your verification link is invalid or expired.');
  expect(container.querySelector('[data-testid=\"resend-verification-email\"]')).toBeTruthy();
});

it('resends a verification email from the login recovery state', async () => {
  vi.mocked(cokeUserApi.post).mockResolvedValueOnce({
    ok: true,
    data: { message: 'If the account exists, a verification email has been sent.' },
  });
  window.history.pushState({}, '', '/coke/login?email=alice@example.com&verification=expired');

  flushSync(() => {
    root.render(
      <LocaleProvider initialLocale="en">
        <CokeLoginPage />
      </LocaleProvider>,
    );
  });

  await Promise.resolve();
  container.querySelector('[data-testid=\"resend-verification-email\"]')?.dispatchEvent(
    new MouseEvent('click', { bubbles: true }),
  );

  await Promise.resolve();

  expect(vi.mocked(cokeUserApi.post)).toHaveBeenCalledWith('/api/coke/verify-email/resend', {
    email: 'alice@example.com',
  });
});
```

- [ ] **Step 2: Run the login page test to verify red**

Run: `pnpm -C gateway --filter @clawscale/web test -- 'app/(coke-user)/coke/login/page.test.tsx'`

Expected: FAIL because the login page does not read recovery query params or show resend UI.

- [ ] **Step 3: Implement login recovery state**

In `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`:

```tsx
useEffect(() => {
  const params = new URLSearchParams(window.location.search);
  const queryEmail = params.get('email') ?? '';
  const verificationState = params.get('verification');

  if (queryEmail) {
    setEmail(queryEmail);
  }

  if (verificationState === 'expired') {
    setStatusMessage(copy.verificationExpired);
  }
}, [copy.verificationExpired]);

async function handleResendVerification() {
  setError('');
  setStatusMessage('');
  setResending(true);

  try {
    const res = await cokeUserApi.post<ApiResponse<{ message?: string }>>('/api/coke/verify-email/resend', {
      email,
    });

    if (!res.ok) {
      setError(copy.resendVerificationError);
      return;
    }

    setStatusMessage(copy.resendVerificationSuccess);
  } catch {
    setError(copy.resendVerificationError);
  } finally {
    setResending(false);
  }
}
```

Render the recovery button only when `verification=expired`:

```tsx
{showVerificationRecovery ? (
  <button
    type="button"
    data-testid="resend-verification-email"
    onClick={handleResendVerification}
    disabled={loading || resending || email.trim() === ''}
  >
    {resending ? copy.resendingVerification : copy.resendVerification}
  </button>
) : null}
```

- [ ] **Step 4: Add login recovery copy**

In `gateway/packages/web/lib/i18n.ts`, add English and Chinese login copy fields:

```ts
verificationExpired: 'Your verification link is invalid or expired. Resend the verification email to continue.',
resendVerification: 'Resend verification email',
resendingVerification: 'Sending...',
resendVerificationSuccess: 'If the account exists, a verification email has been sent.',
resendVerificationError: 'Unable to resend the verification email right now.',
```

- [ ] **Step 5: Run the login page test to verify green**

Run: `pnpm -C gateway --filter @clawscale/web test -- 'app/(coke-user)/coke/login/page.test.tsx'`

Expected: PASS

### Task 3: Full Regression for the Updated Flow

**Files:**
- Verify only

- [ ] **Step 1: Run the focused web auth flow tests**

Run: `pnpm -C gateway --filter @clawscale/web test -- 'app/(coke-user)/coke/login/page.test.tsx' 'app/(coke-user)/coke/verify-email/page.test.tsx' 'app/(coke-user)/coke/register/page.test.tsx'`

Expected: PASS

- [ ] **Step 2: Run the auth route regression tests**

Run: `pnpm -C gateway --filter @clawscale/api test -- src/routes/coke-auth-routes.test.ts`

Expected: PASS

- [ ] **Step 3: Review diff scope before handoff**

Run: `git status --short`

Expected: only the verify-email page, login page, tests, and i18n/doc files changed in this branch.
