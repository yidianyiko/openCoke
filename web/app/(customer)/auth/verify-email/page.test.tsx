import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import { LocaleProvider } from '../../../../components/locale-provider';
const pushMock = vi.hoisted(() => vi.fn());
const replaceMock = vi.hoisted(() => vi.fn());
const verifyCustomerEmailMock = vi.hoisted(() => vi.fn());
const getCustomerProfileMock = vi.hoisted(() => vi.fn());
const resendCustomerVerificationMock = vi.hoisted(() => vi.fn());
const storeCustomerProfileMock = vi.hoisted(() => vi.fn());
const storeCustomerAuthMock = vi.hoisted(() => vi.fn());
const clearCustomerAuthMock = vi.hoisted(() => vi.fn());
const getStoredCustomerProfileMock = vi.hoisted(() => vi.fn());
const getStoredCustomerSessionMock = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
  }),
}));

vi.mock('../../../../lib/customer-auth', () => ({
  verifyCustomerEmail: (...args: unknown[]) => verifyCustomerEmailMock(...args),
  getCustomerProfile: (...args: unknown[]) => getCustomerProfileMock(...args),
  resendCustomerVerification: (...args: unknown[]) => resendCustomerVerificationMock(...args),
  storeCustomerAuth: (...args: unknown[]) => storeCustomerAuthMock(...args),
  storeCustomerProfile: (...args: unknown[]) => storeCustomerProfileMock(...args),
  clearCustomerAuth: (...args: unknown[]) => clearCustomerAuthMock(...args),
  getStoredCustomerProfile: () => getStoredCustomerProfileMock(),
  getStoredCustomerSession: () => getStoredCustomerSessionMock(),
}));

import CustomerVerifyEmailPage from './page';

