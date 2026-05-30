import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';

import { LocaleProvider } from '../../../../components/locale-provider';

const replaceMock = vi.hoisted(() => vi.fn());
const searchParamsMock = vi.hoisted(() => vi.fn());
const getLinkMock = vi.hoisted(() => vi.fn());
const listFriendsMock = vi.hoisted(() => vi.fn());
const removeMock = vi.hoisted(() => vi.fn());
const resetLinkMock = vi.hoisted(() => vi.fn());
const disableLinkMock = vi.hoisted(() => vi.fn());
const getLinkSessionStatusMock = vi.hoisted(() => vi.fn());
const createFriendshipMock = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceMock }),
  useSearchParams: () => searchParamsMock(),
}));

vi.mock('../../../../lib/customer-friends', () => ({
  getCustomerFriendLink: (...args: unknown[]) => getLinkMock(...args),
  listCustomerFriends: (...args: unknown[]) => listFriendsMock(...args),
  removeCustomerFriend: (...args: unknown[]) => removeMock(...args),
  resetCustomerFriendLink: (...args: unknown[]) => resetLinkMock(...args),
  disableCustomerFriendLink: (...args: unknown[]) => disableLinkMock(...args),
}));

vi.mock('../../../../lib/user-link-api', () => ({
  getLinkSessionStatus: (...args: unknown[]) => getLinkSessionStatusMock(...args),
  createFriendship: (...args: unknown[]) => createFriendshipMock(...args),
}));

import FriendsPage from './page';

function friendLink(overrides: Record<string, unknown> = {}) {
  return {
    code: 'friend-code',
    status: 'active',
    url: 'https://kap.example/u/friend-code',
    qrUrl: 'https://kap.example/u/friend-code/qr',
    profile: {
      displayName: 'Mina',
      tagline: null,
      avatarUrl: null,
    },
    ...overrides,
  };
}

function friend(overrides: Record<string, unknown> = {}) {
  return {
    id: 'friendship-1',
    status: 'active',
    counterpartAccountId: 'acct_3',
    counterpartProfile: {
      displayName: 'Rin',
      avatarUrl: null,
    },
    ...overrides,
  };
}

