import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../../../components/locale-provider';
const registerCustomerMock = vi.hoisted(() => vi.fn());
const storeCustomerAuthMock = vi.hoisted(() => vi.fn());

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
  registerCustomer: (...args: unknown[]) => registerCustomerMock(...args),
  storeCustomerAuth: (...args: unknown[]) => storeCustomerAuthMock(...args),
}));

import CustomerRegisterPage from './page';

describe('CustomerRegisterPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  const waitForEffects = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

  function setInputValue(selector: string, value: string) {
    const input = container.querySelector(selector) as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    setter?.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  beforeEach(() => {
    pushMock.mockReset();
    registerCustomerMock.mockReset();
    storeCustomerAuthMock.mockReset();
    window.history.replaceState({}, '', '/auth/register');
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('renders Chinese registration copy at /auth/register without mixed English labels', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <CustomerRegisterPage />
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('.auth-card')).toBeTruthy();
    expect(container.querySelector('.auth-form')).toBeTruthy();
    expect(container.querySelector('.auth-input#displayName')).toBeTruthy();
    expect(container.querySelector('.auth-input#password')).toBeTruthy();
    expect(container.querySelectorAll('.auth-linkrow')).toHaveLength(1);
    expect(container.querySelector('a[href="/auth/login"]')).toBeTruthy();
    expect(container.querySelector('a[href="/"]')).toBeFalsy();

    expect(container.textContent).toContain('创建你的 Kap 账号');
    expect(container.textContent).toContain('已经注册？');
    expect((container.querySelector('input#password') as HTMLInputElement | null)?.placeholder).toBe(
      '创建一个密码',
    );
    expect(container.querySelector('a[href="/auth/login"]')).toBeTruthy();
    expect(container.textContent).not.toContain('Register / 注册');
    expect(container.textContent).not.toContain('Create your Kap account');
    expect(container.textContent).not.toContain('返回首页');
  });

  it('submits through the neutral register API and routes to /auth/verify-email with the email handoff', async () => {
    registerCustomerMock.mockResolvedValueOnce({
      ok: true,
      data: {
        token: 'customer-token',
        customerId: 'ck_1',
        identityId: 'idt_1',
        email: 'alice@example.com',
        claimStatus: 'pending',
        membershipRole: 'owner',
      },
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerRegisterPage />
        </LocaleProvider>,
      );
    });

    setInputValue('#displayName', 'Alice');
    setInputValue('#email', 'alice@example.com');
    setInputValue('#password', 'password-123');

    container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await waitForEffects();

    expect(registerCustomerMock).toHaveBeenCalledWith({
      displayName: 'Alice',
      email: 'alice@example.com',
      password: 'password-123',
    });
    expect(storeCustomerAuthMock).toHaveBeenCalledWith({
      token: 'customer-token',
      customerId: 'ck_1',
      identityId: 'idt_1',
      email: 'alice@example.com',
      claimStatus: 'pending',
      membershipRole: 'owner',
    });
    expect(pushMock).toHaveBeenCalledWith('/auth/verify-email?email=alice%40example.com');
  });

  it('shows the duplicate-email conflict copy when the email already exists', async () => {
    registerCustomerMock.mockResolvedValueOnce({
      ok: false,
      error: 'email_already_exists',
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerRegisterPage />
        </LocaleProvider>,
      );
    });

    setInputValue('#displayName', 'Alice');
    setInputValue('#email', 'alice@example.com');
    setInputValue('#password', 'password-123');

    container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await waitForEffects();

    expect(container.textContent).toContain('That email address is already in use.');
    expect(container.textContent).not.toContain('Unable to create your account right now.');
    expect(storeCustomerAuthMock).not.toHaveBeenCalled();
    expect(pushMock).not.toHaveBeenCalled();
  });
});
