import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../../components/locale-provider';

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import CustomerAccountLayout from './layout';

describe('CustomerAccountLayout', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('renders the neutral customer shell copy around account routes', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <CustomerAccountLayout>
            <div>body</div>
          </CustomerAccountLayout>
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('.coke-site.customer-shell-page')).toBeTruthy();
    expect(container.querySelector('.customer-shell__hero')).toBeTruthy();
    expect(container.querySelector('.customer-shell__spotlight')).toBeTruthy();
    expect(container.querySelector('.customer-shell__workspace')).toBeTruthy();
    expect(container.querySelector('img[alt="Kap koala mascot"]')).toBeTruthy();
    expect(container.querySelector('a[href="/"][aria-label="Kap AI"]')).toBeTruthy();
    expect(container.querySelector('img[alt="Kap koala badge"]')).toBeTruthy();
    expect(container.querySelector('a[href="/account/subscription"]')).toBeTruthy();
    expect(container.querySelector('a[href="/account/friends"]')).toBeTruthy();
    expect(container.querySelector('a[href="/account/reminders"]')).toBeTruthy();
    expect(container.querySelector('a[href="/account/my-agent"]')).toBeTruthy();
    expect(container.textContent).toContain('好友');
    expect(container.textContent).toContain('提醒');
    expect(container.textContent).toContain('我的智能体');
    expect(container.textContent).toContain('把你的下一步继续推进');
    expect(container.textContent).toContain('在同一个地方完成下一步');
    expect(container.textContent).toContain('body');
    expect(container.textContent).not.toContain('管理订阅与 Coke 业务状态');
  });
});
