'use client';

import Link from 'next/link';
import { Suspense, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

import { useLocale } from '../../../../components/locale-provider';
import { customerApi } from '../../../../lib/customer-api';

type SubscriptionSnapshot = {
  accountStatus: 'normal' | 'suspended';
  emailVerified: boolean;
  subscriptionActive: boolean;
  subscriptionExpiresAt: string | null;
  accountAccessAllowed: boolean;
  accountAccessDeniedReason: string | null;
  checkoutUrl: string | null;
};

type CleanSubscriptionStatus = {
  account_id: string;
  subscription_state: string;
  access_allowed: boolean;
  denial_reason: string | null;
  checkout_url: string | null;
};

type CleanCheckoutLink = {
  account_id: string;
  available: boolean;
  checkout_url: string | null;
  denial_reason: string | null;
};

type CleanRouteError = {
  error: {
    code: string;
  };
};

type PageMode = 'checkout' | 'success' | 'cancel';

function resolvePageMode(value: string | null): PageMode {
  if (value === 'success') {
    return 'success';
  }

  if (value === 'cancel') {
    return 'cancel';
  }

  return 'checkout';
}

function formatExpiry(value: string | null, locale: string): string | null {
  if (!value) {
    return null;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function isCleanRouteError(value: unknown): value is CleanRouteError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as CleanRouteError).error?.code === 'string'
  );
}

function subscriptionStatusToSnapshot(access: CleanSubscriptionStatus): SubscriptionSnapshot {
  const emailRequired = access.denial_reason === 'email_verification_required';
  const suspended = access.denial_reason === 'suspended';
  return {
    accountStatus: suspended ? 'suspended' : 'normal',
    emailVerified: !emailRequired,
    subscriptionActive: access.subscription_state === 'active',
    subscriptionExpiresAt: null,
    accountAccessAllowed: access.access_allowed,
    accountAccessDeniedReason: access.denial_reason,
    checkoutUrl: access.checkout_url,
  };
}

