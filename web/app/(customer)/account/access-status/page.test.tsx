import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';

const getCustomerProfileMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../lib/customer-auth', () => ({
  getCustomerProfile: () => getCustomerProfileMock(),
}));

import CustomerAccessStatusPage from './page';

describe('CustomerAccessStatusPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    root.unmount();
    container.remove();
    vi.clearAllMocks();
  });

  it('renders email verification, subscription, and suspension access facts', async () => {
    getCustomerProfileMock.mockResolvedValue({
      ok: true,
      data: {
        email_verified: false,
        subscription_active: false,
        subscription_expires_at: null,
        status: 'normal',
      },
    });
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    flushSync(() => {
      root.render(<CustomerAccessStatusPage />);
    });

    await vi.waitFor(() => {
      expect(container.textContent).toContain('Access status');
      expect(container.textContent).toContain('Email verification required');
      expect(container.textContent).toContain('Subscription inactive');
      expect(container.textContent).toContain('Account active');
    });
  });
});
