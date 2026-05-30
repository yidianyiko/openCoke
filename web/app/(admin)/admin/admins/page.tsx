'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { Loader2, Trash2, UserPlus } from 'lucide-react';
import { useLocale } from '../../../../components/locale-provider';
import { adminApi, type AdminAccountRecord } from '../../../../lib/admin-api';
import { getAdminCopy } from '../../../../lib/admin-copy';
import { formatDateTime } from '../../../../lib/utils';

type CreateAdminForm = {
  email: string;
  password: string;
};

export default function AdminAdminsPage() {
  const { locale } = useLocale();
  const copy = getAdminCopy(locale);
  const [rows, setRows] = useState<AdminAccountRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<CreateAdminForm>({
    email: '',
    password: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [loadError, setLoadError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;

    async function loadAdmins() {
      setLoading(true);
      setLoadError('');
      const response = await adminApi.get<AdminAccountRecord[]>('/api/admin/admins');
      if (!active) {
        return;
      }

      if (!response.ok) {
        setRows([]);
        setLoadError(response.error || copy.admins.genericError);
        setLoading(false);
        return;
      }

      setRows(response.data);
      setLoading(false);
    }

    void loadAdmins();
    return () => {
      active = false;
    };
  }, [copy.admins.genericError, reloadKey]);

  async function handleCreateAdmin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError('');

    const formData = new FormData(event.currentTarget);
    const payload = {
      email: String(formData.get('email') ?? createForm.email),
      password: String(formData.get('password') ?? createForm.password),
    };

    try {
      const response = await adminApi.post<AdminAccountRecord>('/api/admin/admins', payload);
      if (!response.ok) {
        setError(copy.admins.genericError);
        return;
      }

      setRows((current) => [...current, response.data]);
      setCreateForm({ email: '', password: '' });
      setShowCreate(false);
    } finally {
      setSaving(false);
    }
  }

  async function handleRemoveAdmin(id: string) {
    if (!confirm(copy.admins.confirmRemove)) {
      return;
    }

    const response = await adminApi.delete<{ id: string }>('/api/admin/admins/' + id);
    if (!response.ok) {
      setError(copy.admins.genericError);
      return;
    }

    setRows((current) => current.filter((row) => row.id !== id));
  }

  return (
    <div className="p-8">
      <div className="mb-8 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">{copy.admins.title}</h1>
          <p className="mt-1 text-gray-500">{copy.admins.subtitle}</p>
        </div>
        <button
          type="button"
          className="btn-primary"
          data-testid="open-add-admin"
          onClick={() => setShowCreate(true)}
        >
          <UserPlus className="h-4 w-4" />
          {copy.admins.addAdmin}
        </button>
      </div>

      {showCreate ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="card w-full max-w-md p-6">
            <h2 className="mb-4 text-lg font-semibold text-gray-900">{copy.admins.addTitle}</h2>

            <form onSubmit={handleCreateAdmin} className="space-y-4">
              <div>
                <label htmlFor="admin-email" className="label">
                  {copy.admins.emailLabel}
                </label>
                <input
                  id="admin-email"
                  name="email"
                  className="input"
                  type="email"
                  value={createForm.email}
                  onInput={(event) =>
                    setCreateForm((current) => ({
                      ...current,
                      email: (event.target as HTMLInputElement).value,
                    }))
                  }
                  required
                />
              </div>

              <div>
                <label htmlFor="admin-password" className="label">
                  {copy.admins.passwordLabel}
                </label>
                <input
                  id="admin-password"
                  name="password"
                  className="input"
                  type="password"
                  minLength={8}
                  value={createForm.password}
                  onInput={(event) =>
                    setCreateForm((current) => ({
                      ...current,
                      password: (event.target as HTMLInputElement).value,
                    }))
                  }
                  required
                />
              </div>

              <div className="flex items-center gap-3 pt-2">
                <button type="submit" className="btn-primary flex-1" disabled={saving}>
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  {copy.admins.createSubmit}
                </button>
                <button
                  type="button"
                  className="btn-secondary flex-1"
                  onClick={() => setShowCreate(false)}
                >
                  {copy.common.cancel}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      <div className="card overflow-hidden">
        {error ? (
          <div className="border-b border-red-100 bg-red-50 px-5 py-3 text-sm text-red-600">{error}</div>
        ) : null}

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-teal-500" />
          </div>
        ) : loadError ? (
          <div className="px-5 py-8">
            <p className="text-sm text-red-600">
              {copy.common.errorPrefix}: {loadError}
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
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/50">
                <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.admins.columns.email}</th>
                <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.admins.columns.status}</th>
                <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.admins.columns.createdAt}</th>
                <th className="px-5 py-3 text-left font-medium text-gray-500">{copy.admins.columns.updatedAt}</th>
                <th className="px-5 py-3 text-right font-medium text-gray-500">{copy.admins.columns.actions}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-8 text-center text-gray-500">
                    {copy.common.empty}
                  </td>
                </tr>
              ) : (
                rows.map((row) => (
                  <tr key={row.id}>
                    <td className="px-5 py-3.5 text-gray-900">{row.email}</td>
                    <td className="px-5 py-3.5 text-gray-600">
                      {row.isActive ? copy.admins.statusLabels.active : copy.admins.statusLabels.inactive}
                    </td>
                    <td className="px-5 py-3.5 text-gray-600">{formatDateTime(row.createdAt)}</td>
                    <td className="px-5 py-3.5 text-gray-600">{formatDateTime(row.updatedAt)}</td>
                    <td className="px-5 py-3.5 text-right">
                      <button
                        type="button"
                        className="text-gray-400 transition-colors hover:text-red-500"
                        title={copy.admins.removeTitle}
                        aria-label={copy.admins.removeTitle}
                        data-admin-id={row.id}
                        onClick={() => void handleRemoveAdmin(row.id)}
                      >
                        <Trash2 className="ml-auto h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
