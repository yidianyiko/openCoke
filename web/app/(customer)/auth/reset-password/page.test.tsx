import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../../../components/locale-provider';
const resetCustomerPasswordMock = vi.hoisted(() => vi.fn());

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import CustomerResetPasswordPage from './page';

describe('CustomerResetPasswordPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    resetCustomerPasswordMock.mockReset();
    window.history.pushState({}, '', '/auth/reset-password?token=token-123');
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('renders Chinese disabled reset-password copy with the auth login link', async () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <CustomerResetPasswordPage />
        </LocaleProvider>,
      );
    });

    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(container.textContent).toContain('重置密码');
    expect(container.textContent).toContain('密码找回暂时不可用');
    expect(container.querySelector('.auth-card')).toBeTruthy();
    expect(container.querySelector('.auth-form')).toBeFalsy();
    expect(container.querySelector('.auth-input#token')).toBeFalsy();
    expect(container.querySelector('.auth-input#confirmPassword')).toBeFalsy();
    expect(container.querySelector('.auth-submit')).toBeFalsy();
    expect(container.querySelector('.auth-linkrow')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/login"]')).toBeTruthy();
    expect(container.textContent).not.toContain('Reset your password');
    expect(resetCustomerPasswordMock).not.toHaveBeenCalled();
  });
});
