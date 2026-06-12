import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import { LocaleProvider } from '../../../../components/locale-provider';

const replaceMock = vi.hoisted(() => vi.fn());
const verifyCustomerEmailMock = vi.hoisted(() => vi.fn());
const resendCustomerVerificationMock = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: replaceMock,
  }),
}));

vi.mock('../../../../lib/customer-auth', () => ({
  verifyCustomerEmail: (...args: unknown[]) => verifyCustomerEmailMock(...args),
  resendCustomerVerification: (...args: unknown[]) => resendCustomerVerificationMock(...args),
}));

import CustomerVerifyEmailPage from './page';

describe('CustomerVerifyEmailPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    replaceMock.mockReset();
    verifyCustomerEmailMock.mockReset();
    resendCustomerVerificationMock.mockReset();
    window.history.pushState({}, '', '/auth/verify-email?token=verify-token&email=alice@example.com');

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root?.unmount();
    container?.remove();
  });

  it('shows email verification as disabled without verifying or resending', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerVerifyEmailPage />
        </LocaleProvider>,
      );
    });

    expect(container.textContent).toContain('Email verification is temporarily disabled.');
    expect(container.textContent).toContain('New accounts can sign in immediately after registration.');
    expect(container.textContent).toContain('Back to sign in');
    expect(container.querySelector('a[href="/auth/login"]')).toBeTruthy();
    expect(container.querySelector('input')).toBeNull();
    expect(container.querySelector('button')).toBeNull();
    expect(verifyCustomerEmailMock).not.toHaveBeenCalled();
    expect(resendCustomerVerificationMock).not.toHaveBeenCalled();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it('uses the disabled email-auth copy in Chinese', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <CustomerVerifyEmailPage />
        </LocaleProvider>,
      );
    });

    expect(container.textContent).toContain('邮箱验证已暂时关闭。');
    expect(container.textContent).toContain('新账号注册后可以直接登录。');
    expect(container.textContent).toContain('返回登录');
  });
});
