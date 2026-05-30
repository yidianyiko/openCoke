import { describe, expect, it, vi } from 'vitest';

vi.mock('next/font/google', () => {
  const stub = () => ({ variable: '' });
  return { Fraunces: stub, Inter: stub, JetBrains_Mono: stub };
});

import { metadata } from './layout';
import { metadata as globalMetadata } from './global/page';

describe('root metadata', () => {
  it('brands the public site title as kap', () => {
    expect(metadata.title).toBe('kap | An AI Supervisor That Follows Up');
  });

  it('brands the public site description as kap ai', () => {
    expect(metadata.description).toBe(
      'Kap AI turns goals into reminders, check-ins, and follow-up across personal WeChat and WhatsApp.',
    );
  });

  it('points the public site icon at the koala badge asset', () => {
    expect(metadata.icons).toEqual({ icon: '/kap-koala-badge.png' });
  });

  it('brands the global page as a WhatsApp supervision entry', () => {
    expect(globalMetadata.title).toBe('kap global | WhatsApp supervision that follows up');
    expect(globalMetadata.description).toBe(
      'Start a WhatsApp thread with Kap to turn one real goal into a reminder, check-in, and follow-up loop.',
    );
  });
});
