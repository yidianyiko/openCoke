import { describe, expect, it } from 'vitest';

import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE_NAME,
  LOCALE_STORAGE_KEY,
  detectClientLocale,
  detectLocaleFromAcceptLanguage,
  detectLocaleFromNavigator,
  messages,
  normalizeLocale,
  resolveInitialLocale,
} from './i18n';

describe('i18n helpers', () => {
  it('normalizes supported locales and falls back to en for unsupported values', () => {
    expect(normalizeLocale('en')).toBe('en');
    expect(normalizeLocale('zh')).toBe('zh');
    expect(normalizeLocale('ZH-CN')).toBe('zh');
    expect(normalizeLocale('ja')).toBe(DEFAULT_LOCALE);
    expect(normalizeLocale(undefined)).toBe(DEFAULT_LOCALE);
  });

  it('detects locale from navigator language with zh as the only non-en branch', () => {
    expect(detectLocaleFromNavigator('zh-CN')).toBe('zh');
    expect(detectLocaleFromNavigator('zh-TW')).toBe('zh');
    expect(detectLocaleFromNavigator('en-US')).toBe('en');
    expect(detectLocaleFromNavigator('ja-JP')).toBe('en');
    expect(detectLocaleFromNavigator(undefined)).toBe('en');
  });

  it('detects locale from Accept-Language using the first explicit zh entry', () => {
    expect(detectLocaleFromAcceptLanguage('zh-CN,zh;q=0.9,en;q=0.8')).toBe('zh');
    expect(detectLocaleFromAcceptLanguage('en-US,en;q=0.9,zh;q=0.8')).toBe('en');
    expect(detectLocaleFromAcceptLanguage('en-US;q=0.1,zh-CN;q=0.9')).toBe('zh');
    expect(detectLocaleFromAcceptLanguage('fr-FR,zh;q=0.9')).toBe('zh');
    expect(detectLocaleFromAcceptLanguage('fr-FR,en;q=0.8')).toBe('en');
    expect(detectLocaleFromAcceptLanguage('')).toBe('en');
  });

  it('ignores corrupted persisted locales and falls through to cookie values', () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'broken');
    document.cookie = 'coke-locale=zh; path=/';

    try {
      expect(detectClientLocale()).toBe('zh');
    } finally {
      localStorage.removeItem(LOCALE_STORAGE_KEY);
      document.cookie = 'coke-locale=; path=/; Max-Age=0';
    }
  });

  it('falls back to navigator language when storage access fails', () => {
    const originalGetItem = Storage.prototype.getItem;
    const navigatorPrototype = Object.getPrototypeOf(window.navigator);
    const originalLanguage = Object.getOwnPropertyDescriptor(navigatorPrototype, 'language');

    Object.defineProperty(navigatorPrototype, 'language', {
      configurable: true,
      get: () => 'zh-CN',
    });
    Storage.prototype.getItem = () => {
      throw new Error('blocked');
    };

    try {
      expect(detectClientLocale()).toBe('zh');
    } finally {
      Storage.prototype.getItem = originalGetItem;
      if (originalLanguage) {
        Object.defineProperty(navigatorPrototype, 'language', originalLanguage);
      }
    }
  });

  it('prefers a cookie value before Accept-Language when resolving the initial locale', () => {
    expect(
      resolveInitialLocale({
        cookieLocale: 'zh',
        acceptLanguage: 'en-US,en;q=0.9',
      }),
    ).toBe('zh');

    expect(
      resolveInitialLocale({
        cookieLocale: 'fr',
        acceptLanguage: 'zh-CN,zh;q=0.9',
      }),
    ).toBe('zh');

    expect(
      resolveInitialLocale({
        cookieLocale: undefined,
        acceptLanguage: 'fr-FR,fr;q=0.9',
      }),
    ).toBe('en');
  });

  it('exposes matching locale branches in the message catalog', () => {
    expect(messages.en.common.languageLabel).toBe('Language');
    expect(messages.zh.common.languageLabel).toBe('语言');
    expect(messages.en.customerLayout.title).toBeDefined();
    expect(messages.zh.customerLayout.title).toBeDefined();
    expect(messages.en.publicShell.cta.signIn).toBeDefined();
    expect(messages.zh.publicShell.cta.signIn).toBeDefined();
    expect(messages.en.customerPages.login.resendVerificationEmail).toBe('Resend verification email');
    expect(messages.zh.customerPages.login.resendVerificationEmail).toBe('重新发送验证邮件');
    expect(messages.en.customerPages.login.resendVerificationSuccess).toContain(
      'valid for 24 hours',
    );
    expect(messages.en.customerPages.login.resendVerificationSuccess).toContain('spam folder');
    expect(messages.zh.customerPages.login.resendVerificationSuccess).toContain('24 小时内有效');
    expect(messages.zh.customerPages.login.resendVerificationSuccess).toContain('垃圾邮箱');
    expect(messages.en.customerPages.login.verificationRetryDescription).toBe(
      "We couldn't verify your email right now. Resend a verification email to continue.",
    );
    expect(messages.zh.customerPages.login.verificationRetryDescription).toBe(
      '暂时无法验证你的邮箱。请重新发送验证邮件继续。',
    );
    expect(messages.en.customerPages.verifyEmail.verifyingDescription).toBe(
      'Verifying your email link now...',
    );
    expect(messages.zh.customerPages.verifyEmail.verifyingDescription).toBe('正在验证你的邮箱链接...');
    expect(messages.en.customerPages.channelsIndex.title).toBeDefined();
    expect(messages.zh.customerPages.channelsIndex.title).toBeDefined();
    expect(JSON.stringify(messages.en.customerPages.friends)).not.toMatch(/friend request/i);
    expect(JSON.stringify(messages.zh.customerPages.friends)).not.toMatch(/好友请求/);
    expect(messages.en.customerPages.myAgent.title).toBe('My Agent');
    expect(messages.zh.customerPages.myAgent.title).toBe('我的智能体');
    expect(messages.en.customerPages.claim.title).toBeDefined();
    expect(messages.zh.customerPages.claim.title).toBeDefined();
    expect(messages.en.cokeUserLayout.title).toBeDefined();
    expect(messages.zh.cokeUserLayout.title).toBeDefined();
    expect(messages.en.cokeUserPages.renew.title).toBeDefined();
    expect(messages.zh.cokeUserPages.renew.title).toBeDefined();
    expect((messages.en.customerPages as Record<string, unknown>).renew).toBeUndefined();
    expect((messages.en.customerPages as Record<string, unknown>).paymentSuccess).toBeUndefined();
    expect((messages.en.customerPages as Record<string, unknown>).paymentCancel).toBeUndefined();
    expect((messages.zh.customerPages as Record<string, unknown>).renew).toBeUndefined();
    expect((messages.zh.customerPages as Record<string, unknown>).paymentSuccess).toBeUndefined();
    expect((messages.zh.customerPages as Record<string, unknown>).paymentCancel).toBeUndefined();
    expect((messages.en.cokeUserPages as Record<string, unknown>).login).toBeUndefined();
    expect((messages.en.cokeUserPages as Record<string, unknown>).register).toBeUndefined();
    expect((messages.en.cokeUserPages as Record<string, unknown>).forgotPassword).toBeUndefined();
    expect((messages.en.cokeUserPages as Record<string, unknown>).resetPassword).toBeUndefined();
    expect((messages.en.cokeUserPages as Record<string, unknown>).verifyEmail).toBeUndefined();
    expect((messages.en.cokeUserPages as Record<string, unknown>).bindWechat).toBeUndefined();
    expect((messages.zh.cokeUserPages as Record<string, unknown>).login).toBeUndefined();
    expect((messages.zh.cokeUserPages as Record<string, unknown>).register).toBeUndefined();
    expect((messages.zh.cokeUserPages as Record<string, unknown>).forgotPassword).toBeUndefined();
    expect((messages.zh.cokeUserPages as Record<string, unknown>).resetPassword).toBeUndefined();
    expect((messages.zh.cokeUserPages as Record<string, unknown>).verifyEmail).toBeUndefined();
    expect((messages.zh.cokeUserPages as Record<string, unknown>).bindWechat).toBeUndefined();
    expect(messages.en.homepage.platforms.items.length).toBeGreaterThan(0);
    expect(messages.zh.homepage.platforms.items.length).toBeGreaterThan(0);
    expect(LOCALE_COOKIE_NAME).toBe(LOCALE_STORAGE_KEY);
  });
});
