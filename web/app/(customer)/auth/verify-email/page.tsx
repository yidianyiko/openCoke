'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useLocale } from '../../../../components/locale-provider';
import {
  clearCustomerAuth,
  getCustomerProfile,
  getStoredCustomerProfile,
  getStoredCustomerSession,
  resendCustomerVerification,
  verifyCustomerEmail,
  storeCustomerAuth,
  storeCustomerProfile,
} from '../../../../lib/customer-auth';

type RecoveryReason = 'manual' | 'expired' | 'retry';

function isSafeInternalNext(next: string | null): next is string {
  return next != null && next.startsWith('/') && !next.startsWith('//');
}

export default function CustomerVerifyEmailPage() {
  const { messages } = useLocale();
  const copy = messages.customerPages.verifyEmail;
  const loginCopy = messages.customerPages.login;
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState('');
  const [recoveryReason, setRecoveryReason] = useState<RecoveryReason | null>(null);
  const [resendMessage, setResendMessage] = useState('');
  const [resendStatus, setResendStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [resending, setResending] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token')?.trim() ?? '';
    const queryEmail = params.get('email')?.trim() ?? '';
    const next = params.get('next');
    const safeNext = isSafeInternalNext(next) ? next : null;
    const storedEmail =
      getStoredCustomerSession()?.email?.trim() ?? getStoredCustomerProfile()?.email?.trim() ?? '';
    const recoveryEmail = queryEmail || storedEmail;

    if (!token) {
      setEmail(recoveryEmail);
      setRecoveryReason('manual');
      setLoading(false);
      return;
    }

    if (!queryEmail) {
      setEmail(recoveryEmail);
      setRecoveryReason('expired');
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function verifyEmailLink() {
      let storedAuth = false;
      try {
        const res = await verifyCustomerEmail({ token, email: queryEmail });

        if (cancelled) return;

        if (!res.ok) {
          router.replace(`/auth/login?email=${encodeURIComponent(queryEmail)}&verification=expired`);
          return;
        }

        storeCustomerAuth(res.data);
        storedAuth = true;

        const profile = await getCustomerProfile();
        if (!profile.ok) {
          throw new Error('customer_profile_unavailable');
        }

        storeCustomerProfile(profile.data);

        router.replace(
          profile.data.subscription_active === false
            ? '/account/subscription'
            : safeNext ?? '/channels/wechat-personal',
        );
      } catch {
        if (!cancelled) {
          if (storedAuth) {
            clearCustomerAuth();
          }
          router.replace(`/auth/login?email=${encodeURIComponent(queryEmail)}&verification=retry`);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void verifyEmailLink();

    return () => {
      cancelled = true;
    };
  }, [router]);

  async function handleResendVerification() {
    const nextEmail = email.trim();
    if (nextEmail === '') {
      return;
    }

    setResendMessage('');
    setResendStatus('idle');
    setResending(true);

    try {
      const res = await resendCustomerVerification({ email: nextEmail });

      if (!res.ok) {
        setResendStatus('error');
        setResendMessage(loginCopy.resendVerificationError);
        return;
      }

      setResendStatus('success');
      setResendMessage(loginCopy.resendVerificationSuccess);
      setRecoveryReason('manual');
    } catch {
      setResendStatus('error');
      setResendMessage(loginCopy.resendVerificationError);
    } finally {
      setResending(false);
    }
  }

  const isRecoveryMode = recoveryReason != null;
  const recoveryDescription =
    recoveryReason === 'retry'
      ? loginCopy.verificationRetryDescription
      : recoveryReason === 'expired'
        ? loginCopy.verificationRecoveryDescription
        : copy.description;

  return (
    <section className="auth-card">
      <h1 className="auth-card__title">{copy.title}</h1>
      <p className="auth-card__desc">{loading && !isRecoveryMode ? copy.verifyingDescription : copy.description}</p>

      {isRecoveryMode ? (
        <div className="auth-alert auth-alert--warning">
          <div className="auth-alert__body">
            <p className="auth-alert__title">{loginCopy.verificationRecoveryTitle}</p>
            <p className="auth-alert__copy">{recoveryDescription}</p>
          </div>

          <div className="auth-field auth-alert__field">
            <label htmlFor="email" className="auth-label">
              {loginCopy.emailLabel}
            </label>
            <input
              id="email"
              type="email"
              className="auth-input"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder={loginCopy.emailPlaceholder}
              required
            />
          </div>

          <div className="auth-alert__actions">
            <button
              type="button"
              className="auth-submit auth-submit--compact"
              disabled={resending || email.trim() === ''}
              onClick={handleResendVerification}
            >
              {resending ? loginCopy.resendingVerificationEmail : loginCopy.resendVerificationEmail}
            </button>
          </div>
        </div>
      ) : null}

      {resendMessage ? (
        <div className={`auth-alert ${resendStatus === 'success' ? 'auth-alert--success' : 'auth-alert--error'}`}>
          {resendMessage}
        </div>
      ) : null}
    </section>
  );
}
