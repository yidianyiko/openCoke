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

export function getCustomerFriendLink(): Promise<ApiResponse<CustomerFriendLink>> {
  return customerApi.get<ApiResponse<CustomerFriendLink>>('/api/customer/scheduling/user-link');
}

export function resetCustomerFriendLink(): Promise<ApiResponse<CustomerFriendLink>> {
  return customerApi.post<ApiResponse<CustomerFriendLink>>('/api/customer/scheduling/user-link/reset');
}

export function disableCustomerFriendLink(): Promise<ApiResponse<{ count: number }>> {
  return customerApi.post<ApiResponse<{ count: number }>>('/api/customer/scheduling/user-link/disable');
}

export function listCustomerFriends(): Promise<ApiResponse<CustomerFriend[]>> {
  return customerApi.get<ApiResponse<CustomerFriend[]>>('/api/customer/scheduling/friends');
}

export function removeCustomerFriend(friendshipId: string): Promise<ApiResponse<FriendshipActionResult>> {
  return customerApi.delete<ApiResponse<FriendshipActionResult>>(
    `/api/customer/scheduling/friends/${encodeURIComponent(friendshipId)}`,
  );
}
