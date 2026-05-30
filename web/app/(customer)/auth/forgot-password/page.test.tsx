import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../../../components/locale-provider';
const requestCustomerPasswordResetMock = vi.hoisted(() => vi.fn());

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock('../../../../lib/customer-auth', () => ({
  requestCustomerPasswordReset: (...args: unknown[]) => requestCustomerPasswordResetMock(...args),
}));

import CustomerForgotPasswordPage from './page';

describe('CustomerForgotPasswordPage', () => {
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
    requestCustomerPasswordResetMock.mockReset();
    window.history.replaceState({}, '', '/auth/forgot-password');
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('renders English recovery copy with the auth login link', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerForgotPasswordPage />
        </LocaleProvider>,
      );
    });

    expect(container.textContent).toContain('Forgot your password');
    expect(container.textContent).toContain('Send reset link');
    expect(container.textContent).toContain('Remembered your password?');
    expect(container.querySelector('.auth-card')).toBeTruthy();
    expect(container.querySelector('.auth-form')).toBeTruthy();
    expect(container.querySelector('.auth-input#email')).toBeTruthy();
    expect(container.querySelector('.auth-submit')).toBeTruthy();
    expect(container.querySelector('.auth-linkrow')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/login"]')).toBeTruthy();
    expect(container.textContent).not.toContain('忘记密码');
  });

  it('submits through the neutral forgot-password API and shows success copy', async () => {
    requestCustomerPasswordResetMock.mockResolvedValueOnce({ ok: true, data: {} });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerForgotPasswordPage />
        </LocaleProvider>,
      );
    });

    setInputValue('#email', 'alice@example.com');
    container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));

    await waitForEffects();

    expect(requestCustomerPasswordResetMock).toHaveBeenCalledWith({
      email: 'alice@example.com',
    });
    expect(container.textContent).toContain('Password reset instructions were sent if the account exists.');
  });
});
