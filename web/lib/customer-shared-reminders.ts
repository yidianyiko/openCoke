import type { ApiResponse } from './api-types';
import { customerApi } from './customer-api';

export type CustomerSharedReminder = {
  id: string;
  title: string;
  triggerTime: string;
  timezone: string;
  durationMinutes: number;
  status: 'active' | 'cancelled';
  participants: string[];
};

export type CustomerSharedReminderListResult = {
  sharedReminders: CustomerSharedReminder[];
};

export type CustomerSharedReminderActionResult = {
  id: string;
  status: string;
};

type CleanSharedReminder = {
  shared_reminder_id: string;
  title: string;
  local_trigger_at: string;
  captured_timezone: string;
  duration_minutes: number;
  status: 'active' | 'cancelled';
  participant_account_ids: string[];
};

type CleanSharedReminderList = {
  shared_reminders: CleanSharedReminder[];
};

type CleanSharedReminderAction = {
  status: string;
  shared_reminder: CleanSharedReminder;
};

export function listCustomerSharedReminders(): Promise<
  ApiResponse<CustomerSharedReminderListResult>
> {
  return customerApi.get<CleanSharedReminderList>('/api/shared-reminders').then((result) => ({
    ok: true,
    data: {
      sharedReminders: result.shared_reminders.map(cleanSharedReminder),
    },
  }));
}

export function cancelCustomerSharedReminder(
  sharedReminderId: string,
): Promise<ApiResponse<CustomerSharedReminderActionResult>> {
  return customerApi
    .post<CleanSharedReminderAction>(
      `/api/shared-reminders/${encodeURIComponent(sharedReminderId)}/cancel`,
    )
    .then((result) => ({
      ok: true,
      data: {
        id: result.shared_reminder.shared_reminder_id,
        status: result.status,
      },
    }));
}

function cleanSharedReminder(reminder: CleanSharedReminder): CustomerSharedReminder {
  return {
    id: reminder.shared_reminder_id,
    title: reminder.title,
    triggerTime: reminder.local_trigger_at,
    timezone: reminder.captured_timezone,
    durationMinutes: reminder.duration_minutes,
    status: reminder.status,
    participants: reminder.participant_account_ids,
  };
}
