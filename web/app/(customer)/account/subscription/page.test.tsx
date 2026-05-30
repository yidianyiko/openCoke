import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../../../components/locale-provider';
import { customerApi } from '../../../../lib/customer-api';

const replaceMock = vi.hoisted(() => vi.fn());
const openMock = vi.hoisted(() => vi.fn());
const getMock = vi.hoisted(() => vi.fn());
const postMock = vi.hoisted(() => vi.fn());
const searchParamsMock = vi.hoisted(() => vi.fn(() => new URLSearchParams()));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: replaceMock,
  }),
  useSearchParams: () => searchParamsMock(),
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock('../../../../lib/customer-api', () => ({
  customerApi: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}));

import CustomerSubscriptionPage from './page';

async function flushTicks(count: number) {
  for (let i = 0; i < count; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

function makeSubscriptionSnapshot(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    accountStatus: 'normal' as const,
    emailVerified: true,
    subscriptionActive: false,
    subscriptionExpiresAt: '2026-05-10T00:00:00.000Z',
    accountAccessAllowed: false,
    accountAccessDeniedReason: 'subscription_required' as const,
    renewalUrl: 'https://coke.example/account/subscription',
    ...overrides,
  };
}

describe('CustomerSubscriptionPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    replaceMock.mockReset();
    openMock.mockReset();
    getMock.mockReset();
    postMock.mockReset();
    searchParamsMock.mockReset();
    searchParamsMock.mockReturnValue(new URLSearchParams());
    getMock.mockResolvedValue({
      ok: true,
      data: makeSubscriptionSnapshot(),
    });
    postMock.mockResolvedValue({
      ok: true,
      data: {
        url: 'https://stripe.example/checkout/session_123',
      },
    });
    vi.spyOn(window, 'open').mockImplementation(openMock);
    window.history.replaceState({}, '', '/account/subscription');
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    root.unmount();
    container.remove();
  });

  it('fetches the subscription snapshot first and only starts checkout after an explicit click', async () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerSubscriptionPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(5);

    expect(container.querySelector('.customer-view.customer-view--narrow')).toBeTruthy();
    expect(container.querySelector('.customer-panel.customer-panel--narrow')).toBeTruthy();
    expect(getMock).toHaveBeenCalledWith('/api/customer/subscription');
    expect(postMock).not.toHaveBeenCalled();
    expect(container.querySelector('button[type="button"].customer-action.customer-action--primary')).toBeTruthy();
    expect(container.textContent).toContain('Renew your access');

    (container.querySelector('button[type="button"]') as HTMLButtonElement).click();
    await flushTicks(5);

    expect(postMock).toHaveBeenCalledWith('/api/customer/subscription/checkout');
    expect(openMock).toHaveBeenCalledWith('https://stripe.example/checkout/session_123', '_self');
  });

  it('steers email-verification blockers to the verify-email route instead of offering checkout', async () => {
    getMock.mockResolvedValueOnce({
      ok: true,
      data: makeSubscriptionSnapshot({
        emailVerified: false,
        accountAccessAllowed: false,
        accountAccessDeniedReason: 'email_not_verified',
      }),
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerSubscriptionPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(5);

    expect(container.querySelector('a[href="/auth/verify-email"]')).toBeTruthy();
    expect(container.querySelector('button[type="button"]')).toBeFalsy();
    expect(postMock).not.toHaveBeenCalled();
    expect(container.textContent).toContain('Email verification is still required before checkout is available.');
  });

  it('redirects unauthenticated users to the login route after the snapshot request fails', async () => {
    getMock.mockResolvedValueOnce({
      ok: false,
      error: 'unauthorized',
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerSubscriptionPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(2);

    expect(replaceMock).toHaveBeenCalledWith('/auth/login?next=/account/subscription');
    expect(postMock).not.toHaveBeenCalled();
  });

  it('renders the success state without re-triggering checkout', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('status=success'));
    getMock.mockResolvedValueOnce({
      ok: true,
      data: makeSubscriptionSnapshot({
        subscriptionActive: true,
        accountAccessAllowed: true,
        accountAccessDeniedReason: null,
      }),
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerSubscriptionPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(1);

    expect(container.querySelector('.customer-panel.customer-panel--narrow')).toBeTruthy();
    expect(container.textContent).toContain('Payment complete');
    expect(getMock).toHaveBeenCalledWith('/api/customer/subscription');
    expect(container.querySelector('a[href="/channels/wechat-personal"].customer-action')).toBeTruthy();
    expect(container.querySelector('a[href="/account/subscription"].customer-action')).toBeTruthy();
    expect(postMock).not.toHaveBeenCalled();
  });

  it('keeps success-mode users on the subscription page until the renewed access is visible', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('status=success'));
    getMock.mockResolvedValueOnce({
      ok: true,
      data: makeSubscriptionSnapshot({
        subscriptionActive: false,
        accountAccessAllowed: false,
        accountAccessDeniedReason: 'subscription_required',
      }),
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerSubscriptionPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(5);

    expect(getMock).toHaveBeenCalledWith('/api/customer/subscription');
    expect(container.querySelector('a[href="/channels/wechat-personal"]')).toBeFalsy();
    expect(container.querySelector('a[href="/account/subscription"]')).toBeTruthy();
    expect(postMock).not.toHaveBeenCalled();
  });

  it('renders the cancel state without re-triggering checkout', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('status=cancel'));

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <CustomerSubscriptionPage />
        </LocaleProvider>,
      );
    });

    await flushTicks(1);

    expect(container.textContent).toContain('支付已取消');
    expect(container.querySelector('a[href="/channels/wechat-personal"]')).toBeTruthy();
    expect(container.querySelector('a[href="/account/subscription"]')).toBeTruthy();
    expect(getMock).not.toHaveBeenCalled();
    expect(postMock).not.toHaveBeenCalled();
  });
});
