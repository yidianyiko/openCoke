import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';

import { LocaleProvider, useLocale } from './locale-provider';

function Probe() {
  const { locale, setLocale, messages } = useLocale();

  return (
    <div>
      <p data-testid="locale">{locale}</p>
      <p data-testid="label">{messages.common.languageLabel}</p>
      <button type="button" onClick={() => setLocale('zh')}>
        switch
      </button>
    </div>
  );
}

async function flushEffects() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe('LocaleProvider', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    document.cookie = 'coke-locale=; path=/; Max-Age=0';
    document.documentElement.lang = 'en';
    delete document.documentElement.dataset.localeReady;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
    document.getElementById('locale-splash')?.remove();
    delete document.documentElement.dataset.localeReady;
  });

  it('seeds the provided locale and exposes matching messages', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <Probe />
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('[data-testid="locale"]')?.textContent).toBe('zh');
    expect(container.querySelector('[data-testid="label"]')?.textContent).toBe('语言');
  });

  it('keeps the server locale for the first render, then reconciles persisted client locale', async () => {
    localStorage.setItem('coke-locale', 'zh');
    const splash = document.createElement('div');
    splash.id = 'locale-splash';
    document.body.appendChild(splash);

    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en" reconcileClientLocale>
          <Probe />
        </LocaleProvider>,
      );
    });

    expect(container.querySelector('[data-testid="locale"]')?.textContent).toBe('en');

    await flushEffects();

    expect(container.querySelector('[data-testid="locale"]')?.textContent).toBe('zh');
    expect(document.documentElement.lang).toBe('zh');
    expect(document.getElementById('locale-splash')).toBe(splash);
    expect(document.documentElement.dataset.localeReady).toBe('true');
  });

  it('ignores corrupted persisted locales and falls back to the browser language', async () => {
    const navigatorPrototype = Object.getPrototypeOf(window.navigator);
    const originalLanguage = Object.getOwnPropertyDescriptor(navigatorPrototype, 'language');

    localStorage.setItem('coke-locale', 'broken');
    Object.defineProperty(navigatorPrototype, 'language', {
      configurable: true,
      get: () => 'zh-CN',
    });

    try {
      flushSync(() => {
        root.render(
          <LocaleProvider>
            <Probe />
          </LocaleProvider>,
        );
      });

      await flushEffects();

      expect(container.querySelector('[data-testid="locale"]')?.textContent).toBe('zh');
      expect(localStorage.getItem('coke-locale')).toBe('zh');
      expect(document.cookie).toContain('coke-locale=zh');
    } finally {
      localStorage.removeItem('coke-locale');
      if (originalLanguage) {
        Object.defineProperty(navigatorPrototype, 'language', originalLanguage);
      }
    }
  });

  it('continues switching when storage writes fail', () => {
    const originalSetItem = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new Error('blocked');
    };

    try {
      flushSync(() => {
        root.render(
          <LocaleProvider initialLocale="en">
            <Probe />
          </LocaleProvider>,
        );
      });

      flushSync(() => {
        container.querySelector('button')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      });

      expect(container.querySelector('[data-testid="locale"]')?.textContent).toBe('zh');
      expect(document.documentElement.lang).toBe('zh');
      expect(document.cookie).toContain('coke-locale=zh');
    } finally {
      Storage.prototype.setItem = originalSetItem;
    }
  });

  it('updates locale state, storage, cookie, and <html lang> when switched', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <Probe />
        </LocaleProvider>,
      );
    });

    expect(document.documentElement.lang).toBe('en');
    expect(localStorage.getItem('coke-locale')).toBe('en');

    flushSync(() => {
      container.querySelector('button')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(container.querySelector('[data-testid="locale"]')?.textContent).toBe('zh');
    expect(localStorage.getItem('coke-locale')).toBe('zh');
    expect(document.cookie).toContain('coke-locale=zh');
    expect(document.documentElement.lang).toBe('zh');
  });
});
