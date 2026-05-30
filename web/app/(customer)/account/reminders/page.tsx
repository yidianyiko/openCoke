'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  cancelCustomerReminder,
  completeCustomerReminder,
  createCustomerReminder,
  listCustomerReminders,
  repeatFromRrule,
  updateCustomerReminder,
  type CustomerReminder,
  type CustomerReminderFormInput,
  type CustomerReminderRepeat,
} from '../../../../lib/customer-reminders';

const AUTH_ERRORS = new Set(['invalid_or_expired_token', 'unauthorized', 'account_not_found', 'claim_inactive']);

type DrawerState =
  | { mode: 'closed' }
  | { mode: 'create'; initialDate: string }
  | { mode: 'edit'; reminder: CustomerReminder };

function startOfLocalWeek(date: Date): Date {
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const day = start.getDay();
  const offset = day === 0 ? -6 : 1 - day;
  start.setDate(start.getDate() + offset);
  return start;
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function toLocalDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatWeekRange(weekStart: Date): string {
  const weekEnd = addDays(weekStart, 6);
  const sameYear = weekStart.getFullYear() === weekEnd.getFullYear();
  const start = weekStart.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' }),
  });
  const end = weekEnd.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
  return `${start} - ${end}`;
}

function getDefaultTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

function nextFutureTimeSlot(now: Date = new Date()): { localDate: string; localTime: string } {
  const slot = new Date(now);
  slot.setSeconds(0, 0);
  const minutes = slot.getMinutes();
  const nextQuarterHour = Math.ceil((minutes + 1) / 15) * 15;
  slot.setMinutes(nextQuarterHour);
  return {
    localDate: toLocalDate(slot),
    localTime: `${String(slot.getHours()).padStart(2, '0')}:${String(slot.getMinutes()).padStart(2, '0')}`,
  };
}

function emptyForm(localDate: string): CustomerReminderFormInput {
  const today = toLocalDate(new Date());
  const defaultSlot = localDate <= today ? nextFutureTimeSlot() : { localDate, localTime: '09:00' };
  return {
    title: '',
    localDate: defaultSlot.localDate,
    localTime: defaultSlot.localTime,
    timezone: getDefaultTimezone(),
    repeat: 'none',
  };
}

function saveReminderErrorMessage(error: string): string {
  if (error === 'invalid_schedule') {
    return 'Reminder time is in the past. Choose a future time.';
  }
  if (error === 'invalid_body') {
    return 'Check the reminder details and try again.';
  }
  return 'Unable to save this reminder right now.';
}

function formFromReminder(reminder: CustomerReminder): CustomerReminderFormInput {
  return {
    title: reminder.title,
    localDate: reminder.localDate,
    localTime: reminder.localTime,
    timezone: reminder.timezone || getDefaultTimezone(),
    repeat: repeatFromRrule(reminder.rrule),
    ...(reminder.durationMinutes !== undefined ? { durationMinutes: reminder.durationMinutes } : {}),
  };
}

