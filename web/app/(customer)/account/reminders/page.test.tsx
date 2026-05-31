import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../../../components/locale-provider';

const replaceMock = vi.hoisted(() => vi.fn());
const routerMock = vi.hoisted(() => ({
  replace: replaceMock,
}));
const listMock = vi.hoisted(() => vi.fn());
const createMock = vi.hoisted(() => vi.fn());
const updateMock = vi.hoisted(() => vi.fn());
const completeMock = vi.hoisted(() => vi.fn());
const cancelMock = vi.hoisted(() => vi.fn());
const OriginalDateTimeFormat = Intl.DateTimeFormat;

vi.mock('next/navigation', () => ({
  useRouter: () => routerMock,
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock('../../../../lib/customer-reminders', () => ({
  listCustomerReminders: (...args: unknown[]) => listMock(...args),
  createCustomerReminder: (...args: unknown[]) => createMock(...args),
  updateCustomerReminder: (...args: unknown[]) => updateMock(...args),
  completeCustomerReminder: (...args: unknown[]) => completeMock(...args),
  cancelCustomerReminder: (...args: unknown[]) => cancelMock(...args),
  repeatFromRrule: (rrule: string | null | undefined) =>
    rrule === 'FREQ=DAILY' ? 'daily' : rrule === 'FREQ=WEEKLY' ? 'weekly' : 'none',
}));

import RemindersPage from './page';

function makeReminder(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'rem-1',
    title: 'Pay rent',
    lifecycleState: 'active',
    localDate: '2026-05-13',
    localTime: '09:30',
    timezone: 'Asia/Tokyo',
    rrule: null,
    ...overrides,
  };
}

async function flushTicks(count: number) {
  for (let i = 0; i < count; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((innerResolve) => {
    resolve = innerResolve;
  });
  return { promise, resolve };
}

describe('CustomerRemindersPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  function renderPage() {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <RemindersPage />
        </LocaleProvider>,
      );
    });
  }

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-05-13T10:00:00+09:00'));
    replaceMock.mockReset();
    listMock.mockReset();
    createMock.mockReset();
    updateMock.mockReset();
    completeMock.mockReset();
    cancelMock.mockReset();
    listMock.mockResolvedValue({
      ok: true,
      data: {
        reminders: [
          makeReminder({ durationMinutes: 60, localTime: '09:30' }),
          makeReminder({ id: 'rem-2', title: 'Call mom', localDate: '2026-05-15', localTime: '20:00' }),
          makeReminder({ id: 'rem-3', title: 'Early flight', localDate: '2026-05-13', localTime: '05:45' }),
          makeReminder({ id: 'rem-4', title: 'Standup prep', localDate: '2026-05-13', localTime: '09:05' }),
          makeReminder({
            id: 'rem-5',
            title: 'DST local check',
            localDate: '2026-05-14',
            localTime: '06:15',
            timezone: 'America/Los_Angeles',
          }),
        ],
      },
    });
    createMock.mockResolvedValue({ ok: true, data: makeReminder({ id: 'rem-created' }) });
    updateMock.mockResolvedValue({ ok: true, data: makeReminder() });
    completeMock.mockResolvedValue({ ok: true, data: makeReminder({ lifecycleState: 'completed' }) });
    cancelMock.mockResolvedValue({ ok: true, data: makeReminder({ lifecycleState: 'cancelled' }) });
    vi.spyOn(Intl, 'DateTimeFormat').mockImplementation(((...args: Parameters<typeof Intl.DateTimeFormat>) => {
      const formatter = OriginalDateTimeFormat(...args);
      return {
        ...formatter,
        format: formatter.format.bind(formatter),
        formatToParts: formatter.formatToParts.bind(formatter),
        resolvedOptions: () => ({ ...formatter.resolvedOptions(), timeZone: 'Asia/Tokyo' }),
      };
    }) as typeof Intl.DateTimeFormat);
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    root.unmount();
    container.remove();
  });

  it('loads active reminders for the selected Monday-Sunday week and shows a calendar summary', async () => {
    renderPage();
    await flushTicks(3);

    expect(listMock).toHaveBeenCalledWith({
      from: '2026-05-11',
      to: '2026-05-17',
      states: ['active'],
    });
    expect(container.textContent).toContain('Reminder calendar');
    expect(container.textContent).toContain('May 11 - May 17, 2026');
    expect(container.textContent).toContain('5 active this week');
    expect(container.textContent).toContain('4 remaining today');
    expect(container.textContent).toContain('Next: Wed 09:05 - Standup prep');
  });

  it('resets the selected week to the current week from the Today control', async () => {
    renderPage();
    await flushTicks(3);

    const nextButton = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Next');
    expect([...container.querySelectorAll('button')].some((button) => button.textContent === 'Today')).toBe(true);

    nextButton?.click();
    await flushTicks(3);
    expect(listMock).toHaveBeenLastCalledWith({
      from: '2026-05-18',
      to: '2026-05-24',
      states: ['active'],
    });
    expect(container.textContent).toContain('May 18 - May 24, 2026');

    const todayButton = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Today');
    todayButton?.click();
    await flushTicks(3);

    expect(listMock).toHaveBeenLastCalledWith({
      from: '2026-05-11',
      to: '2026-05-17',
      states: ['active'],
    });
    expect(container.textContent).toContain('May 11 - May 17, 2026');
  });

  it('ignores stale reminder list responses after the selected week changes', async () => {
    const firstRequest = createDeferred<Awaited<ReturnType<typeof listMock>>>();
    const secondRequest = createDeferred<Awaited<ReturnType<typeof listMock>>>();
    listMock.mockReset();
    listMock.mockReturnValueOnce(firstRequest.promise);
    listMock.mockReturnValueOnce(secondRequest.promise);

    renderPage();
    await flushTicks(1);

    const nextButton = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Next');
    nextButton?.click();
    await flushTicks(1);

    secondRequest.resolve({
      ok: true,
      data: {
        reminders: [
          makeReminder({
            id: 'rem-next',
            title: 'Next week reminder',
            localDate: '2026-05-20',
          }),
        ],
      },
    });
    await flushTicks(3);
    expect(container.textContent).toContain('Next week reminder');

    firstRequest.resolve({
      ok: true,
      data: {
        reminders: [
          makeReminder({
            id: 'rem-stale',
            title: 'Stale current week reminder',
            localDate: '2026-05-13',
          }),
        ],
      },
    });
    await flushTicks(3);

    expect(container.textContent).toContain('Next week reminder');
    expect(container.textContent).not.toContain('Stale current week reminder');
  });

  it('redirects auth failures to the customer login page with the reminders next path', async () => {
    listMock.mockResolvedValueOnce({ ok: false, error: 'invalid_or_expired_token' });

    renderPage();
    await flushTicks(3);

    expect(replaceMock).toHaveBeenCalledWith('/auth/login?next=/account/reminders');
  });

  it('shows an inline blocked conversation message with a channel link', async () => {
    listMock.mockResolvedValueOnce({ ok: false, error: 'conversation_required' });

    renderPage();
    await flushTicks(3);

    expect(container.textContent).toContain('Conversation required');
    expect(container.textContent).toContain('Start or resume a Kap conversation');
    expect(container.querySelector('a[href="/channels/wechat-personal"]')).toBeTruthy();
  });

  it('creates a reminder from the drawer with the detected default timezone', async () => {
    renderPage();
    await flushTicks(3);

    const newButton = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.includes('New reminder'),
    );
    newButton?.click();
    await flushTicks(1);

    expect((container.querySelector('input[name="timezone"]') as HTMLInputElement | null)?.value).toBe('Asia/Tokyo');
    (container.querySelector('input[name="title"]') as HTMLInputElement).value = 'Water plants';
    (container.querySelector('input[name="title"]') as HTMLInputElement).dispatchEvent(
      new Event('input', { bubbles: true }),
    );
    (container.querySelector('input[name="localDate"]') as HTMLInputElement).value = '2026-05-16';
    (container.querySelector('input[name="localDate"]') as HTMLInputElement).dispatchEvent(
      new Event('input', { bubbles: true }),
    );
    (container.querySelector('input[name="localTime"]') as HTMLInputElement).value = '08:00';
    (container.querySelector('input[name="localTime"]') as HTMLInputElement).dispatchEvent(
      new Event('input', { bubbles: true }),
    );
    (container.querySelector('select[name="repeat"]') as HTMLSelectElement).value = 'daily';
    (container.querySelector('select[name="repeat"]') as HTMLSelectElement).dispatchEvent(
      new Event('change', { bubbles: true }),
    );

    container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await flushTicks(3);

    expect(createMock).toHaveBeenCalledWith({
      title: 'Water plants',
      localDate: '2026-05-16',
      localTime: '08:00',
      timezone: 'Asia/Tokyo',
      repeat: 'daily',
    });
    expect(listMock).toHaveBeenCalledTimes(2);
  });

  it('defaults a new reminder for today to a future time slot', async () => {
    vi.setSystemTime(new Date('2026-05-23T17:03:00+09:00'));
    listMock.mockResolvedValue({
      ok: true,
      data: {
        reminders: [],
      },
    });

    renderPage();
    await flushTicks(3);

    const newButton = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.includes('New reminder'),
    );
    newButton?.click();
    await flushTicks(1);

    expect((container.querySelector('input[name="localDate"]') as HTMLInputElement | null)?.value).toBe('2026-05-23');
    expect((container.querySelector('input[name="localTime"]') as HTMLInputElement | null)?.value).toBe('17:15');
  });

  it('shows a specific message when the selected reminder time is in the past', async () => {
    createMock.mockResolvedValueOnce({ ok: false, error: 'invalid_schedule' });

    renderPage();
    await flushTicks(3);

    const newButton = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.includes('New reminder'),
    );
    newButton?.click();
    await flushTicks(1);

    (container.querySelector('input[name="title"]') as HTMLInputElement).value = 'Past reminder';
    container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await flushTicks(3);

    expect(container.textContent).toContain('Reminder time is in the past. Choose a future time.');
  });

  it('edits, completes, and cancels existing reminders through their action wrappers', async () => {
    renderPage();
    await flushTicks(3);

    const reminderOpenButton = [...container.querySelectorAll('.customer-reminder-card__open')].find((button) =>
      button.textContent?.includes('Pay rent'),
    ) as HTMLButtonElement | undefined;
    reminderOpenButton?.click();
    await flushTicks(1);
    (container.querySelector('input[name="title"]') as HTMLInputElement).value = 'Pay rent updated';
    (container.querySelector('input[name="title"]') as HTMLInputElement).dispatchEvent(
      new Event('input', { bubbles: true }),
    );
    container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await flushTicks(3);

    expect(updateMock).toHaveBeenCalledWith('rem-1', {
      title: 'Pay rent updated',
      localDate: '2026-05-13',
      localTime: '09:30',
      timezone: 'Asia/Tokyo',
      repeat: 'none',
      durationMinutes: 60,
    });

    const completeButton = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Complete');
    completeButton?.click();
    const cancelButton = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Cancel');
    cancelButton?.click();
    await flushTicks(3);

    expect(completeMock).toHaveBeenCalledWith('rem-3');
    expect(cancelMock).toHaveBeenCalledWith('rem-3');
  });

  it('keeps nested lifecycle actions accessible without opening the edit drawer by click or keyboard', async () => {
    renderPage();
    await flushTicks(3);

    const reminderCard = [...container.querySelectorAll('.customer-reminder-card')].find((card) =>
      card.textContent?.includes('Pay rent'),
    ) as HTMLElement | undefined;
    const completeButton = [...(reminderCard?.querySelectorAll('button') ?? [])].find(
      (button) => button.textContent === 'Complete',
    );
    const cancelButton = [...(reminderCard?.querySelectorAll('button') ?? [])].find(
      (button) => button.textContent === 'Cancel',
    );

    completeButton?.click();
    await flushTicks(3);

    expect(completeMock).toHaveBeenCalledWith('rem-1');
    expect(container.querySelector('.customer-reminder-drawer')).toBeNull();

    cancelButton?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await flushTicks(1);
    expect(container.querySelector('.customer-reminder-drawer')).toBeNull();

    cancelButton?.click();
    await flushTicks(3);
    expect(cancelMock).toHaveBeenCalledWith('rem-1');
    expect(container.querySelector('.customer-reminder-drawer')).toBeNull();
  });

  it('shows a retryable inline error when lifecycle action requests reject', async () => {
    completeMock.mockRejectedValueOnce(new Error('network down'));

    renderPage();
    await flushTicks(3);

    const completeButton = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Complete');
    completeButton?.click();
    await flushTicks(3);

    expect(completeMock).toHaveBeenCalledWith('rem-3');
    expect(container.textContent).toContain('Unable to complete this reminder right now.');
  });

  it('shows complete and cancel actions inside the edit drawer', async () => {
    renderPage();
    await flushTicks(3);

    const editButton = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Edit');
    editButton?.click();
    await flushTicks(1);

    const drawer = container.querySelector('.customer-reminder-drawer') as HTMLElement | null;
    expect(drawer?.textContent).toContain('Complete');
    expect(drawer?.textContent).toContain('Cancel');

    const drawerCompleteButton = [...(drawer?.querySelectorAll('button') ?? [])].find(
      (button) => button.textContent === 'Complete',
    );
    drawerCompleteButton?.click();
    await flushTicks(3);
    expect(completeMock).toHaveBeenCalledWith('rem-3');

    editButton?.click();
    await flushTicks(1);
    const reopenedDrawer = container.querySelector('.customer-reminder-drawer') as HTMLElement | null;
    const drawerCancelButton = [...(reopenedDrawer?.querySelectorAll('button') ?? [])].find(
      (button) => button.textContent === 'Cancel',
    );
    drawerCancelButton?.click();
    await flushTicks(3);
    expect(cancelMock).toHaveBeenCalledWith('rem-3');
  });
});
