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

import PrivacyPage, { metadata } from './page';

describe('PrivacyPage', () => {
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

  it('renders public privacy guidance for Kap users', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <PrivacyPage />
        </LocaleProvider>,
      );
    });

    expect(metadata.title).toBe('Privacy | Kap AI');
    expect(container.textContent).toContain('Privacy Notice');
    expect(container.textContent).toContain('We use your account, channel, reminder, and calendar-import information to run the Kap service.');
    expect(container.textContent).toContain('Google Calendar');
    expect(container.textContent).toContain('WeChat');
    expect(container.textContent).toContain('WhatsApp');
    expect(container.querySelector('a[href="/terms"]')).toBeTruthy();
    expect(container.querySelector('a[href="/faqs"]')).toBeTruthy();
  });
});
