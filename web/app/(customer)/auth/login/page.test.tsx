import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../../../components/locale-provider';
const loginCustomerMock = vi.hoisted(() => vi.fn());
const getCustomerProfileMock = vi.hoisted(() => vi.fn());
const storeCustomerAuthMock = vi.hoisted(() => vi.fn());
const storeCustomerProfileMock = vi.hoisted(() => vi.fn());
const clearCustomerAuthMock = vi.hoisted(() => vi.fn());

const pushMock = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock('../../../../lib/customer-auth', () => ({
  loginCustomer: (...args: unknown[]) => loginCustomerMock(...args),
  getCustomerProfile: (...args: unknown[]) => getCustomerProfileMock(...args),
  storeCustomerAuth: (...args: unknown[]) => storeCustomerAuthMock(...args),
  storeCustomerProfile: (...args: unknown[]) => storeCustomerProfileMock(...args),
  clearCustomerAuth: (...args: unknown[]) => clearCustomerAuthMock(...args),
}));

import CustomerLoginPage from './page';

function makeCustomerAuthResult() {
  return {
    token: 'customer-token',
    customerId: 'ck_1',
    identityId: 'idt_1',
    email: 'alice@example.com',
    claimStatus: 'active' as const,
    membershipRole: 'owner' as const,
  };
}

function makeCustomerProfile(overrides: Partial<{
  id: string;
  customerId: string;
  identityId: string;
  claimStatus: 'active' | 'unclaimed' | 'pending';
  email: string;
  membershipRole: 'owner' | 'member' | 'viewer';
  display_name: string;
  email_verified: boolean;
  status: 'normal' | 'suspended';
  subscription_active: boolean;
  subscription_expires_at: string | null;
}> = {}) {
  return {
    id: 'ck_1',
    customerId: 'ck_1',
    identityId: 'idt_1',
    claimStatus: 'active' as const,
    email: 'alice@example.com',
    membershipRole: 'owner' as const,
    display_name: 'Alice',
    email_verified: true,
    status: 'normal' as const,
    subscription_active: true,
    subscription_expires_at: null,
    ...overrides,
  };
}

