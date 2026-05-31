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

type CleanSettings = {
  account_id: string;
  default_timezone: string;
  agent_settings: {
    assistant_name: string | null;
    user_address_name: string | null;
    persona: string | null;
    background: string | null;
    speaking_style: string | null;
    extra_rules: string | null;
    proactive_enabled: boolean | null;
    memory_enabled: boolean | null;
  };
  user_profile: {
    real_name: string | null;
    nickname: string | null;
    description: string | null;
    relationship_description: string | null;
  };
};

type CleanSettingsPatch = Partial<{
  assistant_name: string | null;
  user_address_name: string | null;
  persona: string | null;
  background: string | null;
  speaking_style: string | null;
  extra_rules: string | null;
  proactive_enabled: boolean | null;
  memory_enabled: boolean | null;
}>;

type CleanProfilePatch = Partial<{
  nickname: string | null;
}>;

export function getCustomerAgentInstance(): Promise<ApiResponse<CustomerAgentInstanceResult>> {
  return customerApi.get<CleanSettings>('/api/settings').then((settings) => ({
    ok: true,
    data: cleanSettingsToAgentInstance(settings),
  }));
}

export function updateCustomerAgentInstance(
  patch: CustomerAgentInstancePatch,
): Promise<ApiResponse<CustomerAgentInstanceResult>> {
  const settingsPatch = cleanSettingsPatch(patch);
  const profilePatch = cleanProfilePatch(patch);

  if (Object.keys(settingsPatch).length > 0) {
    return customerApi
      .patch<CleanSettings>('/api/settings', settingsPatch)
      .then((settings) => cleanProfileAfterSettings(settings, profilePatch));
  }
  if (Object.keys(profilePatch).length > 0) {
    return customerApi.patch<CleanSettings>('/api/settings/profile', profilePatch).then((settings) => ({
      ok: true,
      data: cleanSettingsToAgentInstance(settings),
    }));
  }
  return getCustomerAgentInstance();
}

export function resetCustomerAgentInstance(): Promise<ApiResponse<CustomerAgentInstanceResult>> {
  return customerApi.post<CleanSettings>('/api/settings/reset').then((settings) => ({
    ok: true,
    data: cleanSettingsToAgentInstance(settings),
  }));
}

function cleanSettingsPatch(patch: CustomerAgentInstancePatch): CleanSettingsPatch {
  const result: CleanSettingsPatch = {};
  if ('display_name' in patch) result.assistant_name = patch.display_name ?? null;
  if ('user_address_name' in patch) result.user_address_name = patch.user_address_name ?? null;
  if ('persona' in patch) result.persona = patch.persona ?? null;
  if ('background' in patch) result.background = patch.background ?? null;
  if ('speaking_style' in patch) result.speaking_style = patch.speaking_style ?? null;
  if ('extra_rules' in patch) result.extra_rules = patch.extra_rules ?? null;
  if (patch.proactive && 'enabled' in patch.proactive) {
    result.proactive_enabled = patch.proactive.enabled ?? null;
  }
  if (patch.memory && 'enabled' in patch.memory) {
    result.memory_enabled = patch.memory.enabled ?? null;
  }
  return result;
}

function cleanProfilePatch(patch: CustomerAgentInstancePatch): CleanProfilePatch {
  const result: CleanProfilePatch = {};
  if ('nickname' in patch) result.nickname = patch.nickname ?? null;
  return result;
}

function cleanProfileAfterSettings(
  settings: CleanSettings,
  profilePatch: CleanProfilePatch,
): Promise<ApiResponse<CustomerAgentInstanceResult>> {
  if (Object.keys(profilePatch).length === 0) {
    return Promise.resolve({ ok: true, data: cleanSettingsToAgentInstance(settings) });
  }
  return customerApi.patch<CleanSettings>('/api/settings/profile', profilePatch).then((updated) => ({
    ok: true,
    data: cleanSettingsToAgentInstance(updated),
  }));
}

function cleanSettingsToAgentInstance(settings: CleanSettings): CustomerAgentInstanceResult {
  const agentSettings = settings.agent_settings;
  const profile = settings.user_profile;
  const displayName = agentSettings.assistant_name ?? 'Coke';
  const nickname = profile.nickname ?? '';
  const instance: CustomerAgentInstance = {
    agent_instance_id: null,
    owner_user_id: settings.account_id,
    base_agent_type: 'coke_companion',
    base_character_id: 'coke_companion',
    active: true,
    display_name: agentSettings.assistant_name,
    nickname: profile.nickname,
    user_address_name: agentSettings.user_address_name,
    persona: agentSettings.persona,
    background: agentSettings.background,
    speaking_style: agentSettings.speaking_style,
    extra_rules: agentSettings.extra_rules,
    status: {
      place: null,
      action: null,
    },
    proactive: {
      enabled: agentSettings.proactive_enabled,
    },
    memory: {
      enabled: agentSettings.memory_enabled,
    },
  };

  return {
    agent_instance: instance,
    effective_profile: {
      display_name: displayName,
      nickname,
      user_address_name: agentSettings.user_address_name,
      persona: agentSettings.persona,
      background: agentSettings.background,
      speaking_style: agentSettings.speaking_style,
      extra_rules: agentSettings.extra_rules,
      status: {
        place: '',
        action: '',
      },
      proactive: {
        enabled: agentSettings.proactive_enabled ?? true,
      },
      memory: {
        enabled: agentSettings.memory_enabled ?? true,
      },
    },
  };
}
