'use client';

import { useEffect, type FormEvent } from 'react';
import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useLocale } from '../../../../components/locale-provider';
import {
  clearCustomerAuth,
  getCustomerProfile,
  loginCustomer,
  storeCustomerAuth,
  storeCustomerProfile,
} from '../../../../lib/customer-auth';

function isSafeInternalNext(next: string | null): next is string {
  return next != null && next.startsWith('/') && !next.startsWith('//');
}

export default function CustomerLoginPage() {
  const { messages } = useLocale();
  const copy = messages.customerPages.login;
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const params = new URLSearchParams(window.location.search);
    const nextEmail = params.get('email');

    if (nextEmail !== null) {
      setEmail(nextEmail);
    }
  }, []);

  const next =
    typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('next') : null;
  const safeNext = isSafeInternalNext(next) ? next : null;

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    setStatusMessage('');
    setLoading(true);
    let storedAuth = false;

    try {
      const res = await loginCustomer({ email, password });

      if (!res.ok) {
        setError(copy.genericError);
        return;
      }

      storeCustomerAuth(res.data);
      storedAuth = true;

      const profile = await getCustomerProfile();
      if (!profile.ok) {
        clearCustomerAuth();
        setError(copy.genericError);
        return;
      }

      storeCustomerProfile(profile.data);

      if (profile.data.status === 'suspended') {
        setError(copy.suspendedError);
        return;
      }

      if (profile.data.subscription_active !== true) {
        setStatusMessage(copy.subscriptionRenewalRequired);
        router.push('/account/subscription');
        return;
      }

      setStatusMessage(copy.success);
      router.push(safeNext ?? '/channels/wechat-personal');
    } catch {
      if (storedAuth) {
        clearCustomerAuth();
      }
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

      {statusMessage ? <div className="auth-alert auth-alert--info">{statusMessage}</div> : null}

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
            required
          />
        </div>

        <button type="submit" className="auth-submit" disabled={loading}>
          {loading ? copy.submitting : copy.submit}
        </button>
      </form>

      <div className="auth-linkrow">
        <span className="auth-linkrow__text">{copy.registerPrompt}</span>
        <Link
          href={safeNext ? `/auth/register?next=${encodeURIComponent(safeNext)}` : '/auth/register'}
          className="auth-linkrow__link"
        >
          {copy.registerLink}
        </Link>
      </div>
    </section>
  );
}
