'use client';

import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { ApiResponse } from '../../../../lib/api-types';
import { useLocale } from '../../../../components/locale-provider';
import {
  clearCustomerAuth,
  getCustomerProfile,
  getCustomerToken,
  getStoredCustomerProfile,
  storeCustomerProfile,
  type CustomerProfile,
} from '../../../../lib/customer-auth';
import {
  archiveCustomerWechatChannel,
  connectCustomerWechatChannel,
  createCustomerWechatChannel,
  disconnectCustomerWechatChannel,
  getCustomerWechatChannelLoginStatus,
  getCustomerWechatChannelStatus,
  getCustomerWechatChannelViewModel,
  type CustomerWechatChannelState,
} from '../../../../lib/customer-wechat-channel';
import {
  applyCustomerWechatChannelMutationFailure,
  applyCustomerWechatChannelMutationResult,
  applyCustomerWechatChannelRefreshFailure,
} from '../../../../lib/customer-wechat-channel-machine';

type BlockedAccessState = {
  title: string;
  description: string;
  actions: Array<{ href: string; label: string }>;
};

type BindWechatCopy = ReturnType<typeof useLocale>['messages']['customerPages']['bindWechat'];
type ChannelAction = 'create' | 'connect' | 'disconnect' | 'archive';
type ActionErrorState = {
  action: ChannelAction;
  message: string;
};

const primaryButtonClass = 'customer-channel-page__button customer-channel-page__button--primary';
const secondaryButtonClass = 'customer-channel-page__button customer-channel-page__button--secondary';

function formatTemplate(template: string, values: Record<string, string>) {
  return Object.entries(values).reduce(
    (result, [key, value]) => result.replace(`{${key}}`, value),
    template,
  );
}

function ChannelSetupCard({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <div className="coke-site customer-channel-page">
      <section className="auth-card customer-channel-page__card">
        {eyebrow ? <p className="auth-card__eyebrow">{eyebrow}</p> : null}
        <h1 className="auth-card__title">{title}</h1>
        {description ? <p className="auth-card__desc">{description}</p> : null}
        {children}
      </section>
    </div>
  );
}

function getChannelStatusDescription(
  status: CustomerWechatChannelState['status'],
  copy: BindWechatCopy,
): string | null {
  if (status === 'missing') {
    return copy.statusDescriptions.missing;
  }

  if (status === 'archived') {
    return copy.statusDescriptions.archived;
  }

  if (status === 'disconnected') {
    return copy.statusDescriptions.disconnected;
  }

  return null;
}

function getChannelNextSteps(
  status: CustomerWechatChannelState['status'],
  copy: BindWechatCopy,
): string[] {
  if (status === 'missing') {
    return [copy.nextSteps.missing];
  }

  if (status === 'disconnected') {
    return [copy.nextSteps.disconnected];
  }

  if (status === 'pending') {
    return [copy.nextSteps.pending];
  }

  if (status === 'connected') {
    return [copy.nextSteps.connected];
  }

  if (status === 'error') {
    return [copy.nextSteps.error];
  }

  if (status === 'archived') {
    return [copy.nextSteps.archived];
  }

  return [];
}

function isCustomerSuspended(user: CustomerProfile | null): boolean {
  return user?.status === 'suspended';
}

function needsCustomerEmailVerification(user: CustomerProfile | null): boolean {
  return user?.email_verified !== true;
}

function needsCustomerSubscriptionRenewal(user: CustomerProfile | null): boolean {
  return user?.subscription_active !== true;
}