async function flushTicks(count = 4) {
  for (let i = 0; i < count; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

function findButton(container: HTMLElement, label: string) {
  return [...container.querySelectorAll('button')].find((button) => button.textContent === label);
}

describe('CustomerFriendsPage', () => {
  let container: HTMLDivElement;
  let root: Root;
  let writeTextMock: ReturnType<typeof vi.fn>;

  function renderPage() {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <FriendsPage />
        </LocaleProvider>,
      );
    });
  }

  beforeEach(() => {
    replaceMock.mockReset();
    searchParamsMock.mockReset();
    getLinkMock.mockReset();
    listFriendsMock.mockReset();
    removeMock.mockReset();
    resetLinkMock.mockReset();
    disableLinkMock.mockReset();
    getLinkSessionStatusMock.mockReset();
    createFriendshipMock.mockReset();
    searchParamsMock.mockReturnValue(new URLSearchParams());
    getLinkMock.mockResolvedValue({ ok: true, data: friendLink() });
    listFriendsMock.mockResolvedValue({ ok: true, data: [friend()] });
    removeMock.mockResolvedValue({ ok: true, data: { id: 'friendship-1', status: 'removed' } });
    resetLinkMock.mockResolvedValue({ ok: true, data: friendLink({ code: 'new-code' }) });
    disableLinkMock.mockResolvedValue({ ok: true, data: { count: 1 } });
    getLinkSessionStatusMock.mockResolvedValue({
      ok: true,
      data: {
        providerAccountId: 'acct_target',
        consumerAccountId: null,
        status: 'opened',
        expiresAt: '2026-06-21T00:00:00.000Z',
      },
    });
    createFriendshipMock.mockResolvedValue({
      ok: true,
      data: { id: 'friendship-new', status: 'active', friend_account_id: 'acct_target', created: true },
    });
    writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: writeTextMock },
    });
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
    delete (navigator as Partial<Navigator>).clipboard;
  });

  it('loads and renders the friend link and current friends without request panels or actions', async () => {
    renderPage();
    await flushTicks();

    expect(getLinkMock).toHaveBeenCalledOnce();
    expect(listFriendsMock).toHaveBeenCalledOnce();
    expect(container.textContent).toContain('Friend management');
    expect(container.textContent).toContain('https://kap.example/u/friend-code');
    expect(container.textContent).toContain('Current friends');
    expect(container.textContent).toContain('Rin');
    expect(container.textContent).not.toContain('Incoming requests');
    expect(container.textContent).not.toContain('Outgoing requests');
    expect(findButton(container, 'Accept')).toBeUndefined();
    expect(findButton(container, 'Reject')).toBeUndefined();
    expect(findButton(container, 'Cancel request')).toBeUndefined();
    expect(findButton(container, 'Remove friend')).toBeTruthy();
  });

  it('redirects auth failures on load to login with the friends next path', async () => {
    getLinkMock.mockResolvedValueOnce({ ok: false, error: 'claim_inactive' });

    renderPage();
    await flushTicks();

    expect(replaceMock).toHaveBeenCalledWith('/auth/login?next=/account/friends');
  });

  it('creates a direct friendship from a preserved public-link session', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('link_session=session-token'));
    listFriendsMock.mockResolvedValueOnce({ ok: true, data: [] }).mockResolvedValue({
      ok: true,
      data: [friend({ id: 'friendship-new', counterpartAccountId: 'acct_target' })],
    });

    renderPage();
    await flushTicks();

    expect(getLinkSessionStatusMock).toHaveBeenCalledWith('session-token');
    expect(container.textContent).toContain('Add friend');
    expect(container.textContent).toContain('acct_target');

    expect(container.querySelector('textarea')).toBeNull();
    findButton(container, 'Add friend')?.click();
    await flushTicks();

    expect(createFriendshipMock).toHaveBeenCalledWith({ token: 'session-token' });
    expect(listFriendsMock).toHaveBeenCalledTimes(2);
    expect(container.textContent).toContain('Friend added.');
  });

  it('does not show pending request status for a preserved public-link session', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('link_session=session-token'));

    renderPage();
    await flushTicks();

    expect(container.textContent).not.toContain('You already sent a request to this account.');
    expect(container.textContent).not.toContain('Pending');
    expect(findButton(container, 'Add friend')).toBeTruthy();
  });

  it('shows quiet empty state when the friend list is empty', async () => {
    listFriendsMock.mockResolvedValueOnce({ ok: true, data: [] });

    renderPage();
    await flushTicks();

    expect(container.textContent).not.toContain('No incoming friend requests.');
    expect(container.textContent).not.toContain('No outgoing friend requests.');
    expect(container.textContent).toContain('No friends yet.');
  });

  it('refreshes friend datasets after friend removal', async () => {
    renderPage();
    await flushTicks();

    findButton(container, 'Remove friend')?.click();
    await flushTicks();
    expect(removeMock).toHaveBeenCalledWith('friendship-1');
    expect(getLinkMock).toHaveBeenCalledTimes(2);
    expect(listFriendsMock).toHaveBeenCalledTimes(2);
  });

  it('copies and resets the current friend link', async () => {
    renderPage();
    await flushTicks();

    findButton(container, 'Copy link')?.click();
    await flushTicks();
    expect(writeTextMock).toHaveBeenCalledWith('https://kap.example/u/friend-code');
    expect(container.textContent).toContain('Link copied.');

    findButton(container, 'Reset link')?.click();
    await flushTicks();
    expect(resetLinkMock).toHaveBeenCalledOnce();
    expect(getLinkMock).toHaveBeenCalledTimes(2);
    expect(listFriendsMock).toHaveBeenCalledTimes(2);
  });

  it('keeps the disabled friend link local without immediately fetching a replacement link', async () => {
    getLinkMock
      .mockResolvedValueOnce({ ok: true, data: friendLink({ url: 'https://kap.example/u/abc' }) })
      .mockResolvedValue({ ok: true, data: friendLink({ url: 'https://kap.example/u/new-link' }) });

    renderPage();
    await flushTicks();
    expect(container.textContent).toContain('https://kap.example/u/abc');

    findButton(container, 'Disable current link')?.click();
    await flushTicks();

    expect(disableLinkMock).toHaveBeenCalledOnce();
    expect(getLinkMock).toHaveBeenCalledTimes(1);
    expect(listFriendsMock).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain('The current link was disabled.');
    expect(container.textContent).not.toContain('https://kap.example/u/abc');
    expect(container.textContent).not.toContain('https://kap.example/u/new-link');
  });

  it('disables current-link actions after the current friend link is disabled', async () => {
    getLinkMock.mockResolvedValueOnce({
      ok: true,
      data: friendLink({ url: 'https://kap.example/u/current-link' }),
    });

    renderPage();
    await flushTicks();

    findButton(container, 'Disable current link')?.click();
    await flushTicks();

    expect(container.textContent).toContain('The current link was disabled.');
    expect(container.textContent).not.toContain('https://kap.example/u/current-link');

    const copyButton = findButton(container, 'Copy link') as HTMLButtonElement;
    const resetButton = findButton(container, 'Reset link') as HTMLButtonElement;
    const disableButton = findButton(container, 'Disable current link') as HTMLButtonElement;
    expect(copyButton.disabled).toBe(true);
    expect(resetButton.disabled).toBe(true);
    expect(disableButton.disabled).toBe(true);

    disableButton.click();
    await flushTicks();
    expect(disableLinkMock).toHaveBeenCalledOnce();
  });

  it('redirects auth failures from mutations and shows action failures without leaving the page', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('link_session=session-token'));
    createFriendshipMock.mockResolvedValueOnce({ ok: false, error: 'unauthorized' });

    renderPage();
    await flushTicks();
    findButton(container, 'Add friend')?.click();
    await flushTicks();

    expect(replaceMock).toHaveBeenCalledWith(
      '/auth/login?next=%2Faccount%2Ffriends%3Flink_session%3Dsession-token',
    );

    replaceMock.mockReset();
    createFriendshipMock.mockResolvedValueOnce({ ok: false, error: 'upstream_unavailable' });
    findButton(container, 'Add friend')?.click();
    await flushTicks();

    expect(replaceMock).not.toHaveBeenCalled();
    expect(container.textContent).toContain('Unable to update friend data right now.');
  });
});
