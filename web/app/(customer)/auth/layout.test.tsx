import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../../components/locale-provider';

const pathnameMock = vi.hoisted(() => vi.fn());

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => pathnameMock(),
}));

import CustomerAuthLayout from './layout';

describe('CustomerAuthLayout', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    pathnameMock.mockReset();
    pathnameMock.mockReturnValue('/auth/login');
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('renders Chinese customer shell copy with the locale switcher', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <CustomerAuthLayout>
            <div>body</div>
          </CustomerAuthLayout>
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('.coke-site')).toBeTruthy();
    expect(container.querySelector('.auth-shell')).toBeTruthy();
    expect(container.querySelector('.auth-hero')).toBeTruthy();
    expect(container.querySelector('.auth-hero__spotlight')).toBeTruthy();
    expect(container.querySelector('.auth-shell__stage')).toBeTruthy();
    expect(container.querySelector('img[alt="Kap koala mascot"]')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/login"][aria-current="page"]')).toBeTruthy();
    expect(container.textContent).toContain('把你的下一步继续推进');
    expect(container.textContent).toContain('账号访问、验证与微信连接');
    expect(container.textContent).toContain('在同一个地方完成下一步');
    expect(container.textContent).toContain('全程加密传输');
    expect(container.textContent).toContain('EN');
    expect(container.textContent).toContain('中文');
    expect(container.textContent).not.toContain('管理 Coke 账单与交付状态');
  });

  it('marks the register CTA active on the register route', () => {
    pathnameMock.mockReturnValue('/auth/register');

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerAuthLayout>
            <div>body</div>
          </CustomerAuthLayout>
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('a[href="/auth/register"][aria-current="page"]')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/login"][aria-current="page"]')).toBeNull();
  });

  it.each([
    '/auth/forgot-password',
    '/auth/reset-password',
    '/auth/verify-email',
    '/auth/claim',
  ])('leaves both auth CTAs inactive on %s', (pathname) => {
    pathnameMock.mockReturnValue(pathname);

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerAuthLayout>
            <div>body</div>
          </CustomerAuthLayout>
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('a[href="/auth/login"][aria-current="page"]')).toBeNull();
    expect(container.querySelector('a[href="/auth/register"][aria-current="page"]')).toBeNull();
  });
});
