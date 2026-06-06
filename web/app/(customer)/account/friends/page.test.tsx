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
const joinFriendByCodeMock = vi.hoisted(() => vi.fn());

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
  joinFriendByCode: (...args: unknown[]) => joinFriendByCodeMock(...args),
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

  function renderPage(initialLocale: 'en' | 'zh' = 'en') {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale={initialLocale}>
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
    joinFriendByCodeMock.mockReset();
    searchParamsMock.mockReturnValue(new URLSearchParams());
    getLinkMock.mockResolvedValue({ ok: true, data: friendLink() });
    listFriendsMock.mockResolvedValue({ ok: true, data: [friend()] });
    removeMock.mockResolvedValue({ ok: true, data: { id: 'friendship-1', status: 'removed' } });
    resetLinkMock.mockResolvedValue({ ok: true, data: friendLink({ code: 'new-code' }) });
    disableLinkMock.mockResolvedValue({ ok: true, data: { count: 1 } });
    joinFriendByCodeMock.mockResolvedValue({
      ok: true,
      data: {
        status: 'already_active',
        friendship_id: 'friendship-existing',
        counterpart_account_id: 'acct_oliver',
        counterpart_display_name: 'Oliver',
        continuation: {},
      },
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

  it('preserves logged-out join handoff before attempting auto-join', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('join=code_1'));
    getLinkMock.mockResolvedValueOnce({ ok: false, error: 'claim_inactive' });

    renderPage();
    await flushTicks();

    expect(replaceMock).toHaveBeenCalledWith('/auth/login?next=%2Faccount%2Ffriends%3Fjoin%3Dcode_1');
    expect(joinFriendByCodeMock).not.toHaveBeenCalled();
  });

  it('joins by public friend link code once and scrubs the URL', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('join=code_1'));
    listFriendsMock.mockResolvedValueOnce({ ok: true, data: [] }).mockResolvedValue({
      ok: true,
      data: [friend({ id: 'friendship-new', counterpartAccountId: 'acct_target' })],
    });
    joinFriendByCodeMock.mockResolvedValueOnce({
      ok: true,
      data: {
        status: 'created',
        friendship_id: 'friendship-new',
        counterpart_account_id: 'acct_oliver',
        counterpart_display_name: 'Oliver',
        continuation: {},
      },
    });

    renderPage('zh');
    await flushTicks();

    expect(joinFriendByCodeMock).toHaveBeenCalledWith('code_1');
    expect(replaceMock).toHaveBeenCalledWith('/account/friends');
    expect(container.textContent).toContain('已成功添加 Oliver');
    expect(listFriendsMock).toHaveBeenCalledTimes(2);
  });

  it('shows personalized already-active copy after logged-in auto-join', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('join=code_1'));
    listFriendsMock.mockResolvedValueOnce({ ok: true, data: [friend()] }).mockResolvedValue({
      ok: true,
      data: [
        friend({
          counterpartAccountId: 'acct_oliver',
          counterpartProfile: { displayName: 'Oliver', avatarUrl: null },
        }),
      ],
    });
    joinFriendByCodeMock.mockResolvedValueOnce({
      ok: true,
      data: {
        status: 'already_active',
        friendship_id: 'friendship-existing',
        counterpart_account_id: 'acct_oliver',
        counterpart_display_name: 'Oliver',
        continuation: {},
      },
    });

    renderPage('zh');
    await flushTicks();

    expect(joinFriendByCodeMock).toHaveBeenCalledWith('code_1');
    expect(container.textContent).toContain('Oliver 已经在你的好友列表中。');
    expect(replaceMock).toHaveBeenCalledWith('/account/friends');
  });

  it('preserves auth redirects from the reload after a successful public friend join', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('join=code_1'));
    listFriendsMock
      .mockResolvedValueOnce({ ok: true, data: [] })
      .mockResolvedValueOnce({ ok: false, error: 'unauthorized' });
    joinFriendByCodeMock.mockResolvedValueOnce({
      ok: true,
      data: { status: 'created', friendship_id: 'friendship-new', continuation: {} },
    });

    renderPage();
    await flushTicks();

    expect(joinFriendByCodeMock).toHaveBeenCalledWith('code_1');
    expect(replaceMock).toHaveBeenLastCalledWith(
      '/auth/login?next=%2Faccount%2Ffriends%3Fjoin%3Dcode_1',
    );
    expect(replaceMock).not.toHaveBeenLastCalledWith('/account/friends');
  });

  it('keeps friends visible when the current account has no shareable link yet', async () => {
    getLinkMock.mockResolvedValueOnce({ ok: false, error: 'owner_channel_required' });

    renderPage();
    await flushTicks();

    expect(container.textContent).toContain('Connect a messaging channel to get your shareable friend link.');
    expect(container.textContent).toContain('Rin');
    expect(container.textContent).not.toContain('Unable to load friend data right now.');
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
    expect(removeMock).toHaveBeenCalledWith('acct_3');
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

  it('does not scrub the URL after a join auth redirect', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('join=code_1'));
    joinFriendByCodeMock.mockResolvedValueOnce({ ok: false, error: 'unauthorized' });

    renderPage();
    await flushTicks();

    expect(replaceMock).toHaveBeenCalledWith(
      '/auth/login?next=%2Faccount%2Ffriends%3Fjoin%3Dcode_1',
    );
    expect(replaceMock).not.toHaveBeenCalledWith('/account/friends');
  });

  it('shows self-invite errors from clean join failures and scrubs the URL', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('join=code_1'));
    joinFriendByCodeMock.mockResolvedValueOnce({ ok: false, error: 'self_friendship_forbidden' });

    renderPage();
    await flushTicks();

    expect(container.textContent).toContain('You cannot add yourself as a friend.');
    expect(replaceMock).toHaveBeenCalledWith('/account/friends');
  });

  it('keeps self-invite errors visible after the scrubbed URL rerenders', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('join=code_1'));
    joinFriendByCodeMock.mockResolvedValueOnce({ ok: false, error: 'self_friendship_forbidden' });

    renderPage();
    await flushTicks();
    expect(container.textContent).toContain('You cannot add yourself as a friend.');

    searchParamsMock.mockReturnValue(new URLSearchParams());
    renderPage();
    await flushTicks();

    expect(container.textContent).toContain('You cannot add yourself as a friend.');
  });

  it('shows disabled friend link join errors distinctly', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('join=code_1'));
    joinFriendByCodeMock.mockResolvedValueOnce({ ok: false, error: 'friend_link_disabled' });

    renderPage();
    await flushTicks();

    expect(container.textContent).toContain('This friend link has been disabled.');
    expect(replaceMock).toHaveBeenCalledWith('/account/friends');
  });

  it('shows invalid friend link join errors distinctly', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('join=code_1'));
    joinFriendByCodeMock.mockResolvedValueOnce({ ok: false, error: 'friend_link_not_found' });

    renderPage();
    await flushTicks();

    expect(container.textContent).toContain('This friend link is invalid or expired.');
    expect(replaceMock).toHaveBeenCalledWith('/account/friends');
  });
});