async function flushTicks(count: number) {
  for (let i = 0; i < count; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

describe('CustomerVerifyEmailPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    verifyCustomerEmailMock.mockReset();
    getCustomerProfileMock.mockReset();
    resendCustomerVerificationMock.mockReset();
    storeCustomerAuthMock.mockReset();
    storeCustomerProfileMock.mockReset();
    clearCustomerAuthMock.mockReset();
    getStoredCustomerProfileMock.mockReset();
    getStoredCustomerSessionMock.mockReset();
    verifyCustomerEmailMock.mockResolvedValue({
      ok: true,
      data: {
        token: 'customer-token',
        customerId: 'ck_1',
        identityId: 'idt_1',
        email: 'alice@example.com',
        claimStatus: 'active',
        membershipRole: 'owner',
      },
    });
    resendCustomerVerificationMock.mockResolvedValue({
      ok: true,
      data: {},
    });
    getCustomerProfileMock.mockResolvedValue({
      ok: true,
      data: {
        id: 'ck_1',
        customerId: 'ck_1',
        identityId: 'idt_1',
        claimStatus: 'active',
        email: 'alice@example.com',
        membershipRole: 'owner',
        display_name: 'Alice',
        email_verified: true,
        status: 'normal',
        subscription_active: true,
        subscription_expires_at: null,
      },
    });
    getStoredCustomerProfileMock.mockReturnValue({
      id: 'acct_1',
      customerId: 'ck_1',
      identityId: 'idt_1',
      email: 'alice@example.com',
      claimStatus: 'pending',
      membershipRole: 'owner',
      display_name: 'Alice',
      email_verified: false,
      status: 'normal',
      subscription_active: false,
      subscription_expires_at: null,
    });
    getStoredCustomerSessionMock.mockReturnValue({
      customerId: 'ck_1',
      identityId: 'idt_1',
      email: 'alice@example.com',
      claimStatus: 'pending',
      membershipRole: 'owner',
    });
    window.history.pushState({}, '', '/auth/verify-email?token=verify-token&email=alice@example.com');

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root?.unmount();
    container?.remove();
  });

  it('automatically verifies from the query string and redirects without manual entry UI', async () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerVerifyEmailPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(2);

    expect(verifyCustomerEmailMock).toHaveBeenCalledWith({
      token: 'verify-token',
      email: 'alice@example.com',
    });
    expect(getCustomerProfileMock).toHaveBeenCalledWith();
    expect(storeCustomerProfileMock).toHaveBeenCalledWith({
      id: 'ck_1',
      customerId: 'ck_1',
      identityId: 'idt_1',
      claimStatus: 'active',
      email: 'alice@example.com',
      membershipRole: 'owner',
      display_name: 'Alice',
      email_verified: true,
      status: 'normal',
      subscription_active: true,
      subscription_expires_at: null,
    });
    expect(container.querySelector('.auth-card')).toBeTruthy();
    expect(container.querySelector('input#token')).toBeNull();
    expect(container.querySelector('input#email')).toBeNull();
    expect(container.querySelector('.auth-alert--warning')).toBeNull();
    expect(container.querySelector('.auth-input#email')).toBeNull();
    expect(container.querySelector('.auth-submit')).toBeNull();
    expect(replaceMock).toHaveBeenCalledWith('/channels/wechat-personal');
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('routes renewal-required verification success through the account subscription path', async () => {
    getCustomerProfileMock.mockResolvedValueOnce({
      ok: true,
      data: {
        id: 'ck_1',
        customerId: 'ck_1',
        identityId: 'idt_1',
        claimStatus: 'active',
        email: 'alice@example.com',
        membershipRole: 'owner',
        display_name: 'Alice',
        email_verified: true,
        status: 'normal',
        subscription_active: false,
        subscription_expires_at: null,
      },
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerVerifyEmailPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(2);

    expect(verifyCustomerEmailMock).toHaveBeenCalledWith({
      token: 'verify-token',
      email: 'alice@example.com',
    });
    expect(getCustomerProfileMock).toHaveBeenCalledWith();
    expect(storeCustomerProfileMock).toHaveBeenCalledWith(
      expect.objectContaining({
        subscription_active: false,
      }),
    );
    expect(replaceMock).toHaveBeenCalledWith('/account/subscription');
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('redirects to retry recovery when the compatibility Coke profile cannot be loaded', async () => {
    getCustomerProfileMock.mockResolvedValueOnce({
      ok: false,
      error: 'profile_unavailable',
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerVerifyEmailPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(2);

    expect(verifyCustomerEmailMock).toHaveBeenCalledWith({
      token: 'verify-token',
      email: 'alice@example.com',
    });
    expect(getCustomerProfileMock).toHaveBeenCalledWith();
    expect(clearCustomerAuthMock).toHaveBeenCalledTimes(1);
    expect(replaceMock).toHaveBeenCalledWith('/auth/login?email=alice%40example.com&verification=retry');
  });

  it('uses the email query handoff to keep the registration recovery flow working without a token', async () => {
    window.history.pushState({}, '', '/auth/verify-email?email=alice@example.com');

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerVerifyEmailPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(2);

    expect(verifyCustomerEmailMock).not.toHaveBeenCalled();
    expect(container.querySelector('.auth-card')).toBeTruthy();
    expect(container.querySelector('.auth-alert--warning')).toBeTruthy();
    expect(container.querySelector('.auth-alert--warning .auth-alert__body')).toBeTruthy();
    expect(container.querySelector('.auth-alert--warning .auth-field')).toBeTruthy();
    expect(container.querySelector('.auth-alert--warning .auth-alert__actions')).toBeTruthy();
    expect(container.querySelector('.auth-input#email')).toBeTruthy();
    expect(container.querySelector('.auth-alert--warning .auth-submit--compact')).toBeTruthy();
    expect(container.textContent).toContain('Verify your email');
    expect(container.textContent).toContain('Resend verification email');

    const emailInput = container.querySelector('input#email') as HTMLInputElement | null;
    expect(emailInput?.value).toBe('alice@example.com');

    const resendButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Resend verification email'),
    );
    expect(resendButton).toBeTruthy();

    resendButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushTicks(2);

    expect(resendCustomerVerificationMock).toHaveBeenCalledWith({
      email: 'alice@example.com',
    });
    expect(container.querySelector('.auth-alert--warning')).toBeTruthy();
    expect(container.textContent).toContain('Verification email sent. Check your inbox.');
    expect(container.textContent).toContain('valid for 15 minutes');
    expect(container.textContent).toContain('spam folder');
    expect(replaceMock).not.toHaveBeenCalled();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('supports manual resend recovery when opened without query params and no stored auth email', async () => {
    getStoredCustomerProfileMock.mockReturnValue(null);
    getStoredCustomerSessionMock.mockReturnValue(null);
    window.history.pushState({}, '', '/auth/verify-email');

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerVerifyEmailPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(2);

    expect(verifyCustomerEmailMock).not.toHaveBeenCalled();

    const emailInput = container.querySelector('input#email') as HTMLInputElement | null;
    expect(emailInput?.value).toBe('');

    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    setter?.call(emailInput, 'manual@example.com');
    emailInput?.dispatchEvent(new Event('input', { bubbles: true }));

    const resendButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Resend verification email'),
    );
    expect(resendButton).toBeTruthy();

    resendButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushTicks(2);

    expect(resendCustomerVerificationMock).toHaveBeenCalledWith({
      email: 'manual@example.com',
    });
    expect(container.querySelector('.auth-alert--warning')).toBeTruthy();
    expect(container.textContent).toContain('Verification email sent. Check your inbox.');
    expect(container.textContent).toContain('valid for 15 minutes');
    expect(container.textContent).toContain('spam folder');
    expect(replaceMock).not.toHaveBeenCalled();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('recovers through the expired branch when a token is present but the email is missing', async () => {
    window.history.pushState({}, '', '/auth/verify-email?token=verify-token');

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerVerifyEmailPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(2);

    expect(verifyCustomerEmailMock).not.toHaveBeenCalled();
    expect(container.querySelector('.auth-alert--warning')).toBeTruthy();
    expect(container.querySelector('.auth-alert--warning .auth-submit--compact')).toBeTruthy();
    expect((container.querySelector('#email') as HTMLInputElement | null)?.value).toBe('alice@example.com');
    expect(container.textContent).toContain('This link is invalid or expired.');
    expect(container.textContent).toContain('Resend verification email');
  });

  it('shows resend failures with the shared error alert styling and keeps recovery controls available', async () => {
    resendCustomerVerificationMock.mockResolvedValueOnce({
      ok: false,
      error: 'resend_failed',
    });
    window.history.pushState({}, '', '/auth/verify-email?email=alice@example.com');

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerVerifyEmailPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(2);

    const resendButton = container.querySelector('button[type="button"]') as HTMLButtonElement | null;
    expect(resendButton).toBeTruthy();

    resendButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushTicks(2);

    expect(resendCustomerVerificationMock).toHaveBeenCalledWith({
      email: 'alice@example.com',
    });
    expect(container.querySelectorAll('.auth-alert--warning')).toHaveLength(1);
    expect(container.querySelector('.auth-alert--error')).toBeTruthy();
    expect(container.querySelector('.auth-alert--success')).toBeNull();
    expect(container.textContent).toContain('Unable to resend the verification email right now.');
    expect(resendButton?.disabled).toBe(false);
  });

  it('redirects to login recovery when the verification API returns not ok', async () => {
    verifyCustomerEmailMock.mockResolvedValue({
      ok: false,
      error: 'invalid_or_expired_token',
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerVerifyEmailPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(2);

    expect(replaceMock).toHaveBeenCalledWith(
      '/auth/login?email=alice%40example.com&verification=expired',
    );
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('redirects to retry recovery when the verification request throws', async () => {
    verifyCustomerEmailMock.mockRejectedValue(new Error('api unavailable'));

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerVerifyEmailPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(2);

    expect(replaceMock).toHaveBeenCalledWith('/auth/login?email=alice%40example.com&verification=retry');
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('renders the loading-focused verification copy without a manual form', async () => {
    verifyCustomerEmailMock.mockImplementationOnce(
      () =>
        new Promise(() => {
          // Keep the request pending so the loading copy remains visible.
        }),
    );

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <CustomerVerifyEmailPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(1);

    expect(container.textContent).toContain('验证邮箱');
    expect(container.textContent).toContain('正在验证你的邮箱链接');
    expect(container.querySelector('input')).toBeNull();
    expect(container.querySelector('button')).toBeNull();
  });
});
