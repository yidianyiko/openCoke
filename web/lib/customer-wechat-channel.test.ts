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
import { storeCustomerAuth } from './customer-auth';
import { messages } from './i18n';

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('customer-wechat-channel api helpers', () => {
  it('calls the clean channel endpoints with the stored account id', async () => {
    storeCustomerAuth({
      token: 'session_1',
      customerId: 'acct_1',
      identityId: 'acct_1',
      claimStatus: 'active',
      email: 'alice@example.com',
      membershipRole: 'owner',
    });
    const customerPostSpy = vi.spyOn(customerApi, 'post').mockResolvedValue({
      account_id: 'acct_1',
      channel_id: null,
      provider_type: 'wechat_personal',
      connection_state: 'connecting',
      reachable: false,
      pairing_code: 'pairing_abc123',
      pairing_expires_at: 1_780_000_000,
      instructions: 'add the Coke WeChat bot and send this code',
    } as never);
    const customerGetSpy = vi.spyOn(customerApi, 'get')
      .mockResolvedValueOnce({
        account_id: 'acct_1',
        channel_id: null,
        provider_type: null,
        connection_state: 'not_connected',
        reachable: false,
      } as never)
      .mockResolvedValueOnce({
        account_id: 'acct_1',
        channel_id: 'channel_1',
        provider_type: 'wechat_personal',
        connection_state: 'connected',
        reachable: true,
      } as never)
      .mockResolvedValueOnce({
        account_id: 'acct_1',
        channel_id: 'channel_1',
        provider_type: 'wechat_personal',
        connection_state: 'connected',
        reachable: true,
      } as never);

    await expect(createCustomerWechatChannel()).resolves.toMatchObject({
      ok: true,
      data: {
        status: 'pending',
        pairing_code: 'pairing_abc123',
        expires_at: 1_780_000_000,
      },
    });
    await connectCustomerWechatChannel();
    await expect(getCustomerWechatChannelStatus()).resolves.toEqual({
      ok: true,
      data: { status: 'missing' },
    });
    await disconnectCustomerWechatChannel();
    await archiveCustomerWechatChannel();

    expect(customerPostSpy).toHaveBeenNthCalledWith(1, '/api/channels/wechat-personal/connect', {
      account_id: 'acct_1',
    });
    expect(customerPostSpy).toHaveBeenNthCalledWith(2, '/api/channels/wechat-personal/connect', {
      account_id: 'acct_1',
    });
    expect(customerPostSpy).toHaveBeenNthCalledWith(3, '/api/channels/channel_1/remove', {
      account_id: 'acct_1',
    });
    expect(customerPostSpy).toHaveBeenNthCalledWith(4, '/api/channels/channel_1/remove', {
      account_id: 'acct_1',
    });
    expect(customerGetSpy).toHaveBeenNthCalledWith(1, '/api/channels/status?account_id=acct_1');
    expect(customerGetSpy).toHaveBeenNthCalledWith(2, '/api/channels/status?account_id=acct_1');
    expect(customerGetSpy).toHaveBeenNthCalledWith(3, '/api/channels/status?account_id=acct_1');
  });

  it('normalizes an empty archive success into an archived channel state', async () => {
    storeCustomerAuth({
      token: 'session_1',
      customerId: 'acct_1',
      identityId: 'acct_1',
      claimStatus: 'active',
      email: 'alice@example.com',
      membershipRole: 'owner',
    });
    vi.spyOn(customerApi, 'get').mockResolvedValue({
      account_id: 'acct_1',
      channel_id: null,
      provider_type: null,
      connection_state: 'not_connected',
      reachable: false,
    } as never);

    await expect(archiveCustomerWechatChannel()).resolves.toEqual({
      ok: true,
      data: { status: 'archived' },
    });
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
      title: 'Send the pairing code to connect',
      primaryActionLabel: 'Refresh code',
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
      pairing_code: 'pairing_abc123',
      expires_at: 1234567890,
    } as const;

    expect(applyCustomerWechatChannelMutationResult(mutationResult)).toEqual(mutationResult);
  });

  it('preserves an existing pending session when a transient refresh fails', () => {
    const current = {
      status: 'pending',
      pairing_code: 'pairing_abc123',
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
