import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';

import { LocaleProvider } from '../../components/locale-provider';

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import DemosPage, { metadata } from './page';

describe('DemosPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('renders a public demo library with concrete Kap conversations', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <DemosPage />
        </LocaleProvider>,
      );
    });

    expect(metadata.title).toBe('Demos | Kap AI');
    expect(container.querySelector('.coke-site')).toBeTruthy();
    expect(container.textContent).toContain('Conversation demos');
    expect(container.textContent).toContain('Finish one IELTS practice set');
    expect(container.textContent).toContain('Pay the credit card bill');
    expect(container.textContent).toContain('Turn Google Calendar events into reminders');
    expect(container.textContent).toContain('Recover a Personal WeChat channel');
    expect(container.textContent).toContain('Start from WhatsApp');
    expect(container.textContent).toContain('Follow-up active');
    expect(container.querySelectorAll('.demo-card')).toHaveLength(6);
    expect(container.querySelector('a[href="/global"]')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/register"]')).toBeTruthy();
  });
});
