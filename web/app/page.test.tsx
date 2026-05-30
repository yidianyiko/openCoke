import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';

import { LocaleProvider } from '../components/locale-provider';

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import HomePage from './page';

describe('HomePage', () => {
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

  it('renders English homepage copy under LocaleProvider', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <HomePage />
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('a[href="/auth/register"]')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/login"]')).toBeTruthy();
    expect(container.querySelector('#capabilities')).toBeTruthy();
    expect(container.querySelector('#scenarios')).toBeTruthy();
    expect(container.querySelector('#demos')).toBeTruthy();
    expect(container.querySelector('#start-path')).toBeTruthy();
    expect(container.querySelector('#download')).toBeTruthy();
    expect(container.textContent).toContain('An AI Supervisor That Follows Up Until It Is Done');
    expect(container.textContent).toContain('Kap AI');
    expect(container.textContent).toContain('Capabilities');
    expect(container.textContent).toContain('See the supervision loop in real conversations');
    expect(container.textContent).toContain('Choose the fastest way to start');
    expect(container.textContent).not.toContain('Coke AI');
    expect(container.textContent).not.toContain('Register / 注册');
  });

  it('renders Chinese homepage copy under LocaleProvider', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <HomePage />
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('a[href="/auth/register"]')).toBeTruthy();
    expect(container.querySelector('a[href="/auth/login"]')).toBeTruthy();
    expect(container.querySelector('#capabilities')).toBeTruthy();
    expect(container.querySelector('#scenarios')).toBeTruthy();
    expect(container.querySelector('#demos')).toBeTruthy();
    expect(container.querySelector('#start-path')).toBeTruthy();
    expect(container.querySelector('#download')).toBeTruthy();
    expect(container.textContent).toContain('会主动跟进的 AI 监督者');
    expect(container.textContent).toContain('Kap AI');
    expect(container.textContent).toContain('能力');
    expect(container.textContent).toContain('用真实对话看清监督闭环');
    expect(container.textContent).toContain('选择最快的开始方式');
    expect(container.textContent).not.toContain('Coke AI');
    expect(container.textContent).not.toContain('Register / 注册');
  });
});
