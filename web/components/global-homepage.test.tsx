import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { GlobalHomepage, GLOBAL_WHATSAPP_URL } from './global-homepage';

describe('GlobalHomepage', () => {
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

  it('funnels every primary CTA to the WhatsApp chat without auth detours', () => {
    flushSync(() => {
      root.render(<GlobalHomepage />);
    });

    expect(container.querySelector('.global-site.global-site--kap')).toBeTruthy();
    expect(container.querySelector('.global-ticker')).toBeTruthy();
    expect(container.querySelector('.global-hero__scene')).toBeTruthy();
    expect(container.querySelector('.global-hero__phone')).toBeTruthy();
    expect(container.querySelector('.global-stage-note')).toBeNull();
    expect(container.querySelector('.global-stage-card__composer')).toBeNull();
    expect(container.querySelector('img[alt="Kap koala badge"]')).toBeTruthy();
    expect(container.querySelector('img[alt="Kap koala mascot"]')).toBeTruthy();
    expect(container.textContent).toContain('Start with one WhatsApp message.');
    expect(container.textContent).toContain('Turn one real goal into a reminder and follow-up thread without leaving');
    expect(container.textContent).toContain('Set the goal and the time');
    expect(container.textContent).toContain('Use the same thread for reminders, check-ins');
    expect(container.textContent).toContain('WhatsApp');
    expect(container.textContent).toContain('Kap');
    expect(container.textContent).not.toContain('Coke');
    expect(container.textContent).not.toContain('Sign in');
    expect(container.textContent).not.toContain('Register');
    expect(container.textContent).not.toContain('draft the follow-up');
    expect(container.textContent).not.toContain('drafts');

    const primaryCtas = Array.from(
      container.querySelectorAll<HTMLAnchorElement>('a.global-cta--primary'),
    );

    expect(primaryCtas.length).toBeGreaterThanOrEqual(3);
    expect(primaryCtas.every((cta) => cta.getAttribute('href') === GLOBAL_WHATSAPP_URL)).toBe(true);
  });

  it('keeps supporting copy in English and removes multi-channel messaging', () => {
    flushSync(() => {
      root.render(<GlobalHomepage />);
    });

    expect(container.textContent).toContain('Tell Kap what needs doing and when to check back.');
    expect(container.textContent).toContain('Message Kap on WhatsApp');
    expect(container.textContent).not.toContain('WeChat');
    expect(container.textContent).not.toContain('Telegram');
    expect(container.textContent).not.toContain('Slack');
  });
});
