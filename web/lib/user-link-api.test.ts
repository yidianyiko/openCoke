import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchUserLink } from './user-link-api';

const originalApiBaseUrl = process.env['NEXT_PUBLIC_API_BASE_URL'];

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();

  if (originalApiBaseUrl == null) {
    delete process.env['NEXT_PUBLIC_API_BASE_URL'];
  } else {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = originalApiBaseUrl;
  }
});

describe('user-link api helpers', () => {
  it('fetches a public user link from the clean raw response body', async () => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com/';
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        code: 'abc',
        status: 'active',
        profile: { displayName: 'Coach A', tagline: null, avatarUrl: null },
      }),
    }));
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);

    await expect(fetchUserLink('a/b')).resolves.toEqual({
      ok: true,
      data: {
        code: 'abc',
        status: 'active',
        profile: { displayName: 'Coach A', tagline: null, avatarUrl: null },
      },
    });
    expect(fetchMock).toHaveBeenCalledWith('https://api.example.com/api/public/user-links/a%2Fb', {
      cache: 'no-store',
    });
  });

  it('maps non-200 public link responses to link_not_active', async () => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com';
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false })) as unknown as typeof fetch);

    await expect(fetchUserLink('missing')).resolves.toEqual({
      ok: false,
      error: 'link_not_active',
    });
  });
});
