import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const clearAdminSessionMock = vi.hoisted(() => vi.fn());
const getAdminTokenMock = vi.hoisted(() => vi.fn());

vi.mock('./admin-auth', () => ({
  clearAdminSession: () => clearAdminSessionMock(),
  getAdminToken: () => getAdminTokenMock(),
}));

import { adminApi } from './admin-api';

const originalApiBaseUrl = process.env['NEXT_PUBLIC_API_BASE_URL'];

describe('adminApi session invalidation', () => {
  beforeEach(() => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com';
    clearAdminSessionMock.mockReset();
    getAdminTokenMock.mockReset();
    getAdminTokenMock.mockReturnValue('admin-token');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    if (originalApiBaseUrl == null) {
      delete process.env['NEXT_PUBLIC_API_BASE_URL'];
    } else {
      process.env['NEXT_PUBLIC_API_BASE_URL'] = originalApiBaseUrl;
    }
  });

  it('clears the admin session when a protected request returns account_not_found', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        status: 404,
        json: async () => ({
          ok: false,
          error: 'account_not_found',
        }),
      })) as unknown as typeof fetch,
    );

    await expect(adminApi.get('/api/admin/customers?limit=10&offset=0')).resolves.toEqual({
      ok: false,
      error: 'account_not_found',
    });

    expect(clearAdminSessionMock).toHaveBeenCalledTimes(1);
  });
});
