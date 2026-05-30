'use client';

import Link from 'next/link';
import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  getCustomerGoogleCalendarImportPreflight,
  getCustomerGoogleCalendarImportPreflightForHandoff,
  getCustomerGoogleCalendarImportStatusForRun,
  startCustomerGoogleCalendarImport,
  type CustomerGoogleCalendarImportPreflightResult,
  type CustomerGoogleCalendarImportRunSummary,
} from '../../../../lib/customer-google-calendar-import';

function formatRunSummary(run: CustomerGoogleCalendarImportRunSummary): string {
  return `Imported ${run.importedCount}, skipped ${run.skippedCount}, failed ${run.failedCount}`;
}

function getRunTitle(run: CustomerGoogleCalendarImportRunSummary): string {
  if (run.status === 'authorizing' || run.status === 'importing') {
    return 'Importing your Google Calendar';
  }

  if (run.status === 'succeeded_with_errors') {
    return 'Completed with warnings';
  }

  if (run.status === 'failed') {
    return 'Import failed';
  }

  return 'Import complete';
}

function getRunDescription(run: CustomerGoogleCalendarImportRunSummary): string {
  if (run.status === 'authorizing' || run.status === 'importing') {
    return 'We are waiting for the Google callback to finish.';
  }

  if (run.status === 'succeeded_with_errors') {
    return run.errorSummary
      ? `Some events completed with warnings. Latest warning: ${run.errorSummary}.`
      : 'Some events completed with warnings.';
  }

  if (run.status === 'failed') {
    return run.errorSummary
      ? `The latest import failed. ${run.errorSummary}.`
      : 'The latest import failed.';
  }

  return 'Your latest calendar import finished successfully.';
}

function getPreflightDescription(preflight: CustomerGoogleCalendarImportPreflightResult): string {
  if (!preflight.ready) {
    return getBlockedState(preflight.blockedReason)?.description ?? 'Resolve account access before starting the import.';
  }

  return 'Connect Google Calendar to the active Kap conversation for this customer account.';
}

function getBlockedState(blockedReason: string | null | undefined): {
  title: string;
  description: string;
  ctaHref: string;
  ctaLabel: string;
} | null {
  switch (blockedReason) {
    case 'conversation_required':
      return {
        title: 'Conversation required',
        description: 'Start or resume a Kap conversation first, then return here to launch the Google Calendar import.',
        ctaHref: '/channels/wechat-personal',
        ctaLabel: 'Open customer channels',
      };
    case 'subscription_required':
      return {
        title: 'Subscription required',
        description: 'Renew your subscription before importing Google Calendar.',
        ctaHref: '/account/subscription',
        ctaLabel: 'Manage subscription',
      };
    case 'email_not_verified':
      return {
        title: 'Email verification required',
        description: 'Verify your email before importing Google Calendar.',
        ctaHref: '/account/subscription',
        ctaLabel: 'Review account access',
      };
    case 'account_suspended':
      return {
        title: 'Account access is suspended',
        description: 'This customer account is suspended. Review your account status before importing Google Calendar.',
        ctaHref: '/account/subscription',
        ctaLabel: 'Review account status',
      };
    default:
      return null;
  }
}

function CustomerCalendarImportPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const callbackState = searchParams.get('googleCalendarImport');
  const callbackRunId = searchParams.get('runId');
  const handoffToken = searchParams.get('handoff')?.trim() || undefined;
  const [preflight, setPreflight] = useState<CustomerGoogleCalendarImportPreflightResult | null>(null);
  const [latestRun, setLatestRun] = useState<CustomerGoogleCalendarImportRunSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const [summaryNotice, setSummaryNotice] = useState('');
  const pageClassName = 'customer-view customer-view--wide';
  const panelClassName = 'customer-panel customer-panel--wide';
  const primaryActionClassName = 'customer-action customer-action--primary';

  useEffect(() => {
    let cancelled = false;

    async function loadImportState() {
      setLoading(true);
      setError('');
      setSummaryNotice('');

      try {
        const preflightRes = handoffToken
          ? await getCustomerGoogleCalendarImportPreflightForHandoff(handoffToken)
          : await getCustomerGoogleCalendarImportPreflight();

        if (cancelled) {
          return;
        }

        if (!preflightRes.ok) {
          if (
            preflightRes.error === 'invalid_or_expired_token' ||
            preflightRes.error === 'unauthorized' ||
            preflightRes.error === 'account_not_found'
          ) {
            router.replace(
              handoffToken
                ? `/auth/login?next=${encodeURIComponent(
                    `/handoff/calendar-import?token=${encodeURIComponent(handoffToken)}`,
                  )}`
                : '/auth/login?next=/account/calendar-import',
            );
            return;
          }

          setError('Unable to load your Google Calendar import status right now.');
          return;
        }

        setPreflight(preflightRes.data);
        setLatestRun(preflightRes.data.latestRun);

        if (callbackState) {
          const statusRes = await getCustomerGoogleCalendarImportStatusForRun(callbackRunId ?? undefined);
          if (!cancelled && statusRes.ok) {
            const callbackRun = callbackRunId ? statusRes.data.run ?? null : statusRes.data.latestRun;
            setLatestRun(callbackRunId ? callbackRun : callbackRun ?? preflightRes.data.latestRun);
            setSummaryNotice(
              callbackRunId && !callbackRun
                ? 'Unable to load the matching import summary for this callback right now.'
                : '',
            );
          }
        }
      } catch {
        if (!cancelled) {
          setError('Unable to load your Google Calendar import status right now.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadImportState();

    return () => {
      cancelled = true;
    };
  }, [callbackRunId, callbackState, handoffToken, router]);

  const readyToStart = preflight?.ready === true;
  const blockedState = preflight?.ready === false ? getBlockedState(preflight.blockedReason) : null;
  const importing = latestRun?.status === 'authorizing' || latestRun?.status === 'importing';
  const showStartButton = readyToStart && !loading && !importing;
  const run = latestRun;
  const runTone =
    importing ? 'customer-run-summary--info' : run?.status === 'succeeded_with_errors'
      ? 'customer-run-summary--warning'
      : run?.status === 'failed'
        ? 'customer-run-summary--error'
        : 'customer-run-summary--success';

  async function handleStartImport() {
    setStarting(true);
    setError('');

    try {
      const res = handoffToken
        ? await startCustomerGoogleCalendarImport(handoffToken)
        : await startCustomerGoogleCalendarImport();
      if (!res.ok) {
        setError('Unable to start the Google Calendar import right now.');
        return;
      }

      window.open(res.data.url, '_self');
    } catch {
      setError('Unable to start the Google Calendar import right now.');
    } finally {
      setStarting(false);
    }
  }

  return (
    <section className={pageClassName}>
      <div className={panelClassName}>
        <div className="customer-panel__head">
          <p className="customer-panel__eyebrow">Google Calendar import</p>
          <h1 className="customer-panel__title">Import your Google Calendar</h1>
          <p className="customer-panel__body">
            {preflight ? getPreflightDescription(preflight) : 'Checking import readiness for this customer account.'}
          </p>
        </div>

        {callbackState ? (
          <div className="customer-inline-note">
            {callbackState === 'error'
              ? 'The Google authorization callback reported an error. The latest import summary is shown below.'
              : 'Google authorization finished. Refreshing the latest import summary.'}
          </div>
        ) : null}

        {loading ? (
          <p className="customer-inline-note">Loading your Google Calendar import status...</p>
        ) : error ? (
          <p className="customer-inline-note customer-inline-note--error">{error}</p>
        ) : null}

        {!loading && !error && blockedState ? (
          <div className="customer-inline-note customer-inline-note--warning">
            <h2 className="customer-inline-note__title">{blockedState.title}</h2>
            <p>{blockedState.description}</p>
            <Link href={blockedState.ctaHref} className="customer-action customer-action--secondary">
              {blockedState.ctaLabel}
            </Link>
          </div>
        ) : null}

        {!loading && !error && summaryNotice ? <div className="customer-inline-note">{summaryNotice}</div> : null}

        {!loading && !error && run ? (
          <div className={`customer-run-summary ${runTone}`}>
            <p className="customer-run-summary__eyebrow">{getRunTitle(run)}</p>
            <p>{getRunDescription(run)}</p>
            <p>{formatRunSummary(run)}</p>
            {run.providerAccountEmail ? <p>Connected account: {run.providerAccountEmail}</p> : null}
          </div>
        ) : null}

        {!loading && !error && !blockedState && !run ? (
          <p className="customer-inline-note">No calendar import has run yet.</p>
        ) : null}

        {showStartButton ? (
          <button type="button" onClick={handleStartImport} disabled={starting} className={primaryActionClassName}>
            {starting ? 'Starting Google Calendar import...' : 'Start Google Calendar import'}
          </button>
        ) : null}
      </div>
    </section>
  );
}

export default function CustomerCalendarImportPage() {
  return (
    <Suspense fallback={null}>
      <CustomerCalendarImportPageContent />
    </Suspense>
  );
}
