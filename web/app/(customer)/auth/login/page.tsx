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
  resendCustomerVerification,
  storeCustomerAuth,
  storeCustomerProfile,
} from '../../../../lib/customer-auth';

type VerificationRecoveryReason = 'expired' | 'retry' | null;

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
  const [verificationRecovery, setVerificationRecovery] = useState<VerificationRecoveryReason>(null);
  const [resendMessage, setResendMessage] = useState('');
  const [resendStatus, setResendStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [resending, setResending] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const params = new URLSearchParams(window.location.search);
    const nextEmail = params.get('email');

    if (nextEmail !== null) {
      setEmail(nextEmail);
    }

    const verificationState = params.get('verification');
    setVerificationRecovery(
      verificationState === 'expired' || verificationState === 'retry' ? verificationState : null,
    );
  }, []);

  const verificationRecoveryDescription =
    verificationRecovery === 'retry'
      ? copy.verificationRetryDescription
      : copy.verificationRecoveryDescription;
  const next =
    typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('next') : null;
  const safeNext = isSafeInternalNext(next) ? next : null;

  function showVerificationRecovery(reason: Exclude<VerificationRecoveryReason, null>) {
    setVerificationRecovery(reason);
    setResendMessage('');
    setResendStatus('idle');
  }

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

      if (profile.data.email_verified !== true) {
        setStatusMessage(copy.emailVerificationRequired);
        showVerificationRecovery('expired');
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

  async function handleResendVerification() {
    if (email.trim() === '') {
      return;
    }

    setResendMessage('');
    setResendStatus('idle');
    setResending(true);

    try {
      const res = await resendCustomerVerification({ email });

      if (!res.ok) {
        setResendStatus('error');
        setResendMessage(copy.resendVerificationError);
        return;
      }

      setResendStatus('success');
      setResendMessage(copy.resendVerificationSuccess);
    } catch {
      setResendStatus('error');
      setResendMessage(copy.resendVerificationError);
    } finally {
      setResending(false);
    }
  }

  return (
    <section className="auth-card">
      <h1 className="auth-card__title">{copy.title}</h1>
      <p className="auth-card__desc">{copy.description}</p>

      {verificationRecovery ? (
        <div className="auth-alert auth-alert--warning">
          <div className="auth-alert__body">
            <p className="auth-alert__title">{copy.verificationRecoveryTitle}</p>
            <p className="auth-alert__copy">{verificationRecoveryDescription}</p>
          </div>
          <div className="auth-alert__actions">
            <button
              type="button"
              className="auth-submit auth-submit--compact"
              disabled={resending || email.trim() === ''}
              onClick={handleResendVerification}
            >
              {resending ? copy.resendingVerificationEmail : copy.resendVerificationEmail}
            </button>
          </div>
          {resendMessage ? (
            <p
              className={`auth-alert__status ${
                resendStatus === 'success' ? 'auth-alert__status--success' : 'auth-alert__status--error'
              }`}
            >
              {resendMessage}
            </p>
          ) : null}
        </div>
      ) : null}

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
        <span className="auth-linkrow__text">{copy.forgotPasswordPrompt}</span>
        <Link href="/auth/forgot-password" className="auth-linkrow__link">
          {copy.forgotPasswordLink}
        </Link>
      </div>

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
