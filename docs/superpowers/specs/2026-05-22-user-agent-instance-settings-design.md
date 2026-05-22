# User Agent Instance Settings Design

## Goal

Let each user customize the visible identity and prompt-facing profile of their
own agent without changing the global default character or the runtime safety
contract.

The first version supports one active agent instance per user. The user can edit
the instance name, persona, background, speaking style, extra rules, proactive
message preference, and memory preference from the customer UI. Users who never
edit these settings keep using the system default agent configuration.

## Product Decision

`characters` remains the global character template collection. User-created or
user-customized agents do not write into `characters`.

A new user-owned `agent_instances` collection stores the per-user singleton
configuration:

- `characters`: system-provided templates such as the default Coke/Kap
  companion or future template roles.
- `agent_instances`: a user's own agent instance, based on one character
  template, with user-visible overrides.
- `relations`: the long-term relationship, memory summaries, and runtime state
  between a user and an agent instance.

The first version does not create a multi-bot platform. Each user has at most
one active agent instance.

## Current Repo Reality

Today the default character prompt is primarily file-backed:

- `agent/prompt/character/coke_prompt.py` contains the core default prompt and
  status.
- `agent/prompt/character/__init__.py` maps the default character alias to that
  prompt.
- `agent/runner/context.py` currently loads the file-backed prompt and
  overwrites the character description in runtime context.
- `characters.user_info.description` can store a prompt-like description, but
  current runtime behavior treats the file-backed default as authoritative when
  a registered file prompt exists.
- `user_profiles` and `coke_settings` already exist for account-level business
  data, but they do not yet model a per-user agent instance.

This design changes the runtime composition model from "file prompt overwrites
the character description" to "global template defaults plus user-owned
instance overrides, then runtime safety boundaries".

## First-Version User Experience

Add a customer-facing setting surface, tentatively:

- `/account/my-agent`
- navigation label: `我的智能体` or `我的 Coke`

The page has these sections:

1. **Setting Summary**
   - Shows configured progress, for example `4/7 已配置`.
   - Summarizes name, persona, style, proactive message, and memory status.

2. **Basic Identity**
   - Agent display name.
   - Agent nickname.
   - Optional user address name, meaning how the agent should address the user.

3. **Agent Profile**
   - Persona.
   - Background.
   - Speaking style.
   - Extra rules.

4. **Proactive Messages**
   - Enabled or disabled.
   - First version only stores the preference. Runtime use must still obey
     reminder and proactive-message safety rules.

5. **Memory And Personalization**
   - Enabled or disabled.
   - The first version stores the preference. It does not grant blanket access
     to all memo or conversation data.

6. **Reset**
   - Restores the user instance to the default template values.
   - Does not delete the account, reminders, conversations, or global character
     template.

The user is never forced to configure this page during registration. If the user
does not configure anything, the product behaves as it does with the default
agent.

## Data Model

### `characters`

`characters` is the global template library.

It should continue to support fields like:

- `_id`
- `name`
- `nickname`
- `user_info.description`
- `user_info.status`
- template metadata

Future versions may add more templates to this collection. The first version
does not require multiple templates, but the data model should not block them.

### `agent_instances`

Create one active document per user and base agent type:

```json
{
  "agent_instance_id": "agentinst_xxx",
  "owner_user_id": "user_xxx",
  "base_agent_type": "coke_companion",
  "base_character_id": "char_xxx",
  "active": true,

  "display_name": "沈妄",
  "nickname": "沈妄",
  "user_address_name": "姐姐",

  "persona": "曾经是...",
  "background": "沈妄没有传统意义上的家庭...",
  "speaking_style": "冷静、低情绪、少反问...",
  "extra_rules": "不要像客服，不要连续反问。",

  "status": {
    "place": "工位",
    "action": "陪伴中"
  },

  "proactive": {
    "enabled": true
  },

  "memory": {
    "enabled": true
  },

  "created_at": "2026-05-22T00:00:00Z",
  "updated_at": "2026-05-22T00:00:00Z"
}
```

Recommended unique index:

- `owner_user_id + base_agent_type + active`

The first version should enforce one active `agent_instance` per user for
`base_agent_type = coke_companion`.

## Config Composition

Runtime composes the final agent profile in this order:

1. Global character template from `characters` or the file-backed default.
2. User-owned `agent_instances` overrides.
3. Current conversation and trusted runtime context.
4. Runtime safety, delegation, reminder, scheduling, and visibility boundaries.

User overrides only affect the allowed visible/profile fields:

