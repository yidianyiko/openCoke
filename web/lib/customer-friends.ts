import type { ApiResponse } from './api-types';
import { customerApi } from './customer-api';

export interface CustomerFriendLink {
  code: string;
  status: 'active';
  url: string;
  qrUrl: string;
  profile: {
    displayName: string;
    tagline: string | null;
    avatarUrl: string | null;
  };
}

export interface CustomerFriend {
  id: string;
  status: string;
  counterpartAccountId: string;
  counterpartProfile?: {
    displayName: string;
    avatarUrl: string | null;
  };
}

type FriendshipActionResult = {
  id: string;
  status: string;
};

type CleanFriendLink = {
  friend_link_id: string;
  owner_account_id: string;
  lifecycle: string;
  public_token: string;
  link_code: string;
  qr_payload: string;
};

type CleanFriendList = {
  friends: {
    account_id: string;
    friendship_id: string;
  }[];
};

type CleanFriendAction = {
  friendship_id: string;
  lifecycle: string;
};

export function getCustomerFriendLink(): Promise<ApiResponse<CustomerFriendLink>> {
  return customerApi.get<CleanFriendLink>('/api/friends/link').then((link) => ({
    ok: true,
    data: cleanFriendLink(link),
  }));
}

export function resetCustomerFriendLink(): Promise<ApiResponse<CustomerFriendLink>> {
  return customerApi.post<CleanFriendLink>('/api/friends/link/reset').then((link) => ({
    ok: true,
    data: cleanFriendLink(link),
  }));
}

export function disableCustomerFriendLink(): Promise<ApiResponse<{ count: number }>> {
  return customerApi.post<CleanFriendLink>('/api/friends/link/disable').then(() => ({
    ok: true,
    data: { count: 1 },
  }));
}

export function listCustomerFriends(): Promise<ApiResponse<CustomerFriend[]>> {
  return customerApi.get<CleanFriendList>('/api/friends').then((result) => ({
    ok: true,
    data: result.friends.map((friend) => ({
      id: friend.friendship_id,
      status: 'active',
      counterpartAccountId: friend.account_id,
    })),
  }));
}

export function removeCustomerFriend(friendAccountId: string): Promise<ApiResponse<FriendshipActionResult>> {
  return customerApi
    .post<CleanFriendAction>(`/api/friends/${encodeURIComponent(friendAccountId)}/remove`)
    .then((result) => ({
      ok: true,
      data: {
        id: result.friendship_id,
        status: result.lifecycle,
      },
    }));
}

function cleanFriendLink(link: CleanFriendLink): CustomerFriendLink {
  return {
    code: link.link_code,
    status: 'active',
    url: link.qr_payload,
    qrUrl: link.qr_payload,
    profile: {
      displayName: link.owner_account_id,
      tagline: null,
      avatarUrl: null,
    },
  };
}
