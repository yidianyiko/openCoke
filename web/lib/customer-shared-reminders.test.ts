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
    apiMock.get.mockResolvedValue({ shared_reminders: [] });
    apiMock.post.mockResolvedValue({
      status: 'cancelled',
      shared_reminder: {
        shared_reminder_id: 'sr_1',
        title: 'Dinner',
        local_trigger_at: '2026-05-31T19:00:00',
        captured_timezone: 'Asia/Tokyo',
        duration_minutes: 60,
        status: 'cancelled',
        participant_account_ids: ['acct_1', 'acct_2'],
      },
    });

    await listCustomerSharedReminders();
    await cancelCustomerSharedReminder('sr/1');

    expect(apiMock.get).toHaveBeenCalledWith('/api/shared-reminders');
    expect(apiMock.post).toHaveBeenCalledWith('/api/shared-reminders/sr%2F1/cancel');
  });
});
