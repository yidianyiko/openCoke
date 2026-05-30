'use client';

import { Suspense, useEffect, useState, type FormEvent } from 'react';
import { Loader2 } from 'lucide-react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useLocale } from '../../../../../components/locale-provider';
import {
  adminApi,
  type AdminSharedChannelDetail,
} from '../../../../../lib/admin-api';
import { getAdminCopy } from '../../../../../lib/admin-copy';
import { formatDateTime } from '../../../../../lib/utils';

const WHATSAPP_EVOLUTION_KIND = 'whatsapp_evolution';
const WECHAT_ECLOUD_KIND = 'wechat_ecloud';
const LINQ_KIND = 'linq';

function titleCase(value: string): string {
  return value ? value.slice(0, 1).toUpperCase() + value.slice(1) : value;
}

function isWhatsAppEvolutionKind(kind: string): boolean {
  return kind === WHATSAPP_EVOLUTION_KIND;
}

function isWechatEcloudKind(kind: string): boolean {
  return kind === WECHAT_ECLOUD_KIND;
}

function isLinqKind(kind: string): boolean {
  return kind === LINQ_KIND;
}

function supportsSharedChannelLifecycle(kind: string): boolean {
  return isWhatsAppEvolutionKind(kind) || isWechatEcloudKind(kind) || isLinqKind(kind);
}

function buildLinqConfig(fromNumber: string): Record<string, unknown> {
  const trimmed = fromNumber.trim();
  return trimmed ? { fromNumber: trimmed } : {};
}

function parseConfig(value: string): Record<string, unknown> {
  if (!value.trim()) {
    return {};
  }

  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('invalid_config_json');
  }

  return parsed as Record<string, unknown>;
}

function getEvolutionInstanceName(config: Record<string, unknown>): string {
  return typeof config.instanceName === 'string' ? config.instanceName : '';
}

function getStringConfig(config: Record<string, unknown>, key: string): string {
  return typeof config[key] === 'string' ? config[key] : '';
}

function hasEcloudConfigChanged(
  config: Record<string, unknown>,
  appId: string,
  baseUrl: string,
): boolean {
  return getStringConfig(config, 'appId') !== appId || getStringConfig(config, 'baseUrl') !== baseUrl;
}

function getLinqFromNumber(config: Record<string, unknown>): string {
  return typeof config.fromNumber === 'string' ? config.fromNumber : '';
}

function getLinqWebhookSubscriptionId(config: Record<string, unknown>): string {
  return typeof config.webhookSubscriptionId === 'string' ? config.webhookSubscriptionId : '';
}

function AdminSharedChannelDetailPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { locale } = useLocale();
  const copy = getAdminCopy(locale);
  const id = searchParams.get('id') ?? '';
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [retiring, setRetiring] = useState(false);
  const [error, setError] = useState('');
  const [record, setRecord] = useState<AdminSharedChannelDetail | null>(null);
  const [name, setName] = useState('');
  const [agentId, setAgentId] = useState('');
  const [instanceName, setInstanceName] = useState('');
  const [ecloudAppId, setEcloudAppId] = useState('');
  const [ecloudBaseUrl, setEcloudBaseUrl] = useState('');
  const [fromNumber, setFromNumber] = useState('');
  const [configText, setConfigText] = useState('{}');

  useEffect(() => {
    let active = true;

    async function loadDetail() {
      if (!id) {
        setError('missing_id');
        setRecord(null);
        setLoading(false);
        return;
      }

      setLoading(true);
      setError('');
      const response = await adminApi.get<AdminSharedChannelDetail>('/api/admin/shared-channels/' + id);

      if (!active) {
        return;
      }

      if (!response.ok) {
        setError(response.error);
        setRecord(null);
        setLoading(false);
        return;
      }

      const nextRecord = response.data;
      setRecord(nextRecord);
      setName(nextRecord.name);
      setAgentId(nextRecord.agent?.id ?? '');
      if (isWhatsAppEvolutionKind(nextRecord.kind)) {
        setInstanceName(getEvolutionInstanceName(nextRecord.config));
      } else if (isWechatEcloudKind(nextRecord.kind)) {
        setEcloudAppId(getStringConfig(nextRecord.config, 'appId'));
        setEcloudBaseUrl(getStringConfig(nextRecord.config, 'baseUrl'));
      } else if (isLinqKind(nextRecord.kind)) {
        setFromNumber(getLinqFromNumber(nextRecord.config));
      } else {
        setConfigText(JSON.stringify(nextRecord.config ?? {}, null, 2));
      }
      setLoading(false);
    }

    void loadDetail();
    return () => {
      active = false;
    };
  }, [id]);

  function syncRecord(nextRecord: AdminSharedChannelDetail) {
    setRecord(nextRecord);
    setName(nextRecord.name);
    setAgentId(nextRecord.agent?.id ?? '');
    if (isWhatsAppEvolutionKind(nextRecord.kind)) {
      setInstanceName(getEvolutionInstanceName(nextRecord.config));
    } else if (isWechatEcloudKind(nextRecord.kind)) {
      setEcloudAppId(getStringConfig(nextRecord.config, 'appId'));
      setEcloudBaseUrl(getStringConfig(nextRecord.config, 'baseUrl'));
    } else if (isLinqKind(nextRecord.kind)) {
      setFromNumber(getLinqFromNumber(nextRecord.config));
    } else {
      setConfigText(JSON.stringify(nextRecord.config ?? {}, null, 2));
    }
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!record) {
      return;
    }

    setSaving(true);
    setError('');

    const form = new FormData(event.currentTarget);
    const nextName = String(form.get('name') ?? '').trim();
    const nextAgentId = String(form.get('agentId') ?? '').trim();
    const formInstanceName = String(form.get('instanceName') ?? '').trim();
    const formEcloudAppId = String(form.get('ecloudAppId') ?? '').trim();
    const formEcloudBaseUrl = String(form.get('ecloudBaseUrl') ?? '').trim();
    const formFromNumber = String(form.get('fromNumber') ?? '');
    const nextInstanceName = isWhatsAppEvolutionKind(record.kind)
      ? formInstanceName || instanceName.trim() || getEvolutionInstanceName(record.config)
      : formInstanceName;
    const nextFromNumber =
      isLinqKind(record.kind) && record.status === 'connected'
        ? fromNumber.trim() || getLinqFromNumber(record.config)
        : formFromNumber;
    const nextConfigText = String(form.get('config') ?? '{}');

    try {
      const payload: {
        name: string;
        agentId: string;
        config?: Record<string, unknown>;
      } = {
        name: nextName,
        agentId: nextAgentId,
      };

      if (isWhatsAppEvolutionKind(record.kind)) {
        payload.config = {
          instanceName: nextInstanceName,
        };
      } else if (isWechatEcloudKind(record.kind)) {
        const nextEcloudAppId =
          formEcloudAppId || ecloudAppId.trim() || getStringConfig(record.config, 'appId');
        const nextEcloudBaseUrl =
          formEcloudBaseUrl || ecloudBaseUrl.trim() || getStringConfig(record.config, 'baseUrl');
        if (
          record.status !== 'connected' &&
          hasEcloudConfigChanged(record.config, nextEcloudAppId, nextEcloudBaseUrl)
        ) {
          payload.config = {
            appId: nextEcloudAppId,
            baseUrl: nextEcloudBaseUrl,
          };
        }
      } else if (isLinqKind(record.kind)) {
        payload.config = buildLinqConfig(nextFromNumber);
      } else {
        payload.config = parseConfig(nextConfigText);
      }

      const response = await adminApi.patch<AdminSharedChannelDetail>(
        '/api/admin/shared-channels/' + id,
        payload,
      );

      if (!response.ok) {
        setError(response.error);
        return;
      }

      syncRecord(response.data);
    } catch {
      setError('invalid_config_json');
    } finally {
      setSaving(false);
    }
  }

  async function handleConnect() {
    if (!record || !supportsSharedChannelLifecycle(record.kind)) {
      return;
    }

    setConnecting(true);
    setError('');

    const response = await adminApi.post<AdminSharedChannelDetail>('/api/admin/shared-channels/' + id + '/connect');
    setConnecting(false);

    if (!response.ok) {
      setError(response.error);
      return;
    }

    syncRecord(response.data);
  }

  async function handleDisconnect() {
    if (!record || !supportsSharedChannelLifecycle(record.kind)) {
      return;
    }

    setDisconnecting(true);
    setError('');

    const response = await adminApi.post<AdminSharedChannelDetail>('/api/admin/shared-channels/' + id + '/disconnect');
    setDisconnecting(false);

    if (!response.ok) {
      setError(response.error);
      return;
    }

    syncRecord(response.data);
  }

  async function handleRetire() {
    if (!window.confirm(copy.sharedChannels.confirmRetire)) {
      return;
    }

    setRetiring(true);
    setError('');
    const response = await adminApi.delete<null>('/api/admin/shared-channels/' + id);
    setRetiring(false);

    if (!response.ok) {
      setError(response.error);
      return;
    }

    router.push('/admin/shared-channels');
  }

  const evolutionChannel = record ? isWhatsAppEvolutionKind(record.kind) : false;
  const ecloudChannel = record ? isWechatEcloudKind(record.kind) : false;
  const connectableChannel = evolutionChannel || ecloudChannel;
  const linqChannel = record ? isLinqKind(record.kind) : false;
  const instanceNameLocked = evolutionChannel && record?.status === 'connected';
  const fromNumberLocked = linqChannel && record?.status === 'connected';
  const webhookSubscriptionId =
    linqChannel && record ? getLinqWebhookSubscriptionId(record.config) : '';

  return (
    <div className="p-8">
      <div className="mb-8">
        <button type="button" className="btn-secondary mb-4" onClick={() => router.push('/admin/shared-channels')}>
          {copy.sharedChannels.actions.back}
        </button>
        <h1 className="text-2xl font-semibold text-gray-900">{copy.sharedChannels.detailTitle}</h1>
        {record ? <p className="mt-2 text-gray-600">{record.name}</p> : null}
      </div>

      <div className="card p-6">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-teal-500" />
          </div>
        ) : error && !record ? (
          <p className="text-sm text-red-600">
            {copy.common.errorPrefix}: {error}
          </p>
        ) : record ? (
          <form className="space-y-5" onSubmit={(event) => void handleSave(event)}>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <p className="text-sm font-medium text-gray-500">{copy.sharedChannels.columns.status}</p>
                <p className="mt-1 text-base text-gray-900">{titleCase(record.status)}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500">{copy.sharedChannels.columns.updated}</p>
                <p className="mt-1 text-base text-gray-900">{formatDateTime(record.updatedAt)}</p>
              </div>
              {connectableChannel ? (
                <div>
                  <p className="text-sm font-medium text-gray-500">{copy.sharedChannels.fields.webhookToken}</p>
                  <p className="mt-1 text-base text-gray-900">
                    {record.hasWebhookToken ? copy.sharedChannels.webhookTokenHidden : '—'}
                  </p>
                </div>
              ) : null}
              {linqChannel ? (
                <>
                  <div>
                    <p className="text-sm font-medium text-gray-500">{copy.sharedChannels.fields.webhookSubscriptionId}</p>
                    <p className="mt-1 text-base text-gray-900">{webhookSubscriptionId || '—'}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-500">{copy.sharedChannels.fields.webhookToken}</p>
                    <p className="mt-1 text-base text-gray-900">
                      {record.hasWebhookToken ? copy.sharedChannels.webhookTokenHidden : '—'}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-500">{copy.sharedChannels.fields.signingSecret}</p>
                    <p className="mt-1 text-base text-gray-900">
                      {record.hasSigningSecret ? copy.sharedChannels.signingSecretHidden : '—'}
                    </p>
                  </div>
                </>
              ) : null}
            </div>

            {evolutionChannel ? (
              <>
                <div>
                  <label htmlFor="shared-channel-detail-instance-name" className="label">
                    {copy.sharedChannels.fields.instanceName}
                  </label>
                  <input
                    id="shared-channel-detail-instance-name"
                    name="instanceName"
                    className="input"
                    value={instanceName}
                    onInput={(event) => setInstanceName(event.currentTarget.value)}
                    required
                    disabled={instanceNameLocked}
                  />
                  <p className="mt-2 text-xs text-gray-500">
                    {instanceNameLocked ? copy.sharedChannels.instanceNameLocked : copy.sharedChannels.instanceNameHelp}
                  </p>
                </div>
                <div className="flex gap-3">
                  {record.status === 'connected' ? (
                    <button
                      type="button"
                      className="btn-secondary"
                      data-testid="disconnect-shared-channel"
                      disabled={disconnecting}
                      onClick={() => void handleDisconnect()}
                    >
                      {disconnecting ? copy.common.loading : copy.sharedChannels.actions.disconnect}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn-secondary"
                      data-testid="connect-shared-channel"
                      disabled={connecting}
                      onClick={() => void handleConnect()}
                    >
                      {connecting ? copy.common.loading : copy.sharedChannels.actions.connect}
                    </button>
                  )}
                </div>
              </>
            ) : ecloudChannel ? (
              <>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <label htmlFor="shared-channel-detail-ecloud-app-id" className="label">
                      App ID
                    </label>
                    <input
                      id="shared-channel-detail-ecloud-app-id"
                      name="ecloudAppId"
                      className="input"
                      value={ecloudAppId}
                      onInput={(event) => setEcloudAppId(event.currentTarget.value)}
                      required
                      disabled={record.status === 'connected'}
                    />
                  </div>
                  <div>
                    <label htmlFor="shared-channel-detail-ecloud-base-url" className="label">
                      Base URL
                    </label>
                    <input
                      id="shared-channel-detail-ecloud-base-url"
                      name="ecloudBaseUrl"
                      className="input"
                      value={ecloudBaseUrl}
                      onInput={(event) => setEcloudBaseUrl(event.currentTarget.value)}
                      required
                      disabled={record.status === 'connected'}
                    />
                  </div>
                  <div className="md:col-span-2">
                    <p className="text-sm font-medium text-gray-500">Callback path</p>
                    <p className="mt-1 break-all text-base text-gray-900">
	                      {getStringConfig(record.config, 'callbackPath') || '—'}
	                    </p>
	                  </div>
	                </div>
	                <div className="flex gap-3">
	                  {record.status === 'connected' ? (
	                    <button
	                      type="button"
	                      className="btn-secondary"
	                      data-testid="disconnect-shared-channel"
	                      disabled={disconnecting}
	                      onClick={() => void handleDisconnect()}
	                    >
	                      {disconnecting ? copy.common.loading : copy.sharedChannels.actions.disconnect}
	                    </button>
	                  ) : (
	                    <button
	                      type="button"
	                      className="btn-secondary"
	                      data-testid="connect-shared-channel"
	                      disabled={connecting}
	                      onClick={() => void handleConnect()}
	                    >
	                      {connecting ? copy.common.loading : copy.sharedChannels.actions.connect}
	                    </button>
	                  )}
	                </div>
	              </>
	            ) : linqChannel ? (
	              <>
                <div>
                  <label htmlFor="shared-channel-detail-from-number" className="label">
                    {copy.sharedChannels.fields.fromNumber}
                  </label>
                  <input
                    id="shared-channel-detail-from-number"
                    name="fromNumber"
                    className="input"
                    value={fromNumber}
                    placeholder="+13213108456"
                    onInput={(event) => setFromNumber(event.currentTarget.value)}
                    disabled={fromNumberLocked}
                  />
                  <p className="mt-2 text-xs text-gray-500">
                    {fromNumberLocked ? copy.sharedChannels.fromNumberLocked : copy.sharedChannels.fromNumberHelp}
                  </p>
                </div>
                <div className="flex gap-3">
                  {record.status === 'connected' ? (
                    <button
                      type="button"
                      className="btn-secondary"
                      data-testid="disconnect-shared-channel"
                      disabled={disconnecting}
                      onClick={() => void handleDisconnect()}
                    >
                      {disconnecting ? copy.common.loading : copy.sharedChannels.actions.disconnect}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn-secondary"
                      data-testid="connect-shared-channel"
                      disabled={connecting}
                      onClick={() => void handleConnect()}
                    >
                      {connecting ? copy.common.loading : copy.sharedChannels.actions.connect}
                    </button>
                  )}
                </div>
              </>
            ) : (
              <div>
                <label htmlFor="shared-channel-detail-config" className="label">
                  {copy.sharedChannels.fields.config}
                </label>
                <textarea
                  id="shared-channel-detail-config"
                  name="config"
                  className="input min-h-[160px]"
                  value={configText}
                  onInput={(event) => setConfigText(event.currentTarget.value)}
                />
              </div>
            )}

            <div>
              <label htmlFor="shared-channel-detail-name" className="label">
                {copy.sharedChannels.fields.name}
              </label>
              <input
                id="shared-channel-detail-name"
                name="name"
                className="input"
                value={name}
                onInput={(event) => setName(event.currentTarget.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="shared-channel-detail-agent-id" className="label">
                {copy.sharedChannels.fields.agentId}
              </label>
              <input
                id="shared-channel-detail-agent-id"
                name="agentId"
                className="input"
                value={agentId}
                onInput={(event) => setAgentId(event.currentTarget.value)}
                required
              />
            </div>

            {error ? <p className="text-sm text-red-600">{copy.common.errorPrefix}: {error}</p> : null}
            <div className="flex gap-3">
              <button
                type="submit"
                className="btn-primary"
                data-testid="save-shared-channel"
                disabled={saving}
              >
                {saving ? copy.common.loading : copy.sharedChannels.actions.save}
              </button>
              <button
                type="button"
                className="btn-secondary"
                data-testid="retire-shared-channel"
                disabled={retiring}
                onClick={() => void handleRetire()}
              >
                {retiring ? copy.common.loading : copy.sharedChannels.actions.retire}
              </button>
            </div>
          </form>
        ) : null}
      </div>
    </div>
  );
}

export default function AdminSharedChannelDetailPage() {
  return (
    <Suspense fallback={null}>
      <AdminSharedChannelDetailPageContent />
    </Suspense>
  );
}
