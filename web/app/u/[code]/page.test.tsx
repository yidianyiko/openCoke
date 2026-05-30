import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';

const mockFetchUserLink = vi.hoisted(() => vi.fn());
const mockOpenLinkSession = vi.hoisted(() => vi.fn());
const mockRedirect = vi.hoisted(() =>
  vi.fn((url: string) => {
    throw new Error(`redirect:${url}`);
  }),
);

vi.mock('../../../lib/user-link-api', () => ({
  fetchUserLink: mockFetchUserLink,
  openLinkSession: mockOpenLinkSession,
}));
vi.mock('next/navigation', () => ({
  redirect: mockRedirect,
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

  it('renders a public profile and starts login with preserved link session', async () => {
    mockFetchUserLink.mockResolvedValue({
      ok: true,
      data: {
        code: 'abc',
        status: 'active',
        profile: { displayName: 'Coach A', tagline: 'Strength coach', avatarUrl: null },
      },
    });
    mockOpenLinkSession.mockResolvedValue({
      ok: true,
      data: {
        token: 'session-token',
        targetAccountId: 'acct_a',
        expiresAt: '2026-06-21T00:00:00.000Z',
        loginUrl: '/auth/login?next=%2Faccount%2Ffriends%3Flink_session%3Dsession-token',
        registerUrl: '/auth/register?next=%2Faccount%2Ffriends%3Flink_session%3Dsession-token',
      },
    });

    const html = renderToString(
      await UserLinkPage({ params: Promise.resolve({ code: 'abc' }), searchParams: Promise.resolve({}) }),
    );
    const container = renderHtml(html);
    const loginLink = Array.from(container.querySelectorAll('a')).find(
      (link) => link.textContent === 'Log in to add friend',
    );

    expect(container.querySelector('h1')?.textContent).toBe('Coach A');
    expect(container.textContent).toContain('Strength coach');
    expect(mockOpenLinkSession).toHaveBeenCalledWith('abc');
    expect(loginLink?.getAttribute('href')).toBe(
      '/auth/login?next=%2Faccount%2Ffriends%3Flink_session%3Dsession-token',
    );
  });

  it('shows a clear inactive state for inactive or missing links', async () => {
    mockFetchUserLink.mockResolvedValueOnce({ ok: false, error: 'link_not_active' });

    const html = renderToString(await UserLinkPage({ params: Promise.resolve({ code: 'missing-code' }) }));

    expect(html).toContain('Link no longer active');
    expect(html).toContain('cannot be used to add a friend');
    expect(html).not.toContain('/auth/login?next=');
  });

  it('shows a clear retry state when link session creation fails', async () => {
    mockFetchUserLink.mockResolvedValue({
      ok: true,
      data: {
        code: 'abc',
        status: 'active',
        profile: { displayName: 'Coach A', tagline: null, avatarUrl: null },
      },
    });
    mockOpenLinkSession.mockResolvedValue({ ok: false, error: 'link_session_not_opened' });

    const html = renderToString(
      await UserLinkPage({ params: Promise.resolve({ code: 'abc' }), searchParams: Promise.resolve({}) }),
    );

    expect(html).toContain('Friendship setup is temporarily unavailable');
    expect(html).toContain('Please refresh this page and try again');
    expect(html).not.toContain('Log in to add friend');
  });

  it('redirects preserved sessions into the customer friends dashboard', async () => {
    mockFetchUserLink.mockResolvedValue({
      ok: true,
      data: {
        code: 'abc',
        status: 'active',
        profile: { displayName: 'Coach A', tagline: null, avatarUrl: null },
      },
    });

    await expect(
      UserLinkPage({
        params: Promise.resolve({ code: 'abc' }),
        searchParams: Promise.resolve({ link_session: 'session-token' }),
      }),
    ).rejects.toThrow('redirect:/account/friends?link_session=session-token');
    expect(mockOpenLinkSession).not.toHaveBeenCalled();
    expect(mockRedirect).toHaveBeenCalledWith('/account/friends?link_session=session-token');
  });
});