function ReminderForm({
  drawer,
  saving,
  onClose,
  onAction,
  onSubmit,
}: {
  drawer: Exclude<DrawerState, { mode: 'closed' }>;
  saving: boolean;
  onClose: () => void;
  onAction: (action: 'complete' | 'cancel', reminderId: string) => void;
  onSubmit: (input: CustomerReminderFormInput) => void;
}) {
  const form = drawer.mode === 'edit' ? formFromReminder(drawer.reminder) : emptyForm(drawer.initialDate);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    onSubmit({
      title: String(formData.get('title') ?? '').trim(),
      localDate: String(formData.get('localDate') ?? form.localDate),
      localTime: String(formData.get('localTime') ?? form.localTime),
      timezone: String(formData.get('timezone') ?? form.timezone).trim() || 'UTC',
      repeat: String(formData.get('repeat') ?? form.repeat) as CustomerReminderRepeat,
      ...(form.durationMinutes !== undefined ? { durationMinutes: form.durationMinutes } : {}),
    });
  }

  return (
    <aside className="customer-reminder-drawer" aria-label="Reminder editor">
      <div className="customer-reminder-drawer__head">
        <div>
          <p className="customer-panel__eyebrow">{drawer.mode === 'edit' ? 'Edit reminder' : 'New reminder'}</p>
          <h2>{drawer.mode === 'edit' ? 'Update reminder' : 'Create reminder'}</h2>
        </div>
        <button type="button" className="customer-reminder-icon-button" onClick={onClose} aria-label="Close editor">
          x
        </button>
      </div>

      <form className="customer-reminder-form" onSubmit={handleSubmit}>
        <label>
          <span>Title</span>
          <input
            name="title"
            required
            maxLength={200}
            defaultValue={form.title}
          />
        </label>
        <div className="customer-reminder-form__grid">
          <label>
            <span>Date</span>
            <input
              name="localDate"
              type="date"
              required
              defaultValue={form.localDate}
            />
          </label>
          <label>
            <span>Time</span>
            <input
              name="localTime"
              type="time"
              required
              defaultValue={form.localTime}
            />
          </label>
        </div>
        <label>
          <span>Timezone</span>
          <input
            name="timezone"
            required
            defaultValue={form.timezone}
          />
        </label>
        <label>
          <span>Repeat</span>
          <select
            name="repeat"
            defaultValue={form.repeat}
          >
            <option value="none">None</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
          </select>
        </label>
        <div className="customer-action-row">
          <button type="submit" className="customer-action customer-action--primary" disabled={saving}>
            {saving ? 'Saving...' : 'Save'}
          </button>
          {drawer.mode === 'edit' ? (
            <>
              <button
                type="button"
                className="customer-action customer-action--secondary"
                onClick={() => onAction('complete', drawer.reminder.id)}
              >
                Complete
              </button>
              <button
                type="button"
                className="customer-action customer-action--secondary"
                onClick={() => onAction('cancel', drawer.reminder.id)}
              >
                Cancel
              </button>
            </>
          ) : null}
          <button type="button" className="customer-action customer-action--secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </form>
    </aside>
  );
}

