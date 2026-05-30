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
  return customerApi.post<ApiResponse<CustomerAuthResult>>('/api/auth/register', input);
}

export function loginCustomer(
  input: LoginCustomerInput,
): Promise<ApiResponse<CustomerAuthResult>> {
  return customerApi.post<ApiResponse<CustomerAuthResult>>('/api/auth/login', input);
}

export function verifyCustomerEmail(
  input: VerifyCustomerEmailInput,
): Promise<ApiResponse<CustomerAuthResult>> {
  return customerApi.post<ApiResponse<CustomerAuthResult>>('/api/auth/verify-email', input);
}

export function resendCustomerVerification(
  input: CustomerEmailInput,
): Promise<ApiResponse<CustomerAuthMessageResult>> {
  return customerApi.post<ApiResponse<CustomerAuthMessageResult>>('/api/auth/resend-verification', input);
}

export function requestCustomerPasswordReset(
  input: CustomerEmailInput,
): Promise<ApiResponse<CustomerAuthMessageResult>> {
  return customerApi.post<ApiResponse<CustomerAuthMessageResult>>('/api/auth/forgot-password', input);
}

export function resetCustomerPassword(
  input: ResetCustomerPasswordInput,
): Promise<ApiResponse<CustomerAuthMessageResult>> {
  return customerApi.post<ApiResponse<CustomerAuthMessageResult>>('/api/auth/reset-password', input);
}

export function getCustomerProfile(): Promise<ApiResponse<CustomerProfile>> {
  return customerApi.get<ApiResponse<CustomerProfile>>('/api/auth/me');
}
