import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../../../components/locale-provider';

const openMock = vi.hoisted(() => vi.fn());
const replaceMock = vi.hoisted(() => vi.fn());
const routerMock = vi.hoisted(() => ({
  replace: replaceMock,
}));
const searchParamsMock = vi.hoisted(() => vi.fn(() => new URLSearchParams()));
const getPreflightMock = vi.hoisted(() => vi.fn());
const getPreflightForHandoffMock = vi.hoisted(() => vi.fn());
const startMock = vi.hoisted(() => vi.fn());
const getStatusMock = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useSearchParams: () => searchParamsMock(),
  useRouter: () => routerMock,
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock('../../../../lib/customer-google-calendar-import', () => ({
  getCustomerGoogleCalendarImportPreflight: (...args: unknown[]) => getPreflightMock(...args),
  getCustomerGoogleCalendarImportPreflightForHandoff: (...args: unknown[]) =>
    getPreflightForHandoffMock(...args),
  startCustomerGoogleCalendarImport: (...args: unknown[]) => startMock(...args),
  getCustomerGoogleCalendarImportStatusForRun: (...args: unknown[]) => getStatusMock(...args),
}));

import CalendarImportPage from './page';

function makeRunSummary(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'cir_1',
    status: 'succeeded' as const,
    providerAccountEmail: 'alice@example.com',
    importedCount: 3,
    skippedCount: 1,
    failedCount: 0,
    errorSummary: null,
    ...overrides,
  };
}

