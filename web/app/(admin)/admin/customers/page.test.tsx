import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import { LocaleProvider } from '../../../../components/locale-provider';
import { adminApi } from '../../../../lib/admin-api';

vi.mock('../../../../lib/admin-api', () => ({
  adminApi: {
    get: vi.fn(),
  },
}));

import AdminCustomersPage from './page';

describe('AdminCustomersPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    vi.mocked(adminApi.get).mockReset();
    vi.mocked(adminApi.get).mockResolvedValue({
      ok: true,
      data: {
        rows: [
          {
            id: 'cust_123',
            displayName: 'Alice',
            contactIdentifier: {
              type: 'email',
              value: 'alice@example.com',
            },
            claimStatus: 'active',
            parkedInboundCount: 2,
            registeredAt: '2026-04-16T09:00:00.000Z',
            firstSeenAt: '2026-04-15T08:00:00.000Z',
            lastMessageAt: '2026-04-17T10:30:00.000Z',
            conversationCount: 1,
            messageCount: 8,
            agent: {
              id: 'agent_coke',
              slug: 'coke',
              name: 'Coke',
              provisionStatus: 'active',
            },
            channelSummary: {
              total: 2,
              connected: 1,
              disconnected: 1,
              kinds: ['telegram', 'whatsapp'],
            },
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      },
    });
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('renders an explicit load failure with retry instead of the empty state', async () => {
    vi.mocked(adminApi.get)
      .mockResolvedValueOnce({
        ok: false,
        error: 'network_error',
      })
      .mockResolvedValueOnce({
        ok: true,
        data: {
          rows: [
            {
              id: 'cust_123',
              displayName: 'Alice',
              contactIdentifier: {
                type: 'email',
                value: 'alice@example.com',
              },
              claimStatus: 'active',
              parkedInboundCount: 2,
              registeredAt: '2026-04-16T09:00:00.000Z',
              firstSeenAt: '2026-04-15T08:00:00.000Z',
              lastMessageAt: '2026-04-17T10:30:00.000Z',
              conversationCount: 1,
              messageCount: 8,
              agent: {
                id: 'agent_coke',
                slug: 'coke',
                name: 'Coke',
                provisionStatus: 'active',
              },
              channelSummary: {
                total: 2,
                connected: 1,
                disconnected: 1,
                kinds: ['telegram', 'whatsapp'],
              },
            },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        },
      });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <AdminCustomersPage />
        </LocaleProvider>,
      );
    });

    await vi.waitFor(() => {
      expect(container.textContent).toContain('Error: network_error');
      expect(container.querySelector('button[data-testid="retry-load"]')).toBeTruthy();
      expect(container.textContent).not.toContain('No records found.');
    });

    (container.querySelector('button[data-testid="retry-load"]') as HTMLButtonElement).click();

    await vi.waitFor(() => {
      expect(vi.mocked(adminApi.get)).toHaveBeenCalledTimes(2);
      expect(container.textContent).toContain('alice@example.com');
    });
  });


  it('renders the required customer columns', async () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <AdminCustomersPage />
        </LocaleProvider>,
      );
    });

    await vi.waitFor(() => {
      expect(vi.mocked(adminApi.get)).toHaveBeenCalledWith('/api/admin/customers?limit=50&offset=0');
      expect(container.textContent).toContain('Customer');
      expect(container.textContent).toContain('Last message');
      expect(container.textContent).toContain('Messages');
      expect(container.textContent).toContain('Contact identifier');
      expect(container.textContent).toContain('Claim status');
      expect(container.textContent).toContain('Parked inbounds');
      expect(container.textContent).toContain('Registered');
      expect(container.textContent).toContain('First seen');
      expect(container.textContent).toContain('Agent');
      expect(container.textContent).toContain('Channels');
      expect(container.textContent).toContain('alice@example.com');
      expect(container.textContent).toContain('2');
      expect(container.textContent).toContain('telegram, whatsapp');
    });
  });
});
