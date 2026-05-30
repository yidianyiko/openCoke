'use client';

import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import type { ReactNode } from 'react';

import { KapKoalaBadge } from './kap-brand';
import { LocaleSwitch } from './locale-switch';
import { useLocale } from './locale-provider';
import { cn } from '../lib/utils';

interface CokePublicShellProps {
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  activeAuthCta?: 'signIn' | 'register' | null;
}

export function CokePublicShell({
  children,
  className,
  contentClassName,
  activeAuthCta = null,
}: CokePublicShellProps) {
  const { messages } = useLocale();
  const signInCurrent = activeAuthCta === 'signIn' ? 'page' : undefined;
  const registerCurrent = activeAuthCta === 'register' ? 'page' : undefined;

  return (
    <div className={cn('coke-site', className)}>
      <header className="site-header">
        <div className="site-header__inner">
          <Link href="/" className="brand" aria-label="Kap AI">
            <KapKoalaBadge className="brand__icon" />
            <span className="brand__mark">kap</span>
          </Link>

          <nav className="site-nav">
            {messages.publicShell.nav.map((item) => (
              <Link key={item.href} href={item.href} className="site-nav__link">
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="site-header__actions">
            <LocaleSwitch />
            <Link href="/auth/login" className="header-signin" aria-current={signInCurrent}>
              {messages.publicShell.cta.signIn}
            </Link>
            <Link href="/auth/register" className="header-cta" aria-current={registerCurrent}>
              {messages.publicShell.cta.register}
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>
        </div>
      </header>

      <main className={contentClassName}>{children}</main>
    </div>
  );
}