function getBlockedAccessState(
  user: CustomerProfile | null,
  copy: ReturnType<typeof useLocale>['messages']['customerPages']['bindWechat']['blocked'],
): BlockedAccessState | null {
  if (isCustomerSuspended(user)) {
    return {
      title: copy.suspendedTitle,
      description: copy.suspendedDescription,
      actions: [],
    };
  }

  const actions: Array<{ href: string; label: string }> = [];
  if (needsCustomerEmailVerification(user)) {
    actions.push({ href: '/auth/verify-email', label: copy.verifyEmail });
  }
  if (needsCustomerSubscriptionRenewal(user)) {
    actions.push({ href: '/account/subscription', label: copy.renewSubscription });
  }

  if (actions.length === 0) {
    return null;
  }

  return {
    title: copy.prerequisitesTitle,
    description: copy.prerequisitesDescription,
    actions,
  };
}

function normalizeExpiresAt(expiresAt: number): Date {
  return new Date(expiresAt < 1_000_000_000_000 ? expiresAt * 1000 : expiresAt);
}

function currentPendingSession(channel: CustomerWechatChannelState | null): string | null {
  if (channel?.status !== 'pending') {
    return null;
  }
  return channel.session_id ?? null;
}

function actionFailureMessage(action: ChannelAction, copy: BindWechatCopy): string {
  if (action === 'disconnect') {
    return copy.errorCard.disconnectDescription;
  }

  return copy.errorCard.fallbackDescription;
}

