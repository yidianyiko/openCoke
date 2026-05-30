import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ComponentProps, ReactNode } from 'react';
import { LocaleProvider } from '../../../components/locale-provider';

const replaceMock = vi.hoisted(() => vi.fn());
const pushMock = vi.hoisted(() => vi.fn());
const isAdminAuthenticatedMock = vi.hoisted(() => vi.fn());
const getStoredAdminSessionMock = vi.hoisted(() => vi.fn());
const clearAdminSessionMock = vi.hoisted(() => vi.fn());
const pathnameMock = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: replaceMock,
    push: pushMock,
  }),
  usePathname: () => pathnameMock(),
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock('next/image', () => ({
  default: ({ src, className }: ComponentProps<'img'>) => (
    <span data-next-image={typeof src === 'string' ? src : ''} className={className} />
  ),
}));

vi.mock('../../../lib/admin-auth', () => ({
  ADMIN_SESSION_CLEARED_EVENT: 'coke:admin-session-cleared',
  isAdminAuthenticated: () => isAdminAuthenticatedMock(),
  getStoredAdminSession: () => getStoredAdminSessionMock(),
  clearAdminSession: () => clearAdminSessionMock(),
  storeAdminSession: vi.fn(),
}));

vi.mock('../../../lib/admin-api', () => ({
  adminApi: {
    post: vi.fn(),
  },
}));

import AdminLayout from './layout';
import AdminLoginPage from './login/page';

describe('AdminLayout', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    replaceMock.mockReset();
    pushMock.mockReset();
    isAdminAuthenticatedMock.mockReset();
    getStoredAdminSessionMock.mockReset();
    clearAdminSessionMock.mockReset();
    pathnameMock.mockReset();
    pathnameMock.mockReturnValue('/admin/customers');
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('allows logged-out admins to reach the login page when the route composes through the admin layout', async () => {
    isAdminAuthenticatedMock.mockReturnValue(false);
    pathnameMock.mockReturnValue('/admin/login');

    await flushSync(async () => {
      root.render(
        <LocaleProvider initialLocale="en">
          <AdminLayout>
            <AdminLoginPage />
          </AdminLayout>
        </LocaleProvider>,
      );
    });

    expect(replaceMock).not.toHaveBeenCalled();
    expect(container.querySelector('form')).toBeTruthy();
    expect(container.textContent).toContain('Admin sign in');
  });

  it('redirects unauthenticated admins to /admin/login', async () => {
    isAdminAuthenticatedMock.mockReturnValue(false);

    await flushSync(async () => {
      root.render(
        <LocaleProvider initialLocale="en">
          <AdminLayout>
            <div>admin body</div>
          </AdminLayout>
        </LocaleProvider>,
      );
    });

    expect(replaceMock).toHaveBeenCalledWith('/admin/login');
  });

  it('redirects authenticated admins after the session is invalidated post-mount', async () => {
    isAdminAuthenticatedMock.mockReturnValue(true);
    getStoredAdminSessionMock.mockReturnValue({
      adminId: 'adm_123',
      email: 'admin@example.com',
      isActive: true,
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <AdminLayout>
            <div>admin body</div>
          </AdminLayout>
        </LocaleProvider>,
      );
    });

    expect(container.textContent).toContain('Dashboard');
    expect(container.textContent).toContain('Chat records');
    expect(container.textContent).toContain('Shared channels');
    expect(container.textContent).toContain('Deliveries');
    expect(container.textContent).not.toContain('Channels');
    expect(container.textContent).not.toContain('Agents');
    expect(replaceMock).not.toHaveBeenCalled();

    window.dispatchEvent(new Event('coke:admin-session-cleared'));

    await vi.waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith('/admin/login');
    });
  });
});
