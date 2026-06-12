'use client';

import Link from 'next/link';
import { useLocale } from '../../../../components/locale-provider';

export default function CustomerForgotPasswordPage() {
  const { messages } = useLocale();
  const copy = messages.customerPages.forgotPassword;

  return (
    <section className="auth-card">
      <h1 className="auth-card__title">{copy.title}</h1>
      <p className="auth-card__desc">{copy.disabledDescription}</p>

      <div className="auth-linkrow">
        <span className="auth-linkrow__text">{copy.backToSignInPrompt}</span>
        <Link href="/auth/login" className="auth-linkrow__link">
          {copy.backToSignInLink}
        </Link>
      </div>
    </section>
  );
}
