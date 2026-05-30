'use client';

import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useLocale } from '../../../../components/locale-provider';
import { resetCustomerPassword } from '../../../../lib/customer-auth';

export default function CustomerResetPasswordPage() {
  const { messages } = useLocale();
  const copy = messages.customerPages.resetPassword;
  const router = useRouter();
  const [enteredToken, setEnteredToken] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setEnteredToken(params.get('token') ?? '');
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setMessage('');

    if (password !== confirmPassword) {
      setError(copy.mismatchError);
      return;
    }

    setLoading(true);

    try {
      const res = await resetCustomerPassword({
        token: enteredToken,
        password,
      });
      if (!res.ok) {
        setError(copy.genericError);
        return;
      }

      setMessage(copy.success);
      router.push('/auth/login');
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
          <label htmlFor="token" className="auth-label">
            {copy.tokenLabel}
          </label>
          <input
            id="token"
            className="auth-input"
            value={enteredToken}
            onChange={(e) => setEnteredToken(e.target.value)}
            placeholder={copy.tokenPlaceholder}
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
            minLength={8}
            required
          />
        </div>

        <div className="auth-field">
          <label htmlFor="confirmPassword" className="auth-label">
            {copy.confirmPasswordLabel}
          </label>
          <input
            id="confirmPassword"
            type="password"
            className="auth-input"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            minLength={8}
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
        <span className="auth-linkrow__text">{copy.requestNewLinkPrompt}</span>
        <Link href="/auth/forgot-password" className="auth-linkrow__link">
          {copy.requestNewLinkLink}
        </Link>
      </div>
    </section>
  );
}
