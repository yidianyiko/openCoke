'use client';

import { useEffect, useState } from 'react';
import {
  cancelCustomerSharedReminder,
  listCustomerSharedReminders,
  type CustomerSharedReminder,
} from '../../../../lib/customer-shared-reminders';

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function CustomerSharedRemindersPage() {
  const [items, setItems] = useState<CustomerSharedReminder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);

  function loadSharedReminders() {
    setLoading(true);
    listCustomerSharedReminders()
      .then((res) => {
        if (res.ok) {
          setItems(res.data.sharedReminders);
          setError('');
        } else {
          setError('Unable to load shared reminders.');
        }
      })
      .catch(() => setError('Unable to load shared reminders.'))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadSharedReminders();
  }, []);

  async function handleCancel(id: string) {
    setBusyId(id);
    try {
      const res = await cancelCustomerSharedReminder(id);
      if (!res.ok) {
        setError('Unable to cancel this shared reminder.');
        return;
      }
      loadSharedReminders();
    } catch {
      setError('Unable to cancel this shared reminder.');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="customer-panel">
      <div className="customer-panel__header">
        <p className="customer-panel__eyebrow">Friends</p>
        <h1>Shared reminders</h1>
        <p>View active shared reminders and cancel the whole group when needed.</p>
      </div>

      {loading ? <p className="customer-panel__notice">Loading shared reminders...</p> : null}
      {error ? <p className="customer-panel__error">{error}</p> : null}

      <div className="customer-panel__list">
        {items.map((item) => (
          <article className="customer-panel__item" key={item.id}>
            <div>
              <strong>{item.title}</strong>
              <span>{item.participants.join(', ')}</span>
              <span>
                {formatDate(item.triggerTime)} · {item.timezone} · {item.durationMinutes} min
              </span>
            </div>
            {item.status === 'active' ? (
              <button
                type="button"
                className="customer-action customer-action--secondary"
                data-testid="cancel-shared-reminder"
                disabled={busyId === item.id}
                onClick={() => void handleCancel(item.id)}
              >
                {busyId === item.id ? 'Canceling...' : 'Cancel'}
              </button>
            ) : (
              <span>{item.status}</span>
            )}
          </article>
        ))}
      </div>

      {!loading && items.length === 0 ? (
        <p className="customer-panel__notice">No shared reminders yet.</p>
      ) : null}
    </section>
  );
}
