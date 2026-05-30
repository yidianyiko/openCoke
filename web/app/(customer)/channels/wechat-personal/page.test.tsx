import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../../../components/locale-provider';

const searchParamsMock = vi.hoisted(() => vi.fn(() => new URLSearchParams()));
const replaceMock = vi.hoisted(() => vi.fn());
const getCustomerTokenMock = vi.hoisted(() => vi.fn());
const getStoredCustomerProfileMock = vi.hoisted(() => vi.fn());
const getCustomerProfileMock = vi.hoisted(() => vi.fn());
const storeCustomerProfileMock = vi.hoisted(() => vi.fn());
const clearCustomerAuthMock = vi.hoisted(() => vi.fn());
const getCustomerWechatChannelStatusMock = vi.hoisted(() => vi.fn());
const createCustomerWechatChannelMock = vi.hoisted(() => vi.fn());
const connectCustomerWechatChannelMock = vi.hoisted(() => vi.fn());
const disconnectCustomerWechatChannelMock = vi.hoisted(() => vi.fn());
const archiveCustomerWechatChannelMock = vi.hoisted(() => vi.fn());

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

vi.mock('qrcode', () => ({
  default: {
    toDataURL: vi.fn(
      async (value: string) => `data:image/png;base64,${Buffer.from(value).toString('base64')}`,
    ),
  },
}));

vi.mock('../../../../lib/customer-auth', () => ({
  getCustomerToken: () => getCustomerTokenMock(),
  getStoredCustomerProfile: () => getStoredCustomerProfileMock(),
  getCustomerProfile: (...args: unknown[]) => getCustomerProfileMock(...args),
  storeCustomerProfile: (...args: unknown[]) => storeCustomerProfileMock(...args),
  clearCustomerAuth: () => clearCustomerAuthMock(),
}));

vi.mock('../../../../lib/customer-wechat-channel', async () => {
  const actual = await vi.importActual<typeof import('../../../../lib/customer-wechat-channel')>(
    '../../../../lib/customer-wechat-channel',
  );

  return {
    ...actual,
    archiveCustomerWechatChannel: () => archiveCustomerWechatChannelMock(),
    connectCustomerWechatChannel: () => connectCustomerWechatChannelMock(),
    createCustomerWechatChannel: () => createCustomerWechatChannelMock(),
    disconnectCustomerWechatChannel: () => disconnectCustomerWechatChannelMock(),
    getCustomerWechatChannelStatus: () => getCustomerWechatChannelStatusMock(),
  };
});

import CustomerWechatPersonalPage from './page';

async function flushTicks(count: number) {
  for (let i = 0; i < count; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

async function waitForText(container: HTMLElement, text: string) {
  for (let i = 0; i < 20; i += 1) {
    if (container.textContent?.includes(text)) {
      return;
    }

    await flushTicks(1);
  }

  throw new Error(`Timed out waiting for "${text}"`);
}

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });

  return { promise, resolve, reject };
}

function buildProfile(
  overrides: Partial<{
    display_name: string;
    email_verified: boolean;
    status: 'normal' | 'suspended';
    subscription_active: boolean;
    subscription_expires_at: string | null;
  }> = {},
) {
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
    subscription_expires_at: '2026-05-01T00:00:00.000Z',
    ...overrides,
  };
}

function renderWithLocale(root: Root, locale: 'en' | 'zh') {
  flushSync(() => {
    root.render(
      <LocaleProvider initialLocale={locale}>
        <CustomerWechatPersonalPage />
      </LocaleProvider>,
    );
  });
}

