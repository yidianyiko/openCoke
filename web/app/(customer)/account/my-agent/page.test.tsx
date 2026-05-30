import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';
import { LocaleProvider } from '../../../../components/locale-provider';

const replaceMock = vi.hoisted(() => vi.fn());
const getMock = vi.hoisted(() => vi.fn());
const updateMock = vi.hoisted(() => vi.fn());
const resetMock = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock('../../../../lib/customer-agent-instance', () => ({
  getCustomerAgentInstance: (...args: unknown[]) => getMock(...args),
  updateCustomerAgentInstance: (...args: unknown[]) => updateMock(...args),
  resetCustomerAgentInstance: (...args: unknown[]) => resetMock(...args),
}));

import MyAgentPage from './page';

function agentPayload(overrides: Record<string, unknown> = {}) {
  return {
    agent_instance: {
      agent_instance_id: 'agentinst_1',
      owner_user_id: 'ck_123',
      base_agent_type: 'coke_companion',
      base_character_id: 'char_1',
      active: true,
      display_name: 'Shen Wang',
      nickname: null,
      user_address_name: 'Sister',
      persona: 'custom persona',
      background: '',
      speaking_style: 'quiet',
      extra_rules: '',
      status: { place: 'desk', action: 'keeping company' },
      proactive: { enabled: false },
      memory: { enabled: true },
    },
    effective_profile: {
      display_name: 'Shen Wang',
      nickname: 'Shen Wang',
      user_address_name: 'Sister',
      persona: 'custom persona',
      background: null,
      speaking_style: 'quiet',
      extra_rules: null,
      status: { place: 'desk', action: 'keeping company' },
      proactive: { enabled: false },
      memory: { enabled: true },
    },
    ...overrides,
  };
}

