import QRCode from 'qrcode';

function readWebBase(): string {
  return (process.env['NEXT_PUBLIC_COKE_WEB_URL'] || process.env['DOMAIN_CLIENT'] || 'http://localhost:4040')
    .trim()
    .replace(/\/+$/, '');
}

export async function GET(_req: Request, { params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const url = `${readWebBase()}/u/${encodeURIComponent(code)}`;
  const buffer = await QRCode.toBuffer(url, { type: 'png', margin: 1, width: 320 });

  return new Response(new Uint8Array(buffer), {
    headers: {
      'content-type': 'image/png',
      'cache-control': 'public, max-age=300',
    },
  });
}
