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
const VISIBLE_START_HOUR = 6;
const VISIBLE_END_HOUR = 22;
const MAX_OUTSIDE_HOURS_ITEMS = 3;

interface WeekSummary {
  total: number;
  remainingToday: number;
  nextReminder: CustomerReminder | null;
}

interface DayReminderBuckets {
  outside: CustomerReminder[];
  byHour: Map<number, CustomerReminder[]>;
}

type DrawerState =
  | { mode: 'closed' }
  | { mode: 'create'; initialDate: string; initialTime?: string }
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

function buildHourSlots(startHour: number, endHourInclusive: number): number[] {
  return Array.from({ length: endHourInclusive - startHour + 1 }, (_, index) => startHour + index);
}

function formatHour(hour: number): string {
  return `${String(hour).padStart(2, '0')}:00`;
}

function reminderHour(reminder: CustomerReminder): number {
  return Number(reminder.localTime.slice(0, 2));
}

function compareReminders(a: CustomerReminder, b: CustomerReminder): number {
  return a.localTime.localeCompare(b.localTime) || a.title.localeCompare(b.title) || a.id.localeCompare(b.id);
}

function isOutsideVisibleHours(
  reminder: CustomerReminder,
  startHour: number,
  endHourInclusive: number,
): boolean {
  const hour = reminderHour(reminder);
  return Number.isNaN(hour) || hour < startHour || hour > endHourInclusive;
}

function buildDayBuckets(
  reminders: CustomerReminder[],
  startHour: number,
  endHourInclusive: number,
): DayReminderBuckets {
  const byHour = new Map<number, CustomerReminder[]>();
  for (const hour of buildHourSlots(startHour, endHourInclusive)) {
    byHour.set(hour, []);
  }
  const outside: CustomerReminder[] = [];

  for (const reminder of [...reminders].sort(compareReminders)) {
    if (isOutsideVisibleHours(reminder, startHour, endHourInclusive)) {
      outside.push(reminder);
      continue;
    }
    byHour.get(reminderHour(reminder))?.push(reminder);
  }

  return { outside, byHour };
}

function nowLocalTime(now: Date): string {
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
}

