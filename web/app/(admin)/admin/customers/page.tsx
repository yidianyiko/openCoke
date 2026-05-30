'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { useLocale } from '../../../../components/locale-provider';
import { adminApi, type AdminCustomerRow, type AdminPagedResult } from '../../../../lib/admin-api';
import { getAdminCopy } from '../../../../lib/admin-copy';
import { formatDateTime } from '../../../../lib/utils';

const PAGE_SIZE = 50;

function getPagingSummary(total: number, offset: number, limit: number, summarize: (from: number, to: number, total: number) => string) {
  if (total === 0) {
    return summarize(0, 0, 0);
  }

  return summarize(offset + 1, Math.min(offset + limit, total), total);
}

export default function AdminCustomersPage() {
  const { locale } = useLocale();
  const copy = getAdminCopy(locale);
  const [rows, setRows] = useState<AdminCustomerRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;

    async function loadCustomers() {
      setLoading(true);
      setError('');
      const response = await adminApi.get<AdminPagedResult<AdminCustomerRow>>(
        '/api/admin/customers?limit=' + PAGE_SIZE + '&offset=' + offset,
      );

      if (!active) {
        return;
      }

      if (!response.ok) {
        setError(response.error);
        setRows([]);
        setTotal(0);
        setLoading(false);
        return;
      }

      setRows(response.data.rows);
      setTotal(response.data.total);
      setLoading(false);
    }

    void loadCustomers();
    return () => {
      active = false;
    };
  }, [offset, reloadKey]);

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-gray-900">{copy.customers.title}</h1>
        <p className="mt-1 text-gray-500">{copy.customers.subtitle}</p>
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
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.customers.columns.customer}</th>
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.customers.columns.lastMessage}</th>
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.customers.columns.messageCount}</th>
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.customers.columns.contactIdentifier}</th>
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.customers.columns.claimStatus}</th>
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.customers.columns.parkedInbounds}</th>
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.customers.columns.registered}</th>
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.customers.columns.firstSeen}</th>
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.customers.columns.agent}</th>
                  <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.customers.columns.channels}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="px-5 py-8 text-center text-gray-500">
                      {copy.common.empty}
                    </td>
                  </tr>
                ) : (
                  rows.map((row) => (
                    <tr key={row.id} className="align-top">
                      <td className="px-5 py-3.5">
                        <div className="font-medium text-gray-900">{row.displayName}</div>
                        <div className="text-xs text-gray-400">{row.id}</div>
                      </td>
                      <td className="px-5 py-3.5 text-gray-600">
                        {row.lastMessageAt ? formatDateTime(row.lastMessageAt) : '—'}
                        <div className="text-xs text-gray-400">
                          {row.conversationCount} conversation{row.conversationCount === 1 ? '' : 's'}
                        </div>
                      </td>
                      <td className="px-5 py-3.5 text-gray-600">{row.messageCount}</td>
                      <td className="px-5 py-3.5 text-gray-600">
                        <div>{row.contactIdentifier.value || 'Unknown'}</div>
                        <div className="text-xs text-gray-400">{row.contactIdentifier.type}</div>
                      </td>
                      <td className="px-5 py-3.5 text-gray-600">{row.claimStatus}</td>
                      <td className="px-5 py-3.5 text-gray-600">{row.parkedInboundCount}</td>
                      <td className="px-5 py-3.5 text-gray-600">{formatDateTime(row.registeredAt)}</td>
                      <td className="px-5 py-3.5 text-gray-600">
                        {row.firstSeenAt ? formatDateTime(row.firstSeenAt) : '—'}
                      </td>
                      <td className="px-5 py-3.5 text-gray-600">
                        {row.agent ? (
                          <>
                            <div>{row.agent.name}</div>
                            <div className="text-xs text-gray-400">{row.agent.provisionStatus}</div>
                          </>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="px-5 py-3.5 text-gray-600">
                        <div>{row.channelSummary.kinds.join(', ') || '—'}</div>
                        <div className="text-xs text-gray-400">
                          {row.channelSummary.connected} connected / {row.channelSummary.disconnected} disconnected
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>

            <div className="flex items-center justify-between border-t border-gray-100 px-5 py-3 text-sm text-gray-500">
              <span>{getPagingSummary(total, offset, PAGE_SIZE, copy.paging.summary)}</span>
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
