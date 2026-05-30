import type {
  ApiResponse,
  DirectFriendshipResponse,
  PublicLinkSessionResponse,
  PublicLinkSessionStatusResponse,
  PublicUserLinkResponse,
} from './api-types';
import { getCustomerApiBase } from './customer-api';
import { getCustomerToken } from './customer-auth';

function isPublicLinkSessionResponse(data: unknown): data is PublicLinkSessionResponse {
  if (typeof data !== 'object' || data === null || Array.isArray(data)) {
    return false;
  }
  const row = data as Record<string, unknown>;
  return (
    typeof row.token === 'string' &&
    typeof row.targetAccountId === 'string' &&
    typeof row.expiresAt === 'string' &&
    typeof row.loginUrl === 'string' &&
    typeof row.registerUrl === 'string'
  );
}

function isPublicLinkSessionStatusResponse(data: unknown): data is PublicLinkSessionStatusResponse {
  if (typeof data !== 'object' || data === null || Array.isArray(data)) {
    return false;
  }
  const row = data as Record<string, unknown>;
  return (
    typeof row.providerAccountId === 'string' &&
    (typeof row.consumerAccountId === 'string' || row.consumerAccountId === null) &&
    (row.status === 'opened' || row.status === 'claimed' || row.status === 'abandoned') &&
    typeof row.expiresAt === 'string'
  );
}

export async function fetchUserLink(code: string): Promise<ApiResponse<PublicUserLinkResponse>> {
  const base = getCustomerApiBase();
  const encodedCode = encodeURIComponent(code);
  const metaRes = await fetch(`${base}/api/public/user-links/${encodedCode}`, { cache: 'no-store' });
  if (!metaRes.ok) {
    return { ok: false, error: 'link_not_active' };
  }

  const meta = (await metaRes.json()) as ApiResponse<PublicUserLinkResponse>;
  return meta.ok ? { ok: true, data: meta.data } : meta;
}

export async function openLinkSession(code: string): Promise<ApiResponse<PublicLinkSessionResponse>> {
  const base = getCustomerApiBase();
  const encodedCode = encodeURIComponent(code);

  try {
    const sessionRes = await fetch(`${base}/api/public/user-links/${encodedCode}/sessions`, {
      method: 'POST',
      cache: 'no-store',
    });
    if (!sessionRes.ok) {
      return { ok: false, error: 'link_session_not_opened' };
    }

    const session = (await sessionRes.json()) as ApiResponse<unknown>;
    if (!session.ok) {
      return session;
    }
    if (!isPublicLinkSessionResponse(session.data)) {
      return { ok: false, error: 'link_session_not_opened' };
    }

    return {
      ok: true,
      data: session.data,
    };
  } catch {
    return { ok: false, error: 'link_session_not_opened' };
  }
}

export async function getLinkSessionStatus(
  token: string,
): Promise<ApiResponse<PublicLinkSessionStatusResponse>> {
  const base = getCustomerApiBase();
  try {
    const statusRes = await fetch(
      `${base}/api/public/link-sessions/${encodeURIComponent(token)}/status`,
      { cache: 'no-store' },
    );
    if (!statusRes.ok) {
      return { ok: false, error: 'link_session_not_found' };
    }

    const status = (await statusRes.json()) as ApiResponse<unknown>;
    if (!status.ok) {
      return status;
    }
    if (!isPublicLinkSessionStatusResponse(status.data)) {
      return { ok: false, error: 'link_session_not_found' };
    }
    return { ok: true, data: status.data };
  } catch {
    return { ok: false, error: 'link_session_not_found' };
  }
}

export async function createFriendship(input: {
  token: string;
}): Promise<ApiResponse<DirectFriendshipResponse>> {
  const customerToken = getCustomerToken();
  if (!customerToken) {
    return { ok: false, error: 'unauthorized' };
  }

  try {
    const res = await fetch(
      `${getCustomerApiBase()}/api/public/link-sessions/${encodeURIComponent(input.token)}/friendships`,
      {
        method: 'POST',
        cache: 'no-store',
        headers: {
          Authorization: `Bearer ${customerToken}`,
          'Content-Type': 'application/json',
        },
      },
    );
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as ApiResponse<DirectFriendshipResponse> | null;
      if (body && !body.ok && typeof body.error === 'string') {
        return body;
      }
      return { ok: false, error: 'friendship_failed' };
    }
    return (await res.json()) as ApiResponse<DirectFriendshipResponse>;
  } catch {
    return { ok: false, error: 'friendship_failed' };
  }
}
