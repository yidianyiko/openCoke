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

import CustomerChannelsPage from './page';

describe('CustomerChannelsPage', () => {
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

  it('renders English channel index copy from the locale catalog', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CustomerChannelsPage />
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('.customer-view')).toBeTruthy();
    expect(container.querySelector('.customer-panel')).toBeTruthy();
    expect(container.textContent).toContain('Phase 1 channels');
    expect(container.textContent).toContain('Customer channels');
    expect(container.textContent).toContain('Personal WeChat');
    expect(container.querySelector('a[href="/channels/wechat-personal"].customer-link-card')).toBeTruthy();
  });

  it('renders Chinese channel index copy from the locale catalog', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <CustomerChannelsPage />
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('.customer-view')).toBeTruthy();
    expect(container.textContent).toContain('第一阶段通道');
    expect(container.textContent).toContain('客户通道');
    expect(container.textContent).toContain('个人微信');
    expect(container.textContent).not.toContain('Phase 1 channels');
  });
});
