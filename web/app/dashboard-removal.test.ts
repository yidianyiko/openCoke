import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('dashboard route retirement cleanup', () => {
  it('removes the retired dashboard route tree', () => {
    expect(existsSync(resolve(process.cwd(), 'app/dashboard'))).toBe(false);
  });
});
