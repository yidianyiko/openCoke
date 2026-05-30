import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  archiveCustomerWechatChannel,
  connectCustomerWechatChannel,
  createCustomerWechatChannel,
  disconnectCustomerWechatChannel,
  getCustomerWechatChannelStatus,
  getCustomerWechatChannelViewModel,
} from './customer-wechat-channel';
import {
  applyCustomerWechatChannelMutationFailure,
  applyCustomerWechatChannelMutationResult,
  applyCustomerWechatChannelRefreshFailure,
} from './customer-wechat-channel-machine';
import { customerApi } from './customer-api';
import { messages } from './i18n';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('customer-wechat-channel api helpers', () => {
  it('calls the neutral personal channel create/connect/status/disconnect/archive endpoints', async () => {
    const customerPostSpy = vi.spyOn(customerApi, 'post').mockResolvedValue({
      ok: true,
      data: { status: 'missing' },
    } as never);
    const customerGetSpy = vi.spyOn(customerApi, 'get').mockResolvedValue({
      ok: true,
      data: { status: 'missing' },
    } as never);
    const customerDeleteSpy = vi.spyOn(customerApi, 'delete').mockResolvedValue({
      ok: true,
      data: { status: 'archived' },
    } as never);

    await createCustomerWechatChannel();
    await connectCustomerWechatChannel();
    await getCustomerWechatChannelStatus();
    await disconnectCustomerWechatChannel();
    await archiveCustomerWechatChannel();

    expect(customerPostSpy).toHaveBeenNthCalledWith(1, '/api/customer/channels/wechat-personal');
    expect(customerPostSpy).toHaveBeenNthCalledWith(2, '/api/customer/channels/wechat-personal/connect');
    expect(customerPostSpy).toHaveBeenNthCalledWith(3, '/api/customer/channels/wechat-personal/disconnect');
    expect(customerGetSpy).toHaveBeenCalledWith('/api/customer/channels/wechat-personal/status');
    expect(customerDeleteSpy).toHaveBeenCalledWith('/api/customer/channels/wechat-personal');
  });

  it('normalizes an empty archive success into an archived channel state', async () => {
    const customerDeleteSpy = vi.spyOn(customerApi, 'delete').mockResolvedValue(undefined as never);

    await expect(archiveCustomerWechatChannel()).resolves.toEqual({
      ok: true,
      data: { status: 'archived' },
    });

    expect(customerDeleteSpy).toHaveBeenCalledWith('/api/customer/channels/wechat-personal');
  });
});

describe('getCustomerWechatChannelViewModel', () => {
  it('maps lifecycle states to the expected copy', () => {
    const copy = messages.en.customerPages.bindWechat.viewModel;

    expect(getCustomerWechatChannelViewModel(null, copy)).toMatchObject({
      eyebrow: 'No channel yet',
      primaryActionLabel: 'Create my WeChat channel',
    });
    expect(getCustomerWechatChannelViewModel({ status: 'disconnected' }, copy)).toMatchObject({
      title: 'Connect WeChat',
      primaryActionLabel: 'Connect WeChat',
    });
    expect(getCustomerWechatChannelViewModel({ status: 'pending' }, copy)).toMatchObject({
      title: 'Scan the QR code to connect',
      primaryActionLabel: 'Refresh QR',
    });
    expect(
      getCustomerWechatChannelViewModel(
        {
          status: 'connected',
          masked_identity: 'wx***1234',
        },
        copy,
      ),
    ).toMatchObject({
      eyebrow: 'Connected',
      primaryActionLabel: 'Disconnect WeChat',
      description: 'Your personal channel is live as wx***1234.',
    });
    expect(
      getCustomerWechatChannelViewModel(
        {
          status: 'error',
          error: 'Temporary bridge failure',
        },
        copy,
      ),
    ).toMatchObject({
      eyebrow: 'Connection error',
      primaryActionLabel: 'Reconnect',
      secondaryActionLabel: 'Archive channel',
      description: 'The last connect attempt failed. You can retry or archive this channel.',
    });
    expect(getCustomerWechatChannelViewModel({ status: 'archived' }, copy)).toMatchObject({
      title: 'This WeChat channel is archived',
      primaryActionLabel: 'Create my WeChat channel again',
    });
  });
});

describe('customer-wechat-channel state machine', () => {
  it('uses the mutation response immediately, including pending connect payloads', () => {
    const mutationResult = {
      status: 'pending',
      connect_url: 'https://wx.example.com/connect?session=abc',
      expires_at: 1234567890,
    } as const;

    expect(applyCustomerWechatChannelMutationResult(mutationResult)).toEqual(mutationResult);
  });

  it('preserves an existing pending session when a transient refresh fails', () => {
    const current = {
      status: 'pending',
      connect_url: 'https://wx.example.com/connect?session=abc',
      expires_at: 1234567890,
    } as const;

    expect(
      applyCustomerWechatChannelRefreshFailure(current, 'Temporary bridge failure'),
    ).toEqual({
      channel: current,
      transientError: 'Temporary bridge failure',
    });
  });

  it('preserves a missing channel when create fails and surfaces an action error', () => {
    expect(
      applyCustomerWechatChannelMutationFailure(
        { status: 'missing' },
        'Temporary bridge failure',
      ),
    ).toEqual({
      channel: { status: 'missing' },
      actionError: 'Temporary bridge failure',
    });
  });

  it('preserves a connected channel when archive fails and surfaces an action error', () => {
    expect(
      applyCustomerWechatChannelMutationFailure(
        {
          status: 'connected',
          masked_identity: 'wx***1234',
        },
        'Temporary bridge failure',
      ),
    ).toEqual({
      channel: {
        status: 'connected',
        masked_identity: 'wx***1234',
      },
      actionError: 'Temporary bridge failure',
    });
  });
});