describe('CustomerWechatPersonalPage initial load failure', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    replaceMock.mockReset();
    getCustomerTokenMock.mockReset();
    getStoredCustomerProfileMock.mockReset();
    getCustomerProfileMock.mockReset();
    storeCustomerProfileMock.mockReset();
    clearCustomerAuthMock.mockReset();
    getCustomerWechatChannelStatusMock.mockReset();

    searchParamsMock.mockReturnValue(new URLSearchParams());
    getCustomerTokenMock.mockReturnValue('token');
    getStoredCustomerProfileMock.mockReturnValue(buildProfile());
    getCustomerProfileMock.mockResolvedValue({
      ok: true,
      data: buildProfile(),
    });

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    root?.unmount();
    container?.remove();
  });

  it('shows a plain retry state when the initial status load fails', async () => {
    getCustomerWechatChannelStatusMock.mockResolvedValueOnce({
      ok: false,
      error: 'Temporary bridge failure',
    });

    renderWithLocale(root, 'en');
    await flushTicks(5);

    expect(container.textContent).toContain('Unable to load your WeChat channel');
    expect(container.textContent).toContain('Retry');
    expect(container.textContent).not.toContain('Reconnect');
    expect(container.textContent).not.toContain('Archive channel');
  });
});

describe('CustomerWechatPersonalPage profile hydration', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    replaceMock.mockReset();
    getCustomerTokenMock.mockReset();
    getStoredCustomerProfileMock.mockReset();
    getCustomerProfileMock.mockReset();
    storeCustomerProfileMock.mockReset();
    clearCustomerAuthMock.mockReset();
    getCustomerWechatChannelStatusMock.mockReset();

    searchParamsMock.mockReturnValue(new URLSearchParams());
    getCustomerTokenMock.mockReturnValue('token');
    getStoredCustomerProfileMock.mockReturnValue(null);
    getCustomerProfileMock.mockResolvedValue({
      ok: true,
      data: buildProfile({
        email_verified: false,
        subscription_active: false,
        subscription_expires_at: null,
      }),
    });

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    root?.unmount();
    container?.remove();
  });

  it('hydrates the missing profile from /api/auth/me before applying blocked account rules', async () => {
    renderWithLocale(root, 'en');
    await flushTicks(5);

    expect(getCustomerProfileMock).toHaveBeenCalledTimes(1);
    expect(storeCustomerProfileMock).toHaveBeenCalledWith(
      expect.objectContaining({
        email_verified: false,
        subscription_active: false,
      }),
    );
    expect(getCustomerWechatChannelStatusMock).not.toHaveBeenCalled();
    expect(container.querySelector('a[href="/account/subscription"]')).toBeTruthy();
  });

  it('refreshes a cached profile before allowing channel setup', async () => {
    getStoredCustomerProfileMock.mockReturnValue(buildProfile());
    getCustomerProfileMock.mockResolvedValueOnce({
      ok: true,
      data: buildProfile({
        email_verified: false,
        subscription_active: false,
        subscription_expires_at: null,
      }),
    });

    renderWithLocale(root, 'en');
    await flushTicks(5);

    expect(getCustomerProfileMock).toHaveBeenCalledTimes(1);
    expect(storeCustomerProfileMock).toHaveBeenCalledWith(
      expect.objectContaining({
        email_verified: false,
        subscription_active: false,
      }),
    );
    expect(getCustomerWechatChannelStatusMock).not.toHaveBeenCalled();
    expect(container.querySelector('a[href="/account/subscription"]')).toBeTruthy();
  });
});

describe('CustomerWechatPersonalPage branded layout', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    replaceMock.mockReset();
    getCustomerTokenMock.mockReset();
    getStoredCustomerProfileMock.mockReset();
    getCustomerProfileMock.mockReset();
    storeCustomerProfileMock.mockReset();
    clearCustomerAuthMock.mockReset();
    getCustomerWechatChannelStatusMock.mockReset();

    searchParamsMock.mockReturnValue(new URLSearchParams());
    getCustomerTokenMock.mockReturnValue('token');
    getStoredCustomerProfileMock.mockReturnValue(buildProfile());
    getCustomerProfileMock.mockResolvedValue({
      ok: true,
      data: buildProfile(),
    });

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    root?.unmount();
    container?.remove();
  });

  it('renders the missing-channel flow inside the branded channel setup card', async () => {
    getCustomerWechatChannelStatusMock.mockResolvedValueOnce({
      ok: true,
      data: {
        status: 'missing',
      },
    });

    renderWithLocale(root, 'en');
    await waitForText(container, 'Create my WeChat channel');

    expect(container.querySelector('.customer-channel-page')).toBeTruthy();
    expect(container.querySelector('.customer-channel-page__card')).toBeTruthy();
    expect(container.querySelector('.customer-channel-page__section')).toBeTruthy();
    expect(container.querySelector('.customer-channel-page__actions')).toBeTruthy();
    expect(container.textContent).toContain('What you can do next');
    expect(container.textContent).toContain('Need an account?');
  });
});

