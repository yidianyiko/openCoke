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
    delete: vi.fn(),
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

  it('reads the current friend link and friends from scheduling endpoints', async () => {
    apiMock.get.mockResolvedValue({ ok: true, data: null });

    await getCustomerFriendLink();
    await listCustomerFriends();

    expect(apiMock.get).toHaveBeenNthCalledWith(1, '/api/customer/scheduling/user-link');
    expect(apiMock.get).toHaveBeenNthCalledWith(2, '/api/customer/scheduling/friends');
    expect(apiMock.get).not.toHaveBeenCalledWith('/api/customer/scheduling/friend-requests');
  });

  it('mutates the current friend link through reset and disable endpoints', async () => {
    apiMock.post.mockResolvedValue({ ok: true, data: null });

    await resetCustomerFriendLink();
    await disableCustomerFriendLink();

    expect(apiMock.post).toHaveBeenNthCalledWith(1, '/api/customer/scheduling/user-link/reset');
    expect(apiMock.post).toHaveBeenNthCalledWith(2, '/api/customer/scheduling/user-link/disable');
  });

  it('removes a friendship with an encoded friendship id', async () => {
    apiMock.delete.mockResolvedValueOnce({ ok: true, data: { id: 'fs/1', status: 'removed' } });

    await removeCustomerFriend('fs/1');

    expect(apiMock.delete).toHaveBeenCalledWith('/api/customer/scheduling/friends/fs%2F1');
  });
});
