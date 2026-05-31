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

type CleanCalendarEntry = {
  entry_type: string;
  reminder_id: string | null;
  display_start: string | null;
  display_end: string | null;
  content: string;
  action_handles?: string[];
  fact?: Record<string, unknown> | null;
};

type CleanCalendarResult = {
  owner_account_id: string;
  entries: CleanCalendarEntry[];
};

type CleanBatchItemResult = {
  state: string;
  reminder_id: string | null;
  reason: string | null;
  time_state: string | null;
  fact: Record<string, unknown> | null;
};

type CleanBatchResult = {
  owner_account_id: string;
  items: CleanBatchItemResult[];
};

function repeatToRrule(repeat: CustomerReminderRepeat): string | null {
  if (repeat === 'daily') {
    return 'FREQ=DAILY';
  }
  if (repeat === 'weekly') {
    return 'FREQ=WEEKLY';
  }
  return null;
}

function currentTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
}

function reminderKind(input: CustomerReminderFormInput): string {
  if (!input.localDate || !input.localTime) {
    return 'no_trigger_time';
  }
  if (repeatToRrule(input.repeat)) {
    return 'recurring';
  }
  return 'timed';
}

function triggerTime(input: CustomerReminderFormInput): string | null {
  if (!input.localDate || !input.localTime) {
    return null;
  }
  return `${input.localDate}T${input.localTime}:00`;
}

function recurrenceRule(input: CustomerReminderFormInput): Record<string, string> {
  const rrule = repeatToRrule(input.repeat);
  return rrule ? { rrule } : {};
}

function batchItem(operation: 'create' | 'update', input: CustomerReminderFormInput, reminderId?: string) {
  return {
    operation,
    ...(reminderId ? { reminder_id: reminderId } : {}),
    content: input.title,
    raw_text: input.title,
    trigger_time: triggerTime(input),
    captured_timezone: input.timezone,
    recurrence_rule: recurrenceRule(input),
    duration_minutes: input.durationMinutes ?? null,
    kind: reminderKind(input),
    entry_point: 'web',
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
    visible_start: new Date(`${input.from}T00:00:00.000Z`).toISOString(),
    visible_end: new Date(`${input.to}T23:59:59.999Z`).toISOString(),
    display_timezone: currentTimezone(),
  });

  return customerApi
    .get<CleanCalendarResult>(`/api/reminders/calendar?${params.toString()}`)
    .then((result) => ({
      ok: true,
      data: {
        reminders: result.entries
          .filter((entry) => entry.reminder_id)
          .map((entry) => calendarEntryToReminder(entry)),
      },
    }));
}

export function createCustomerReminder(
  input: CustomerReminderFormInput,
): Promise<ApiResponse<CustomerReminder>> {
  return customerApi
    .post<CleanBatchResult>('/api/reminders/batch', { items: [batchItem('create', input)] })
    .then((result) => cleanBatchResultToReminder(result, input));
}

export function updateCustomerReminder(
  reminderId: string,
  input: CustomerReminderFormInput,
): Promise<ApiResponse<CustomerReminder>> {
  return customerApi
    .post<CleanBatchResult>('/api/reminders/batch', {
      items: [batchItem('update', input, reminderId)],
    })
    .then((result) => cleanBatchResultToReminder(result, input, reminderId));
}

export function completeCustomerReminder(reminderId: string): Promise<ApiResponse<CustomerReminder>> {
  return customerApi
    .post<CleanBatchItemResult>(`/api/reminders/${encodeURIComponent(reminderId)}/complete`)
    .then((result) => cleanActionResultToReminder(result, reminderId, 'completed'));
}

export function cancelCustomerReminder(reminderId: string): Promise<ApiResponse<CustomerReminder>> {
  return customerApi
    .post<CleanBatchItemResult>(`/api/reminders/${encodeURIComponent(reminderId)}/delete`)
    .then((result) => cleanActionResultToReminder(result, reminderId, 'cancelled'));
}

function calendarEntryToReminder(entry: CleanCalendarEntry): CustomerReminder {
  const start = entry.display_start ? localDateTimeParts(entry.display_start) : null;
  return {
    id: entry.reminder_id ?? '',
    title: entry.content,
    lifecycleState: 'active',
    localDate: start?.localDate ?? '',
    localTime: start?.localTime ?? '',
    timezone: currentTimezone(),
    durationMinutes: null,
  };
}

function localDateTimeParts(value: string): { localDate: string; localTime: string } | null {
  const match = value.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
  if (!match) {
    return null;
  }
  return {
    localDate: match[1],
    localTime: match[2],
  };
}

function cleanBatchResultToReminder(
  result: CleanBatchResult,
  input: CustomerReminderFormInput,
  fallbackReminderId?: string,
): ApiResponse<CustomerReminder> {
  const item = result.items[0];
  if (!item || item.state === 'failed') {
    return { ok: false, error: item?.reason ?? 'reminder_update_failed' };
  }
  return {
    ok: true,
    data: {
      id: item.reminder_id ?? fallbackReminderId ?? '',
      title: input.title,
      lifecycleState: 'active',
      localDate: input.localDate,
      localTime: input.localTime,
      timezone: input.timezone,
      rrule: repeatToRrule(input.repeat),
      durationMinutes: input.durationMinutes ?? null,
    },
  };
}

function cleanActionResultToReminder(
  result: CleanBatchItemResult,
  fallbackReminderId: string,
  state: CustomerReminderState,
): ApiResponse<CustomerReminder> {
  if (result.state === 'failed') {
    return { ok: false, error: result.reason ?? 'reminder_action_failed' };
  }
  return {
    ok: true,
    data: {
      id: result.reminder_id ?? fallbackReminderId,
      title: '',
      lifecycleState: state,
      localDate: '',
      localTime: '',
      timezone: currentTimezone(),
    },
  };
}
