import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ComponentProps, ReactNode } from 'react';
import { LocaleProvider } from '../../../../components/locale-provider';
import { adminApi } from '../../../../lib/admin-api';

const pushMock = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: pushMock,
  }),
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

vi.mock('../../../../lib/admin-api', () => ({
  adminApi: {
    post: vi.fn(),
  },
}));

vi.mock('../../../../lib/admin-auth', () => ({
  storeAdminSession: vi.fn(),
}));

import { storeAdminSession } from '../../../../lib/admin-auth';
import AdminLoginPage from './page';

describe('AdminLoginPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  const waitForEffects = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

  beforeEach(() => {
    pushMock.mockReset();
    vi.mocked(adminApi.post).mockReset();
    vi.mocked(storeAdminSession).mockReset();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('submits admin credentials, stores the session, and routes into /admin/customers', async () => {
    vi.mocked(adminApi.post).mockResolvedValue({
      ok: true,
      data: {
        adminId: 'adm_123',
        email: 'admin@example.com',
        isActive: true,
        token: 'admin-token',
      },
    });

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <AdminLoginPage />
        </LocaleProvider>,
      );
    });

    const emailInput = container.querySelector('#email') as HTMLInputElement;
    const passwordInput = container.querySelector('#password') as HTMLInputElement;
    emailInput.value = 'admin@example.com';
    emailInput.dispatchEvent(new Event('input', { bubbles: true }));
    passwordInput.value = 'password123';
    passwordInput.dispatchEvent(new Event('input', { bubbles: true }));

    container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await waitForEffects();

    expect(vi.mocked(adminApi.post)).toHaveBeenCalledWith('/api/admin/login', {
      email: 'admin@example.com',
      password: 'password123',
    });
    expect(vi.mocked(storeAdminSession)).toHaveBeenCalledWith({
      adminId: 'adm_123',
      email: 'admin@example.com',
      isActive: true,
      token: 'admin-token',
    });
    expect(pushMock).toHaveBeenCalledWith('/admin/customers');
  });
});
