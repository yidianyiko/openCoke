import { afterEach, describe, expect, it, vi } from 'vitest';
import { customerApi } from './customer-api';
import {
  cancelCustomerReminder,
  completeCustomerReminder,
  createCustomerReminder,
  listCustomerReminders,
  updateCustomerReminder,
} from './customer-reminders';

vi.mock('./customer-api', () => ({
  customerApi: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

const apiMock = vi.mocked(customerApi);

afterEach(() => {
  vi.clearAllMocks();
});

describe('customer reminder wrappers', () => {
  it('lists customer reminders for a date range with active as the default state', async () => {
    apiMock.get.mockResolvedValueOnce({ ok: true, data: { reminders: [] } });

    await listCustomerReminders({ from: '2026-05-11', to: '2026-05-17' });

    expect(apiMock.get).toHaveBeenCalledWith('/api/customer/reminders?from=2026-05-11&to=2026-05-17&state=active');
  });

  it('passes selected reminder states as repeated state query params', async () => {
    apiMock.get.mockResolvedValueOnce({ ok: true, data: { reminders: [] } });

    await listCustomerReminders({
      from: '2026-05-11',
      to: '2026-05-17',
      states: ['active', 'completed'],
    });

    expect(apiMock.get).toHaveBeenCalledWith(
      '/api/customer/reminders?from=2026-05-11&to=2026-05-17&state=active&state=completed',
    );
  });

  it('creates and updates reminders using repeat selections mapped to rrule values', async () => {
    apiMock.post.mockResolvedValueOnce({ ok: true, data: { id: 'rem-1' } });
    apiMock.patch.mockResolvedValueOnce({ ok: true, data: { id: 'rem-1' } });

    await createCustomerReminder({
      title: 'Standup',
      localDate: '2026-05-13',
      localTime: '09:30',
      timezone: 'Asia/Tokyo',
      repeat: 'weekly',
      durationMinutes: 60,
    });
    await updateCustomerReminder('rem-1', {
      title: 'Daily standup',
      localDate: '2026-05-14',
      localTime: '09:00',
      timezone: 'Asia/Tokyo',
      repeat: 'daily',
      durationMinutes: 90,
    });

    expect(apiMock.post).toHaveBeenCalledWith('/api/customer/reminders', {
      title: 'Standup',
      localDate: '2026-05-13',
      localTime: '09:30',
      timezone: 'Asia/Tokyo',
      rrule: 'FREQ=WEEKLY',
      durationMinutes: 60,
    });
    expect(apiMock.patch).toHaveBeenCalledWith('/api/customer/reminders/rem-1', {
      title: 'Daily standup',
      localDate: '2026-05-14',
      localTime: '09:00',
      timezone: 'Asia/Tokyo',
      rrule: 'FREQ=DAILY',
      durationMinutes: 90,
    });
  });

  it('maps the none repeat selection to a null rrule', async () => {
    apiMock.post.mockResolvedValueOnce({ ok: true, data: { id: 'rem-1' } });

    await createCustomerReminder({
      title: 'One shot',
      localDate: '2026-05-13',
      localTime: '10:00',
      timezone: 'UTC',
      repeat: 'none',
    });

    expect(apiMock.post).toHaveBeenCalledWith('/api/customer/reminders', {
      title: 'One shot',
      localDate: '2026-05-13',
      localTime: '10:00',
      timezone: 'UTC',
      rrule: null,
      durationMinutes: null,
    });
  });

  it('completes and cancels reminders through action endpoints', async () => {
    apiMock.post.mockResolvedValue({ ok: true, data: { id: 'rem-1' } });

    await completeCustomerReminder('rem-1');
    await cancelCustomerReminder('rem-2');

    expect(apiMock.post).toHaveBeenNthCalledWith(1, '/api/customer/reminders/rem-1/complete');
    expect(apiMock.post).toHaveBeenNthCalledWith(2, '/api/customer/reminders/rem-2/cancel');
  });
});
