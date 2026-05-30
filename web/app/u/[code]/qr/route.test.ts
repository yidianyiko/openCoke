import { describe, expect, it } from 'vitest';
import { GET } from './route';

describe('/u/[code]/qr', () => {
  it('returns a QR png for the absolute user link URL', async () => {
    process.env.NEXT_PUBLIC_COKE_WEB_URL = 'https://kap.example';

    const res = await GET(new Request('https://kap.example/u/AbCdEfGhIjK_/qr'), {
      params: Promise.resolve({ code: 'AbCdEfGhIjK_' }),
    });

    expect(res.headers.get('content-type')).toBe('image/png');
    expect((await res.arrayBuffer()).byteLength).toBeGreaterThan(100);
  });
});
