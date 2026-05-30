'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { type Locale } from '../lib/i18n';
import { KapKoalaBadge, KapKoalaHero } from './kap-brand';
import { LocaleSwitch } from './locale-switch';
import { useLocale } from './locale-provider';

const CUSTOMER_NAV = {
  en: [
    { href: '/channels', label: 'Channels' },
    { href: '/channels/wechat-personal', label: 'WeChat' },
    { href: '/account/access-status', label: 'Access' },
    { href: '/account/subscription', label: 'Renewal' },
    { href: '/account/calendar-import', label: 'Calendar' },
    { href: '/account/friends', label: 'Friends' },
    { href: '/account/shared-reminders', label: 'Shared' },
    { href: '/account/reminders', label: 'Reminders' },
    { href: '/account/my-agent', label: 'My Agent' },
  ],
  zh: [
    { href: '/channels', label: '通道' },
    { href: '/channels/wechat-personal', label: '微信' },
    { href: '/account/access-status', label: '权限' },
    { href: '/account/subscription', label: '续费' },
    { href: '/account/calendar-import', label: '日历' },
    { href: '/account/friends', label: '好友' },
    { href: '/account/shared-reminders', label: '共享' },
    { href: '/account/reminders', label: '提醒' },
    { href: '/account/my-agent', label: '我的智能体' },
  ],
} satisfies Record<Locale, ReadonlyArray<{ href: string; label: string }>>;

export function CustomerShell({ children }: { children: ReactNode }) {
  const { locale, messages } = useLocale();
  const copy = messages.customerLayout;
  const pathname = usePathname();
  const navItems = CUSTOMER_NAV[locale];

  return (
    <div className="coke-site customer-shell-page">
      <header className="customer-shell__header">
        <div className="customer-shell__header-inner">
          <div className="customer-shell__header-top">
            <Link href="/" className="brand" aria-label="Kap AI">
              <KapKoalaBadge className="brand__icon" />
              <span className="brand__mark">kap</span>
            </Link>

            <p className="customer-shell__header-copy">{copy.brandTagline}</p>

            <div className="customer-shell__header-actions">
              <LocaleSwitch />
            </div>
          </div>

          <nav className="customer-shell__nav" aria-label={copy.navLabel}>
            {navItems.map((item) => {
              const isCurrent =
                pathname === item.href || (item.href !== '/channels' && pathname?.startsWith(`${item.href}/`));

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="customer-shell__nav-link"
                  aria-current={isCurrent ? 'page' : undefined}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <p className="customer-shell__route-copy">{copy.navLabel}</p>
        </div>
      </header>

      <main className="customer-shell__main">
        <section className="customer-shell__grid">
          <aside className="customer-shell__hero">
            <div className="customer-shell__spotlight">
              <div className="customer-shell__spotlight-copy">
                <p className="customer-shell__eyebrow">{copy.eyebrow}</p>
                <h1 className="customer-shell__title">{copy.title}</h1>
                <p className="customer-shell__body">{copy.body}</p>
                <p className="customer-shell__secondary">{copy.secondaryBody}</p>
              </div>

              <div className="customer-shell__spotlight-visual" aria-hidden="true">
                <div className="customer-shell__spotlight-note">
                  {locale === 'zh' ? '回来之后，直接继续你的下一步。' : 'Come back and pick up the next step.'}
                </div>
                <KapKoalaHero className="customer-shell__mascot" />
              </div>
            </div>

            <div className="customer-shell__trust">
              {copy.trustLines.map((line) => (
                <div key={line} className="customer-shell__trust-chip">
                  {line}
                </div>
              ))}
            </div>
          </aside>

          <div className="customer-shell__workspace">
            <div className="customer-shell__workspace-bar">
              <span>{copy.navLabel}</span>
              <strong>{locale === 'zh' ? '继续你的 Kap 流程' : 'Continue your Kap flow'}</strong>
            </div>
            <div className="customer-shell__content">{children}</div>
          </div>
        </section>
      </main>
    </div>
  );
}
