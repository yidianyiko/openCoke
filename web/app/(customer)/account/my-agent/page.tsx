'use client';

import { useRouter } from 'next/navigation';
import { type FormEvent, useCallback, useEffect, useState } from 'react';

import { useLocale } from '../../../../components/locale-provider';
import {
  getCustomerAgentInstance,
  resetCustomerAgentInstance,
  updateCustomerAgentInstance,
  type CustomerAgentInstance,
  type CustomerAgentInstanceResult,
} from '../../../../lib/customer-agent-instance';

const AUTH_ERRORS = new Set(['invalid_or_expired_token', 'unauthorized', 'account_not_found', 'claim_inactive']);
const LOGIN_NEXT_PATH = '/auth/login?next=/account/my-agent';

type FormState = {
  display_name: string;
  nickname: string;
  user_address_name: string;
  persona: string;
  background: string;
  speaking_style: string;
  extra_rules: string;
  status_place: string;
  status_action: string;
  proactive_enabled: boolean;
  proactive_overridden: boolean;
  memory_enabled: boolean;
  memory_overridden: boolean;
};

function formFromInstance(
  instance: CustomerAgentInstance,
  effective: CustomerAgentInstanceResult['effective_profile'],
): FormState {
  return {
    display_name: instance.display_name ?? '',
    nickname: instance.nickname ?? '',
    user_address_name: instance.user_address_name ?? '',
    persona: instance.persona ?? '',
    background: instance.background ?? '',
    speaking_style: instance.speaking_style ?? '',
    extra_rules: instance.extra_rules ?? '',
    status_place: instance.status.place ?? '',
    status_action: instance.status.action ?? '',
    proactive_enabled: instance.proactive.enabled ?? effective.proactive.enabled,
    proactive_overridden: instance.proactive.enabled !== null,
    memory_enabled: instance.memory.enabled ?? effective.memory.enabled,
    memory_overridden: instance.memory.enabled !== null,
  };
}

function configuredCount(instance: CustomerAgentInstance): number {
  return [
    instance.display_name,
    instance.nickname,
    instance.user_address_name,
    instance.persona,
    instance.background,
    instance.speaking_style,
    instance.extra_rules,
  ].filter((value) => value?.trim()).length;
}

function emptyAsNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

