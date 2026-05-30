import { clearAdminSession, getAdminToken, type AdminLoginResult } from './admin-auth';
import { getCustomerApiBase } from './customer-api';

type AdminApiSuccess<T> = {
  ok: true;
  data: T;
};

type AdminApiFailure = {
  ok: false;
  error: string;
  issues?: unknown;
};

type AdminApiResponse<T> = AdminApiSuccess<T> | AdminApiFailure;

export type AdminCustomerRow = {
  id: string;
  displayName: string;
  contactIdentifier: {
    type: string;
    value: string;
  };
  claimStatus: string;
  registeredAt: string;
  firstSeenAt: string | null;
  lastMessageAt: string | null;
  conversationCount: number;
  messageCount: number;
  agent: {
    id: string;
    slug: string;
    name: string;
    provisionStatus: string;
  } | null;
  channelSummary: {
    total: number;
    connected: number;
    disconnected: number;
    kinds: string[];
  };
  parkedInboundCount: number;
};

export type AdminSharedChannelRow = {
  id: string;
  name: string;
  kind: string;
  status: string;
  ownershipKind: string;
  customerId: string | null;
  hasWebhookToken?: boolean;
  hasSigningSecret?: boolean;
  agent: {
    id: string;
    slug: string;
    name: string;
  } | null;
  createdAt: string;
  updatedAt: string;
};

export type AdminSharedChannelDetail = AdminSharedChannelRow & {
  config: Record<string, unknown>;
  hasWebhookToken?: boolean;
  hasSigningSecret?: boolean;
};

export type AdminDeliveryRow = {
  id: string;
  tenantId: string | null;
  channelId: string | null;
  idempotencyKey: string;
  status: string;
  error: string | null;
  createdAt: string;
  updatedAt: string;
};

export type AdminAccountRecord = {
  id: string;
  email: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
};

export type AdminDashboardMetrics = {
  activeCustomers: {
    day: number;
    week: number;
    month: number;
  };
  messages: {
    day: number;
    week: number;
    month: number;
    userDay: number;
    assistantDay: number;
    total: number;
    lastMessageAt: string | null;
  };
  customers: {
    total: number;
  };
  conversations: {
    total: number;
  };
  channels: {
    total: number;
    connected: number;
  };
  parkedInbounds: {
    queued: number;
  };
  agentBindings: {
    ready: number;
    pending: number;
    error: number;
  };
};

export type AdminPagedResult<T> = {
  rows: T[];
  total: number;
  limit: number;
  offset: number;
};

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<AdminApiResponse<T>> {
  const token = getAdminToken();
  const headers: Record<string, string> = {
    Accept: 'application/json',
  };

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  if (token) {
    headers.Authorization = 'Bearer ' + token;
  }

  try {
    const res = await fetch(getCustomerApiBase() + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    const json = (await res.json()) as AdminApiResponse<T>;
    if (
      !json.ok &&
      path !== '/api/admin/login' &&
      (
        res.status === 401 ||
        res.status === 403 ||
        (res.status === 404 && json.error === 'account_not_found')
      )
    ) {
      clearAdminSession();
    }

    return json;
  } catch {
    return {
      ok: false,
      error: 'network_error',
    };
  }
}

export const adminApi = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
};

export type { AdminLoginResult };
