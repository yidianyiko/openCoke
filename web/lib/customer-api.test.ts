import { afterEach, describe, expect, it, vi } from 'vitest';
import { CustomerApiConfigurationError, customerApi, getCustomerApiBase } from './customer-api';

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
    delete (globalThis as typeof globalThis & { window?: Window }).window;
  } else {
    globalThis.window = originalWindow;
  }
});

describe('customer api base helpers', () => {
  it('uses the single configured Python API base URL without a trailing slash', () => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com/';
    expect(getCustomerApiBase()).toBe('https://api.example.com');
  });

  it('throws a configuration error when no public api url is configured', () => {
    delete process.env['NEXT_PUBLIC_API_BASE_URL'];

    expect(() => getCustomerApiBase()).toThrow(CustomerApiConfigurationError);
  });
});

describe('customerApi', () => {
  it('calls neutral auth endpoints with the stored customer token', async () => {
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
      text: async () => JSON.stringify({ ok: true, data: { email: 'alice@example.com' } }),
    }));
    vi.stubGlobal('fetch', fetchMock as typeof fetch);

    await expect(customerApi.get('/api/auth/me')).resolves.toEqual({
      ok: true,
      data: { email: 'alice@example.com' },
    });

    expect(fetchMock).toHaveBeenCalledWith('https://api.example.com/api/auth/me', {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer customer-token',
      },
      body: undefined,
    });
  });

  it('treats an empty successful body as undefined for delete responses', async () => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com';
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        localStorage: {
          getItem: vi.fn(() => null),
        },
      },
    });

    const fetchMock = vi.fn(async () => ({
      ok: true,
      text: async () => '',
    }));
    vi.stubGlobal('fetch', fetchMock as typeof fetch);

    await expect(customerApi.delete('/api/customer/channels/wechat-personal')).resolves.toBeUndefined();
  });

  it('throws the HTTP status when a failed response has an empty body', async () => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com';
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        localStorage: {
          getItem: vi.fn(() => null),
        },
      },
    });

    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 500,
      text: async () => '',
    }));
    vi.stubGlobal('fetch', fetchMock as typeof fetch);

    await expect(customerApi.delete('/api/customer/channels/wechat-personal')).rejects.toThrow('HTTP 500');
  });
});
