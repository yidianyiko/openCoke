type TokenGetter = () => string | null;

function getStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function getStoredCustomerToken(): string | null {
  return getStorage()?.getItem('customer_token') ?? null;
}

export class CustomerApiConfigurationError extends Error {
  constructor() {
    super('Customer API base URL is not configured');
    this.name = 'CustomerApiConfigurationError';
  }
}

export function getCustomerApiBase(): string {
  const base = process.env['NEXT_PUBLIC_API_BASE_URL'];
  if (!base) {
    throw new CustomerApiConfigurationError();
  }
  return base.replace(/\/+$/, '');
}

async function request<T>(method: string, path: string, getToken: TokenGetter, body?: unknown): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${getCustomerApiBase()}${path}`, {
    method,
    headers,
    body: body != null ? JSON.stringify(body) : undefined,
  });

  const text = await res.text();
  if (!res.ok && text.trim() === '') {
    throw new Error(`HTTP ${res.status}`);
  }

  if (res.ok && text.trim() === '') {
    return undefined as T;
  }

  return JSON.parse(text) as T;
}

function createCustomerApiClient(getToken: TokenGetter) {
  return {
    get: <T>(path: string) => request<T>('GET', path, getToken),
    post: <T>(path: string, body?: unknown) => request<T>('POST', path, getToken, body),
    patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, getToken, body),
    delete: <T>(path: string) => request<T>('DELETE', path, getToken),
  };
}

export const customerApi = createCustomerApiClient(getStoredCustomerToken);