async function flushTicks(count: number) {
  for (let i = 0; i < count; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

describe('CustomerCalendarImportPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  function renderPage() {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CalendarImportPage />
        </LocaleProvider>,
      );
    });
  }

  beforeEach(() => {
    openMock.mockReset();
    replaceMock.mockReset();
    searchParamsMock.mockReset();
    searchParamsMock.mockReturnValue(new URLSearchParams());
    getPreflightMock.mockReset();
    getPreflightForHandoffMock.mockReset();
    startMock.mockReset();
    getStatusMock.mockReset();
    getPreflightMock.mockResolvedValue({
      ok: true,
      data: {
        ready: true,
        latestRun: null,
      },
    });
    getStatusMock.mockResolvedValue({
      ok: true,
      data: {
        run: null,
        latestRun: null,
      },
    });
    vi.spyOn(window, 'open').mockImplementation(openMock);
    window.history.replaceState({}, '', '/account/calendar-import');
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    root.unmount();
    container.remove();
  });

  it('shows the blocked conversation guidance when preflight requires an existing Kap conversation', async () => {
    getPreflightMock.mockResolvedValueOnce({
      ok: true,
      data: {
        ready: false,
        blockedReason: 'conversation_required',
        latestRun: null,
      },
    });

    renderPage();
    await flushTicks(3);

    expect(container.querySelector('.customer-view.customer-view--wide')).toBeTruthy();
    expect(container.querySelector('.customer-panel.customer-panel--wide')).toBeTruthy();
    expect(container.textContent).toContain('Start or resume a Kap conversation first');
    expect(container.textContent).toContain('Google Calendar import');
    expect(container.querySelector('button[type="button"]')).toBeNull();
  });

  it('shows the account recovery card when preflight is blocked for subscription renewal', async () => {
    getPreflightMock.mockResolvedValueOnce({
      ok: true,
      data: {
        ready: false,
        blockedReason: 'subscription_required',
        latestRun: null,
      },
    });

    renderPage();
    await flushTicks(3);

    expect(container.textContent).toContain('Renew your subscription before importing Google Calendar');
    expect(container.querySelector('a[href="/account/subscription"]')).toBeTruthy();
    expect(container.querySelector('button[type="button"]')).toBeNull();
  });

  it('redirects back to login when preflight returns an unauthorized response', async () => {
    getPreflightMock.mockResolvedValueOnce({
      ok: false,
      error: 'invalid_or_expired_token',
    });

    renderPage();
    await flushTicks(3);

    expect(replaceMock).toHaveBeenCalledWith('/auth/login?next=/account/calendar-import');
  });

  it('keeps runtime failures on-page instead of redirecting to login', async () => {
    getPreflightMock.mockResolvedValueOnce({
      ok: false,
      error: 'bridge_unavailable',
    });

    renderPage();
    await flushTicks(3);

    expect(replaceMock).not.toHaveBeenCalled();
    expect(container.textContent).toContain('Unable to load your Google Calendar import status right now.');
  });

  it('starts the import flow from the ready state and opens the returned Google auth URL', async () => {
    getPreflightMock.mockResolvedValueOnce({
      ok: true,
      data: {
        ready: true,
        latestRun: null,
      },
    });
    startMock.mockResolvedValueOnce({
      ok: true,
      data: {
        runId: 'cir_2',
        url: 'https://accounts.google.com/o/oauth2/v2/auth?state=test-state',
      },
    });

    renderPage();
    await flushTicks(3);

    const button = container.querySelector('button[type="button"]') as HTMLButtonElement | null;
    expect(button).toBeTruthy();
    button?.click();
    await flushTicks(3);

    expect(startMock).toHaveBeenCalledWith();
    expect(openMock).toHaveBeenCalledWith('https://accounts.google.com/o/oauth2/v2/auth?state=test-state', '_self');
  });

  it('uses the handoff token for preflight and start when present', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('handoff=tok_1'));
    getPreflightForHandoffMock.mockResolvedValueOnce({
      ok: true,
      data: {
        ready: true,
        latestRun: null,
      },
    });
    startMock.mockResolvedValueOnce({
      ok: true,
      data: {
        runId: 'cir_2',
        url: 'https://accounts.google.com/o/oauth2/v2/auth?state=test-state',
      },
    });

    renderPage();
    await flushTicks(3);

    const button = container.querySelector('button[type="button"]') as HTMLButtonElement | null;
    expect(button).toBeTruthy();
    button?.click();
    await flushTicks(3);

    expect(getPreflightForHandoffMock).toHaveBeenCalledWith('tok_1');
    expect(getPreflightMock).not.toHaveBeenCalled();
    expect(startMock).toHaveBeenCalledWith('tok_1');
  });

  it('shows the importing state with the latest run summary from preflight', async () => {
    getPreflightMock.mockResolvedValueOnce({
      ok: true,
      data: {
        ready: true,
        latestRun: makeRunSummary({
          status: 'importing',
          importedCount: 1,
          skippedCount: 0,
          failedCount: 0,
          errorSummary: null,
        }),
      },
    });

    renderPage();
    await flushTicks(3);

    expect(container.textContent).toContain('Importing your Google Calendar');
    expect(container.textContent).toContain('Imported 1, skipped 0, failed 0');
    expect(container.textContent).toContain('We are waiting for the Google callback to finish');
  });

  it('shows the success state for a completed import', async () => {
    getPreflightMock.mockResolvedValueOnce({
      ok: true,
      data: {
        ready: true,
        latestRun: makeRunSummary({
          status: 'succeeded',
          importedCount: 5,
          skippedCount: 2,
          failedCount: 0,
          errorSummary: null,
        }),
      },
    });

    renderPage();
    await flushTicks(3);

    expect(container.querySelector('.customer-run-summary')).toBeTruthy();
    expect(container.textContent).toContain('Import complete');
    expect(container.textContent).toContain('Imported 5, skipped 2, failed 0');
    expect(container.textContent).toContain('alice@example.com');
  });

  it('shows a partial-failure summary when the latest run completed with warnings', async () => {
    getPreflightMock.mockResolvedValueOnce({
      ok: true,
      data: {
        ready: true,
        latestRun: makeRunSummary({
          status: 'succeeded_with_errors',
          importedCount: 2,
          skippedCount: 1,
          failedCount: 1,
          errorSummary: 'unsupported_recurring_exceptions',
        }),
      },
    });

    renderPage();
    await flushTicks(3);

    expect(container.textContent).toContain('Completed with warnings');
    expect(container.textContent).toContain('unsupported_recurring_exceptions');
    expect(container.textContent).toContain('Imported 2, skipped 1, failed 1');
  });

  it('refreshes the latest run from the status endpoint after a callback redirect', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('googleCalendarImport=complete&runId=cir_3'));
    getPreflightMock.mockResolvedValueOnce({
      ok: true,
      data: {
        ready: true,
        latestRun: makeRunSummary({
          id: 'cir_old',
          status: 'importing',
          importedCount: 0,
          skippedCount: 0,
          failedCount: 0,
          errorSummary: null,
        }),
      },
    });
    getStatusMock.mockResolvedValueOnce({
      ok: true,
      data: {
        run: makeRunSummary({
          id: 'cir_3',
          status: 'succeeded',
          importedCount: 4,
          skippedCount: 0,
          failedCount: 0,
          errorSummary: null,
        }),
        latestRun: makeRunSummary({
          id: 'cir_other',
          status: 'succeeded_with_errors',
          importedCount: 2,
          skippedCount: 1,
          failedCount: 1,
          errorSummary: 'unsupported_recurring_exceptions',
        }),
      },
    });

    renderPage();
    await flushTicks(3);

    expect(getStatusMock).toHaveBeenCalledWith('cir_3');
    expect(container.textContent).toContain('Import complete');
    expect(container.textContent).toContain('Imported 4, skipped 0, failed 0');
  });

  it('shows a callback notice when the requested run summary is unavailable', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('googleCalendarImport=complete&runId=cir_3'));
    getPreflightMock.mockResolvedValueOnce({
      ok: true,
      data: {
        ready: true,
        latestRun: null,
      },
    });
    getStatusMock.mockResolvedValueOnce({
      ok: true,
      data: {
        run: null,
        latestRun: makeRunSummary({
          id: 'cir_other',
          status: 'succeeded',
          importedCount: 9,
          skippedCount: 0,
          failedCount: 0,
          errorSummary: null,
        }),
      },
    });

    renderPage();
    await flushTicks(3);

    expect(getStatusMock).toHaveBeenCalledWith('cir_3');
    expect(container.textContent).toContain('Unable to load the matching import summary for this callback');
    expect(container.textContent).not.toContain('Imported 9, skipped 0, failed 0');
  });
});