function summarizeWeek(reminders: CustomerReminder[], now: Date): WeekSummary {
  const today = toLocalDate(now);
  const currentTime = nowLocalTime(now);
  const upcoming = [...reminders]
    .filter((reminder) => reminder.localDate > today || (reminder.localDate === today && reminder.localTime >= currentTime))
    .sort((a, b) => a.localDate.localeCompare(b.localDate) || compareReminders(a, b));

  return {
    total: reminders.length,
    remainingToday: reminders.filter((reminder) => reminder.localDate === today && reminder.localTime >= currentTime).length,
    nextReminder: upcoming[0] ?? null,
  };
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

function emptyForm(localDate: string, localTime?: string): CustomerReminderFormInput {
  const today = toLocalDate(new Date());
  const defaultSlot = localTime
    ? { localDate, localTime }
    : localDate <= today
      ? nextFutureTimeSlot()
      : { localDate, localTime: '09:00' };
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
  const form = drawer.mode === 'edit' ? formFromReminder(drawer.reminder) : emptyForm(drawer.initialDate, drawer.initialTime);

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
                Delete
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

function ReminderCalendarItem({
  reminder,
  onEdit,
  onAction,
}: {
  reminder: CustomerReminder;
  onEdit: () => void;
  onAction: (action: 'complete' | 'cancel', reminderId: string) => void;
}) {
  const repeat = repeatFromRrule(reminder.rrule);
  const meta = repeat === 'none' ? reminder.timezone : repeat;
  return (
    <article className="customer-reminder-card">
      <button type="button" className="customer-reminder-card__open" onClick={onEdit}>
        <time>{reminder.localTime}</time>
        <h2>{reminder.title}</h2>
        <p>{meta}</p>
      </button>
      <div className="customer-reminder-card__actions">
        <button type="button" onClick={onEdit}>
          Edit
        </button>
        <button type="button" onClick={() => void onAction('complete', reminder.id)}>
          Complete
        </button>
        <button type="button" onClick={() => void onAction('cancel', reminder.id)}>
          Delete
        </button>
      </div>
    </article>
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
  const selectedWeekReminders = useMemo(() => Array.from(grouped.values()).flat(), [grouped]);
  const summary = useMemo(() => summarizeWeek(selectedWeekReminders, new Date()), [selectedWeekReminders]);
  const hourSlots = useMemo(() => buildHourSlots(VISIBLE_START_HOUR, VISIBLE_END_HOUR), []);
  const bucketsByDate = useMemo(() => {
    const map = new Map<string, DayReminderBuckets>();
    for (const day of days) {
      const localDate = toLocalDate(day);
      map.set(localDate, buildDayBuckets(grouped.get(localDate) ?? [], VISIBLE_START_HOUR, VISIBLE_END_HOUR));
    }
    return map;
  }, [days, grouped]);

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
    const actionLabel = action === 'cancel' ? 'delete' : action;
    try {
      const res =
        action === 'complete' ? await completeCustomerReminder(reminderId) : await cancelCustomerReminder(reminderId);
      if (!res.ok) {
        if (AUTH_ERRORS.has(res.error)) {
          router.replace('/auth/login?next=/account/reminders');
          return;
        }
        setError(`Unable to ${actionLabel} this reminder right now.`);
        return;
      }
      setDrawer({ mode: 'closed' });
      await loadWeek();
    } catch {
      setError(`Unable to ${actionLabel} this reminder right now.`);
    }
  }

  return (
    <section className="customer-view customer-view--wide customer-reminders-page">
      <div className="customer-panel customer-panel--wide customer-reminder-board">
        <div className="customer-reminder-board__head">
          <div className="customer-panel__head">
            <p className="customer-panel__eyebrow">Reminders</p>
            <h1 className="customer-panel__title">Reminder calendar</h1>
            <p className="customer-panel__body">
              Plan active reminders by day and time for the selected Monday-Sunday week.
            </p>
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

        <div className="customer-reminder-summary" aria-label="Selected week reminder summary">
          <span>
            <strong>{summary.total}</strong>
            {summary.total === 1 ? ' active this week' : ' active this week'}
          </span>
          <span>
            <strong>{summary.remainingToday}</strong>
            {summary.remainingToday === 1 ? ' remaining today' : ' remaining today'}
          </span>
          <span>
            {summary.nextReminder ? (
              <>
                Next:{' '}
                {new Date(`${summary.nextReminder.localDate}T00:00:00`).toLocaleDateString('en-US', {
                  weekday: 'short',
                })}{' '}
                {summary.nextReminder.localTime} - {summary.nextReminder.title}
              </>
            ) : (
              'No upcoming reminders this week'
            )}
          </span>
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

        <div className="customer-reminder-timeline" aria-label="Selected week reminder timeline">
          <div className="customer-reminder-time-gutter" aria-hidden="true">
            <div className="customer-reminder-time-gutter__spacer" />
            {hourSlots.map((hour) => (
              <span key={hour}>{formatHour(hour)}</span>
            ))}
          </div>
          <div className="customer-reminder-days">
            {days.map((day) => {
              const localDate = toLocalDate(day);
              const dayBuckets = bucketsByDate.get(localDate) ?? buildDayBuckets([], VISIBLE_START_HOUR, VISIBLE_END_HOUR);
              const isToday = localDate === toLocalDate(new Date());
              return (
                <section key={localDate} className="customer-reminder-day" data-today={isToday ? 'true' : undefined}>
                  <div className="customer-reminder-day__head">
                    <strong>{day.toLocaleDateString('en-US', { weekday: 'short' })}</strong>
                    <span>{day.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                  </div>
                  {dayBuckets.outside.length > 0 ? (
                    <div className="customer-reminder-outside" data-testid={`outside-${localDate}`}>
                      <span className="customer-reminder-outside__label">Outside visible hours</span>
                      {dayBuckets.outside.slice(0, MAX_OUTSIDE_HOURS_ITEMS).map((reminder) => (
                        <ReminderCalendarItem
                          key={reminder.id}
                          reminder={reminder}
                          onEdit={() => setDrawer({ mode: 'edit', reminder })}
                          onAction={runAction}
                        />
                      ))}
                      {dayBuckets.outside.length > MAX_OUTSIDE_HOURS_ITEMS ? (
                        <p className="customer-reminder-outside__more">
                          +{dayBuckets.outside.length - MAX_OUTSIDE_HOURS_ITEMS} more outside visible hours
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                  <div className="customer-reminder-day__hours">
                    {hourSlots.map((hour) => {
                      const slotReminders = dayBuckets.byHour.get(hour) ?? [];
                      return (
                        <div
                          key={hour}
                          className="customer-reminder-hour"
                          data-testid={`slot-${localDate}-${String(hour).padStart(2, '0')}`}
                        >
                          <button
                            type="button"
                            className="customer-reminder-slot-button"
                            data-testid={`slot-button-${localDate}-${String(hour).padStart(2, '0')}`}
                            aria-label={`Create reminder on ${localDate} at ${formatHour(hour)}`}
                            onClick={() =>
                              setDrawer({ mode: 'create', initialDate: localDate, initialTime: formatHour(hour) })
                            }
                          />
                          <div className="customer-reminder-hour__items">
                            {slotReminders.map((reminder) => (
                              <ReminderCalendarItem
                                key={reminder.id}
                                reminder={reminder}
                                onEdit={() => setDrawer({ mode: 'edit', reminder })}
                                onAction={runAction}
                              />
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      </div>

      {drawer.mode !== 'closed' ? (
        <ReminderForm
          key={drawer.mode === 'edit' ? drawer.reminder.id : `${drawer.initialDate}-${drawer.initialTime ?? 'default'}`}
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
