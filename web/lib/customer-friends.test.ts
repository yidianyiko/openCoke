import { afterEach, describe, expect, it, vi } from 'vitest';
import { customerApi } from './customer-api';
import {
  disableCustomerFriendLink,
  getCustomerFriendLink,
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
        qr_payload: 'https://example.test/f/code_1',
      })
      .mockResolvedValueOnce({ friends: [] });

    await getCustomerFriendLink();
    await listCustomerFriends();

    expect(apiMock.get).toHaveBeenNthCalledWith(1, '/api/friends/link');
    expect(apiMock.get).toHaveBeenNthCalledWith(2, '/api/friends');
    expect(apiMock.get).not.toHaveBeenCalledWith('/api/customer/scheduling/friend-requests');
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
