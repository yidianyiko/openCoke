import { beforeEach, describe, expect, it, vi } from 'vitest';
import { customerApi } from './customer-api';
import {
  clearCustomerAuth,
  getCustomerToken,
  getCustomerProfile,
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

  it('fetches the hydrated customer profile from the neutral me endpoint', async () => {
    vi.mocked(customerApi.get).mockResolvedValueOnce({
      ok: true,
      data: {
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
      },
    });

    await expect(getCustomerProfile()).resolves.toEqual({
      ok: true,
      data: {
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
      },
    });
    expect(vi.mocked(customerApi.get)).toHaveBeenCalledWith('/api/auth/me');
  });
});
