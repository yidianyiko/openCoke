'use client';

import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { ApiResponse } from '../../../../lib/api-types';
import { useLocale } from '../../../../components/locale-provider';
import { customerApi } from '../../../../lib/customer-api';
import { storeCustomerAuth, type CustomerAuthResult } from '../../../../lib/customer-auth';

function isSafeInternalPath(next: string | undefined): next is string {
  return typeof next === 'string' && next.startsWith('/') && !next.startsWith('//') && !next.includes('\\');
}

export default function ClaimPage() {
  const { messages } = useLocale();
  const copy = messages.customerPages.claim;
  const router = useRouter();
  const [token, setToken] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const nextToken = params.get('token') ?? '';
    setToken(nextToken);

    if (!nextToken) {
      return;
    }

    params.delete('token');
    const nextQuery = params.toString();
    const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}${window.location.hash}`;
    window.history.replaceState(window.history.state, '', nextUrl);
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError(copy.mismatchError);
      return;
    }

    setLoading(true);

    try {
      const res = await customerApi.post<ApiResponse<CustomerAuthResult>>('/api/auth/claim', {
        token,
        password,
      });

      if (!res.ok) {
        setError(
          res.error === 'invalid_or_expired_token'
            ? copy.invalidOrExpiredError
            : res.error === 'email_already_exists'
              ? copy.emailAlreadyExistsError
              : copy.genericError,
        );
        return;
      }

      storeCustomerAuth(res.data);
      router.push(isSafeInternalPath(res.data.continueTo) ? res.data.continueTo : '/channels/wechat-personal');
    } catch {
      setError(copy.genericError);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="auth-card">
      <p className="auth-card__eyebrow">{copy.eyebrow}</p>
      <h1 className="auth-card__title">{copy.title}</h1>
      <p className="auth-card__desc">{copy.description}</p>

      {error ? <div className="auth-alert auth-alert--error">{error}</div> : null}

      <form onSubmit={handleSubmit} className="auth-form">
        <div className="auth-field">
          <label htmlFor="token" className="auth-label">
            {copy.tokenLabel}
          </label>
          <input
            id="token"
            className="auth-input"
            value={token}
            onChange={(event) => setToken(event.target.value)}
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
            onChange={(event) => setPassword(event.target.value)}
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
            onChange={(event) => setConfirmPassword(event.target.value)}
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
        <span className="auth-linkrow__text">{copy.signInPrompt}</span>
        <Link href="/auth/login" className="auth-linkrow__link">
          {copy.signInLink}
        </Link>
      </div>
    </section>
  );
}