describe('CustomerWechatPersonalPage sign out', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    replaceMock.mockReset();
    getCustomerTokenMock.mockReset();
    getStoredCustomerProfileMock.mockReset();
    getCustomerProfileMock.mockReset();
    storeCustomerProfileMock.mockReset();
    clearCustomerAuthMock.mockReset();
    getCustomerWechatChannelStatusMock.mockReset();

    searchParamsMock.mockReturnValue(new URLSearchParams());
    getCustomerTokenMock.mockReturnValue('token');
    getStoredCustomerProfileMock.mockReturnValue(
      buildProfile({
        email_verified: false,
        subscription_active: false,
        subscription_expires_at: null,
      }),
    );
    getCustomerProfileMock.mockResolvedValue({
      ok: true,
      data: buildProfile({
        email_verified: false,
        subscription_active: false,
        subscription_expires_at: null,
      }),
    });

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    root?.unmount();
    container?.remove();
  });

  it('clears the neutral auth store when signing out from the blocked state', async () => {
    renderWithLocale(root, 'en');
    await flushTicks(2);

    const signOutButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Sign out'),
    );
    expect(signOutButton).toBeTruthy();

    signOutButton?.click();

    expect(clearCustomerAuthMock).toHaveBeenCalledTimes(1);
    expect(replaceMock).toHaveBeenCalledWith('/auth/login');
  });
});

describe('CustomerWechatPersonalPage blocked access states', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    replaceMock.mockReset();
    getCustomerTokenMock.mockReset();
    getStoredCustomerProfileMock.mockReset();
    getCustomerProfileMock.mockReset();
    storeCustomerProfileMock.mockReset();
    clearCustomerAuthMock.mockReset();
    getCustomerWechatChannelStatusMock.mockReset();

    searchParamsMock.mockReturnValue(new URLSearchParams());
    getCustomerTokenMock.mockReturnValue('token');
    getStoredCustomerProfileMock.mockReturnValue(
      buildProfile({
        email_verified: false,
        subscription_active: false,
        subscription_expires_at: null,
      }),
    );
    getCustomerProfileMock.mockResolvedValue({
      ok: true,
      data: buildProfile({
        email_verified: false,
        subscription_active: false,
        subscription_expires_at: null,
      }),
    });

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    root?.unmount();
    container?.remove();
  });

  it('shows the blocked access prompt and does not load channel state', async () => {
    renderWithLocale(root, 'zh');
    await flushTicks(2);

    expect(getCustomerWechatChannelStatusMock).not.toHaveBeenCalled();
    expect(container.textContent).toContain('先完成邮箱验证和订阅续费');
    expect(container.querySelector('a[href="/auth/verify-email"]')).toBeTruthy();
    expect(container.querySelector('a[href="/account/subscription"]')).toBeTruthy();
    expect(container.querySelector('a[href="/coke/payment"]')).toBeFalsy();
    expect(container.textContent).not.toContain('Verify your email and renew your subscription');
  });
});

