'use client';

import type { FormEvent } from 'react';
import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useLocale } from '../../../../components/locale-provider';
import { registerCustomer, storeCustomerAuth } from '../../../../lib/customer-auth';

export default function CustomerRegisterPage() {
  const { messages } = useLocale();
  const copy = messages.customerPages.register;
  const router = useRouter();
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const next =
    typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('next') : null;
  const safeNext = next && next.startsWith('/') && !next.startsWith('//') ? next : null;

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await registerCustomer({
        displayName,
        email,
        password,
      });

      if (!res.ok) {
        setError(res.error === 'email_already_exists' ? copy.emailAlreadyExistsError : copy.genericError);
        return;
      }

      storeCustomerAuth(res.data);
      router.push(
        `/auth/verify-email?email=${encodeURIComponent(res.data.email)}${
          safeNext ? `&next=${encodeURIComponent(safeNext)}` : ''
        }`,
      );
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

      <form onSubmit={handleSubmit} className="auth-form">
        <div className="auth-field">
          <label htmlFor="displayName" className="auth-label">
            {copy.displayNameLabel}
          </label>
          <input
            id="displayName"
            className="auth-input"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder={copy.displayNamePlaceholder}
            required
          />
        </div>

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

        <div className="auth-field">
          <label htmlFor="password" className="auth-label">
            {copy.passwordLabel}
          </label>
          <input
            id="password"
            type="password"
            className="auth-input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={copy.passwordPlaceholder}
            minLength={8}
            required
          />
        </div>

        <button type="submit" className="auth-submit" disabled={loading}>
          {loading ? copy.submitting : copy.submit}
        </button>
      </form>

      <div className="auth-linkrow">
        <span className="auth-linkrow__text">{copy.signInPrompt}</span>
        <Link
          href={safeNext ? `/auth/login?next=${encodeURIComponent(safeNext)}` : '/auth/login'}
          className="auth-linkrow__link"
        >
          {copy.signInLink}
        </Link>
      </div>
    </section>
  );
}