export default function CustomerRemindersPage() {
  const router = useRouter();
  const [weekStart, setWeekStart] = useState(() => startOfLocalWeek(new Date()));
  const [reminders, setReminders] = useState<CustomerReminder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [blocked, setBlocked] = useState(false);
  const [drawer, setDrawer] = useState<DrawerState>({ mode: 'closed' });
  const [saving, setSaving] = useState(false);
  const listRequestIdRef = useRef(0);

  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)), [weekStart]);
  const from = toLocalDate(days[0]);
  const to = toLocalDate(days[6]);
  const grouped = useMemo(() => {
    const map = new Map<string, CustomerReminder[]>();
    for (const day of days) {
      map.set(toLocalDate(day), []);
    }
    for (const reminder of reminders) {
      map.get(reminder.localDate)?.push(reminder);
    }
    for (const items of map.values()) {
      items.sort((a, b) => a.localTime.localeCompare(b.localTime));
    }
    return map;
  }, [days, reminders]);

  const loadWeek = useCallback(async () => {
    const requestId = listRequestIdRef.current + 1;
    listRequestIdRef.current = requestId;
    setLoading(true);
    setError('');
    setBlocked(false);

    try {
      const res = await listCustomerReminders({ from, to, states: ['active'] });
      if (requestId !== listRequestIdRef.current) {
        return;
      }
      if (!res.ok) {
        if (AUTH_ERRORS.has(res.error)) {
          router.replace('/auth/login?next=/account/reminders');
          return;
        }
        if (res.error === 'conversation_required') {
          setBlocked(true);
          return;
        }
        setError('Unable to load reminders right now.');
        return;
      }
      setReminders(res.data.reminders);
    } catch {
      if (requestId !== listRequestIdRef.current) {
        return;
      }
      setError('Unable to load reminders right now.');
    } finally {
      if (requestId === listRequestIdRef.current) {
        setLoading(false);
      }
    }
  }, [from, router, to]);

  useEffect(() => {
    void loadWeek();
  }, [loadWeek]);

  async function saveReminder(input: CustomerReminderFormInput) {
    setSaving(true);
    setError('');
    setBlocked(false);
    try {
      const res =
        drawer.mode === 'edit'
          ? await updateCustomerReminder(drawer.reminder.id, input)
          : await createCustomerReminder(input);
      if (!res.ok) {
        if (AUTH_ERRORS.has(res.error)) {
          router.replace('/auth/login?next=/account/reminders');
          return;
        }
        if (res.error === 'conversation_required') {
          setBlocked(true);
          return;
        }
        setError(saveReminderErrorMessage(res.error));
        return;
      }
      setDrawer({ mode: 'closed' });
      await loadWeek();
    } catch {
      setError('Unable to save this reminder right now.');
    } finally {
      setSaving(false);
    }
  }

  async function runAction(action: 'complete' | 'cancel', reminderId: string) {
    setError('');
    try {
      const res =
        action === 'complete' ? await completeCustomerReminder(reminderId) : await cancelCustomerReminder(reminderId);
      if (!res.ok) {
        if (AUTH_ERRORS.has(res.error)) {
          router.replace('/auth/login?next=/account/reminders');
          return;
        }
        setError(`Unable to ${action} this reminder right now.`);
        return;
      }
      setDrawer({ mode: 'closed' });
      await loadWeek();
    } catch {
      setError(`Unable to ${action} this reminder right now.`);
    }
  }

  return (
    <section className="customer-view customer-view--wide customer-reminders-page">
      <div className="customer-panel customer-panel--wide customer-reminder-board">
        <div className="customer-reminder-board__head">
          <div className="customer-panel__head">
            <p className="customer-panel__eyebrow">Reminders</p>
            <h1 className="customer-panel__title">Weekly reminder board</h1>
            <p className="customer-panel__body">Manage active reminders for the selected Monday-Sunday week.</p>
          </div>
          <button
            type="button"
            className="customer-action customer-action--primary"
            onClick={() => setDrawer({ mode: 'create', initialDate: toLocalDate(new Date()) })}
          >
            New reminder
          </button>
        </div>

        <div className="customer-reminder-weekbar">
          <button
            type="button"
            className="customer-action customer-action--secondary"
            onClick={() => setWeekStart((current) => addDays(current, -7))}
          >
            Previous
          </button>
          <button
            type="button"
            className="customer-action customer-action--secondary"
            onClick={() => setWeekStart(startOfLocalWeek(new Date()))}
          >
            Today
          </button>
          <strong>{formatWeekRange(weekStart)}</strong>
          <button
            type="button"
            className="customer-action customer-action--secondary"
            onClick={() => setWeekStart((current) => addDays(current, 7))}
          >
            Next
          </button>
        </div>

        {loading ? <p className="customer-inline-note">Loading reminders...</p> : null}
        {blocked ? (
          <div className="customer-inline-note customer-inline-note--warning">
            <h2 className="customer-inline-note__title">Conversation required</h2>
            <p>Start or resume a Kap conversation first, then return here to manage reminders.</p>
            <Link href="/channels/wechat-personal" className="customer-action customer-action--secondary">
              Open WeChat channel
            </Link>
          </div>
        ) : null}
        {error ? <p className="customer-inline-note customer-inline-note--error">{error}</p> : null}

        <div className="customer-reminder-week" aria-label="Selected week reminders">
          {days.map((day) => {
            const localDate = toLocalDate(day);
            const dayReminders = grouped.get(localDate) ?? [];
            return (
              <section key={localDate} className="customer-reminder-day">
                <div className="customer-reminder-day__head">
                  <strong>{day.toLocaleDateString('en-US', { weekday: 'short' })}</strong>
                  <span>{day.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                </div>
                <div className="customer-reminder-day__items">
                  {dayReminders.length === 0 ? (
                    <p className="customer-reminder-empty">No active reminders</p>
                  ) : (
                    dayReminders.map((reminder) => (
                      <article key={reminder.id} className="customer-reminder-card">
                        <button
                          type="button"
                          className="customer-reminder-card__open"
                          onClick={() => setDrawer({ mode: 'edit', reminder })}
                        >
                          <time>{reminder.localTime}</time>
                          <h2>{reminder.title}</h2>
                          <p>{repeatFromRrule(reminder.rrule) === 'none' ? reminder.timezone : repeatFromRrule(reminder.rrule)}</p>
                        </button>
                        <div className="customer-reminder-card__actions">
                          <button
                            type="button"
                            onClick={() => setDrawer({ mode: 'edit', reminder })}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => void runAction('complete', reminder.id)}
                          >
                            Complete
                          </button>
                          <button
                            type="button"
                            onClick={() => void runAction('cancel', reminder.id)}
                          >
                            Cancel
                          </button>
                        </div>
                      </article>
                    ))
                  )}
                </div>
              </section>
            );
          })}
        </div>
      </div>

      {drawer.mode !== 'closed' ? (
        <ReminderForm
          key={drawer.mode === 'edit' ? drawer.reminder.id : drawer.initialDate}
          drawer={drawer}
          saving={saving}
          onClose={() => setDrawer({ mode: 'closed' })}
          onAction={(action, reminderId) => void runAction(action, reminderId)}
          onSubmit={saveReminder}
        />
      ) : null}
    </section>
  );
}
