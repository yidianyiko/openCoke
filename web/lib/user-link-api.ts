import type { ApiResponse, PublicUserLinkResponse } from './api-types';
import { getCustomerApiBase } from './customer-api';

export async function fetchUserLink(code: string): Promise<ApiResponse<PublicUserLinkResponse>> {
  const base = getCustomerApiBase();
  const encodedCode = encodeURIComponent(code);
  const metaRes = await fetch(`${base}/api/public/user-links/${encodedCode}`, { cache: 'no-store' });
  if (!metaRes.ok) {
    return { ok: false, error: 'link_not_active' };
  }

  return {
    ok: true,
    data: (await metaRes.json()) as PublicUserLinkResponse,
  };
}
