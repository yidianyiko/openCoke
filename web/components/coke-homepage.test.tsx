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

import { CokeHomepage } from './coke-homepage';

describe('CokeHomepage', () => {
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

  it('renders all editorial sections in English', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CokeHomepage />
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('.coke-site')).toBeTruthy();
    expect(container.querySelector('a[href="/"][aria-label="Kap AI"]')).toBeTruthy();
    expect(container.querySelector('img[alt="Kap koala badge"]')).toBeTruthy();
    expect(container.querySelector('#capabilities')).toBeTruthy();
    expect(container.querySelector('#scenarios')).toBeTruthy();
    expect(container.querySelector('#demos')).toBeTruthy();
    expect(container.querySelector('#start-path')).toBeTruthy();
    expect(container.querySelector('#voices')).toBeTruthy();
    expect(container.querySelector('#download')).toBeTruthy();
    expect(container.querySelector('.ticker')).toBeTruthy();
    expect(container.querySelector('.hero__title em')).toBeTruthy();
    expect(container.querySelector('.hero-mascot-figure')).toBeTruthy();
    expect(container.querySelector('img[alt="Kap koala mascot"]')).toBeTruthy();
    expect(container.textContent).toContain('Kap AI');
    expect(container.textContent).toContain('© 2026 Kap AI');
    expect(container.textContent).toContain('Personal WeChat');
    expect(container.textContent).toContain('WhatsApp');
    expect(container.textContent).toContain('Google Calendar');
    expect(container.textContent).toContain('An AI supervisor');
    expect(container.textContent).toContain('Turn goals into reminders, check-ins, and follow-up.');
    expect(container.textContent).toContain('Import Google Calendar into Kap reminders.');
    expect(container.textContent).toContain('See the supervision loop in real conversations');
    expect(container.textContent).toContain('Finish one IELTS practice set');
    expect(container.textContent).toContain('Pay the credit card bill');
    expect(container.querySelector('a[href="/demos"]')).toBeTruthy();
    expect(container.textContent).toContain('Choose the fastest way to start');
    expect(container.textContent).toContain('Domestic users');
    expect(container.textContent).toContain('Global users');
    expect(container.querySelector('a[href="/global"]')).toBeTruthy();
    expect(container.querySelector('a[href="/faqs"]')).toBeTruthy();
    expect(container.querySelector('a[href="/terms"]')).toBeTruthy();
    expect(container.querySelector('a[href="/privacy"]')).toBeTruthy();
    expect(container.querySelector('footer a[href="#"]')).toBeFalsy();
    expect(container.textContent).not.toContain('6+');
    expect(container.textContent).not.toContain('99.9%');
    expect(container.textContent).not.toContain('<100ms');
    expect(container.textContent).not.toContain('Turn the loose thought into a sendable message.');
    expect(container.textContent).not.toContain('Not just a new coat of paint');
    expect(container.textContent).not.toContain('one public experience that feels coherent');
    expect(container.querySelector('a[href="/channels/wechat-personal"]')).toBeTruthy();
    expect(container.querySelector('a[href="/account/subscription"]')).toBeTruthy();
    expect(container.querySelector('a[href="/login"]')).toBeFalsy();
    expect(container.querySelector('a[href="/coke/login"]')).toBeFalsy();
    expect(container.querySelector('a[href="/api/coke/auth/login"]')).toBeFalsy();
  });

  it('renders Chinese hero copy', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <CokeHomepage />
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('a[href="/"][aria-label="Kap AI"]')).toBeTruthy();
    expect(container.querySelector('img[alt="Kap koala badge"]')).toBeTruthy();
    expect(container.querySelector('img[alt="Kap koala mascot"]')).toBeTruthy();
    expect(container.textContent).toContain('AI 监督者');
    expect(container.textContent).toContain('会主动跟进');
    expect(container.textContent).toContain('Kap AI');
    expect(container.textContent).toContain('© 2026 Kap AI');
    expect(container.textContent).toContain('把目标变成提醒、检查和后续跟进。');
    expect(container.textContent).toContain('把 Google Calendar 导入成 Kap 提醒。');
    expect(container.textContent).toContain('用真实对话看清监督闭环');
    expect(container.textContent).toContain('做完一套雅思练习');
    expect(container.textContent).toContain('选择最快的开始方式');
    expect(container.textContent).toContain('国内用户');
    expect(container.textContent).toContain('海外用户');
    expect(container.textContent).not.toContain('六个平台');
    expect(container.textContent).not.toContain('99.9%');
    expect(container.textContent).not.toContain('<100ms');
    expect(container.textContent).not.toContain('把要发出去的那条消息先起草出来。');
    expect(container.textContent).not.toContain('不是只把页面换个颜色');
    expect(container.textContent).not.toContain('这轮改版把主页、认证、客户页面和全球入口统一成同一种产品语言');
    expect(container.textContent).not.toContain('让公开站点更像产品');
  });
});
