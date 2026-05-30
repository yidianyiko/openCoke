import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const sharedChannelsDir = resolve(process.cwd(), 'app/(admin)/admin/shared-channels');

describe('shared channel detail route shape', () => {
  it('replaces the export-blocking dynamic segment with a static detail page', () => {
    expect(existsSync(resolve(sharedChannelsDir, '[id]/page.tsx'))).toBe(false);
    expect(existsSync(resolve(sharedChannelsDir, 'detail/page.tsx'))).toBe(true);
  });
});
