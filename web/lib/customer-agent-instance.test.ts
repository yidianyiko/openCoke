import { afterEach, describe, expect, it, vi } from 'vitest';
import { customerApi } from './customer-api';
import {
  type CustomerAgentInstancePatch,
  getCustomerAgentInstance,
  resetCustomerAgentInstance,
  updateCustomerAgentInstance,
} from './customer-agent-instance';

vi.mock('./customer-api', () => ({
  customerApi: {
    get: vi.fn(),
    patch: vi.fn(),
    post: vi.fn(),
  },
}));

const apiMock = vi.mocked(customerApi);

const cleanSettings = {
  account_id: 'acct_1',
  default_timezone: 'Asia/Tokyo',
  agent_settings: {
    assistant_name: '沈妄',
    user_address_name: null,
    persona: null,
    background: null,
    speaking_style: null,
    extra_rules: null,
    proactive_enabled: true,
    memory_enabled: true,
  },
  user_profile: {
    real_name: null,
    nickname: 'Oliver',
    description: null,
    relationship_description: null,
  },
};

const partialNestedOverridePatch = {
  status: { place: '书桌' },
  proactive: null,
  memory: {},
} satisfies CustomerAgentInstancePatch;

afterEach(() => {
  vi.clearAllMocks();
});

describe('customer agent instance wrappers', () => {
  it('gets the current agent instance', async () => {
    apiMock.get.mockResolvedValueOnce(cleanSettings);

    await getCustomerAgentInstance();

    expect(apiMock.get).toHaveBeenCalledWith('/api/settings');
  });

  it('patches only the provided override fields', async () => {
    apiMock.patch.mockResolvedValueOnce(cleanSettings);

    await updateCustomerAgentInstance({
      display_name: '沈妄',
      proactive: { enabled: false },
    });

    expect(apiMock.patch).toHaveBeenCalledWith('/api/settings', {
      assistant_name: '沈妄',
      proactive_enabled: false,
    });
  });

  it('preserves partial and nullable nested override fields', async () => {
    apiMock.get.mockResolvedValueOnce(cleanSettings);

    await updateCustomerAgentInstance(partialNestedOverridePatch);

    expect(apiMock.patch).not.toHaveBeenCalled();
    expect(apiMock.get).toHaveBeenCalledWith('/api/settings');
  });

  it('resets the instance through the reset endpoint', async () => {
    apiMock.post.mockResolvedValueOnce(cleanSettings);

    await resetCustomerAgentInstance();

    expect(apiMock.post).toHaveBeenCalledWith('/api/settings/reset');
  });
});