describe('CustomerWechatPersonalPage archive action', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    replaceMock.mockReset();
    getCustomerTokenMock.mockReset();
    getStoredCustomerProfileMock.mockReset();
    getCustomerProfileMock.mockReset();
    storeCustomerProfileMock.mockReset();
    clearCustomerAuthMock.mockReset();
    getCustomerWechatChannelStatusMock.mockReset();
    connectCustomerWechatChannelMock.mockReset();
    disconnectCustomerWechatChannelMock.mockReset();
    createCustomerWechatChannelMock.mockReset();
    archiveCustomerWechatChannelMock.mockReset();

    searchParamsMock.mockReturnValue(new URLSearchParams());
    getCustomerTokenMock.mockReturnValue('token');
    getStoredCustomerProfileMock.mockReturnValue(buildProfile());
    getCustomerProfileMock.mockResolvedValue({
      ok: true,
      data: buildProfile(),
    });
    archiveCustomerWechatChannelMock.mockResolvedValue({
      ok: true,
      data: { status: 'archived' },
    });

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    root?.unmount();
    container?.remove();
  });

  it('lands in the archived state when archive succeeds with an empty response body', async () => {
    getCustomerWechatChannelStatusMock.mockResolvedValueOnce({
      ok: true,
      data: {
        status: 'error',
        error: 'Temporary bridge failure',
      },
    });

    renderWithLocale(root, 'en');
    await flushTicks(5);

    const archiveButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent?.includes('Archive channel'),
    );

    expect(archiveButton).toBeTruthy();
    archiveButton?.click();
    await waitForText(container, 'This WeChat channel is archived');

    expect(archiveCustomerWechatChannelMock).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain('This WeChat channel is archived');
    expect(container.textContent).toContain('Create my WeChat channel again');
    expect(container.textContent).not.toContain('Reconnect or archive your channel');
  });
});

describe('CustomerWechatPersonalPage concurrent mutation guard', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    replaceMock.mockReset();
    getCustomerTokenMock.mockReset();
    getStoredCustomerProfileMock.mockReset();
    getCustomerProfileMock.mockReset();
    storeCustomerProfileMock.mockReset();
    clearCustomerAuthMock.mockReset();
    getCustomerWechatChannelStatusMock.mockReset();
    connectCustomerWechatChannelMock.mockReset();
    disconnectCustomerWechatChannelMock.mockReset();
    createCustomerWechatChannelMock.mockReset();
    archiveCustomerWechatChannelMock.mockReset();

    searchParamsMock.mockReturnValue(new URLSearchParams());
    getCustomerTokenMock.mockReturnValue('token');
    getStoredCustomerProfileMock.mockReturnValue(buildProfile());
    getCustomerProfileMock.mockResolvedValue({
      ok: true,
      data: buildProfile(),
    });
    connectCustomerWechatChannelMock.mockReturnValue(new Promise(() => {}));

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    root?.unmount();
    container?.remove();
  });

  it('prevents archive from firing while reconnect is in flight', async () => {
    getCustomerWechatChannelStatusMock.mockResolvedValueOnce({
      ok: true,
      data: {
        status: 'error',
        error: 'Temporary bridge failure',
      },
    });

    renderWithLocale(root, 'en');
    await flushTicks(5);

    const reconnectButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Reconnect'),
    );
    const archiveButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Archive channel'),
    );

    expect(reconnectButton).toBeTruthy();
    expect(archiveButton).toBeTruthy();

    reconnectButton?.click();
    archiveButton?.click();

    expect(connectCustomerWechatChannelMock).toHaveBeenCalledTimes(1);
    expect(archiveCustomerWechatChannelMock).not.toHaveBeenCalled();
  });
});

