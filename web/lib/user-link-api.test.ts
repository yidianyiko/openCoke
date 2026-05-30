import { afterEach, describe, expect, it, vi } from 'vitest';

import { createFriendship, fetchUserLink, getLinkSessionStatus, openLinkSession } from './user-link-api';

const originalApiBaseUrl = process.env['NEXT_PUBLIC_API_BASE_URL'];
const originalWindow = globalThis.window;

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();

  if (originalApiBaseUrl == null) {
    delete process.env['NEXT_PUBLIC_API_BASE_URL'];
  } else {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = originalApiBaseUrl;
  }

  if (originalWindow === undefined) {
    Reflect.deleteProperty(globalThis, 'window');
  } else {
    globalThis.window = originalWindow;
  }
});

describe('user-link api helpers', () => {
  it('fetches a public user link without opening a session', async () => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com';
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        ok: true,
        data: {
          code: 'abc',
          status: 'active',
          profile: { displayName: 'Coach A', tagline: 'Strength coach', avatarUrl: null },
        },
      }),
    }));
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);

    await expect(fetchUserLink('abc')).resolves.toEqual({
      ok: true,
      data: {
        code: 'abc',
        status: 'active',
        profile: { displayName: 'Coach A', tagline: 'Strength coach', avatarUrl: null },
      },
    });
    expect(fetchMock).toHaveBeenCalledWith('https://api.example.com/api/public/user-links/abc', {
      cache: 'no-store',
    });
  });

  it('opens a public link session', async () => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com';
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        ok: true,
        data: {
          token: 'session-token',
          targetAccountId: 'acct_a',
          expiresAt: '2026-06-21T00:00:00.000Z',
          loginUrl: '/auth/login?next=%2Faccount%2Ffriends%3Flink_session%3Dsession-token',
          registerUrl: '/auth/register?next=%2Faccount%2Ffriends%3Flink_session%3Dsession-token',
        },
      }),
    }));
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);

    await expect(openLinkSession('abc')).resolves.toMatchObject({
      ok: true,
      data: { token: 'session-token', targetAccountId: 'acct_a' },
    });
    expect(fetchMock).toHaveBeenCalledWith('https://api.example.com/api/public/user-links/abc/sessions', {
      method: 'POST',
      cache: 'no-store',
    });
  });

  it('does not synthesize missing link-session fields from legacy responses', async () => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com';
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        ok: true,
        data: {
          token: 'session-token',
          nextUrl: '/auth/login?next=%2Faccount%2Ffriends%3Flink_session%3Dsession-token',
          registerUrl: '/auth/register?next=%2Faccount%2Ffriends%3Flink_session%3Dsession-token',
          expiresAt: '2026-06-21T00:00:00.000Z',
        },
      }),
    }));
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);

    await expect(openLinkSession('abc')).resolves.toEqual({
      ok: false,
      error: 'link_session_not_opened',
    });
  });

  it('reads a public link session status for the friends dashboard handoff', async () => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com';
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        ok: true,
        data: {
          providerAccountId: 'acct_target',
          consumerAccountId: null,
          status: 'opened',
          expiresAt: '2026-06-21T00:00:00.000Z',
        },
      }),
    }));
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);

    await expect(getLinkSessionStatus('session/token')).resolves.toEqual({
      ok: true,
      data: {
        providerAccountId: 'acct_target',
        consumerAccountId: null,
        status: 'opened',
        expiresAt: '2026-06-21T00:00:00.000Z',
      },
    });
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.com/api/public/link-sessions/session%2Ftoken/status',
      { cache: 'no-store' },
    );
  });

  it('creates a friendship for a preserved link session', async () => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com';
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        localStorage: {
          getItem: vi.fn((key: string) => (key === 'customer_token' ? 'customer-token' : null)),
        },
      },
    });
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        ok: true,
        data: { id: 'friendship_1', status: 'active', friend_account_id: 'ck_owner', created: true },
      }),
    }));
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);

    await expect(createFriendship({ token: 'session/token' })).resolves.toEqual({
      ok: true,
      data: { id: 'friendship_1', status: 'active', friend_account_id: 'ck_owner', created: true },
    });
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.com/api/public/link-sessions/session%2Ftoken/friendships',
      {
        method: 'POST',
        cache: 'no-store',
        headers: {
          Authorization: 'Bearer customer-token',
          'Content-Type': 'application/json',
        },
      },
    );
  });

  it('returns a failed friendship result when fetch rejects', async () => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com';
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        localStorage: {
          getItem: vi.fn((key: string) => (key === 'customer_token' ? 'customer-token' : null)),
        },
      },
    });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')) as unknown as typeof fetch);

    await expect(createFriendship({ token: 'session-token' })).resolves.toEqual({
      ok: false,
      error: 'friendship_failed',
    });
  });

  it('preserves friendship API error bodies on non-2xx responses', async () => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com';
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        localStorage: {
          getItem: vi.fn((key: string) => (key === 'customer_token' ? 'customer-token' : null)),
        },
      },
    });
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      json: async () => ({ ok: false, error: 'unauthorized' }),
    })) as unknown as typeof fetch);

    await expect(createFriendship({ token: 'session-token' })).resolves.toEqual({
      ok: false,
      error: 'unauthorized',
    });
  });
});
