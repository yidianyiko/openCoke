'use client';

import type { FormEvent } from 'react';
import { useState } from 'react';
import Link from 'next/link';
import { useLocale } from '../../../../components/locale-provider';
import { requestCustomerPasswordReset } from '../../../../lib/customer-auth';

export default function CustomerForgotPasswordPage() {
  const { messages } = useLocale();
  const copy = messages.customerPages.forgotPassword;
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);

    try {
      const res = await requestCustomerPasswordReset({ email });
      if (!res.ok) {
        setError(copy.genericError);
        return;
      }

      setMessage(copy.success);
    } catch {
      setError(copy.genericError);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="auth-card">
      <h1 className="auth-card__title">{copy.title}</h1>
      <p className="auth-card__desc">{copy.description}</p>

      {error ? <div className="auth-alert auth-alert--error">{error}</div> : null}

      {message ? <div className="auth-alert auth-alert--info">{message}</div> : null}

      <form onSubmit={handleSubmit} className="auth-form">
        <div className="auth-field">
          <label htmlFor="email" className="auth-label">
            {copy.emailLabel}
          </label>
          <input
            id="email"
            type="email"
            className="auth-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={copy.emailPlaceholder}
            required
          />
        </div>

        <button
          type="submit"
          className="auth-submit"
          disabled={loading}
        >
          {loading ? copy.submitting : copy.submit}
        </button>
      </form>

      <div className="auth-linkrow">
        <span className="auth-linkrow__text">{copy.backToSignInPrompt}</span>
        <Link href="/auth/login" className="auth-linkrow__link">
          {copy.backToSignInLink}
        </Link>
      </div>
    </section>
  );
}
