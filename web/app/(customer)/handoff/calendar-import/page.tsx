'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { claimCustomerCalendarImportHandoff } from '../../../../lib/customer-google-calendar-import';

function CustomerCalendarImportHandoffContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [message, setMessage] = useState('正在确认你的 WhatsApp 身份...');

  useEffect(() => {
    const token = searchParams.get('token')?.trim() ?? '';
    if (!token) {
      setMessage('这个导入链接无效，请回到 WhatsApp 重新生成。');
      return;
    }

    let cancelled = false;
    async function claim() {
      const next = `/handoff/calendar-import?token=${encodeURIComponent(token)}`;
      try {
        const res = await claimCustomerCalendarImportHandoff(token);
        if (cancelled) return;

        if (res.ok) {
          router.replace(res.data.continue_to);
          return;
        }

        if (
          res.error === 'unauthorized' ||
          res.error === 'invalid_or_expired_token' ||
          res.error === 'account_not_found'
        ) {
          router.replace(`/auth/login?next=${encodeURIComponent(next)}`);
          return;
        }

        if (res.error === 'account_not_active') {
          router.replace(`/auth/login?next=${encodeURIComponent(next)}&verification=retry`);
          return;
        }

        setMessage(
          res.error === 'identity_already_bound'
            ? '这个 WhatsApp 已绑定到另一个邮箱账号，请使用原账号登录。'
            : '这个导入链接已失效，请回到 WhatsApp 重新生成。',
        );
      } catch {
        if (!cancelled) {
          router.replace(`/auth/login?next=${encodeURIComponent(next)}`);
        }
      }
    }

    void claim();
    return () => {
      cancelled = true;
    };
  }, [router, searchParams]);

  return (
    <section className="customer-view customer-view--narrow">
      <div className="customer-panel">
        <div className="customer-panel__head">
          <p className="customer-panel__eyebrow">WhatsApp handoff</p>
          <h1 className="customer-panel__title">Google Calendar import</h1>
          <p className="customer-panel__body">{message}</p>
        </div>
      </div>
    </section>
  );
}

export default function CustomerCalendarImportHandoffPage() {
  return (
    <Suspense fallback={null}>
      <CustomerCalendarImportHandoffContent />
    </Suspense>
  );
}
