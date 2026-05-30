import { afterEach, describe, expect, it, vi } from 'vitest';
import { customerApi } from './customer-api';
import {
  cancelCustomerSharedReminder,
  listCustomerSharedReminders,
} from './customer-shared-reminders';

vi.mock('./customer-api', () => ({
  customerApi: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const apiMock = vi.mocked(customerApi);

afterEach(() => {
  vi.clearAllMocks();
});

describe('customer shared reminder wrappers', () => {
  it('lists and cancels shared reminders through Python API paths', async () => {
    apiMock.get.mockResolvedValue({ ok: true, data: { sharedReminders: [] } });
    apiMock.post.mockResolvedValue({ ok: true, data: { id: 'sr_1', status: 'cancelled' } });

    await listCustomerSharedReminders();
    await cancelCustomerSharedReminder('sr/1');

    expect(apiMock.get).toHaveBeenCalledWith('/api/customer/shared-reminders');
    expect(apiMock.post).toHaveBeenCalledWith('/api/customer/shared-reminders/sr%2F1/cancel');
  });
});
