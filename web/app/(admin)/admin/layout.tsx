'use client';

import { useEffect, useReducer, type ReactNode } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { BarChart3, LogOut, MessageSquareText, Radio, Send, ShieldCheck } from 'lucide-react';
import { LocaleSwitch } from '../../../components/locale-switch';
import { useLocale } from '../../../components/locale-provider';
import { adminApi } from '../../../lib/admin-api';
import {
  ADMIN_SESSION_CLEARED_EVENT,
  clearAdminSession,
  getStoredAdminSession,
  isAdminAuthenticated,
} from '../../../lib/admin-auth';
import { getAdminCopy } from '../../../lib/admin-copy';
import { cn } from '../../../lib/utils';

const navIcons = {
  '/admin/dashboard': BarChart3,
  '/admin/customers': MessageSquareText,
  '/admin/shared-channels': Radio,
  '/admin/deliveries': Send,
  '/admin/admins': ShieldCheck,
} as const;

export default function AdminLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { locale, messages } = useLocale();
  const [, forceSessionCheck] = useReducer((count: number) => count + 1, 0);
  const copy = getAdminCopy(locale);
  const admin = getStoredAdminSession();
  const isLoginRoute = pathname === '/admin/login';
  const isAuthenticated = isAdminAuthenticated();

  useEffect(() => {
    if (!isLoginRoute && !isAuthenticated) {
      router.replace('/admin/login');
    }
  }, [isAuthenticated, isLoginRoute, router]);

  useEffect(() => {
    if (isLoginRoute) {
      return;
    }

    function handleSessionCleared() {
      // Admin auth lives outside React state, so force one re-render before redirecting.
      forceSessionCheck();
      router.replace('/admin/login');
    }

    window.addEventListener(ADMIN_SESSION_CLEARED_EVENT, handleSessionCleared);
    return () => {
      window.removeEventListener(ADMIN_SESSION_CLEARED_EVENT, handleSessionCleared);
    };
  }, [isLoginRoute, router]);

  async function handleLogout() {
    await adminApi.post<null>('/api/admin/logout');
    clearAdminSession();
    router.push('/admin/login');
  }

  if (isLoginRoute) {
    return <>{children}</>;
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="flex min-h-screen bg-gray-50">
      <aside className="flex w-64 flex-col bg-navy-950 text-white">
        <div className="flex items-center gap-3 border-b border-white/10 px-5 py-5">
          <Image src="/logo.png" alt="Coke" width={28} height={28} className="h-7 w-7" />
          <div>
            <p className="text-sm font-semibold">{copy.brand.name}</p>
            <p className="text-[11px] text-white/50">{copy.brand.tagline}</p>
          </div>
        </div>

        <div className="mx-4 mt-4 rounded-lg border border-white/10 px-3 py-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-white/40">
            {messages.common.languageLabel}
          </div>
          <div className="mt-2 text-sm text-white/80">
            <LocaleSwitch />
          </div>
        </div>

        <nav className="flex-1 space-y-1 px-3 py-4">
          {copy.layout.nav.map(({ href, label, exact }) => {
            const Icon = navIcons[href as keyof typeof navIcons];
            const isActive = exact ? pathname === href : pathname.startsWith(href);

            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-teal-500/20 text-teal-400'
                    : 'text-white/65 hover:bg-white/5 hover:text-white',
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-white/10 px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-teal-500/20 text-sm font-semibold text-teal-300">
              {admin?.email?.[0]?.toUpperCase() ?? '?'}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-white">{admin?.email ?? copy.layout.title}</p>
              <p className="text-xs text-white/45">{copy.layout.roleLabel}</p>
            </div>
            <button
              type="button"
              title={copy.layout.signOutTitle}
              aria-label={copy.layout.signOutTitle}
              className="text-white/45 transition-colors hover:text-white"
              onClick={() => void handleLogout()}
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
