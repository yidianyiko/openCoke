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
    apiMock.get.mockResolvedValueOnce({ ok: true, data: { agent_instance: {}, effective_profile: {} } });

    await getCustomerAgentInstance();

    expect(apiMock.get).toHaveBeenCalledWith('/api/customer/agent-instance');
  });

  it('patches only the provided override fields', async () => {
    apiMock.patch.mockResolvedValueOnce({ ok: true, data: { agent_instance: {}, effective_profile: {} } });

    await updateCustomerAgentInstance({
      display_name: '沈妄',
      proactive: { enabled: false },
    });

    expect(apiMock.patch).toHaveBeenCalledWith('/api/customer/agent-instance', {
      display_name: '沈妄',
      proactive: { enabled: false },
    });
  });

  it('preserves partial and nullable nested override fields', async () => {
    apiMock.patch.mockResolvedValueOnce({ ok: true, data: { agent_instance: {}, effective_profile: {} } });

    await updateCustomerAgentInstance(partialNestedOverridePatch);

    expect(apiMock.patch).toHaveBeenCalledWith('/api/customer/agent-instance', {
      status: { place: '书桌' },
      proactive: null,
      memory: {},
    });
  });

  it('resets the instance through the reset endpoint', async () => {
    apiMock.post.mockResolvedValueOnce({ ok: true, data: { agent_instance: {}, effective_profile: {} } });

    await resetCustomerAgentInstance();

    expect(apiMock.post).toHaveBeenCalledWith('/api/customer/agent-instance/reset');
  });
});