describe('CustomerWechatPersonalPage suspended account state', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    replaceMock.mockReset();
    getCustomerTokenMock.mockReset();
    getStoredCustomerProfileMock.mockReset();
    getCustomerProfileMock.mockReset();
    storeCustomerProfileMock.mockReset();
    clearCustomerAuthMock.mockReset();
    getCustomerWechatChannelStatusMock.mockReset();

    searchParamsMock.mockReturnValue(new URLSearchParams());
    getCustomerTokenMock.mockReturnValue('token');
    getStoredCustomerProfileMock.mockReturnValue(
      buildProfile({
        status: 'suspended',
      }),
    );
    getCustomerProfileMock.mockResolvedValue({
      ok: true,
      data: buildProfile({
        status: 'suspended',
      }),
    });

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    root?.unmount();
    container?.remove();
  });

  it('shows a suspended account message without loading channel state', async () => {
    renderWithLocale(root, 'en');
    await flushTicks(2);

    expect(getCustomerWechatChannelStatusMock).not.toHaveBeenCalled();
    expect(container.textContent).toContain('Your Kap account is suspended');
    expect(container.textContent).not.toContain('Create my WeChat channel');
  });
});

describe('CustomerWechatPersonalPage refresh ordering', () => {
  let container: HTMLDivElement;
  let root: Root;
  let intervalCallbacks: Array<() => void>;

  beforeEach(() => {
    replaceMock.mockReset();
    getCustomerTokenMock.mockReset();
    getStoredCustomerProfileMock.mockReset();
    getCustomerProfileMock.mockReset();
    storeCustomerProfileMock.mockReset();
    clearCustomerAuthMock.mockReset();
    getCustomerWechatChannelStatusMock.mockReset();
    connectCustomerWechatChannelMock.mockReset();
    disconnectCustomerWechatChannelMock.mockReset();
    createCustomerWechatChannelMock.mockReset();
    archiveCustomerWechatChannelMock.mockReset();
    intervalCallbacks = [];

    vi.spyOn(window, 'setInterval').mockImplementation(((handler: TimerHandler) => {
      intervalCallbacks.push(() => {
        if (typeof handler === 'function') {
          handler();
        }
      });
      return 1 as unknown as number;
    }) as typeof window.setInterval);
    vi.spyOn(window, 'clearInterval').mockImplementation(() => undefined);

    searchParamsMock.mockReturnValue(new URLSearchParams());
    getCustomerTokenMock.mockReturnValue('token');
    getStoredCustomerProfileMock.mockReturnValue(buildProfile());
    getCustomerProfileMock.mockResolvedValue({
      ok: true,
      data: buildProfile(),
    });

    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    root?.unmount();
    container?.remove();
  });

  it('keeps fresher mutation QR data when an older poll resolves later', async () => {
    const staleRefresh = createDeferred<{
      ok: true;
      data: {
        status: 'pending';
        connect_url: string;
        expires_at: number;
      };
    }>();

    getCustomerWechatChannelStatusMock
      .mockResolvedValueOnce({
        ok: true,
        data: {
          status: 'pending',
          connect_url: 'https://wx.example.com/connect/initial',
          expires_at: 1710000000,
        },
      })
      .mockReturnValueOnce(staleRefresh.promise);

    connectCustomerWechatChannelMock.mockResolvedValueOnce({
      ok: true,
      data: {
        status: 'pending',
        connect_url: 'https://wx.example.com/connect/fresh',
        expires_at: 1710003600,
      },
    });

    renderWithLocale(root, 'en');

    const freshExpiryText = new Date(1710003600 * 1000).toLocaleString();
    const staleExpiryText = new Date(1709990000 * 1000).toLocaleString();

    await flushTicks(5);
    expect(intervalCallbacks).toHaveLength(1);
    intervalCallbacks[0]();

    const refreshButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Refresh QR'),
    );
    expect(refreshButton).toBeTruthy();
    refreshButton?.click();

    await waitForText(container, freshExpiryText);
    staleRefresh.resolve({
      ok: true,
      data: {
        status: 'pending',
        connect_url: 'https://wx.example.com/connect/stale',
        expires_at: 1709990000,
      },
    });

    await flushTicks(5);

    expect(container.textContent).toContain(freshExpiryText);
    expect(container.textContent).not.toContain(staleExpiryText);
  });
});
