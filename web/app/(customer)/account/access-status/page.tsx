'use client';

import { useEffect, useState } from 'react';
import { getCustomerProfile, type CustomerProfile } from '../../../../lib/customer-auth';

function statusLabel(ok: boolean, good: string, blocked: string): string {
  return ok ? good : blocked;
}

export default function CustomerAccessStatusPage() {
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;

    getCustomerProfile()
      .then((res) => {
        if (!active) {
          return;
        }
        if (res.ok) {
          setProfile(res.data);
          setError('');
        } else {
          setError('Unable to load access status.');
        }
      })
      .catch(() => {
        if (active) {
          setError('Unable to load access status.');
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const emailStatus = profile
    ? statusLabel(profile.email_verified, 'Email verified', 'Email verification required')
    : 'Email status unavailable';
  const subscriptionStatus = profile
    ? statusLabel(profile.subscription_active, 'Subscription active', 'Subscription inactive')
    : 'Subscription status unavailable';
  const accountStatus = profile?.status === 'suspended' ? 'Account suspended' : 'Account active';

  return (
    <section className="customer-panel">
      <div className="customer-panel__header">
        <p className="customer-panel__eyebrow">Account</p>
        <h1>Access status</h1>
        <p>Review the account gates that control channel connection and calendar import.</p>
      </div>

      {loading ? <p className="customer-panel__notice">Loading access status...</p> : null}
      {error ? <p className="customer-panel__error">{error}</p> : null}

      <div className="customer-panel__list">
        <article className="customer-panel__item">
          <strong>{emailStatus}</strong>
          <span>Email verification gate</span>
        </article>
        <article className="customer-panel__item">
          <strong>{subscriptionStatus}</strong>
          <span>Subscription access gate</span>
        </article>
        <article className="customer-panel__item">
          <strong>{accountStatus}</strong>
          <span>Suspension gate</span>
        </article>
      </div>
    </section>
  );
}
