import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import { LocaleProvider } from '../../../../components/locale-provider';

const replaceMock = vi.hoisted(() => vi.fn());
const routerMock = vi.hoisted(() => ({
  replace: replaceMock,
}));
const searchParamsMock = vi.hoisted(() => vi.fn(() => new URLSearchParams()));
const claimMock = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useSearchParams: () => searchParamsMock(),
  useRouter: () => routerMock,
}));

vi.mock('../../../../lib/customer-google-calendar-import', () => ({
  claimCustomerCalendarImportHandoff: (...args: unknown[]) => claimMock(...args),
}));

import CalendarImportHandoffPage from './page';

async function flushTicks(count: number) {
  for (let i = 0; i < count; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

describe('CustomerCalendarImportHandoffPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  function renderPage() {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CalendarImportHandoffPage />
        </LocaleProvider>,
      );
    });
  }

  beforeEach(() => {
    vi.clearAllMocks();
    searchParamsMock.mockReturnValue(new URLSearchParams('token=tok_1'));
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('claims the whatsapp handoff and continues to calendar import with the same token', async () => {
    claimMock.mockResolvedValueOnce({
      ok: true,
      data: {
        status: 'claimed',
        continue_to: '/account/calendar-import?handoff=tok_1',
      },
    });

    renderPage();
    await flushTicks(2);

    expect(claimMock).toHaveBeenCalledWith('tok_1');
    expect(replaceMock).toHaveBeenCalledWith('/account/calendar-import?handoff=tok_1');
  });

  it('routes unauthenticated users to login with the handoff link as next', async () => {
    claimMock.mockResolvedValueOnce({
      ok: false,
      error: 'unauthorized',
    });

    renderPage();
    await flushTicks(2);

    expect(replaceMock).toHaveBeenCalledWith(
      '/auth/login?next=%2Fhandoff%2Fcalendar-import%3Ftoken%3Dtok_1',
    );
  });

  it('does not call the API when the token is missing', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams());

    renderPage();
    await flushTicks(1);

    expect(claimMock).not.toHaveBeenCalled();
    expect(container.textContent).toContain('这个导入链接无效');
  });
});