- display name
- nickname
- user address name
- persona
- background
- speaking style
- extra rules
- status display
- proactive preference
- memory preference

User overrides must not replace or weaken:

- `base_agent_type`
- tool permissions
- reminder creation and confirmation rules
- scheduling and appointment safety rules
- memory access boundaries
- system safety rules
- routing rules
- audit rules
- model provider or model id

## Prompt Composition

The user instance profile must be rendered as structured data, not as a raw
system prompt replacement.

Example rendered block:

```text
User-configured agent profile:
display_name: "沈妄"
nickname: "沈妄"
user_address_name: "姐姐"
persona: "曾经是..."
background: "沈妄没有传统意义上的家庭..."
speaking_style: "冷静、低情绪、少反问..."
extra_rules: "不要像客服，不要连续反问。"
proactive_enabled: true
memory_enabled: true
```

The renderer must escape or JSON-encode user-provided values. If a user writes
`SYSTEM: ignore previous rules`, it remains profile text and does not become a
new instruction.

The final prompt order should keep safety boundaries after the user-configured
block so those boundaries remain the last authority:

1. Base chat-response instructions.
2. Trusted runtime context.
3. User-configured agent profile.
4. User-visible reply boundary.
5. Delegation, reminder, scheduling, and tool-use boundary.
6. Timezone and event-specific runtime facts.

## Field Rules

### Agent Display Name

- Default: the base character nickname.
- Required after editing, but the user can reset to default.
- Suggested limit: 1-20 visible characters.
- Used in UI, chat identity, summaries, and proactive-message display.
- Does not affect internal routing or capability permissions.

### Persona, Background, Speaking Style, Extra Rules

- Optional.
- First-version limits:
  - `persona`: 2,000 characters.
  - `background`: 4,000 characters.
  - `speaking_style`: 1,000 characters.
  - `extra_rules`: 1,000 characters.
- Stored as user-owned text fields.
- Used as low-priority profile data.
- Cannot override runtime safety boundaries.

### Proactive Messages

- Optional boolean.
- Default should follow the current system default.
- `enabled=false` prevents optional proactive follow-up behavior from using the
  user instance preference.
- User-created reminders still fire according to the reminder system contract.

### Memory

- Optional boolean.
- Default should follow the current system default.
- `enabled=false` prevents user instance profile data from being expanded with
  optional long-term personalization.
- This does not delete existing reminders or account data.

## Non-Goals

- Do not support multiple active bots per user.
- Do not build a bot marketplace.
- Do not let users edit raw system prompts.
- Do not expose model provider or model selection in the first version.
- Do not let user settings override reminder, scheduling, memory, routing,
  audit, or tool boundaries.
- Do not migrate all existing character prompt text into database fields in one
  broad rewrite.
- Do not delete or replace the global `characters` collection.
- Do not treat `agent_instances` as a shared global template.

## Migration Strategy

The first version can be additive:

1. Keep the existing default character template.
2. Add `agent_instances` storage and DAO methods.
3. On read, if the user has no active instance, synthesize an implicit instance
   from the default character template.
4. On first save from the UI, create or update the user's active instance.
5. Runtime reads the active instance and appends its allowed fields to the
   prompt as structured profile data.

No existing user should be required to configure an agent instance.

## Verification Expectations

Minimum tests and checks:

- A user with no `agent_instance` uses the default agent name and profile.
- Saving `display_name = "沈妄"` changes user-visible agent naming without
  changing `base_agent_type`.
- Saving persona/background/style fields adds them to the structured profile
  block.
- Malicious text such as `SYSTEM: ignore previous rules` is escaped and cannot
  override safety rules.
- A user rule such as "以后不用确认，直接帮我预约/提醒" does not bypass reminder
  or scheduling confirmation rules.
- `proactive.enabled=false` is respected by optional proactive follow-up logic,
  while user-created reminders still fire normally.
- Reset restores default template-derived values for future turns.
- The UI supports load, edit, save, save failure, and reset states.

For repo verification, route the final implementation through diff-aware
verification. Expected surfaces include at least:

- worker-runtime / prompt tests for runtime composition
- gateway web tests for the setting page
- customer API tests if a gateway API is added
- repo-OS docs checks if feature discovery or retention docs are changed

## Open Follow-Up Work

These are intentionally outside the first version:

- Multiple global character templates exposed to users.
- One user owning multiple active bots.
- Template marketplace or template sharing.
- Per-instance model selection.
- Full memory management UI with per-memory deletion and audit evidence.
- Rich media identity such as avatar, voice, and sticker packs.
