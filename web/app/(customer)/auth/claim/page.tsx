'use client';

import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useLocale } from '../../../../components/locale-provider';
import { customerApi } from '../../../../lib/customer-api';
import { storeCustomerAuth, type CustomerAuthResult } from '../../../../lib/customer-auth';

const CLAIM_BROWSER_SESSION_KEY = 'customer_claim_browser_session';

type CleanClaimRedemption = {
  account_id: string;
  session_token: string;
  continuation?: {
    next?: unknown;
  };
};

type CleanRouteError = {
  error: {
    code: string;
  };
};

function isSafeInternalPath(next: string | undefined): next is string {
  return typeof next === 'string' && next.startsWith('/') && !next.startsWith('//') && !next.includes('\\');
}

function isCleanRouteError(value: unknown): value is CleanRouteError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as CleanRouteError).error?.code === 'string'
  );
}

function getStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function createBrowserSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `browser_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

function getClaimBrowserSession(): string {
  const storage = getStorage();
  const existing = storage?.getItem(CLAIM_BROWSER_SESSION_KEY);
  if (existing) {
    return existing;
  }

  const next = createBrowserSessionId();
  storage?.setItem(CLAIM_BROWSER_SESSION_KEY, next);
  return next;
}

function customerAuthFromClaim(result: CleanClaimRedemption): CustomerAuthResult {
  const next = typeof result.continuation?.next === 'string' ? result.continuation.next : undefined;
  return {
    token: result.session_token,
    customerId: result.account_id,
    identityId: result.account_id,
    email: '',
    claimStatus: 'active',
    membershipRole: 'owner',
    continueTo: isSafeInternalPath(next) ? next : undefined,
  };
}

export default function ClaimPage() {
  const { messages } = useLocale();
  const copy = messages.customerPages.claim;
  const router = useRouter();
  const [token, setToken] = useState('');
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

    setLoading(true);

    try {
      const res = await customerApi.post<CleanClaimRedemption | CleanRouteError>('/api/claim/login-url/redeem', {
        token,
        browser_session: getClaimBrowserSession(),
      });

      if (isCleanRouteError(res)) {
        setError(
          ['artifact_not_found', 'artifact_expired', 'artifact_consumed', 'artifact_wrong_type'].includes(
            res.error.code,
          )
            ? copy.invalidOrExpiredError
            : copy.genericError,
        );
        return;
      }

      const auth = customerAuthFromClaim(res);
      storeCustomerAuth(auth);
      router.push(auth.continueTo ?? '/channels/wechat-personal');
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
