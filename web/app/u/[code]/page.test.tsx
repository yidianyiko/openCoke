import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';

const mockFetchUserLink = vi.hoisted(() => vi.fn());

vi.mock('../../../lib/user-link-api', () => ({
  fetchUserLink: mockFetchUserLink,
}));

import UserLinkPage from './page';

function renderHtml(html: string): HTMLElement {
  const container = document.createElement('main');
  container.innerHTML = html;
  return container;
}

describe('UserLinkPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders a public profile and starts login with the join code', async () => {
    mockFetchUserLink.mockResolvedValue({
      ok: true,
      data: {
        code: 'abc',
        status: 'active',
        profile: { displayName: 'Coach A', tagline: 'Strength coach', avatarUrl: null },
      },
    });

    const html = renderToString(
      await UserLinkPage({ params: Promise.resolve({ code: 'abc' }), searchParams: Promise.resolve({}) }),
    );
    const container = renderHtml(html);
    const loginLink = Array.from(container.querySelectorAll('a')).find(
      (link) => link.textContent === 'Log in to add friend',
    );
    const registerLink = Array.from(container.querySelectorAll('a')).find(
      (link) => link.textContent === 'Create account to add friend',
    );

    expect(container.querySelector('h1')?.textContent).toBe('Coach A');
    expect(container.textContent).toContain('Strength coach');
    expect(loginLink?.getAttribute('href')).toBe('/auth/login?next=%2Faccount%2Ffriends%3Fjoin%3Dabc');
    expect(registerLink?.getAttribute('href')).toBe(
      '/auth/register?next=%2Faccount%2Ffriends%3Fjoin%3Dabc',
    );
  });

  it('shows a clear inactive state for inactive or missing links', async () => {
    mockFetchUserLink.mockResolvedValueOnce({ ok: false, error: 'link_not_active' });

    const html = renderToString(await UserLinkPage({ params: Promise.resolve({ code: 'missing-code' }) }));

    expect(html).toContain('Link no longer active');
    expect(html).toContain('cannot be used to add a friend');
    expect(html).not.toContain('/auth/login?next=');
  });

  it('renders auth actions carrying the encoded join code', async () => {
    mockFetchUserLink.mockResolvedValue({
      ok: true,
      data: {
        code: 'abc/123',
        status: 'active',
        profile: { displayName: 'Coach A', tagline: null, avatarUrl: null },
      },
    });

    const html = renderToString(
      await UserLinkPage({ params: Promise.resolve({ code: 'abc/123' }), searchParams: Promise.resolve({}) }),
    );
    const container = renderHtml(html);
    const links = Array.from(container.querySelectorAll('a')).map((link) => link.getAttribute('href'));

    expect(links).toContain('/auth/login?next=%2Faccount%2Ffriends%3Fjoin%3Dabc%252F123');
    expect(links).toContain('/auth/register?next=%2Faccount%2Ffriends%3Fjoin%3Dabc%252F123');
  });
});