export default function CustomerWechatPersonalPage() {
  const { locale, messages } = useLocale();
  const copy = messages.customerPages.bindWechat;
  const dateLocale = locale === 'zh' ? 'zh-CN' : 'en-US';
  const router = useRouter();
  const [hasToken] = useState<boolean>(() => getCustomerToken() != null);
  const [user, setUser] = useState<CustomerProfile | null>(() => getStoredCustomerProfile());
  const [profileReady, setProfileReady] = useState<boolean>(false);
  const [channel, setChannel] = useState<CustomerWechatChannelState | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<ChannelAction | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<ActionErrorState | null>(null);
  const channelRef = useRef<CustomerWechatChannelState | null>(null);
  const profileRefreshStartedRef = useRef(false);
  const busyActionRef = useRef<ChannelAction | null>(null);
  const channelRevisionRef = useRef(0);
  const channelViewModel = useMemo(
    () => getCustomerWechatChannelViewModel(channel, copy.viewModel),
    [channel, copy.viewModel],
  );
  const blockedAccessState = useMemo(() => getBlockedAccessState(user, copy.blocked), [copy.blocked, user]);
  const userName = user?.display_name ?? '';

  useEffect(() => {
    channelRef.current = channel;
  }, [channel]);

  useEffect(() => {
    if (!hasToken) {
      router.replace('/auth/login');
      setLoading(false);
      setProfileReady(true);
      return;
    }

    if (profileRefreshStartedRef.current) {
      return;
    }

    profileRefreshStartedRef.current = true;

    let cancelled = false;

    async function hydrateProfile() {
      try {
        const res = await getCustomerProfile();
        if (cancelled) {
          return;
        }

        if (!res.ok) {
          clearCustomerAuth();
          setUser(null);
          router.replace('/auth/login');
          setLoading(false);
          setProfileReady(true);
          return;
        }

        storeCustomerProfile(res.data);
        setUser(res.data);
        setProfileReady(true);
      } catch {
        if (cancelled) {
          return;
        }

        clearCustomerAuth();
        setUser(null);
        router.replace('/auth/login');
        setLoading(false);
        setProfileReady(true);
      }
    }

    void hydrateProfile();

    return () => {
      cancelled = true;
    };
  }, [hasToken, router]);

  const refreshChannel = useCallback(async (options?: { silent?: boolean }) => {
    const requestRevision = channelRevisionRef.current;

    if (!options?.silent) {
      setLoading(true);
    }

    try {
      const pendingSession = currentPendingSession(channelRef.current);
      const res = pendingSession
        ? await getCustomerWechatChannelLoginStatus(pendingSession)
        : await getCustomerWechatChannelStatus();
      if (requestRevision != channelRevisionRef.current) {
        return;
      }

      if (!res.ok) {
        const message = copy.loadFailure.title;
        if (channelRef.current == null) {
          setLoadError(message);
          setRefreshError(null);
          setActionError(null);
          setChannel(null);
        } else {
          const next = applyCustomerWechatChannelRefreshFailure(channelRef.current, message);
          setChannel(next.channel);
          setRefreshError(next.transientError);
        }
        return;
      }

      setLoadError(null);
      setRefreshError(null);
      channelRevisionRef.current += 1;
      setActionError(null);
      setChannel(res.data);
    } catch {
      if (requestRevision != channelRevisionRef.current) {
        return;
      }

      const message = copy.loadFailure.title;
      if (channelRef.current == null) {
        setLoadError(message);
        setRefreshError(null);
        setActionError(null);
        setChannel(null);
      } else {
        const next = applyCustomerWechatChannelRefreshFailure(channelRef.current, message);
        setChannel(next.channel);
        setRefreshError(next.transientError);
      }
    } finally {
      if (!options?.silent) {
        setLoading(false);
      }
    }
  }, [copy.loadFailure.title]);

  useEffect(() => {
    if (!hasToken) {
      return;
    }

    if (!profileReady) {
      return;
    }

    if (user == null) {
      return;
    }

    if (blockedAccessState != null) {
      setLoading(false);
      return;
    }

    void refreshChannel();
  }, [blockedAccessState, hasToken, profileReady, refreshChannel, user]);

  useEffect(() => {
    if (channel?.status !== 'pending') {
      return;
    }

    const timer = window.setInterval(() => {
      void refreshChannel({ silent: true });
    }, 3000);

    return () => {
      window.clearInterval(timer);
    };
  }, [channel?.status, refreshChannel]);

  function handleSignOut() {
    clearCustomerAuth();
    router.replace('/auth/login');
  }

  async function runAction(
    action: ChannelAction,
    operation: () => Promise<ApiResponse<CustomerWechatChannelState>>,
  ) {
    if (busyActionRef.current != null) {
      return;
    }

    const currentChannel = channel;
    busyActionRef.current = action;
    setBusyAction(action);

    try {
      const res = await operation();
      if (!res.ok) {
        setRefreshError(null);
        const next = applyCustomerWechatChannelMutationFailure(
          currentChannel,
          actionFailureMessage(action, copy),
        );
        channelRevisionRef.current += 1;
        setActionError(next.actionError ? { action, message: next.actionError } : null);
        setChannel(next.channel);
        return;
      }

      setRefreshError(null);
      channelRevisionRef.current += 1;
      setActionError(null);
      setChannel(applyCustomerWechatChannelMutationResult(res.data));
    } catch {
      setRefreshError(null);
      const next = applyCustomerWechatChannelMutationFailure(
        currentChannel,
        actionFailureMessage(action, copy),
      );
      channelRevisionRef.current += 1;
      setActionError(next.actionError ? { action, message: next.actionError } : null);
      setChannel(next.channel);
    } finally {
      busyActionRef.current = null;
      setBusyAction(null);
    }
  }

  async function handleCreateChannel() {
    await runAction('create', () => createCustomerWechatChannel());
  }

  async function handleConnectChannel() {
    await runAction('connect', () => connectCustomerWechatChannel());
  }

  async function handleDisconnectChannel() {
    await runAction('disconnect', () => disconnectCustomerWechatChannel());
  }

  async function handleArchiveChannel() {
    await runAction('archive', () => archiveCustomerWechatChannel());
  }

  if (!hasToken) {
    return null;
  }

  if (!profileReady && !channel) {
    return (
      <ChannelSetupCard title={copy.loading.title} description={copy.loading.description} />
    );
  }

  if (blockedAccessState != null) {
    return (
      <ChannelSetupCard
        eyebrow={copy.blocked.accessEyebrow}
        title={blockedAccessState.title}
        description={blockedAccessState.description}
      >
        <div className="customer-channel-page__section customer-channel-page__actions">
          <div className="customer-channel-page__button-row">
            {blockedAccessState.actions.map((action) => (
              <Link key={action.href} href={action.href} className={primaryButtonClass}>
                {action.label}
              </Link>
            ))}
            <button type="button" onClick={handleSignOut} className={secondaryButtonClass}>
              {messages.common.signOutLabel}
            </button>
          </div>
        </div>
      </ChannelSetupCard>
    );
  }

  if (loadError && !channel) {
    return (
      <ChannelSetupCard title={copy.loadFailure.title} description={loadError}>
        <div className="customer-channel-page__section customer-channel-page__actions">
          <div className="customer-channel-page__button-row">
            <button type="button" onClick={() => void refreshChannel()} className={primaryButtonClass}>
              {messages.common.retryLabel}
            </button>
            <button type="button" onClick={handleSignOut} className={secondaryButtonClass}>
              {messages.common.signOutLabel}
            </button>
          </div>
        </div>
      </ChannelSetupCard>
    );
  }

  if (loading && !channel) {
    return (
      <ChannelSetupCard title={copy.loading.title} description={copy.loading.description} />
    );
  }

  if (!channel) {
    return null;
  }

  const statusDescription = getChannelStatusDescription(channel.status, copy);
  const nextSteps = getChannelNextSteps(channel.status, copy);
  const visibleActionError =
    channel.status === 'connected' && actionError?.action !== 'disconnect' ? null : actionError?.message;

  return (
    <ChannelSetupCard
      eyebrow={channelViewModel.eyebrow}
      title={channelViewModel.title}
      description={`${channelViewModel.description}${
        userName && channel.status === 'connected'
          ? ` ${formatTemplate(copy.connectedCard.accountOwnershipSuffix, { name: userName })}`
          : ''
      }`}
    >
      {visibleActionError ? (
        <div className="auth-alert auth-alert--warning customer-channel-page__alert">{visibleActionError}</div>
      ) : null}

      {statusDescription ? (
        <div className="customer-channel-page__section">
          <div className="customer-channel-page__surface customer-channel-page__surface--neutral">
            <p className="customer-channel-page__surface-copy">{statusDescription}</p>
          </div>
        </div>
      ) : null}

      {channel.status === 'pending' ? (
        <div className="customer-channel-page__section">
          <div className="customer-channel-page__surface customer-channel-page__surface--neutral">
            <p className="customer-channel-page__surface-eyebrow">{copy.pairing.codeLabel}</p>
            {channel.qrcode_image ? (
              <div className="customer-channel-page__qr-frame">
                <img
                  className="customer-channel-page__qr-image"
                  src={channel.qrcode_image}
                  alt={copy.pairing.qrAlt}
                />
              </div>
            ) : (
              <p className="customer-channel-page__surface-copy">{copy.pairing.preparing}</p>
            )}
            <p className="customer-channel-page__surface-copy">
              {channel.instructions ?? copy.pairing.instructions}
            </p>
            {channel.connector_status ? (
              <p className="customer-channel-page__meta">
                {copy.pairing.connectorStatusPrefix} {channel.connector_status}
              </p>
            ) : null}
          </div>

          {channel.expires_at ? (
            <p className="customer-channel-page__meta">
              {copy.pairing.expiresPrefix} {normalizeExpiresAt(channel.expires_at).toLocaleString(dateLocale)}.
            </p>
          ) : null}

          {refreshError ? (
            <p className="auth-alert auth-alert--warning customer-channel-page__alert">
              {refreshError} {copy.pairing.activeSuffix}
            </p>
          ) : null}
        </div>
      ) : null}

      {channel.status === 'connected' ? (
        <div className="customer-channel-page__section">
          <div className="customer-channel-page__surface customer-channel-page__surface--success">
            <p className="customer-channel-page__surface-eyebrow">{copy.connectedCard.eyebrow}</p>
            <p className="customer-channel-page__surface-copy">
              {channel.masked_identity
                ? formatTemplate(copy.connectedCard.descriptionWithIdentity, {
                    identity: channel.masked_identity,
                  })
                : copy.connectedCard.descriptionWithoutIdentity}
            </p>
          </div>
        </div>
      ) : null}

      {channel.status === 'error' ? (
        <div className="customer-channel-page__section">
          <div className="customer-channel-page__surface customer-channel-page__surface--danger">
            <p className="customer-channel-page__surface-eyebrow">{copy.errorCard.eyebrow}</p>
            <p className="customer-channel-page__surface-copy">{copy.errorCard.fallbackDescription}</p>
          </div>
        </div>
      ) : null}

      <div className="customer-channel-page__section">
        <p className="customer-channel-page__section-title">{copy.nextSteps.title}</p>
        <ul className="customer-channel-page__steps">
          {nextSteps.map((step) => (
            <li key={step} className="customer-channel-page__step">
              {step}
            </li>
          ))}
        </ul>
      </div>

      <div className="customer-channel-page__section customer-channel-page__actions">
        <div className="customer-channel-page__button-row">
          {channel.status === 'missing' ? (
            <button
              type="button"
              onClick={handleCreateChannel}
              disabled={busyAction != null}
              className={primaryButtonClass}
            >
              {busyAction === 'create' ? copy.busyActions.create : channelViewModel.primaryActionLabel}
            </button>
          ) : null}

          {channel.status === 'disconnected' ? (
            <button
              type="button"
              onClick={handleConnectChannel}
              disabled={busyAction != null}
              className={primaryButtonClass}
            >
              {busyAction === 'connect' ? copy.busyActions.connect : channelViewModel.primaryActionLabel}
            </button>
          ) : null}

          {channel.status === 'pending' ? (
            <button
              type="button"
              onClick={handleConnectChannel}
              disabled={busyAction != null}
              className={primaryButtonClass}
            >
              {busyAction === 'connect' ? copy.busyActions.refresh : channelViewModel.primaryActionLabel}
            </button>
          ) : null}

          {channel.status === 'connected' ? (
            <button
              type="button"
              onClick={handleDisconnectChannel}
              disabled={busyAction != null}
              className={primaryButtonClass}
            >
              {busyAction === 'disconnect'
                ? copy.busyActions.disconnect
                : channelViewModel.primaryActionLabel}
            </button>
          ) : null}

          {channel.status === 'error' ? (
            <>
              <button
                type="button"
                onClick={handleConnectChannel}
                disabled={busyAction != null}
                className={primaryButtonClass}
              >
                {busyAction === 'connect'
                  ? copy.busyActions.reconnect
                  : channelViewModel.primaryActionLabel}
              </button>
              <button
                type="button"
                onClick={handleArchiveChannel}
                disabled={busyAction != null}
                className={secondaryButtonClass}
              >
                {busyAction === 'archive'
                  ? copy.busyActions.archive
                  : channelViewModel.secondaryActionLabel}
              </button>
            </>
          ) : null}

          {channel.status === 'archived' ? (
            <button
              type="button"
              onClick={handleCreateChannel}
              disabled={busyAction != null}
              className={primaryButtonClass}
            >
              {busyAction === 'create' ? copy.busyActions.create : channelViewModel.primaryActionLabel}
            </button>
          ) : null}

          <button type="button" onClick={handleSignOut} className={secondaryButtonClass}>
            {messages.common.signOutLabel}
          </button>
        </div>
      </div>

      <div className="customer-channel-page__section customer-channel-page__footer">
        <p className="customer-channel-page__footer-copy">
          {copy.accountPrompt}{' '}
          <Link href="/auth/register" className="customer-channel-page__footer-link">
            {copy.createAccount}
          </Link>
        </p>
      </div>
    </ChannelSetupCard>
  );
}
