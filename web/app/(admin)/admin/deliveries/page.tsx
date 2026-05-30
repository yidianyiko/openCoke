'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { Loader2 } from 'lucide-react';
import { useLocale } from '../../../../components/locale-provider';
import { adminApi, type AdminDeliveryRow, type AdminPagedResult } from '../../../../lib/admin-api';
import { getAdminCopy } from '../../../../lib/admin-copy';
import { formatDateTime } from '../../../../lib/utils';

const PAGE_SIZE = 10;

function getPagingSummary(total: number, offset: number, visibleCount: number, summarize: (from: number, to: number, total: number) => string) {
  if (total === 0 || visibleCount === 0) {
    return summarize(0, 0, total);
  }

  return summarize(offset + 1, offset + visibleCount, total);
}

export default function AdminDeliveriesPage() {
  const { locale } = useLocale();
  const copy = getAdminCopy(locale);
  const [rows, setRows] = useState<AdminDeliveryRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [draftChannelId, setDraftChannelId] = useState('');
  const [channelId, setChannelId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;

    async function loadDeliveries() {
      setLoading(true);
      setError('');
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(offset),
      });

      if (channelId) {
        params.set('channelId', channelId);
      }

      const response = await adminApi.get<AdminPagedResult<AdminDeliveryRow>>(
        '/api/admin/deliveries?' + params.toString(),
      );

      if (!active) {
        return;
      }

      if (!response.ok) {
        setRows([]);
        setTotal(0);
        setError(response.error);
        setLoading(false);
        return;
      }

      setError('');

      setRows(response.data.rows);
      setTotal(response.data.total);
      setLoading(false);
    }

    void loadDeliveries();
    return () => {
      active = false;
    };
  }, [channelId, offset, reloadKey]);

  function applyFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setOffset(0);
    setChannelId(draftChannelId.trim());
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-gray-900">{copy.deliveries.title}</h1>
        <p className="mt-1 text-gray-500">{copy.deliveries.subtitle}</p>
      </div>

      <div className="card mb-4 p-4">
        <form onSubmit={applyFilter} className="flex flex-col gap-4 md:flex-row md:items-end">
          <div className="flex-1">
            <label htmlFor="channel-id-filter" className="label">
              {copy.deliveries.filters.channelId}
            </label>
            <input
              id="channel-id-filter"
              name="channelId"
              className="input"
              value={draftChannelId}
              onChange={(event) => setDraftChannelId(event.target.value)}
            />
          </div>
          <button type="submit" className="btn-primary">
            {copy.deliveries.filters.apply}
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              setDraftChannelId('');
              setChannelId('');
              setOffset(0);
            }}
          >
            {copy.deliveries.filters.clear}
          </button>
        </form>
      </div>

      <div className="card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-teal-500" />
          </div>
        ) : error ? (
          <div className="px-5 py-8">
            <p className="text-sm text-red-600">
              {copy.common.errorPrefix}: {error}
            </p>
            <button
              type="button"
              className="btn-secondary mt-4"
              data-testid="retry-load"
              onClick={() => setReloadKey((current) => current + 1)}
            >
              {copy.common.retry}
            </button>
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50/50">
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.deliveries.columns.delivery}</th>
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.deliveries.columns.tenantId}</th>
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.deliveries.columns.channelId}</th>
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.deliveries.columns.idempotencyKey}</th>
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.deliveries.columns.error}</th>
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.deliveries.columns.updated}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-8 text-center text-gray-500">
                      {copy.common.empty}
                    </td>
                  </tr>
                ) : (
                  rows.map((row) => (
                    <tr key={row.id}>
                      <td className="px-5 py-3.5 text-gray-900">
                        <div className="font-medium">{row.id}</div>
                        <div className="text-xs text-gray-400">{row.status}</div>
                      </td>
                      <td className="px-5 py-3.5 text-gray-600">{row.tenantId ?? '—'}</td>
                      <td className="px-5 py-3.5 text-gray-600">{row.channelId ?? '—'}</td>
                      <td className="px-5 py-3.5 text-gray-600">{row.idempotencyKey}</td>
                      <td className="px-5 py-3.5 text-gray-600">{row.error ?? '—'}</td>
                      <td className="px-5 py-3.5 text-gray-600">{formatDateTime(row.updatedAt)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>

            <div className="flex items-center justify-between border-t border-gray-100 px-5 py-3 text-sm text-gray-500">
              <span>{getPagingSummary(total, offset, rows.length, copy.paging.summary)}</span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="btn-secondary"
                  aria-label="Previous page"
                  disabled={offset === 0}
                  onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
                >
                  {copy.paging.previous}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  aria-label="Next page"
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => setOffset((current) => current + PAGE_SIZE)}
                >
                  {copy.paging.next}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
