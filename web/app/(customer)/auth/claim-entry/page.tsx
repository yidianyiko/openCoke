'use client';

import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useLocale } from '../../../../components/locale-provider';
import { requestCustomerClaimEmail } from '../../../../lib/customer-google-calendar-import';

export default function ClaimEntryPage() {
  const { messages } = useLocale();
  const copy = messages.customerPages.claimEntry;
  const [entryToken, setEntryToken] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setEntryToken(params.get('entry') ?? '');
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await requestCustomerClaimEmail({
        entryToken: entryToken ?? '',
        email,
        next: '/account/calendar-import',
      });

      if (!res.ok) {
        setError(
          res.error === 'invalid_or_expired_token'
            ? copy.invalidOrExpiredError
            : res.error === 'email_already_exists'
              ? copy.emailAlreadyExistsError
              : copy.genericError,
        );
        setSubmitted(false);
        return;
      }

      setSubmitted(true);
    } catch {
      setError(copy.genericError);
      setSubmitted(false);
    } finally {
      setLoading(false);
    }
  }

  const hasResolvedEntryToken = entryToken !== null;
  const isMissingEntryToken = hasResolvedEntryToken && entryToken === '';

  return (
    <section className="auth-card">
      <p className="auth-card__eyebrow">{copy.eyebrow}</p>
      <h1 className="auth-card__title">{copy.title}</h1>
      <p className="auth-card__desc">{copy.description}</p>

      {submitted ? <div className="auth-alert auth-alert--info">{copy.success}</div> : null}
      {error ? <div className="auth-alert auth-alert--error">{error}</div> : null}

      {isMissingEntryToken ? (
        <div className="auth-alert auth-alert--error">{copy.invalidOrExpiredError}</div>
      ) : null}

      {hasResolvedEntryToken && !isMissingEntryToken ? (
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
            onChange={(event) => setEmail(event.target.value)}
            placeholder={copy.emailPlaceholder}
            required
          />
        </div>

        <button type="submit" className="auth-submit" disabled={loading}>
          {loading ? copy.submitting : copy.submit}
        </button>
        </form>
      ) : null}

      <div className="auth-linkrow">
        <span className="auth-linkrow__text">{copy.signInPrompt}</span>
        <Link href="/auth/login" className="auth-linkrow__link">
          {copy.signInLink}
        </Link>
      </div>
    </section>
  );
}
