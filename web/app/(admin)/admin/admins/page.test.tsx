import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import { LocaleProvider } from '../../../../components/locale-provider';
import { adminApi } from '../../../../lib/admin-api';

vi.mock('../../../../lib/admin-api', () => ({
  adminApi: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import AdminAdminsPage from './page';

describe('AdminAdminsPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  const waitForEffects = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

  beforeEach(() => {
    vi.mocked(adminApi.get).mockReset();
    vi.mocked(adminApi.post).mockReset();
    vi.mocked(adminApi.delete).mockReset();
    vi.mocked(adminApi.get).mockResolvedValue({
      ok: true,
      data: [
        {
          id: 'adm_123',
          email: 'owner@example.com',
          isActive: true,
          createdAt: '2026-04-16T09:00:00.000Z',
          updatedAt: '2026-04-16T10:00:00.000Z',
        },
      ],
    });
    vi.mocked(adminApi.post).mockResolvedValue({
      ok: true,
      data: {
        id: 'adm_456',
        email: 'new-admin@example.com',
        isActive: true,
        createdAt: '2026-04-16T11:00:00.000Z',
        updatedAt: '2026-04-16T11:00:00.000Z',
      },
    });
    vi.mocked(adminApi.delete).mockResolvedValue({
      ok: true,
      data: {
        id: 'adm_456',
      },
    });
    vi.stubGlobal('confirm', vi.fn(() => true));
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
    vi.unstubAllGlobals();
  });

  it('renders an explicit load failure with retry instead of the empty state', async () => {
    vi.mocked(adminApi.get)
      .mockResolvedValueOnce({
        ok: false,
        error: 'network_error',
      })
      .mockResolvedValueOnce({
        ok: true,
        data: [
          {
            id: 'adm_123',
            email: 'owner@example.com',
            isActive: true,
            createdAt: '2026-04-16T09:00:00.000Z',
            updatedAt: '2026-04-16T10:00:00.000Z',
          },
        ],
      });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <AdminAdminsPage />
        </LocaleProvider>,
      );
    });

    await vi.waitFor(() => {
      expect(container.textContent).toContain('Error: network_error');
      expect(container.querySelector('button[data-testid="retry-load"]')).toBeTruthy();
      expect(container.textContent).not.toContain('No records found.');
    });

    (container.querySelector('button[data-testid="retry-load"]') as HTMLButtonElement).click();
    await waitForEffects();

    await vi.waitFor(() => {
      expect(vi.mocked(adminApi.get)).toHaveBeenCalledTimes(2);
      expect(container.textContent).toContain('owner@example.com');
    });
  });


  it('adds and removes admin accounts', async () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <AdminAdminsPage />
        </LocaleProvider>,
      );
    });

    await vi.waitFor(() => {
      expect(vi.mocked(adminApi.get)).toHaveBeenCalledWith('/api/admin/admins');
      expect(container.textContent).toContain('owner@example.com');
    });

    (container.querySelector('button[data-testid="open-add-admin"]') as HTMLButtonElement).click();
    await waitForEffects();

    const emailInput = container.querySelector('#admin-email') as HTMLInputElement;
    const passwordInput = container.querySelector('#admin-password') as HTMLInputElement;
    emailInput.value = 'new-admin@example.com';
    emailInput.dispatchEvent(new Event('input', { bubbles: true }));
    passwordInput.value = 'password123';
    passwordInput.dispatchEvent(new Event('input', { bubbles: true }));

    container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await waitForEffects();

    expect(vi.mocked(adminApi.post)).toHaveBeenCalledWith('/api/admin/admins', {
      email: 'new-admin@example.com',
      password: 'password123',
    });
    expect(container.textContent).toContain('new-admin@example.com');

    (container.querySelector('button[data-admin-id="adm_456"]') as HTMLButtonElement).click();
    await waitForEffects();

    expect(vi.mocked(adminApi.delete)).toHaveBeenCalledWith('/api/admin/admins/adm_456');
    expect(container.textContent).not.toContain('new-admin@example.com');
  });
});
