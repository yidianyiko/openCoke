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

export function listCustomerSharedReminders(): Promise<
  ApiResponse<CustomerSharedReminderListResult>
> {
  return customerApi.get<ApiResponse<CustomerSharedReminderListResult>>(
    '/api/customer/shared-reminders',
  );
}

export function cancelCustomerSharedReminder(
  sharedReminderId: string,
): Promise<ApiResponse<CustomerSharedReminderActionResult>> {
  return customerApi.post<ApiResponse<CustomerSharedReminderActionResult>>(
    `/api/customer/shared-reminders/${encodeURIComponent(sharedReminderId)}/cancel`,
  );
}