describe('CustomerLoginPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  async function flushTicks(count: number) {
    for (let i = 0; i < count; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  }

  function setInputValue(selector: string, value: string) {
    const input = container.querySelector(selector) as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    setter?.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  async function submitLoginForm(email = 'alice@example.com', password = 'password-123') {
    setInputValue('#email', email);
    setInputValue('#password', password);
    container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await flushTicks(3);
  }

  beforeEach(() => {
    pushMock.mockReset();
    loginCustomerMock.mockReset();
    getCustomerProfileMock.mockReset();
    storeCustomerAuthMock.mockReset();
    storeCustomerProfileMock.mockReset();
    clearCustomerAuthMock.mockReset();
    window.history.replaceState({}, '', '/auth/login');
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root?.unmount();
    container?.remove();
  });

  it('renders the customer login experience at /auth/login with auth route links', async () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerLoginPage />
        </LocaleProvider>,
      );
    });
    await flushTicks(1);

    expect(container.querySelector('.auth-card')).toBeTruthy();
    expect(container.querySelector('.auth-form')).toBeTruthy();
    expect(container.querySelector('.auth-input#email')).toBeTruthy();
    expect(container.querySelector('.auth-submit')).toBeTruthy();
    expect(container.querySelectorAll('.auth-linkrow')).toHaveLength(1);
    expect(container.querySelector('a[href="/auth/register"]')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/forgot-password"]')).toBeFalsy();
    expect(container.querySelector('a[href="/"]')).toBeFalsy();

    const links = Array.from(container.querySelectorAll('a')).map((link) => link.getAttribute('href'));

    expect(container.textContent).toContain('Sign in to Kap');
    expect(container.textContent).not.toContain('Return to your Kap account');
    expect(container.textContent).not.toContain('Back to homepage');
    expect(links).not.toContain('/auth/forgot-password');
    expect(links).toContain('/auth/register');
  });

  it('prefills the email but does not show expired-verification recovery UI', async () => {
    window.history.replaceState({}, '', '/auth/login?email=alice%40example.com&verification=expired');

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerLoginPage />
        </LocaleProvider>,
      );
    });
    await flushTicks(1);

    expect((container.querySelector('#email') as HTMLInputElement).value).toBe('alice@example.com');
    expect(container.querySelector('.auth-alert--warning')).toBeFalsy();
    expect(container.textContent).not.toContain('This link is invalid or expired.');
    expect(container.textContent).not.toContain('Resend verification email');
    expect(container.querySelector('button[type="button"]')).toBeFalsy();
  });

  it('does not show retry verification recovery UI while email auth is disabled', async () => {
    window.history.replaceState({}, '', '/auth/login?email=alice%40example.com&verification=retry');

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerLoginPage />
        </LocaleProvider>,
      );
    });
    await flushTicks(1);

    expect((container.querySelector('#email') as HTMLInputElement).value).toBe('alice@example.com');
    expect(container.textContent).not.toContain("We couldn't verify your email right now.");
    expect(container.textContent).not.toContain('Resend verification email');
    expect(container.querySelector('button[type="button"]')).toBeFalsy();
  });

  it('allows login to continue even when the hydrated profile still reports unverified email', async () => {
    loginCustomerMock.mockResolvedValueOnce({
      ok: true,
      data: makeCustomerAuthResult(),
    });
    getCustomerProfileMock.mockResolvedValueOnce({
      ok: true,
      data: makeCustomerProfile({
        email_verified: false,
      }),
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerLoginPage />
        </LocaleProvider>,
      );
    });

    await submitLoginForm();

    expect(loginCustomerMock).toHaveBeenCalledWith({
      email: 'alice@example.com',
      password: 'password-123',
    });
    expect(getCustomerProfileMock).toHaveBeenCalledWith();
    expect(storeCustomerProfileMock).toHaveBeenCalledWith(
      expect.objectContaining({
        email_verified: false,
      }),
    );
    expect(pushMock).not.toHaveBeenCalledWith('/auth/verify-email');
    expect(pushMock).toHaveBeenCalledWith('/channels/wechat-personal');
    expect(container.textContent).not.toContain('This link is invalid or expired.');
    expect(container.querySelector('button[type="button"]')).toBeFalsy();
  });

  it('routes renewal-required login success through the account subscription path', async () => {
    loginCustomerMock.mockResolvedValueOnce({
      ok: true,
      data: makeCustomerAuthResult(),
    });
    getCustomerProfileMock.mockResolvedValueOnce({
      ok: true,
      data: makeCustomerProfile({
        subscription_active: false,
      }),
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerLoginPage />
        </LocaleProvider>,
      );
    });

    await submitLoginForm();

    expect(loginCustomerMock).toHaveBeenCalledWith({
      email: 'alice@example.com',
      password: 'password-123',
    });
    expect(getCustomerProfileMock).toHaveBeenCalledWith();
    expect(storeCustomerProfileMock).toHaveBeenCalledWith(
      expect.objectContaining({
        subscription_active: false,
      }),
    );
    expect(pushMock).toHaveBeenCalledWith('/account/subscription');
  });

  it('stores the neutral customer session and hydrated customer profile before routing to the channel surface', async () => {
    loginCustomerMock.mockResolvedValueOnce({
      ok: true,
      data: makeCustomerAuthResult(),
    });
    getCustomerProfileMock.mockResolvedValueOnce({
      ok: true,
      data: makeCustomerProfile(),
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerLoginPage />
        </LocaleProvider>,
      );
    });

    await submitLoginForm();

    expect(loginCustomerMock).toHaveBeenCalledWith({
      email: 'alice@example.com',
      password: 'password-123',
    });
    expect(getCustomerProfileMock).toHaveBeenCalledWith();
    expect(storeCustomerProfileMock).toHaveBeenCalledWith(makeCustomerProfile());
    expect(pushMock).toHaveBeenCalledWith('/channels/wechat-personal');
  });

  it('shows a generic error and does not route when the compatibility profile cannot be loaded', async () => {
    loginCustomerMock.mockResolvedValueOnce({
      ok: true,
      data: makeCustomerAuthResult(),
    });
    getCustomerProfileMock.mockResolvedValueOnce({
      ok: false,
      error: 'account_not_found',
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerLoginPage />
        </LocaleProvider>,
      );
    });

    await submitLoginForm();

    expect(loginCustomerMock).toHaveBeenCalledWith({
      email: 'alice@example.com',
      password: 'password-123',
    });
    expect(getCustomerProfileMock).toHaveBeenCalledWith();
    expect(storeCustomerProfileMock).not.toHaveBeenCalled();
    expect(clearCustomerAuthMock).toHaveBeenCalledTimes(1);
    expect(pushMock).not.toHaveBeenCalled();
    expect(container.textContent).toContain('Unable to sign in right now.');
  });

  it('preserves a safe neutral internal next destination after login', async () => {
    loginCustomerMock.mockResolvedValueOnce({
      ok: true,
      data: makeCustomerAuthResult(),
    });
    getCustomerProfileMock.mockResolvedValueOnce({
      ok: true,
      data: makeCustomerProfile(),
    });
    window.history.replaceState({}, '', '/auth/login?next=%2Fchannels%2Fwechat-personal%3Fsource%3Dauth');

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerLoginPage />
        </LocaleProvider>,
      );
    });

    await submitLoginForm();

    expect(loginCustomerMock).toHaveBeenCalledWith({
      email: 'alice@example.com',
      password: 'password-123',
    });
    expect(getCustomerProfileMock).toHaveBeenCalledWith();
    expect(pushMock).toHaveBeenCalledWith('/channels/wechat-personal?source=auth');
  });

  it('falls back to the neutral default when next is an unsafe external target', async () => {
    loginCustomerMock.mockResolvedValueOnce({
      ok: true,
      data: makeCustomerAuthResult(),
    });
    getCustomerProfileMock.mockResolvedValueOnce({
      ok: true,
      data: makeCustomerProfile(),
    });
    window.history.replaceState({}, '', '/auth/login?next=https%3A%2F%2Fevil.example%2Fphish');

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerLoginPage />
        </LocaleProvider>,
      );
    });

    await submitLoginForm();

    expect(loginCustomerMock).toHaveBeenCalledWith({
      email: 'alice@example.com',
      password: 'password-123',
    });
    expect(getCustomerProfileMock).toHaveBeenCalledWith();
    expect(pushMock).toHaveBeenCalledWith('/channels/wechat-personal');
    expect(pushMock).not.toHaveBeenCalledWith('https://evil.example/phish');
  });

  it('only shows the resend button in verification recovery state', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <CustomerLoginPage />
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('button[type="button"]')).toBeNull();
    expect(container.textContent).not.toContain('重新发送验证邮件');
  });
});
