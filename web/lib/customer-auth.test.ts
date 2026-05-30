import { beforeEach, describe, expect, it, vi } from 'vitest';
import { customerApi } from './customer-api';
import {
  clearCustomerAuth,
  getCustomerToken,
  getCustomerProfile,
  loginCustomer,
  registerCustomer,
  getStoredCustomerProfile,
  getStoredCustomerSession,
  storeCustomerAuth,
  storeCustomerProfile,
} from './customer-auth';

vi.mock('./customer-api', () => ({
  customerApi: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('customer auth storage', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(customerApi.get).mockReset();
    vi.mocked(customerApi.post).mockReset();
  });

  it('stores customer profile state separately from the session token', () => {
    storeCustomerProfile({
      id: 'ck_1',
      customerId: 'ck_1',
      identityId: 'idt_1',
      claimStatus: 'active',
      email: 'alice@example.com',
      membershipRole: 'owner',
      display_name: 'Alice',
      email_verified: true,
      status: 'normal',
      subscription_active: false,
      subscription_expires_at: null,
    });

    expect(getCustomerToken()).toBeNull();
    expect(getStoredCustomerProfile()).toEqual({
      id: 'ck_1',
      customerId: 'ck_1',
      identityId: 'idt_1',
      claimStatus: 'active',
      email: 'alice@example.com',
      membershipRole: 'owner',
      display_name: 'Alice',
      email_verified: true,
      status: 'normal',
      subscription_active: false,
      subscription_expires_at: null,
    });
    expect(getStoredCustomerSession()).toBeNull();
  });

  it('drops any stale cached profile when storing a new customer session', () => {
    storeCustomerProfile({
      id: 'old_ck',
      customerId: 'old_ck',
      identityId: 'old_idt',
      claimStatus: 'active',
      email: 'old@example.com',
      membershipRole: 'owner',
      display_name: 'Old Alice',
      email_verified: false,
      status: 'normal',
      subscription_active: false,
      subscription_expires_at: null,
    });

    storeCustomerAuth({
      token: 'customer-token',
      customerId: 'ck_2',
      identityId: 'idt_2',
      claimStatus: 'pending',
      email: 'new@example.com',
      membershipRole: 'owner',
    });

    expect(getCustomerToken()).toBe('customer-token');
    expect(getStoredCustomerProfile()).toBeNull();
    expect(getStoredCustomerSession()).toEqual({
      customerId: 'ck_2',
      identityId: 'idt_2',
      claimStatus: 'pending',
      email: 'new@example.com',
      membershipRole: 'owner',
    });
  });

  it('clears the stored customer profile when clearing customer auth', () => {
    storeCustomerAuth({
      token: 'customer-token',
      customerId: 'ck_1',
      identityId: 'idt_1',
      claimStatus: 'active',
      email: 'alice@example.com',
      membershipRole: 'owner',
    });
    storeCustomerProfile({
      id: 'ck_1',
      customerId: 'ck_1',
      identityId: 'idt_1',
      claimStatus: 'active',
      email: 'alice@example.com',
      membershipRole: 'owner',
      display_name: 'Alice',
      email_verified: true,
      status: 'normal',
      subscription_active: true,
      subscription_expires_at: null,
    });

    clearCustomerAuth();

    expect(getCustomerToken()).toBeNull();
    expect(getStoredCustomerSession()).toBeNull();
    expect(getStoredCustomerProfile()).toBeNull();
  });

  it('maps login credentials and the clean auth response into customer session state', async () => {
    vi.mocked(customerApi.post).mockResolvedValueOnce({
      account_id: 'acct_1',
      session_token: 'session_1',
    });

    await expect(
      loginCustomer({
        email: 'alice@example.com',
        password: 'secret',
      }),
    ).resolves.toEqual({
      ok: true,
      data: {
        token: 'session_1',
        customerId: 'acct_1',
        identityId: 'acct_1',
        claimStatus: 'active',
        email: 'alice@example.com',
        membershipRole: 'owner',
      },
    });
    expect(vi.mocked(customerApi.post)).toHaveBeenCalledWith('/api/auth/login', {
      email: 'alice@example.com',
      password: 'secret',
    });
  });

  it('maps register input to the clean account registration endpoint', async () => {
    vi.mocked(customerApi.post).mockResolvedValueOnce({
      account_id: 'acct_2',
      session_token: 'session_2',
      email_verification_artifact_id: 'artifact_1',
    });

    await expect(
      registerCustomer({
        displayName: 'Alice',
        email: 'alice@example.com',
        password: 'secret',
      }),
    ).resolves.toMatchObject({
      ok: true,
      data: {
        token: 'session_2',
        customerId: 'acct_2',
        identityId: 'acct_2',
        email: 'alice@example.com',
      },
    });
    expect(vi.mocked(customerApi.post)).toHaveBeenCalledWith('/api/auth/register', {
      email: 'alice@example.com',
      password: 'secret',
      default_timezone: expect.any(String),
    });
  });

  it('hydrates the customer profile from current-user and access-status', async () => {
    storeCustomerAuth({
      token: 'customer-token',
      customerId: 'acct_1',
      identityId: 'acct_1',
      claimStatus: 'active',
      email: 'alice@example.com',
      membershipRole: 'owner',
    });
    vi.mocked(customerApi.get)
      .mockResolvedValueOnce({
        account_id: 'acct_1',
        origin: 'web_first',
      })
      .mockResolvedValueOnce({
        account_id: 'acct_1',
        access_allowed: true,
        denial_reason: null,
      });

    await expect(getCustomerProfile()).resolves.toEqual({
      ok: true,
      data: {
        id: 'acct_1',
        customerId: 'acct_1',
        identityId: 'acct_1',
        claimStatus: 'active',
        email: 'alice@example.com',
        membershipRole: 'owner',
        display_name: 'Alice',
        email_verified: true,
        status: 'normal',
        subscription_active: true,
        subscription_expires_at: null,
      },
    });
    expect(vi.mocked(customerApi.get)).toHaveBeenNthCalledWith(1, '/api/auth/current-user');
    expect(vi.mocked(customerApi.get)).toHaveBeenNthCalledWith(2, '/api/auth/access-status');
  });
});
