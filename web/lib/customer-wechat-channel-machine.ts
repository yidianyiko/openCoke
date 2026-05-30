import type { CustomerWechatChannelState } from './customer-wechat-channel';

export function applyCustomerWechatChannelMutationResult(
  result: CustomerWechatChannelState,
): CustomerWechatChannelState {
  return result;
}

export function applyCustomerWechatChannelMutationFailure(
  current: CustomerWechatChannelState | null,
  error: string,
): {
  channel: CustomerWechatChannelState;
  actionError: string | null;
} {
  if (current == null) {
    return {
      channel: {
        status: 'error',
        error,
      },
      actionError: null,
    };
  }

  return {
    channel: current,
    actionError: error,
  };
}

export function applyCustomerWechatChannelRefreshFailure(
  current: CustomerWechatChannelState | null,
  error: string,
): {
  channel: CustomerWechatChannelState | null;
  transientError: string | null;
} {
  if (current?.status === 'pending') {
    return {
      channel: current,
      transientError: error,
    };
  }

  return {
    channel: {
      status: 'error',
      error,
    },
    transientError: null,
  };
}
