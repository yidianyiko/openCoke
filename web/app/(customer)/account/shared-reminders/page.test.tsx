import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';

const listCustomerSharedRemindersMock = vi.hoisted(() => vi.fn());
const cancelCustomerSharedReminderMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../lib/customer-shared-reminders', () => ({
  listCustomerSharedReminders: () => listCustomerSharedRemindersMock(),
  cancelCustomerSharedReminder: (id: string) => cancelCustomerSharedReminderMock(id),
}));

import CustomerSharedRemindersPage from './page';

describe('CustomerSharedRemindersPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    root.unmount();
    container.remove();
    vi.clearAllMocks();
  });

  it('renders shared reminders and cancels through the shared-reminder API wrapper', async () => {
    listCustomerSharedRemindersMock.mockResolvedValue({
      ok: true,
      data: {
        sharedReminders: [
          {
            id: 'sr_1',
            title: 'Coffee with Bob',
            triggerTime: '2026-06-01T10:00:00.000Z',
            timezone: 'Asia/Tokyo',
            durationMinutes: 30,
            status: 'active',
            participants: ['Alice', 'Bob'],
          },
        ],
      },
    });
    cancelCustomerSharedReminderMock.mockResolvedValue({
      ok: true,
      data: { id: 'sr_1', status: 'cancelled' },
    });
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    flushSync(() => {
      root.render(<CustomerSharedRemindersPage />);
    });

    await vi.waitFor(() => {
      expect(container.textContent).toContain('Shared reminders');
      expect(container.textContent).toContain('Coffee with Bob');
      expect(container.textContent).toContain('Alice, Bob');
    });

    (container.querySelector('button[data-testid="cancel-shared-reminder"]') as HTMLButtonElement).click();

    await vi.waitFor(() => {
      expect(cancelCustomerSharedReminderMock).toHaveBeenCalledWith('sr_1');
    });
  });
});
