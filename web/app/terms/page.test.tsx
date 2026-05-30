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

import TermsPage, { metadata } from './page';

describe('TermsPage', () => {
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

  it('renders public terms for Kap usage', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <TermsPage />
        </LocaleProvider>,
      );
    });

    expect(metadata.title).toBe('Terms | Kap AI');
    expect(container.textContent).toContain('Terms of Use');
    expect(container.textContent).toContain('Kap helps you manage reminders, check-ins, follow-up, channel access, and calendar import flows.');
    expect(container.textContent).toContain('You are responsible for the tasks, decisions, and commitments you ask Kap to track.');
    expect(container.querySelector('a[href="/privacy"]')).toBeTruthy();
    expect(container.querySelector('a[href="/faqs"]')).toBeTruthy();
  });
});
