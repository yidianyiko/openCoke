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
const displayTimezone = encodeURIComponent(
  Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
);

afterEach(() => {
  vi.clearAllMocks();
});

describe('customer reminder wrappers', () => {
  it('lists customer reminders for a date range with active as the default state', async () => {
    apiMock.get.mockResolvedValueOnce({ owner_account_id: 'acct_1', entries: [] });

    await listCustomerReminders({ from: '2026-05-11', to: '2026-05-17' });

    expect(apiMock.get).toHaveBeenCalledWith(
      `/api/reminders/calendar?visible_start=2026-05-11T00%3A00%3A00.000Z&visible_end=2026-05-17T23%3A59%3A59.999Z&display_timezone=${displayTimezone}`,
    );
  });

  it('uses the clean calendar read endpoint regardless of stale state filters', async () => {
    apiMock.get.mockResolvedValueOnce({ owner_account_id: 'acct_1', entries: [] });

    await listCustomerReminders({
      from: '2026-05-11',
      to: '2026-05-17',
      states: ['active', 'completed'],
    });

    expect(apiMock.get).toHaveBeenCalledWith(
      `/api/reminders/calendar?visible_start=2026-05-11T00%3A00%3A00.000Z&visible_end=2026-05-17T23%3A59%3A59.999Z&display_timezone=${displayTimezone}`,
    );
  });

  it('preserves display_start local date and time without UTC shifting', async () => {
    apiMock.get.mockResolvedValueOnce({
      owner_account_id: 'acct_1',
      entries: [{
        reminder_id: 'rem-local',
        content: 'Late local reminder',
        display_start: '2026-05-30T22:00:00+09:00',
      }],
    });

    const result = await listCustomerReminders({ from: '2026-05-30', to: '2026-05-30' });

    expect(result).toMatchObject({
      ok: true,
      data: {
        reminders: [{
          id: 'rem-local',
          title: 'Late local reminder',
          localDate: '2026-05-30',
          localTime: '22:00',
        }],
      },
    });
  });

  it('creates and updates reminders using repeat selections mapped to rrule values', async () => {
    apiMock.post
      .mockResolvedValueOnce({
        owner_account_id: 'acct_1',
        items: [{
          state: 'created',
          reminder_id: 'rem-1',
          reason: null,
          time_state: 'scheduled',
          fact: null,
        }],
      })
      .mockResolvedValueOnce({
        owner_account_id: 'acct_1',
        items: [{
          state: 'updated',
          reminder_id: 'rem-1',
          reason: null,
          time_state: 'scheduled',
          fact: null,
        }],
      });

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

    expect(apiMock.post).toHaveBeenCalledWith('/api/reminders/batch', {
      items: [{
        operation: 'create',
        content: 'Standup',
        raw_text: 'Standup',
        trigger_time: '2026-05-13T09:30:00',
        captured_timezone: 'Asia/Tokyo',
        recurrence_rule: { rrule: 'FREQ=WEEKLY' },
        duration_minutes: 60,
        kind: 'recurring',
        entry_point: 'web',
      }],
    });
    expect(apiMock.post).toHaveBeenCalledWith('/api/reminders/batch', {
      items: [{
        operation: 'update',
        reminder_id: 'rem-1',
        content: 'Daily standup',
        raw_text: 'Daily standup',
        trigger_time: '2026-05-14T09:00:00',
        captured_timezone: 'Asia/Tokyo',
        recurrence_rule: { rrule: 'FREQ=DAILY' },
        duration_minutes: 90,
        kind: 'recurring',
        entry_point: 'web',
      }],
    });
  });

  it('maps the none repeat selection to a null rrule', async () => {
    apiMock.post.mockResolvedValueOnce({
      owner_account_id: 'acct_1',
      items: [{
        state: 'created',
        reminder_id: 'rem-1',
        reason: null,
        time_state: 'scheduled',
        fact: null,
      }],
    });

    await createCustomerReminder({
      title: 'One shot',
      localDate: '2026-05-13',
      localTime: '10:00',
      timezone: 'UTC',
      repeat: 'none',
    });

    expect(apiMock.post).toHaveBeenCalledWith('/api/reminders/batch', {
      items: [{
        operation: 'create',
        content: 'One shot',
        raw_text: 'One shot',
        trigger_time: '2026-05-13T10:00:00',
        captured_timezone: 'UTC',
        recurrence_rule: {},
        duration_minutes: null,
        kind: 'timed',
        entry_point: 'web',
      }],
    });
  });

  it('completes and cancels reminders through action endpoints', async () => {
    apiMock.post.mockResolvedValue({
      state: 'updated',
      reminder_id: 'rem-1',
      reason: null,
      time_state: 'scheduled',
      fact: null,
    });

    await completeCustomerReminder('rem-1');
    await cancelCustomerReminder('rem-2');

    expect(apiMock.post).toHaveBeenNthCalledWith(1, '/api/reminders/rem-1/complete');
    expect(apiMock.post).toHaveBeenNthCalledWith(2, '/api/reminders/rem-2/delete');
  });
});
