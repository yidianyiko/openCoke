import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  archiveCustomerWechatChannel,
  connectCustomerWechatChannel,
  createCustomerWechatChannel,
  disconnectCustomerWechatChannel,
  getCustomerWechatChannelLoginStatus,
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
      session_id: 'ilink_session_1',
      qrcode_id: 'qr_1',
      qrcode_image: 'data:image/png;base64,QR1',
      connector_status: 'waiting_for_scan',
      instructions: "scan this QR code with this user's own WeChat account",
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
        session_id: 'ilink_session_1',
        qrcode_id: 'qr_1',
        qrcode_image: 'data:image/png;base64,QR1',
        connector_status: 'waiting_for_scan',
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

  it('polls a clean iLink login session for account-bound QR confirmation', async () => {
    storeCustomerAuth({
      token: 'session_1',
      customerId: 'acct_1',
      identityId: 'acct_1',
      claimStatus: 'active',
      email: 'alice@example.com',
      membershipRole: 'owner',
    });
    const customerGetSpy = vi.spyOn(customerApi, 'get').mockResolvedValueOnce({
      account_id: 'acct_1',
      channel_id: 'channel_1',
      provider_type: 'wechat_personal',
      connection_state: 'connected',
      reachable: true,
      session_id: 'ilink_session_1',
      connector_status: 'connected',
      masked_identity: 'wxid...lice',
    } as never);

    await expect(getCustomerWechatChannelLoginStatus('ilink_session_1')).resolves.toEqual({
      ok: true,
      data: {
        status: 'connected',
        channel_id: 'channel_1',
        session_id: 'ilink_session_1',
        connector_status: 'connected',
        masked_identity: 'wxid...lice',
      },
    });

    expect(customerGetSpy).toHaveBeenCalledWith(
      '/api/channels/wechat-personal/login-status?account_id=acct_1&session_id=ilink_session_1',
    );
  });

  it('maps the live QR connect response without legacy pairing fields', async () => {
    storeCustomerAuth({
      token: 'session_1',
      customerId: 'acct_1',
      identityId: 'acct_1',
      claimStatus: 'active',
      email: 'alice@example.com',
      membershipRole: 'owner',
    });
    vi.spyOn(customerApi, 'post').mockResolvedValueOnce({
      account_id: 'acct_1',
      channel_id: null,
      connection_state: 'connecting',
      connector_status: 'waiting_for_scan',
      instructions: "scan this QR code with this user's own WeChat account",
      provider_type: 'wechat_personal',
      qrcode_id: 'qr_1',
      qrcode_image: 'data:image/png;base64,QR1',
      session_id: 'session_1',
    } as never);

    await expect(connectCustomerWechatChannel()).resolves.toEqual({
      ok: true,
      data: {
        status: 'pending',
        channel_id: undefined,
        connector_status: 'waiting_for_scan',
        instructions: "scan this QR code with this user's own WeChat account",
        qrcode_id: 'qr_1',
        qrcode_image: 'data:image/png;base64,QR1',
        session_id: 'session_1',
      },
    });
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
      title: 'Scan to connect WeChat',
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
      session_id: 'ilink_session_1',
      qrcode_image: 'data:image/png;base64,QR1',
    } as const;

    expect(applyCustomerWechatChannelMutationResult(mutationResult)).toEqual(mutationResult);
  });

  it('preserves an existing pending session when a transient refresh fails', () => {
    const current = {
      status: 'pending',
      session_id: 'ilink_session_1',
      qrcode_image: 'data:image/png;base64,QR1',
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
