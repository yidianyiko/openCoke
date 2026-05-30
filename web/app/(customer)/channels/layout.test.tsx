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

import CustomerChannelsLayout from './layout';

describe('CustomerChannelsLayout', () => {
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

  it('renders the shared customer shell with locale controls for channel routes', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <CustomerChannelsLayout>
            <div>body</div>
          </CustomerChannelsLayout>
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('.coke-site.customer-shell-page')).toBeTruthy();
    expect(container.querySelector('.customer-shell__nav')).toBeTruthy();
    expect(container.querySelector('.customer-shell__spotlight')).toBeTruthy();
    expect(container.querySelector('.customer-shell__workspace')).toBeTruthy();
    expect(container.querySelector('img[alt="Kap koala mascot"]')).toBeTruthy();
    expect(container.querySelector('a[href="/channels"]')).toBeTruthy();
    expect(container.querySelector('a[href="/account/subscription"]')).toBeTruthy();
    expect(container.textContent).toContain('把你的下一步继续推进');
    expect(container.textContent).toContain('账号访问、验证与微信连接');
    expect(container.textContent).toContain('在同一个地方完成下一步');
    expect(container.textContent).toContain('EN');
    expect(container.textContent).toContain('中文');
  });
});
