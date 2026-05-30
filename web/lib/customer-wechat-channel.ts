import type { ApiResponse } from '../../shared/src/types/api';
import type { ProductActionAvailability } from '../../shared/src/types/action-availability';
import type { LocaleMessages } from './i18n';
import { customerApi } from './customer-api';

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
  expires_at?: number;
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
  return customerApi.post<ApiResponse<CustomerWechatChannelState>>('/api/customer/channels/wechat-personal');
}

export function connectCustomerWechatChannel(): Promise<ApiResponse<CustomerWechatChannelState>> {
  return customerApi.post<ApiResponse<CustomerWechatChannelState>>(
    '/api/customer/channels/wechat-personal/connect',
  );
}

export function getCustomerWechatChannelStatus(): Promise<ApiResponse<CustomerWechatChannelState>> {
  return customerApi.get<ApiResponse<CustomerWechatChannelState>>(
    '/api/customer/channels/wechat-personal/status',
  );
}

export function disconnectCustomerWechatChannel(): Promise<ApiResponse<CustomerWechatChannelState>> {
  return customerApi.post<ApiResponse<CustomerWechatChannelState>>(
    '/api/customer/channels/wechat-personal/disconnect',
  );
}

export function archiveCustomerWechatChannel(): Promise<ApiResponse<CustomerWechatChannelState>> {
  return customerApi
    .delete<ApiResponse<CustomerWechatChannelState> | undefined>('/api/customer/channels/wechat-personal')
    .then(normalizeEmptyArchiveResponse);
}
