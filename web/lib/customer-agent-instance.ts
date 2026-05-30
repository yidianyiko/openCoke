import type { ApiResponse } from './api-types';
import { customerApi } from './customer-api';

export interface CustomerAgentInstance {
  agent_instance_id: string | null;
  owner_user_id: string;
  base_agent_type: 'coke_companion';
  base_character_id: string;
  active: boolean;
  display_name: string | null;
  nickname: string | null;
  user_address_name: string | null;
  persona: string | null;
  background: string | null;
  speaking_style: string | null;
  extra_rules: string | null;
  status: {
    place: string | null;
    action: string | null;
  };
  proactive: {
    enabled: boolean | null;
  };
  memory: {
    enabled: boolean | null;
  };
  created_at?: string | null;
  updated_at?: string | null;
}

interface CustomerAgentEffectiveProfile {
  display_name: string;
  nickname: string;
  user_address_name: string | null;
  persona: string | null;
  background: string | null;
  speaking_style: string | null;
  extra_rules: string | null;
  status: {
    place: string;
    action: string;
  };
  proactive: {
    enabled: boolean;
  };
  memory: {
    enabled: boolean;
  };
}

export interface CustomerAgentInstanceResult {
  agent_instance: CustomerAgentInstance;
  effective_profile: CustomerAgentEffectiveProfile;
}

type CustomerAgentInstanceScalarPatch = Partial<
  Pick<
    CustomerAgentInstance,
    | 'display_name'
    | 'nickname'
    | 'user_address_name'
    | 'persona'
    | 'background'
    | 'speaking_style'
    | 'extra_rules'
  >
>;

type NullableNestedPatch<T extends object> = Partial<T> | null;

export type CustomerAgentInstancePatch = CustomerAgentInstanceScalarPatch & {
  status?: NullableNestedPatch<CustomerAgentInstance['status']>;
  proactive?: NullableNestedPatch<CustomerAgentInstance['proactive']>;
  memory?: NullableNestedPatch<CustomerAgentInstance['memory']>;
};

export function getCustomerAgentInstance(): Promise<ApiResponse<CustomerAgentInstanceResult>> {
  return customerApi.get<ApiResponse<CustomerAgentInstanceResult>>('/api/customer/agent-instance');
}

export function updateCustomerAgentInstance(
  patch: CustomerAgentInstancePatch,
): Promise<ApiResponse<CustomerAgentInstanceResult>> {
  return customerApi.patch<ApiResponse<CustomerAgentInstanceResult>>(
    '/api/customer/agent-instance',
    patch,
  );
}

export function resetCustomerAgentInstance(): Promise<ApiResponse<CustomerAgentInstanceResult>> {
  return customerApi.post<ApiResponse<CustomerAgentInstanceResult>>('/api/customer/agent-instance/reset');
}
