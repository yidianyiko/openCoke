import type { Metadata } from 'next';
import { Fraunces, Inter, JetBrains_Mono } from 'next/font/google';

import { KapKoalaBadge } from '../components/kap-brand';
import { LocaleProvider } from '../components/locale-provider';
import './globals.css';
import './public-site.css';

const fraunces = Fraunces({
  subsets: ['latin'],
  variable: '--font-fraunces',
  axes: ['SOFT', 'opsz'],
  display: 'swap',
});

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'kap | An AI Supervisor That Follows Up',
  description: 'Kap AI turns goals into reminders, check-ins, and follow-up across personal WeChat and WhatsApp.',
  icons: { icon: '/kap-koala-badge.png' },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${fraunces.variable} ${inter.variable} ${jetbrainsMono.variable}`}>
        <div id="locale-splash" className="coke-site-splash">
          <div className="coke-site-splash__card">
            <KapKoalaBadge className="coke-site-splash__icon" />
            <span className="coke-site-splash__mark">kap</span>
            <p className="coke-site-splash__body">Preparing your workspace...</p>
          </div>
        </div>
        <LocaleProvider initialLocale="en" reconcileClientLocale>
          {children}
        </LocaleProvider>
      </body>
    </html>
  );
}
