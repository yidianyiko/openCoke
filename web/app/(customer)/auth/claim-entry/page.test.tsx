import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../../../components/locale-provider';

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const requestCustomerClaimEmail = vi.hoisted(() => vi.fn());

vi.mock('../../../../lib/customer-google-calendar-import', () => ({
  requestCustomerClaimEmail,
}));

import ClaimEntryPage from './page';

describe('ClaimEntryPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  const waitForEffects = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

  function setInputValue(selector: string, value: string) {
    const input = container.querySelector(selector) as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    setter?.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function renderPage() {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <ClaimEntryPage />
        </LocaleProvider>,
      );
    });
  }

  beforeEach(() => {
    vi.mocked(requestCustomerClaimEmail).mockReset();
    window.history.replaceState({}, '', '/auth/claim-entry?entry=entry-token-123');
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('shows recovery guidance immediately when the entry token is missing', async () => {
    window.history.replaceState({}, '', '/auth/claim-entry');

    renderPage();

    await waitForEffects();

    expect(container.textContent).toContain('This WhatsApp claim link is invalid or has expired.');
    expect(container.textContent).toContain('Request a fresh link from WhatsApp to continue.');
    expect(container.querySelector('form')).toBeNull();
    expect(requestCustomerClaimEmail).not.toHaveBeenCalled();
  });

  it('does not flash the recovery state before the entry token is resolved from the URL', () => {
    renderPage();

    expect(container.textContent).not.toContain('This WhatsApp claim link is invalid or has expired.');
    expect(container.querySelector('form')).toBeNull();
  });

  it('renders the email-first claim entry page and requests a claim email for calendar import continuation', async () => {
    vi.mocked(requestCustomerClaimEmail).mockResolvedValueOnce({
      ok: true,
      data: {
        message: 'claim_email_sent',
      },
    });

    renderPage();

    await waitForEffects();

    expect(container.textContent).toContain('Claim your customer account');
    expect(container.querySelector('input[type="email"]')).toBeTruthy();

    setInputValue('#email', 'alice@example.com');
    container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));

    await waitForEffects();

    expect(requestCustomerClaimEmail).toHaveBeenCalledWith({
      entryToken: 'entry-token-123',
      email: 'alice@example.com',
      next: '/account/calendar-import',
    });
    expect(container.textContent).toContain('Check your inbox for the claim link.');
  });

  it('shows recovery copy when the claim-entry token is invalid or expired', async () => {
    vi.mocked(requestCustomerClaimEmail).mockResolvedValueOnce({
      ok: false,
      error: 'invalid_or_expired_token',
    });

    renderPage();

    await waitForEffects();

    setInputValue('#email', 'alice@example.com');
    container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));

    await waitForEffects();

    expect(container.textContent).toContain('This WhatsApp claim link is invalid or has expired.');
    expect(container.textContent).toContain('Request a fresh link from WhatsApp to continue.');
  });

  it('shows the duplicate-email error without switching to the success state', async () => {
    vi.mocked(requestCustomerClaimEmail).mockResolvedValueOnce({
      ok: false,
      error: 'email_already_exists',
    });

    renderPage();

    await waitForEffects();

    setInputValue('#email', 'alice@example.com');
    container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));

    await waitForEffects();

    expect(container.textContent).toContain('That email address is already in use.');
    expect(container.textContent).not.toContain('Check your inbox for the claim link.');
  });
});
