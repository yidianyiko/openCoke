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

export type CustomerFriendshipJoin = {
  status: 'created' | 'already_active';
  friendship_id: string | null;
  counterpart_account_id: string;
  counterpart_display_name: string;
  continuation?: Record<string, unknown>;
};

type CleanRouteError = {
  error: {
    code: string;
  };
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
    display_name?: string;
  }[];
};

type CleanFriendAction = {
  friendship_id: string;
  lifecycle: string;
};

export function getCustomerFriendLink(): Promise<ApiResponse<CustomerFriendLink>> {
  return customerApi
    .get<CleanFriendLink | CleanRouteError>('/api/friends/link')
    .then((link) => okOrError(link, cleanFriendLink));
}

export function resetCustomerFriendLink(): Promise<ApiResponse<CustomerFriendLink>> {
  return customerApi
    .post<CleanFriendLink | CleanRouteError>('/api/friends/link/reset')
    .then((link) => okOrError(link, cleanFriendLink));
}

export function disableCustomerFriendLink(): Promise<ApiResponse<{ count: number }>> {
  return customerApi
    .post<CleanFriendLink | CleanRouteError>('/api/friends/link/disable')
    .then((link) => okOrError(link, () => ({ count: 1 })));
}

export function listCustomerFriends(): Promise<ApiResponse<CustomerFriend[]>> {
  return customerApi.get<CleanFriendList | CleanRouteError>('/api/friends').then((result) =>
    okOrError(result, (friendList) =>
      friendList.friends.map((friend) => ({
        id: friend.friendship_id,
        status: 'active',
        counterpartAccountId: friend.account_id,
        counterpartProfile: {
          displayName: friend.display_name || friend.account_id,
          avatarUrl: null,
        },
      })),
    ),
  );
}

export function removeCustomerFriend(friendAccountId: string): Promise<ApiResponse<FriendshipActionResult>> {
  return customerApi
    .post<CleanFriendAction | CleanRouteError>(`/api/friends/${encodeURIComponent(friendAccountId)}/remove`)
    .then((result) =>
      okOrError(result, (action) => ({
        id: action.friendship_id,
        status: action.lifecycle,
      })),
    );
}

export function joinFriendByCode(code: string): Promise<ApiResponse<CustomerFriendshipJoin>> {
  return customerApi
    .post<CustomerFriendshipJoin | CleanRouteError>('/api/friends/join', { link_code: code })
    .then((result) => okOrError(result, (join) => join));
}

function isCleanRouteError(value: unknown): value is CleanRouteError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as CleanRouteError).error?.code === 'string'
  );
}

function okOrError<T, U>(value: T | CleanRouteError, map: (value: T) => U): ApiResponse<U> {
  if (isCleanRouteError(value)) {
    return { ok: false, error: value.error.code };
  }
  return { ok: true, data: map(value) };
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
