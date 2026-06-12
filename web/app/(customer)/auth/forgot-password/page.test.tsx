import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../../../components/locale-provider';

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import CustomerForgotPasswordPage from './page';

describe('CustomerForgotPasswordPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    window.history.replaceState({}, '', '/auth/forgot-password');
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('renders English disabled recovery copy with the auth login link', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerForgotPasswordPage />
        </LocaleProvider>,
      );
    });

    expect(container.textContent).toContain('Forgot your password');
    expect(container.textContent).toContain('Password recovery is temporarily unavailable.');
    expect(container.querySelector('.auth-card')).toBeTruthy();
    expect(container.querySelector('.auth-form')).toBeFalsy();
    expect(container.querySelector('.auth-input#email')).toBeFalsy();
    expect(container.querySelector('.auth-submit')).toBeFalsy();
    expect(container.querySelector('.auth-linkrow')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/login"]')).toBeTruthy();
    expect(container.textContent).not.toContain('忘记密码');
  });
});
