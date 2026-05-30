'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Loader2, RefreshCw } from 'lucide-react';
import { useLocale } from '../../../../components/locale-provider';
import { adminApi, type AdminDashboardMetrics } from '../../../../lib/admin-api';
import { getAdminCopy } from '../../../../lib/admin-copy';
import { formatDateTime } from '../../../../lib/utils';

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="card p-5">
      <div className="text-sm text-gray-500">{label}</div>
      <div className="mt-3 text-3xl font-semibold text-gray-900">{value.toLocaleString()}</div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between border-b border-gray-100 py-3 last:border-0">
      <span className="text-sm text-gray-500">{label}</span>
      <span className="text-sm font-medium text-gray-900">{value}</span>
    </div>
  );
}

export default function AdminDashboardPage() {
  const { locale } = useLocale();
  const copy = getAdminCopy(locale);
  const [metrics, setMetrics] = useState<AdminDashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;

    async function loadDashboard() {
      setLoading(true);
      setError('');
      const response = await adminApi.get<AdminDashboardMetrics>('/api/admin/dashboard');

      if (!active) {
        return;
      }

      if (!response.ok) {
        setMetrics(null);
        setError(response.error);
        setLoading(false);
        return;
      }

      setMetrics(response.data);
      setLoading(false);
    }

    void loadDashboard();
    return () => {
      active = false;
    };
  }, [reloadKey]);

  return (
    <div className="p-8">
      <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">{copy.dashboard.title}</h1>
          <p className="mt-1 text-gray-500">{copy.dashboard.subtitle}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href="/admin/customers" className="btn-primary">
            {copy.dashboard.actions.chatRecords}
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link href="/admin/shared-channels" className="btn-secondary">
            {copy.dashboard.actions.sharedChannels}
          </Link>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-teal-500" />
        </div>
      ) : error || !metrics ? (
        <div className="card px-5 py-8">
          <p className="text-sm text-red-600">
            {copy.common.errorPrefix}: {error || 'unknown_error'}
          </p>
          <button
            type="button"
            className="btn-secondary mt-4"
            onClick={() => setReloadKey((current) => current + 1)}
          >
            <RefreshCw className="h-4 w-4" />
            {copy.common.retry}
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <MetricCard label={copy.dashboard.cards.activeToday} value={metrics.activeCustomers.day} />
            <MetricCard label={copy.dashboard.cards.activeWeek} value={metrics.activeCustomers.week} />
            <MetricCard label={copy.dashboard.cards.activeMonth} value={metrics.activeCustomers.month} />
            <MetricCard label={copy.dashboard.cards.messagesToday} value={metrics.messages.day} />
            <MetricCard label={copy.dashboard.cards.totalCustomers} value={metrics.customers.total} />
            <MetricCard label={copy.dashboard.cards.queuedInbounds} value={metrics.parkedInbounds.queued} />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <section className="card p-5">
              <h2 className="text-lg font-semibold text-gray-900">{copy.dashboard.sections.messageBreakdown}</h2>
              <div className="mt-3">
                <DetailRow label={copy.dashboard.fields.userMessagesToday} value={metrics.messages.userDay.toLocaleString()} />
                <DetailRow label={copy.dashboard.fields.assistantMessagesToday} value={metrics.messages.assistantDay.toLocaleString()} />
                <DetailRow label={copy.dashboard.fields.messagesWeek} value={metrics.messages.week.toLocaleString()} />
                <DetailRow label={copy.dashboard.fields.messagesMonth} value={metrics.messages.month.toLocaleString()} />
                <DetailRow label={copy.dashboard.fields.totalMessages} value={metrics.messages.total.toLocaleString()} />
                <DetailRow
                  label={copy.dashboard.fields.lastMessageAt}
                  value={metrics.messages.lastMessageAt ? formatDateTime(metrics.messages.lastMessageAt) : '—'}
                />
              </div>
            </section>

            <section className="card p-5">
              <h2 className="text-lg font-semibold text-gray-900">{copy.dashboard.sections.operations}</h2>
              <div className="mt-3">
                <DetailRow label={copy.dashboard.fields.conversations} value={metrics.conversations.total.toLocaleString()} />
                <DetailRow label={copy.dashboard.fields.channels} value={metrics.channels.total.toLocaleString()} />
                <DetailRow label={copy.dashboard.fields.connectedChannels} value={metrics.channels.connected.toLocaleString()} />
                <DetailRow label={copy.dashboard.fields.readyBindings} value={metrics.agentBindings.ready.toLocaleString()} />
                <DetailRow label={copy.dashboard.fields.pendingBindings} value={metrics.agentBindings.pending.toLocaleString()} />
                <DetailRow label={copy.dashboard.fields.errorBindings} value={metrics.agentBindings.error.toLocaleString()} />
              </div>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
