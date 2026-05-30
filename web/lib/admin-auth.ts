type StoredAdminSession = {
  adminId: string;
  email: string;
  isActive: boolean;
};

export type AdminLoginResult = StoredAdminSession & {
  token: string;
};

const ADMIN_TOKEN_KEY = 'coke_admin_token';
const ADMIN_SESSION_KEY = 'coke_admin_session';
export const ADMIN_SESSION_CLEARED_EVENT = 'coke:admin-session-cleared';

export function storeAdminSession(result: AdminLoginResult): void {
  try {
    localStorage.setItem(ADMIN_TOKEN_KEY, result.token);
    localStorage.setItem(
      ADMIN_SESSION_KEY,
      JSON.stringify({
        adminId: result.adminId,
        email: result.email,
        isActive: result.isActive,
      } satisfies StoredAdminSession),
    );
  } catch {
    // Ignore storage write failures and keep callers stateless.
  }
}

export function clearAdminSession(): void {
  try {
    localStorage.removeItem(ADMIN_TOKEN_KEY);
    localStorage.removeItem(ADMIN_SESSION_KEY);
  } catch {
    // Ignore storage cleanup failures.
  }

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(ADMIN_SESSION_CLEARED_EVENT));
  }
}

export function getAdminToken(): string | null {
  try {
    return localStorage.getItem(ADMIN_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getStoredAdminSession(): StoredAdminSession | null {
  try {
    const raw = localStorage.getItem(ADMIN_SESSION_KEY);
    if (!raw) {
      return null;
    }

    return JSON.parse(raw) as StoredAdminSession;
  } catch {
    return null;
  }
}

export function isAdminAuthenticated(): boolean {
  return getAdminToken() != null;
}
