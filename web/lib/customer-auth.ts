import type { ApiResponse } from './api-types';
import { customerApi } from './customer-api';

const TOKEN_KEY = 'customer_token';
const SESSION_KEY = 'customer_session';
const PROFILE_KEY = 'customer_profile';

type CustomerClaimStatus = 'active' | 'unclaimed' | 'pending';
type CustomerMembershipRole = 'owner' | 'member' | 'viewer';

interface CustomerSession {
  customerId: string;
  identityId: string;
  claimStatus: CustomerClaimStatus;
  email: string;
  membershipRole: CustomerMembershipRole;
}

export interface CustomerAuthResult extends CustomerSession {
  token: string;
  continueTo?: string;
}

export interface CustomerProfile extends CustomerSession {
  id: string;
  display_name: string;
  email_verified: boolean;
  status: 'normal' | 'suspended';
  subscription_active: boolean;
  subscription_expires_at: string | null;
}

interface CustomerAuthMessageResult {
  message: string;
}

interface RegisterCustomerInput {
  displayName: string;
  email: string;
  password: string;
}

interface LoginCustomerInput {
  email: string;
  password: string;
}

interface VerifyCustomerEmailInput {
  email: string;
  token: string;
}

interface CustomerEmailInput {
  email: string;
}

interface ResetCustomerPasswordInput {
  token: string;
  password: string;
}

type CleanAuthError = {
  error: {
    code: string;
  };
};

type CleanAuthResult = {
  account_id: string;
  session_token: string;
};

type CleanEmailVerificationResult = {
  account_id: string;
  email: string;
  session_token?: string;
};

type CleanCurrentUser = {
  account_id: string;
  origin: string;
};

type CleanAccessStatus = {
  account_id: string;
  access_allowed: boolean;
  denial_reason: string | null;
};

function isCleanAuthError(value: unknown): value is CleanAuthError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as CleanAuthError).error?.code === 'string'
  );
}

function currentTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
}

function displayNameFromEmail(email: string): string {
  const name = email.split('@')[0]?.trim();
  if (!name) {
    return 'Coke user';
  }
  return name.charAt(0).toUpperCase() + name.slice(1);
}

function sessionFromCleanAuth(result: CleanAuthResult, email: string): CustomerAuthResult {
  return {
    token: result.session_token,
    customerId: result.account_id,
    identityId: result.account_id,
    claimStatus: 'active',
    email,
    membershipRole: 'owner',
  };
}

function errorResponse<T>(error: string): ApiResponse<T> {
  return { ok: false, error };
}

function getStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function storeCustomerAuth(result: CustomerAuthResult): void {
  const storage = getStorage();
  if (!storage) {
    return;
  }

  const { token, continueTo: _continueTo, ...session } = result;
  storage.removeItem(PROFILE_KEY);
  storage.setItem(TOKEN_KEY, token);
  storage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearCustomerAuth(): void {
  const storage = getStorage();
  if (!storage) {
    return;
  }

  storage.removeItem(TOKEN_KEY);
  storage.removeItem(SESSION_KEY);
  storage.removeItem(PROFILE_KEY);
}

export function getCustomerToken(): string | null {
  return getStorage()?.getItem(TOKEN_KEY) ?? null;
}

export function getStoredCustomerSession(): CustomerSession | null {
  const raw = getStorage()?.getItem(SESSION_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as CustomerSession;
  } catch {
    return null;
  }
}

export function storeCustomerProfile(profile: CustomerProfile): void {
  const storage = getStorage();
  if (!storage) {
    return;
  }

  storage.setItem(PROFILE_KEY, JSON.stringify(profile));
}

export function getStoredCustomerProfile(): CustomerProfile | null {
  const raw = getStorage()?.getItem(PROFILE_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as CustomerProfile;
  } catch {
    return null;
  }
}

export function registerCustomer(
  input: RegisterCustomerInput,
): Promise<ApiResponse<CustomerAuthResult>> {
  return customerApi
    .post<CleanAuthResult | CleanAuthError>('/api/auth/register', {
      email: input.email,
      password: input.password,
      display_name: input.displayName,
      default_timezone: currentTimezone(),
    })
    .then((result) => {
      if (isCleanAuthError(result)) {
        return errorResponse<CustomerAuthResult>(
          result.error.code === 'email_already_registered'
            ? 'email_already_exists'
            : result.error.code,
        );
      }
      return { ok: true, data: sessionFromCleanAuth(result, input.email) };
    });
}

export function loginCustomer(
  input: LoginCustomerInput,
): Promise<ApiResponse<CustomerAuthResult>> {
  return customerApi
    .post<CleanAuthResult | CleanAuthError>('/api/auth/login', {
      email: input.email,
      password: input.password,
    })
    .then((result) => {
      if (isCleanAuthError(result)) {
        return errorResponse<CustomerAuthResult>(result.error.code);
      }
      return { ok: true, data: sessionFromCleanAuth(result, input.email) };
    });
}

export function verifyCustomerEmail(
  input: VerifyCustomerEmailInput,
): Promise<ApiResponse<CustomerAuthResult>> {
  const session = getStoredCustomerSession();
  return customerApi
    .post<CleanEmailVerificationResult | CleanAuthError>(
      '/api/auth/email-verification/verify',
      { token: input.token },
    )
    .then((result) => {
      if (isCleanAuthError(result)) {
        return errorResponse<CustomerAuthResult>(result.error.code);
      }
      if (result.session_token) {
        return {
          ok: true,
          data: sessionFromCleanAuth(
            {
              account_id: result.account_id,
              session_token: result.session_token,
            },
            result.email,
          ),
        };
      }
      if (!session || session.email.toLowerCase() !== input.email.toLowerCase()) {
        return errorResponse<CustomerAuthResult>('verified_login_required');
      }
      return {
        ok: true,
        data: {
          ...session,
          token: getCustomerToken() ?? '',
          claimStatus: 'active',
          email: result.email,
        },
      };
    });
}

export function resendCustomerVerification(
  input: CustomerEmailInput,
): Promise<ApiResponse<CustomerAuthMessageResult>> {
  return customerApi
    .post<{ accepted: boolean } | CleanAuthError>('/api/auth/email-verification/resend', input)
    .then((result) => {
      if (isCleanAuthError(result)) {
        return errorResponse<CustomerAuthMessageResult>(result.error.code);
      }
      return { ok: true, data: { message: 'accepted' } };
    });
}

export function requestCustomerPasswordReset(
  input: CustomerEmailInput,
): Promise<ApiResponse<CustomerAuthMessageResult>> {
  return customerApi
    .post<{ accepted: boolean } | CleanAuthError>('/api/auth/password-reset/request', input)
    .then((result) => {
      if (isCleanAuthError(result)) {
        return errorResponse<CustomerAuthMessageResult>(result.error.code);
      }
      return { ok: true, data: { message: 'accepted' } };
    });
}

export function resetCustomerPassword(
  input: ResetCustomerPasswordInput,
): Promise<ApiResponse<CustomerAuthMessageResult>> {
  return customerApi
    .post<{ account_id: string; email: string } | CleanAuthError>(
      '/api/auth/password-reset/complete',
      {
        token: input.token,
        password: input.password,
      },
    )
    .then((result) => {
      if (isCleanAuthError(result)) {
        return errorResponse<CustomerAuthMessageResult>(result.error.code);
      }
      return { ok: true, data: { message: 'password_reset' } };
    });
}

export function getCustomerProfile(): Promise<ApiResponse<CustomerProfile>> {
  const session = getStoredCustomerSession();
  if (!session) {
    return Promise.resolve(errorResponse<CustomerProfile>('missing_session'));
  }
  return customerApi
    .get<CleanCurrentUser | CleanAuthError>('/api/account/current-user')
    .then((currentUser) => {
      if (isCleanAuthError(currentUser)) {
        return errorResponse<CustomerProfile>(currentUser.error.code);
      }
      return customerApi
        .get<CleanAccessStatus | CleanAuthError>('/api/account/access-status')
        .then((access) => {
          if (isCleanAuthError(access)) {
            return errorResponse<CustomerProfile>(access.error.code);
          }
          const denialReason = access.denial_reason;
          return {
            ok: true,
            data: {
              id: currentUser.account_id,
              customerId: currentUser.account_id,
              identityId: currentUser.account_id,
              claimStatus: access.access_allowed ? 'active' : 'pending',
              email: session.email,
              membershipRole: session.membershipRole,
              display_name: displayNameFromEmail(session.email),
              email_verified: denialReason !== 'email_verification_required',
              status: denialReason === 'suspended' ? 'suspended' : 'normal',
              subscription_active: denialReason !== 'subscription_inactive',
              subscription_expires_at: null,
            },
          } satisfies ApiResponse<CustomerProfile>;
        });
    });
}