export default function CustomerMyAgentPage() {
  const { replace } = useRouter();
  const { messages } = useLocale();
  const copy = messages.customerPages.myAgent;
  const [data, setData] = useState<CustomerAgentInstanceResult | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const applyData = useCallback((next: CustomerAgentInstanceResult) => {
    setData(next);
    setForm(formFromInstance(next.agent_instance, next.effective_profile));
  }, []);

  useEffect(() => {
    let active = true;

    async function load() {
      setLoading(true);
      setError('');
      try {
        const res = await getCustomerAgentInstance();
        if (!active) {
          return;
        }
        if (!res.ok) {
          if (AUTH_ERRORS.has(res.error)) {
            replace(LOGIN_NEXT_PATH);
            return;
          }
          setError(copy.loadFailure);
          return;
        }
        applyData(res.data);
      } catch {
        if (active) {
          setError(copy.loadFailure);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      active = false;
    };
  }, [applyData, copy.loadFailure, replace]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form) {
      return;
    }
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const formData = new FormData(event.currentTarget);
      const res = await updateCustomerAgentInstance({
        display_name: emptyAsNull(String(formData.get('display_name') ?? '')),
        nickname: emptyAsNull(String(formData.get('nickname') ?? '')),
        user_address_name: emptyAsNull(String(formData.get('user_address_name') ?? '')),
        persona: emptyAsNull(String(formData.get('persona') ?? '')),
        background: emptyAsNull(String(formData.get('background') ?? '')),
        speaking_style: emptyAsNull(String(formData.get('speaking_style') ?? '')),
        extra_rules: emptyAsNull(String(formData.get('extra_rules') ?? '')),
        status: {
          place: emptyAsNull(String(formData.get('status_place') ?? '')),
          action: emptyAsNull(String(formData.get('status_action') ?? '')),
        },
        proactive: form.proactive_overridden ? { enabled: form.proactive_enabled } : null,
        memory: form.memory_overridden ? { enabled: form.memory_enabled } : null,
      });
      if (!res.ok) {
        if (AUTH_ERRORS.has(res.error)) {
          replace(LOGIN_NEXT_PATH);
          return;
        }
        setError(copy.saveFailure);
        return;
      }
      applyData(res.data);
      setNotice(copy.saved);
    } catch {
      setError(copy.saveFailure);
    } finally {
      setSaving(false);
    }
  }

  async function reset() {
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const res = await resetCustomerAgentInstance();
      if (!res.ok) {
        if (AUTH_ERRORS.has(res.error)) {
          replace(LOGIN_NEXT_PATH);
          return;
        }
        setError(copy.resetFailure);
        return;
      }
      applyData(res.data);
      setNotice(copy.saved);
    } catch {
      setError(copy.resetFailure);
    } finally {
      setSaving(false);
    }
  }

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
  }

  if (loading) {
    return (
      <section className="customer-view customer-view--wide my-agent-page">
        <div className="customer-panel customer-panel--wide">
          <p className="customer-inline-note">Loading...</p>
        </div>
      </section>
    );
  }

  if (!form || !data) {
    return (
      <section className="customer-view customer-view--wide my-agent-page">
        <div className="customer-panel customer-panel--wide">
          <p className="customer-inline-note customer-inline-note--error">{error || copy.loadFailure}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="customer-view customer-view--wide my-agent-page">
      <div className="customer-panel customer-panel--wide my-agent-panel">
        <div className="customer-panel__head">
          <p className="customer-panel__eyebrow">{copy.eyebrow}</p>
          <h1 className="customer-panel__title">{copy.title}</h1>
          <p className="customer-panel__body">{copy.description}</p>
        </div>

        <div className="my-agent-summary">
          <strong>
            {configuredCount(data.agent_instance)}/7 {copy.configured}
          </strong>
          <span>{data.effective_profile.display_name}</span>
          <span>{data.effective_profile.proactive.enabled ? 'Proactive on' : 'Proactive off'}</span>
          <span>{data.effective_profile.memory.enabled ? 'Memory on' : 'Memory off'}</span>
        </div>

        {notice ? <p className="customer-inline-note">{notice}</p> : null}
        {error ? <p className="customer-inline-note customer-inline-note--error">{error}</p> : null}

        <form className="my-agent-form" onSubmit={save}>
          <fieldset>
            <legend>{copy.basicIdentity}</legend>
            <label>
              <span>Display name</span>
              <input
                name="display_name"
                maxLength={20}
                value={form.display_name}
                onChange={(event) => updateField('display_name', event.target.value)}
              />
            </label>
            <label>
              <span>Nickname</span>
              <input
                name="nickname"
                maxLength={20}
                value={form.nickname}
                onChange={(event) => updateField('nickname', event.target.value)}
              />
            </label>
            <label>
              <span>User address name</span>
              <input
                name="user_address_name"
                maxLength={10}
                value={form.user_address_name}
                onChange={(event) => updateField('user_address_name', event.target.value)}
              />
            </label>
          </fieldset>

          <fieldset>
            <legend>{copy.agentProfile}</legend>
            <label>
              <span>Persona</span>
              <textarea
                name="persona"
                maxLength={2000}
                value={form.persona}
                onChange={(event) => updateField('persona', event.target.value)}
              />
            </label>
            <label>
              <span>Background</span>
              <textarea
                name="background"
                maxLength={4000}
                value={form.background}
                onChange={(event) => updateField('background', event.target.value)}
              />
            </label>
            <label>
              <span>Speaking style</span>
              <textarea
                name="speaking_style"
                maxLength={1000}
                value={form.speaking_style}
                onChange={(event) => updateField('speaking_style', event.target.value)}
              />
            </label>
            <label>
              <span>Extra rules</span>
              <textarea
                name="extra_rules"
                maxLength={1000}
                value={form.extra_rules}
                onChange={(event) => updateField('extra_rules', event.target.value)}
              />
            </label>
          </fieldset>

          <fieldset className="my-agent-form__grid">
            <legend>Status</legend>
            <label>
              <span>Place</span>
              <input
                name="status_place"
                maxLength={20}
                value={form.status_place}
                onChange={(event) => updateField('status_place', event.target.value)}
              />
            </label>
            <label>
              <span>Action</span>
              <input
                name="status_action"
                maxLength={20}
                value={form.status_action}
                onChange={(event) => updateField('status_action', event.target.value)}
              />
            </label>
          </fieldset>

          <fieldset className="my-agent-toggle-list">
            <legend>{copy.proactiveMessages}</legend>
            <label>
              <input
                name="proactive"
                type="checkbox"
                checked={form.proactive_enabled}
                onChange={(event) =>
                  setForm((current) =>
                    current
                      ? { ...current, proactive_enabled: event.target.checked, proactive_overridden: true }
                      : current,
                  )
                }
              />
              <span>Enable optional proactive follow-up</span>
            </label>
            <label>
              <input
                name="memory"
                type="checkbox"
                checked={form.memory_enabled}
                onChange={(event) =>
                  setForm((current) =>
                    current ? { ...current, memory_enabled: event.target.checked, memory_overridden: true } : current,
                  )
                }
              />
              <span>{copy.memoryPersonalization}</span>
            </label>
          </fieldset>

          <div className="customer-action-row">
            <button type="submit" className="customer-action customer-action--primary" disabled={saving}>
              {saving ? copy.saving : copy.save}
            </button>
            <button
              type="button"
              className="customer-action customer-action--secondary"
              disabled={saving}
              onClick={() => void reset()}
            >
              {copy.reset}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
