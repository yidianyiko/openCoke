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

import FaqsPage, { metadata } from './page';

describe('FaqsPage', () => {
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

  it('renders a public FAQ for starting Kap', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <FaqsPage />
        </LocaleProvider>,
      );
    });

    expect(metadata.title).toBe('FAQ | Kap AI');
    expect(container.querySelector('.coke-site')).toBeTruthy();
    expect(container.textContent).toContain('Frequently asked questions');
    expect(container.textContent).toContain('How do I start using Kap?');
    expect(container.textContent).toContain('Personal WeChat');
    expect(container.textContent).toContain('WhatsApp');
    expect(container.textContent).toContain('Google Calendar');
    expect(container.textContent).toContain('Is Kap free to try?');
    expect(container.querySelector('a[href="/global"]')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/register"]')).toBeTruthy();
  });
});