function CustomerSubscriptionPageContent() {
  const { locale, messages } = useLocale();
  const renewCopy = messages.cokeUserPages.renew;
  const successCopy = messages.cokeUserPages.paymentSuccess;
  const cancelCopy = messages.cokeUserPages.paymentCancel;
  const copy = messages.customerPages.bindWechat.blocked;
  const router = useRouter();
  const searchParams = useSearchParams();
  const mode = resolvePageMode(searchParams.get('status'));
  const [snapshot, setSnapshot] = useState<SubscriptionSnapshot | null>(null);
  const [loading, setLoading] = useState(mode !== 'cancel');
  const [error, setError] = useState('');
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const loadModeRef = useRef<PageMode | null>(null);
  const pageClassName = 'customer-view customer-view--narrow';
  const panelClassName = 'customer-panel customer-panel--narrow';
  const primaryActionClassName = 'customer-action customer-action--primary';
  const secondaryActionClassName = 'customer-action customer-action--secondary';

  useEffect(() => {
    if (mode === 'cancel') {
      setLoading(false);
      return;
    }

    if (loadModeRef.current === mode) {
      return;
    }

    loadModeRef.current = mode;

    let cancelled = false;

    async function loadSubscription() {
      try {
        const res = await customerApi.get<CleanSubscriptionStatus | CleanRouteError>('/api/subscription/status');

        if (cancelled) {
          return;
        }

        if (isCleanRouteError(res)) {
          router.replace('/auth/login?next=/account/subscription');
          return;
        }

        setSnapshot(subscriptionStatusToSnapshot(res));
      } catch {
        if (!cancelled) {
          setError(renewCopy.genericError);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadSubscription();

    return () => {
      cancelled = true;
    };
  }, [mode, renewCopy.genericError, router]);

  async function handleCheckout() {
    setCheckoutLoading(true);
    setError('');

    try {
      const res = await customerApi.post<CleanCheckoutLink | CleanRouteError>('/api/subscription/checkout-link');

      if (isCleanRouteError(res)) {
        if (res.error.code === 'unauthorized') {
          router.replace('/auth/login?next=/account/subscription');
          return;
        }
        setError(renewCopy.genericError);
        return;
      }

      if (!res.available || !res.checkout_url) {
        setError(renewCopy.genericError);
        return;
      }

      window.open(res.checkout_url, '_self');
    } catch {
      setError(renewCopy.genericError);
    } finally {
      setCheckoutLoading(false);
    }
  }

  if (mode === 'success') {
    const successReadyForSetup = snapshot?.subscriptionActive === true;

    return (
      <section className={pageClassName}>
        <div className={panelClassName}>
          <p className="customer-panel__eyebrow">{locale === 'zh' ? '支付状态' : 'Payment status'}</p>
          <h1 className="customer-panel__title">{successCopy.title}</h1>
          <p className="customer-panel__body">{successCopy.description}</p>
        {loading ? (
          <p className="customer-inline-note">Refreshing your subscription status...</p>
        ) : error ? (
          <p className="customer-inline-note customer-inline-note--error">{error}</p>
        ) : null}
          <div className="customer-action-row">
            <Link
              href={successReadyForSetup ? '/channels/wechat-personal' : '/account/subscription'}
              className={primaryActionClassName}
            >
              {successReadyForSetup ? successCopy.primaryCta : successCopy.secondaryCta}
            </Link>
            {successReadyForSetup ? (
              <Link href="/account/subscription" className={secondaryActionClassName}>
                {successCopy.secondaryCta}
              </Link>
            ) : null}
          </div>
        </div>
      </section>
    );
  }

  if (mode === 'cancel') {
    return (
      <section className={pageClassName}>
        <div className={panelClassName}>
          <p className="customer-panel__eyebrow">{locale === 'zh' ? '支付状态' : 'Payment status'}</p>
          <h1 className="customer-panel__title">{cancelCopy.title}</h1>
          <p className="customer-panel__body">{cancelCopy.description}</p>
          <div className="customer-action-row">
            <Link href="/account/subscription" className={primaryActionClassName}>
              {cancelCopy.primaryCta}
            </Link>
            <Link href="/channels/wechat-personal" className={secondaryActionClassName}>
              {cancelCopy.secondaryCta}
            </Link>
          </div>
        </div>
      </section>
    );
  }

  const expiry = formatExpiry(snapshot?.subscriptionExpiresAt ?? null, locale === 'zh' ? 'zh-CN' : 'en-US');
  const needsRenewal = snapshot?.subscriptionActive !== true;
  const canStartCheckout =
    needsRenewal &&
    Boolean(snapshot?.checkoutUrl) &&
    snapshot?.accountAccessDeniedReason === 'subscription_inactive';
  const mustVerifyEmail = snapshot?.accountAccessDeniedReason === 'email_verification_required';

  return (
    <section className={pageClassName}>
      <div className={panelClassName}>
        <p className="customer-panel__eyebrow">{locale === 'zh' ? '账号访问' : 'Account access'}</p>
        <h1 className="customer-panel__title">{renewCopy.title}</h1>

        {loading ? (
          <p className="customer-inline-note">Loading subscription status...</p>
        ) : error ? (
          <p className="customer-inline-note customer-inline-note--error">{error}</p>
        ) : snapshot ? (
          <div className="customer-status-list">
            <p>
              {snapshot.subscriptionActive ? 'Subscription is active.' : 'Subscription renewal is required.'}
              {expiry ? ` Expires ${expiry}.` : ''}
            </p>
            <p>
              {snapshot.emailVerified
                ? 'Email is verified.'
                : 'Email verification is still required before checkout is available.'}
            </p>
            <p>
              {snapshot.accountStatus === 'suspended'
                ? 'The customer account is suspended.'
                : 'The customer account is active.'}
            </p>
          </div>
        ) : null}

        {!loading && !error && snapshot ? (
          <div className="customer-action-row">
            {canStartCheckout ? (
              <button
                type="button"
                onClick={handleCheckout}
                disabled={checkoutLoading}
                className={primaryActionClassName}
              >
                {checkoutLoading ? 'Starting checkout...' : copy.renewSubscription}
              </button>
            ) : null}
            {mustVerifyEmail ? (
              <Link href="/auth/verify-email" className={primaryActionClassName}>
                {copy.verifyEmail}
              </Link>
            ) : null}
            <Link href="/channels/wechat-personal" className={secondaryActionClassName}>
              {renewCopy.backToSetup}
            </Link>
          </div>
        ) : null}

        {checkoutLoading ? <p className="customer-inline-note">Opening checkout…</p> : null}
      </div>
    </section>
  );
}

export default function CustomerSubscriptionPage() {
  return (
    <Suspense fallback={null}>
      <CustomerSubscriptionPageContent />
    </Suspense>
  );
}
