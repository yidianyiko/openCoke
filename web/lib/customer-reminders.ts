import type { ApiResponse } from './api-types';
import { customerApi } from './customer-api';

type CustomerReminderState = 'active' | 'completed' | 'cancelled' | 'failed';
export type CustomerReminderRepeat = 'none' | 'daily' | 'weekly';

export interface CustomerReminder {
  id: string;
  title: string;
  lifecycleState?: CustomerReminderState;
  localDate: string;
  localTime: string;
  timezone: string;
  rrule?: string | null;
  durationMinutes?: number | null;
}

export interface CustomerReminderFormInput {
  title: string;
  localDate: string;
  localTime: string;
  timezone: string;
  repeat: CustomerReminderRepeat;
  durationMinutes?: number | null;
}

interface ListCustomerRemindersInput {
  from: string;
  to: string;
  states?: CustomerReminderState[];
}

interface CustomerReminderListResult {
  reminders: CustomerReminder[];
}

function repeatToRrule(repeat: CustomerReminderRepeat): string | null {
  if (repeat === 'daily') {
    return 'FREQ=DAILY';
  }
  if (repeat === 'weekly') {
    return 'FREQ=WEEKLY';
  }
  return null;
}

function reminderBody(input: CustomerReminderFormInput) {
  return {
    title: input.title,
    localDate: input.localDate,
    localTime: input.localTime,
    timezone: input.timezone,
    rrule: repeatToRrule(input.repeat),
    durationMinutes: input.durationMinutes ?? null,
  };
}

export function repeatFromRrule(rrule: string | null | undefined): CustomerReminderRepeat {
  if (rrule === 'FREQ=DAILY') {
    return 'daily';
  }
  if (rrule === 'FREQ=WEEKLY') {
    return 'weekly';
  }
  return 'none';
}

export function listCustomerReminders(
  input: ListCustomerRemindersInput,
): Promise<ApiResponse<CustomerReminderListResult>> {
  const params = new URLSearchParams({
    from: input.from,
    to: input.to,
  });
  const states = input.states && input.states.length > 0 ? input.states : ['active'];
  for (const state of states) {
    params.append('state', state);
  }

  return customerApi.get<ApiResponse<CustomerReminderListResult>>(`/api/customer/reminders?${params.toString()}`);
}

export function createCustomerReminder(
  input: CustomerReminderFormInput,
): Promise<ApiResponse<CustomerReminder>> {
  return customerApi.post<ApiResponse<CustomerReminder>>('/api/customer/reminders', reminderBody(input));
}

export function updateCustomerReminder(
  reminderId: string,
  input: CustomerReminderFormInput,
): Promise<ApiResponse<CustomerReminder>> {
  return customerApi.patch<ApiResponse<CustomerReminder>>(
    `/api/customer/reminders/${encodeURIComponent(reminderId)}`,
    reminderBody(input),
  );
}

export function completeCustomerReminder(reminderId: string): Promise<ApiResponse<CustomerReminder>> {
  return customerApi.post<ApiResponse<CustomerReminder>>(
    `/api/customer/reminders/${encodeURIComponent(reminderId)}/complete`,
  );
}

export function cancelCustomerReminder(reminderId: string): Promise<ApiResponse<CustomerReminder>> {
  return customerApi.post<ApiResponse<CustomerReminder>>(
    `/api/customer/reminders/${encodeURIComponent(reminderId)}/cancel`,
  );
}
