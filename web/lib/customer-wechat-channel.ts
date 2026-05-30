import type { ApiResponse, ProductActionAvailability } from './api-types';
import type { LocaleMessages } from './i18n';
import { customerApi } from './customer-api';
import { getStoredCustomerSession } from './customer-auth';

type CustomerWechatChannelStatus =
  | 'missing'
  | 'disconnected'
  | 'pending'
  | 'connected'
  | 'error'
  | 'archived';

export interface CustomerWechatChannelState {
  status: CustomerWechatChannelStatus;
  connect_url?: string;
  pairing_code?: string;
  instructions?: string;
  expires_at?: number;
  channel_id?: string;
  masked_identity?: string;
  error?: string;
  message?: string;
  actionAvailability?: ProductActionAvailability<
    'create' | 'connect' | 'disconnect' | 'archive' | 'refresh',
    string
  >;
}

interface CustomerWechatChannelViewModel {
  eyebrow: string;
  title: string;
  description: string;
  primaryActionLabel: string;
  secondaryActionLabel?: string;
}

type CustomerWechatChannelViewModelMessages = LocaleMessages['customerPages']['bindWechat']['viewModel'];

type CleanChannelError = {
  error: {
    code: string;
  };
};

type CleanChannelStatus = {
  account_id: string;
  channel_id: string | null;
  provider_type: string | null;
  connection_state: string;
  reachable: boolean;
  pairing_code?: string;
  pairing_expires_at?: number;
  instructions?: string;
};

type CleanChannelBody = {
  channel_id: string;
  account_id: string;
  provider_type: string;
  channel_identity_id: string;
  lifecycle: string;
  connection_state: string;
  removable: boolean;
};

function isCleanChannelError(value: unknown): value is CleanChannelError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as CleanChannelError).error?.code === 'string'
  );
}

function currentAccountId(): string | null {
  return getStoredCustomerSession()?.customerId ?? null;
}

function accountRequired<T>(): ApiResponse<T> {
  return { ok: false, error: 'missing_session' };
}

function cleanStatusToCustomerState(
  status: CleanChannelStatus | CleanChannelError,
): ApiResponse<CustomerWechatChannelState> {
  if (isCleanChannelError(status)) {
    return { ok: false, error: status.error.code };
  }

  const state: CustomerWechatChannelState = {
    status: 'missing',
    channel_id: status.channel_id ?? undefined,
  };

  if (status.connection_state === 'connecting') {
    state.status = 'pending';
    state.pairing_code = status.pairing_code;
    state.expires_at = status.pairing_expires_at;
    state.instructions = status.instructions;
  } else if (status.connection_state === 'connected') {
    state.status = 'connected';
  } else if (status.connection_state === 'not_connected' && status.channel_id != null) {
    state.status = 'disconnected';
  } else if (
    status.connection_state === 'connection_failed' ||
    status.connection_state === 'reconnection_required'
  ) {
    state.status = 'error';
    state.error = status.connection_state;
  } else if (status.connection_state === 'removed') {
    state.status = 'archived';
  }

  return { ok: true, data: state };
}

function removedChannelToState(
  channel: CleanChannelBody | CleanChannelError | undefined,
): ApiResponse<CustomerWechatChannelState> {
  if (channel == null) {
    return { ok: true, data: { status: 'archived' } };
  }
  if (isCleanChannelError(channel)) {
    return { ok: false, error: channel.error.code };
  }
  return {
    ok: true,
    data: {
      status: channel.connection_state === 'removed' ? 'archived' : 'disconnected',
      channel_id: channel.channel_id,
    },
  };
}

function normalizeEmptyArchiveResponse(
  response: ApiResponse<CustomerWechatChannelState> | undefined,
): ApiResponse<CustomerWechatChannelState> {
  if (response == null) {
    return {
      ok: true,
      data: { status: 'archived' },
    };
  }

  return response;
}

export function getCustomerWechatChannelViewModel(
  channel: Pick<CustomerWechatChannelState, 'status' | 'masked_identity' | 'error'> | null,
  copy: CustomerWechatChannelViewModelMessages,
): CustomerWechatChannelViewModel {
  switch (channel?.status) {
    case 'disconnected':
      return {
        eyebrow: copy.disconnected.eyebrow,
        title: copy.disconnected.title,
        description: copy.disconnected.description,
        primaryActionLabel: copy.disconnected.primaryActionLabel,
      };
    case 'pending':
      return {
        eyebrow: copy.pending.eyebrow,
        title: copy.pending.title,
        description: copy.pending.description,
        primaryActionLabel: copy.pending.primaryActionLabel,
      };
    case 'connected':
      return {
        eyebrow: copy.connected.eyebrow,
        title: copy.connected.title,
        description: channel.masked_identity
          ? copy.connected.descriptionWithIdentity.replace('{identity}', channel.masked_identity)
          : copy.connected.descriptionWithoutIdentity,
        primaryActionLabel: copy.connected.primaryActionLabel,
      };
    case 'error':
      return {
        eyebrow: copy.error.eyebrow,
        title: copy.error.title,
        description: copy.error.descriptionFallback,
        primaryActionLabel: copy.error.primaryActionLabel,
        secondaryActionLabel: copy.error.secondaryActionLabel,
      };
    case 'archived':
      return {
        eyebrow: copy.archived.eyebrow,
        title: copy.archived.title,
        description: copy.archived.description,
        primaryActionLabel: copy.archived.primaryActionLabel,
      };
    case 'missing':
    default:
      return {
        eyebrow: copy.missing.eyebrow,
        title: copy.missing.title,
        description: copy.missing.description,
        primaryActionLabel: copy.missing.primaryActionLabel,
      };
  }
}

export function createCustomerWechatChannel(): Promise<ApiResponse<CustomerWechatChannelState>> {
  return connectCustomerWechatChannel();
}

export function connectCustomerWechatChannel(): Promise<ApiResponse<CustomerWechatChannelState>> {
  const accountId = currentAccountId();
  if (!accountId) {
    return Promise.resolve(accountRequired<CustomerWechatChannelState>());
  }
  return customerApi
    .post<CleanChannelStatus | CleanChannelError>('/api/channels/wechat-personal/connect', {
      account_id: accountId,
    })
    .then(cleanStatusToCustomerState);
}

export function getCustomerWechatChannelStatus(): Promise<ApiResponse<CustomerWechatChannelState>> {
  const accountId = currentAccountId();
  if (!accountId) {
    return Promise.resolve(accountRequired<CustomerWechatChannelState>());
  }
  return customerApi
    .get<CleanChannelStatus | CleanChannelError>(
      `/api/channels/status?account_id=${encodeURIComponent(accountId)}`,
    )
    .then(cleanStatusToCustomerState);
}

export function disconnectCustomerWechatChannel(): Promise<ApiResponse<CustomerWechatChannelState>> {
  const accountId = currentAccountId();
  if (!accountId) {
    return Promise.resolve(accountRequired<CustomerWechatChannelState>());
  }
  return getCustomerWechatChannelStatus().then((status) => {
    if (!status.ok) {
      return status;
    }
    if (!status.data.channel_id) {
      return { ok: true, data: { status: 'archived' } };
    }
    return customerApi
      .post<CleanChannelBody | CleanChannelError>(
        `/api/channels/${encodeURIComponent(status.data.channel_id)}/remove`,
        { account_id: accountId },
      )
      .then(removedChannelToState);
  });
}

export function archiveCustomerWechatChannel(): Promise<ApiResponse<CustomerWechatChannelState>> {
  return disconnectCustomerWechatChannel().then(normalizeEmptyArchiveResponse);
}
