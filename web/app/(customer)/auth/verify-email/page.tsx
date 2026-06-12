'use client';

import Link from 'next/link';
import { useLocale } from '../../../../components/locale-provider';

export default function CustomerVerifyEmailPage() {
  const { messages } = useLocale();
  const copy = messages.customerPages.verifyEmail;

  return (
    <section className="auth-card">
      <h1 className="auth-card__title">{copy.title}</h1>
      <p className="auth-card__desc">{copy.disabledDescription}</p>

      <div className="auth-alert auth-alert--warning">
        <div className="auth-alert__body">
          <p className="auth-alert__copy">{copy.disabledDetail}</p>
        </div>
      </div>

      <div className="auth-card__footer">
        <Link href="/auth/login" className="auth-link">
          {copy.backToSignInLink}
        </Link>
      </div>
    </section>
  );
}
