import { beforeEach, describe, expect, it, vi } from 'vitest';
import { customerApi } from './customer-api';
import { requestCustomerClaimEmail } from './customer-google-calendar-import';

vi.mock('./customer-api', () => ({
  customerApi: {
    post: vi.fn(),
  },
}));

describe('customer Google calendar import claim helpers', () => {
  beforeEach(() => {
    vi.mocked(customerApi.post).mockReset();
  });

  it('requests a claim email using the entry token and target email', async () => {
    vi.mocked(customerApi.post).mockResolvedValueOnce({ accepted: true });

    await expect(
      requestCustomerClaimEmail({
        entryToken: 'entry-token-123',
        email: 'claimant@example.com',
        next: '/account/calendar-import',
      }),
    ).resolves.toEqual({ ok: true, data: { message: 'claim_email_sent' } });
    expect(vi.mocked(customerApi.post)).toHaveBeenCalledWith('/api/claim/email', {
      entry_token: 'entry-token-123',
      email: 'claimant@example.com',
      continuation: { next: '/account/calendar-import' },
    });
  });

  it('maps invalid claim entry tokens to the claim-entry recovery error', async () => {
    vi.mocked(customerApi.post).mockResolvedValueOnce({
      error: { code: 'artifact_expired' },
    });

    await expect(
      requestCustomerClaimEmail({
        entryToken: 'expired-token',
        email: 'claimant@example.com',
      }),
    ).resolves.toEqual({ ok: false, error: 'invalid_or_expired_token' });
  });

  it('maps duplicate emails to the claim-entry duplicate email error', async () => {
    vi.mocked(customerApi.post).mockResolvedValueOnce({
      error: { code: 'email_already_registered' },
    });

    await expect(
      requestCustomerClaimEmail({
        entryToken: 'entry-token-123',
        email: 'a@example.com',
      }),
    ).resolves.toEqual({ ok: false, error: 'email_already_exists' });
  });
});
