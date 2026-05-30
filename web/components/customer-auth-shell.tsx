'use client';

import type { ReactNode } from 'react';
import { usePathname } from 'next/navigation';

import { CokePublicShell } from './coke-public-shell';
import { KapKoalaHero } from './kap-brand';
import { useLocale } from './locale-provider';

function getActiveAuthCta(pathname: string | null): 'signIn' | 'register' | null {
  if (!pathname) {
    return null;
  }

  if (pathname === '/auth/login') {
    return 'signIn';
  }

  if (pathname === '/auth/register') {
    return 'register';
  }

  if (
    pathname === '/auth/forgot-password' ||
    pathname === '/auth/reset-password' ||
    pathname === '/auth/verify-email' ||
    pathname === '/auth/claim'
  ) {
    return null;
  }

  return null;
}

export function CustomerAuthShell({ children }: { children: ReactNode }) {
  const { locale, messages } = useLocale();
  const pathname = usePathname();
  const copy = messages.customerLayout;

  return (
    <CokePublicShell activeAuthCta={getActiveAuthCta(pathname)} contentClassName="auth-shell">
      <div className="auth-shell__grid">
        <section className="auth-hero" aria-label={copy.title}>
          <div className="auth-hero__spotlight">
            <div className="auth-hero__copy">
              <p className="auth-hero__brand">{copy.brandName}</p>
              <p className="auth-hero__tagline">{copy.brandTagline}</p>
              <p className="auth-hero__nav-label">{copy.navLabel}</p>
              <p className="auth-hero__eyebrow">{copy.eyebrow}</p>
              <h1 className="auth-hero__title">{copy.title}</h1>
              <p className="auth-hero__body">{copy.body}</p>
              <p className="auth-hero__secondary">{copy.secondaryBody}</p>
            </div>

            <div className="auth-hero__visual" aria-hidden="true">
              <div className="auth-hero__sticker">
                {locale === 'zh' ? '安全进入，然后继续下一步。' : 'Secure entry, then keep going.'}
              </div>
              <KapKoalaHero className="auth-hero__mascot" />
            </div>
          </div>

          <div className="auth-shell__stage">
            <ul className="auth-hero__trust-list">
              {copy.trustLines.map((line) => (
                <li key={line} className="auth-hero__trust-item">
                  {line}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <div className="auth-shell__content">{children}</div>
      </div>
    </CokePublicShell>
  );
}