async function flushTicks(count = 3) {
  for (let i = 0; i < count; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

describe('CustomerMyAgentPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  function renderPage(locale: 'en' | 'zh' = 'en') {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale={locale}>
          <MyAgentPage />
        </LocaleProvider>,
      );
    });
  }

  beforeEach(() => {
    replaceMock.mockReset();
    getMock.mockReset();
    updateMock.mockReset();
    resetMock.mockReset();
    getMock.mockResolvedValue({ ok: true, data: agentPayload() });
    updateMock.mockResolvedValue({
      ok: true,
      data: agentPayload({
        effective_profile: { ...agentPayload().effective_profile, display_name: 'New name' },
      }),
    });
    resetMock.mockResolvedValue({
      ok: true,
      data: agentPayload({
        agent_instance: { ...agentPayload().agent_instance, display_name: null },
      }),
    });
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('loads and renders the current agent settings', async () => {
    renderPage();
    await flushTicks();

    expect(getMock).toHaveBeenCalledOnce();
    expect(container.textContent).toContain('My Agent');
    expect(container.textContent).toContain('4/7');
    expect((container.querySelector('input[name="display_name"]') as HTMLInputElement).value).toBe('Shen Wang');
    expect((container.querySelector('input[name="nickname"]') as HTMLInputElement).value).toBe('');
    expect((container.querySelector('input[name="user_address_name"]') as HTMLInputElement).value).toBe('Sister');
    expect((container.querySelector('textarea[name="persona"]') as HTMLTextAreaElement).value).toBe('custom persona');
    expect((container.querySelector('input[name="proactive"]') as HTMLInputElement).checked).toBe(false);
  });

  it('redirects auth failures to login with the my-agent next path', async () => {
    getMock.mockResolvedValueOnce({ ok: false, error: 'invalid_or_expired_token' });

    renderPage();
    await flushTicks();

    expect(replaceMock).toHaveBeenCalledWith('/auth/login?next=/account/my-agent');
  });

  it('shows a terminal empty state for generic load failures', async () => {
    getMock.mockResolvedValueOnce({ ok: false, error: 'upstream_unavailable' });

    renderPage();
    await flushTicks();

    expect(replaceMock).not.toHaveBeenCalled();
    expect(container.textContent).toContain('Unable to load agent settings right now.');
    expect(container.textContent).not.toContain('Loading...');
  });

  it('saves edited fields through the customer API helper', async () => {
    renderPage();
    await flushTicks();

    const displayName = container.querySelector('input[name="display_name"]') as HTMLInputElement;
    displayName.value = ' New name ';
    displayName.dispatchEvent(new Event('input', { bubbles: true }));
    const nickname = container.querySelector('input[name="nickname"]') as HTMLInputElement;
    nickname.value = '   ';
    nickname.dispatchEvent(new Event('input', { bubbles: true }));
    const form = container.querySelector('form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await flushTicks();

    expect(updateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        display_name: 'New name',
        nickname: null,
        user_address_name: 'Sister',
        persona: 'custom persona',
        status: { place: 'desk', action: 'keeping company' },
        proactive: { enabled: false },
        memory: { enabled: true },
      }),
    );
    expect(container.textContent).toContain('Agent settings saved.');
  });

  it('does not echo inherited defaults into persisted override fields on save', async () => {
    getMock.mockResolvedValueOnce({
      ok: true,
      data: agentPayload({
        agent_instance: {
          ...agentPayload().agent_instance,
          display_name: null,
          nickname: null,
          user_address_name: null,
          persona: null,
          background: null,
          speaking_style: null,
          extra_rules: null,
          status: { place: null, action: null },
          proactive: { enabled: null },
          memory: { enabled: null },
        },
        effective_profile: {
          display_name: 'Default Agent',
          nickname: 'Default Nickname',
          user_address_name: 'Friend',
          persona: 'inherited persona',
          background: 'inherited background',
          speaking_style: 'inherited style',
          extra_rules: 'inherited rules',
          status: { place: 'inherited place', action: 'inherited action' },
          proactive: { enabled: false },
          memory: { enabled: true },
        },
      }),
    });

    renderPage();
    await flushTicks();

    expect(container.textContent).toContain('Default Agent');
    expect((container.querySelector('input[name="display_name"]') as HTMLInputElement).value).toBe('');
    expect((container.querySelector('input[name="nickname"]') as HTMLInputElement).value).toBe('');
    expect((container.querySelector('input[name="user_address_name"]') as HTMLInputElement).value).toBe('');
    expect((container.querySelector('textarea[name="persona"]') as HTMLTextAreaElement).value).toBe('');
    expect((container.querySelector('input[name="proactive"]') as HTMLInputElement).checked).toBe(false);
    expect((container.querySelector('input[name="memory"]') as HTMLInputElement).checked).toBe(true);

    const persona = container.querySelector('textarea[name="persona"]') as HTMLTextAreaElement;
    persona.value = ' explicit persona ';
    persona.dispatchEvent(new Event('input', { bubbles: true }));

    (container.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true }),
    );
    await flushTicks();

    expect(updateMock).toHaveBeenCalledWith({
      display_name: null,
      nickname: null,
      user_address_name: null,
      persona: 'explicit persona',
      background: null,
      speaking_style: null,
      extra_rules: null,
      status: { place: null, action: null },
      proactive: null,
      memory: null,
    });
  });

  it('resets settings and keeps the account data intact', async () => {
    renderPage();
    await flushTicks();

    const resetButton = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Reset');
    resetButton?.click();
    await flushTicks();

    expect(resetMock).toHaveBeenCalledOnce();
    expect(container.textContent).toContain('Agent settings saved.');
  });

  it('shows save failure without leaving the page', async () => {
    updateMock.mockResolvedValueOnce({ ok: false, error: 'invalid_body' });

    renderPage();
    await flushTicks();
    (container.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true }),
    );
    await flushTicks();

    expect(replaceMock).not.toHaveBeenCalled();
    expect(container.textContent).toContain('Unable to save agent settings right now.');
  });
});
