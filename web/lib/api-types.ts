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

export type ProductActionAvailability<Action extends string, Reason extends string> = {
  actions: Record<Action, boolean>;
  unavailableReasons: Partial<Record<Action, Reason[]>>;
};

export type PublicUserLinkResponse = {
  code: string;
  status: 'active';
  profile: {
    displayName: string;
    tagline: string | null;
    avatarUrl: string | null;
  };
};
