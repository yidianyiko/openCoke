import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';

import { LocaleProvider } from './locale-provider';

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { CokePublicShell } from './coke-public-shell';

describe('CokePublicShell', () => {
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

  it('renders the English shell contract without mixed locale labels', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CokePublicShell activeAuthCta="signIn">
            <div>shell body</div>
          </CokePublicShell>
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('.coke-site')).toBeTruthy();
    expect(container.querySelector('a[href="/"][aria-label="Kap AI"]')).toBeTruthy();
    expect(container.querySelector('img[alt="Kap koala badge"]')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/login"][aria-current="page"]')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/login"]')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/register"]')).toBeTruthy();
    expect(container.querySelector('a[href="/login"]')).toBeFalsy();
    expect(container.querySelector('a[href="/coke/login"]')).toBeFalsy();
    expect(container.querySelector('a[href="/api/coke/auth/login"]')).toBeFalsy();
    expect(container.textContent).toContain('Capabilities');
    expect(container.textContent).toContain('Scenarios');
    expect(container.textContent).toContain('Demos');
    expect(container.textContent).toContain('Proof');
    expect(container.textContent).toContain('Start');
    expect(container.textContent).toContain('Sign in');
    expect(container.textContent).toContain('Register');
    expect(container.textContent?.toLowerCase()).toContain('kap');
    expect(container.textContent?.toLowerCase()).not.toContain('coke');
    expect(container.textContent).toContain('EN');
    expect(container.textContent).toContain('中');
    expect(container.textContent).not.toContain('Register / 注册');
    expect(container.textContent).not.toContain('Platforms / 平台');
  });

  it('renders the Chinese shell contract without mixed locale labels', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <CokePublicShell>
            <div>shell body</div>
          </CokePublicShell>
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('.coke-site')).toBeTruthy();
    expect(container.querySelector('a[href="/"][aria-label="Kap AI"]')).toBeTruthy();
    expect(container.querySelector('img[alt="Kap koala badge"]')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/login"]')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/register"]')).toBeTruthy();
    expect(container.querySelector('a[href="/login"]')).toBeFalsy();
    expect(container.querySelector('a[href="/coke/login"]')).toBeFalsy();
    expect(container.querySelector('a[href="/api/coke/auth/login"]')).toBeFalsy();
    expect(container.textContent).toContain('能力');
    expect(container.textContent).toContain('场景');
    expect(container.textContent).toContain('示例');
    expect(container.textContent).toContain('口碑');
    expect(container.textContent).toContain('开始');
    expect(container.textContent).toContain('登录');
    expect(container.textContent).toContain('注册');
    expect(container.textContent?.toLowerCase()).toContain('kap');
    expect(container.textContent?.toLowerCase()).not.toContain('coke');
    expect(container.textContent).toContain('EN');
    expect(container.textContent).toContain('中');
    expect(container.textContent).not.toContain('Register / 注册');
    expect(container.textContent).not.toContain('Platforms / 平台');
  });
});
