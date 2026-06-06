import { afterEach, describe, expect, it, vi } from 'vitest';
import { customerApi } from './customer-api';
import {
  disableCustomerFriendLink,
  getCustomerFriendLink,
  joinFriendByCode,
  listCustomerFriends,
  removeCustomerFriend,
  resetCustomerFriendLink,
} from './customer-friends';
import * as customerFriends from './customer-friends';

vi.mock('./customer-api', () => ({
  customerApi: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const apiMock = vi.mocked(customerApi);

afterEach(() => {
  vi.clearAllMocks();
});

describe('customer friends wrappers', () => {
  it('does not expose retired friend request helpers', () => {
    expect(customerFriends).not.toHaveProperty('listCustomerFriendRequests');
    expect(customerFriends).not.toHaveProperty('acceptCustomerFriendRequest');
    expect(customerFriends).not.toHaveProperty('rejectCustomerFriendRequest');
    expect(customerFriends).not.toHaveProperty('cancelCustomerFriendRequest');
  });

  it('reads the current friend link and friends from clean friend endpoints', async () => {
    apiMock.get
      .mockResolvedValueOnce({
        friend_link_id: 'fl_1',
        owner_account_id: 'acct_1',
        lifecycle: 'active',
        public_token: 'token_1',
        link_code: 'code_1',
        qr_payload: 'https://example.test/u/code_1',
      })
      .mockResolvedValueOnce({ friends: [] });

    const result = await getCustomerFriendLink();
    await listCustomerFriends();

    expect(result).toEqual({
      ok: true,
      data: {
        code: 'code_1',
        status: 'active',
        url: 'https://example.test/u/code_1',
        qrUrl: 'https://example.test/u/code_1',
        profile: { displayName: 'acct_1', tagline: null, avatarUrl: null },
      },
    });
    expect(apiMock.get).toHaveBeenNthCalledWith(1, '/api/friends/link');
    expect(apiMock.get).toHaveBeenNthCalledWith(2, '/api/friends');
    expect(apiMock.get).not.toHaveBeenCalledWith('/api/customer/scheduling/friend-requests');
  });

  it('maps clean route error bodies instead of treating them as successful friend-link data', async () => {
    apiMock.get.mockResolvedValueOnce({ error: { code: 'owner_channel_required' } });

    await expect(getCustomerFriendLink()).resolves.toEqual({
      ok: false,
      error: 'owner_channel_required',
    });
  });

  it('joins a friend by clean link code and preserves created status', async () => {
    apiMock.post.mockResolvedValueOnce({
      status: 'created',
      friendship_id: 'friendship_1',
      counterpart_account_id: 'acct_oliver',
      counterpart_display_name: 'Oliver',
      continuation: {},
    });

    await expect(joinFriendByCode('code/1')).resolves.toEqual({
      ok: true,
      data: {
        status: 'created',
        friendship_id: 'friendship_1',
        counterpart_account_id: 'acct_oliver',
        counterpart_display_name: 'Oliver',
        continuation: {},
      },
    });
    expect(apiMock.post).toHaveBeenCalledWith('/api/friends/join', { link_code: 'code/1' });
  });

  it('maps clean join error bodies to ApiResponse errors', async () => {
    apiMock.post.mockResolvedValueOnce({ error: { code: 'self_friendship_forbidden' } });

    await expect(joinFriendByCode('code_1')).resolves.toEqual({
      ok: false,
      error: 'self_friendship_forbidden',
    });
  });

  it('maps backend friend display names and falls back to account ids', async () => {
    apiMock.get.mockResolvedValueOnce({
      friends: [
        { account_id: 'acct_named', friendship_id: 'friendship_named', display_name: 'Mina' },
        { account_id: 'acct_fallback', friendship_id: 'friendship_fallback' },
      ],
    });

    await expect(listCustomerFriends()).resolves.toEqual({
      ok: true,
      data: [
        {
          id: 'friendship_named',
          status: 'active',
          counterpartAccountId: 'acct_named',
          counterpartProfile: { displayName: 'Mina', avatarUrl: null },
        },
        {
          id: 'friendship_fallback',
          status: 'active',
          counterpartAccountId: 'acct_fallback',
          counterpartProfile: { displayName: 'acct_fallback', avatarUrl: null },
        },
      ],
    });
  });

  it('mutates the current friend link through reset and disable endpoints', async () => {
    apiMock.post.mockResolvedValue({
      friend_link_id: 'fl_1',
      owner_account_id: 'acct_1',
      lifecycle: 'active',
      public_token: 'token_1',
      link_code: 'code_1',
      qr_payload: 'https://example.test/f/code_1',
    });

    await resetCustomerFriendLink();
    await disableCustomerFriendLink();

    expect(apiMock.post).toHaveBeenNthCalledWith(1, '/api/friends/link/reset');
    expect(apiMock.post).toHaveBeenNthCalledWith(2, '/api/friends/link/disable');
  });

  it('removes a friend with an encoded friend account id', async () => {
    apiMock.post.mockResolvedValueOnce({ friendship_id: 'fs/1', lifecycle: 'removed' });

    await removeCustomerFriend('fs/1');

    expect(apiMock.post).toHaveBeenCalledWith('/api/friends/fs%2F1/remove');
  });
});
