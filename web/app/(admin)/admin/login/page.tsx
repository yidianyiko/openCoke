'use client';

import { useState, type FormEvent } from 'react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { useLocale } from '../../../../components/locale-provider';
import { adminApi, type AdminLoginResult } from '../../../../lib/admin-api';
import { storeAdminSession } from '../../../../lib/admin-auth';
import { getAdminCopy } from '../../../../lib/admin-copy';

export default function AdminLoginPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const copy = getAdminCopy(locale);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setSubmitting(true);

    const formData = new FormData(event.currentTarget);
    const submittedEmail = String(formData.get('email') ?? email);
    const submittedPassword = String(formData.get('password') ?? password);

    try {
      const response = await adminApi.post<AdminLoginResult>('/api/admin/login', {
        email: submittedEmail,
        password: submittedPassword,
      });

      if (!response.ok) {
        if (response.error === 'invalid_credentials') {
          setError(copy.login.invalidCredentials);
        } else if (response.error === 'inactive_account') {
          setError(copy.login.inactiveAccount);
        } else {
          setError(copy.login.genericError);
        }
        return;
      }

      storeAdminSession(response.data);
      router.push('/admin/customers');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-navy-950 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center justify-center gap-3">
          <Image src="/logo.png" alt="ClawScale" width={32} height={32} className="h-8 w-8" />
          <div>
            <p className="text-xl font-semibold text-white">ClawScale</p>
            <p className="text-xs text-white/50">Admin backend MVP</p>
          </div>
        </div>

        <div className="card p-8">
          <h1 className="mb-1 text-xl font-semibold text-gray-900">{copy.login.title}</h1>
          <p className="mb-6 text-sm text-gray-500">{copy.login.description}</p>

          {error ? (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
              {error}
            </div>
          ) : null}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="label">
                {copy.login.emailLabel}
              </label>
              <input
                id="email"
                type="email"
                name="email"
                className="input"
                autoComplete="username"
                value={email}
                onInput={(event) => setEmail((event.target as HTMLInputElement).value)}
                required
              />
            </div>

            <div>
              <label htmlFor="password" className="label">
                {copy.login.passwordLabel}
              </label>
              <input
                id="password"
                type="password"
                name="password"
                className="input"
                autoComplete="current-password"
                value={password}
                onInput={(event) => setPassword((event.target as HTMLInputElement).value)}
                required
              />
            </div>

            <button type="submit" className="btn-primary w-full" disabled={submitting}>
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {submitting ? copy.login.submitting : copy.login.submit}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
