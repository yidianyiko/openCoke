export type ApiResponse<T> =
  | {
      ok: true;
      data: T;
    }
  | {
      ok: false;
      error: string;
      issues?: unknown;
    };

export type PublicUserLinkResponse = {
  code: string;
  status: 'active' | 'disabled' | 'expired';
  profile: {
    displayName: string;
    tagline: string | null;
    avatarUrl: string | null;
  };
};

export type PublicLinkSessionResponse = {
  token: string;
  targetAccountId: string;
  expiresAt: string;
  loginUrl: string;
  registerUrl: string;
};

export type PublicLinkSessionStatusResponse = {
  providerAccountId: string;
  consumerAccountId: string | null;
  status: 'opened' | 'claimed' | 'abandoned';
  expiresAt: string;
};

export type DirectFriendshipResponse = {
  id: string;
  status: string;
  friend_account_id: string;
  created: boolean;
};
