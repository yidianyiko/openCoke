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
  between a user and the active companion. In the first version this remains
  keyed by the existing user id plus base character id pair.

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
- The active single-Agent path converts the legacy context into
  `AgentRunContext` in `agent/agno_agent/runtime/context.py`, then builds the
  model-facing instruction string in
  `agent/agno_agent/runtime/chat_response_instructions.py`. Unknown keys added
  to the legacy context are not automatically rendered into the model
  instructions.
- `characters.user_info.description` can store a prompt-like description, but
  current runtime behavior treats the file-backed default as authoritative when
  a registered file prompt exists.
- `user_profiles` and `coke_settings` already exist for account-level business
  data, but they do not yet model a per-user agent instance.
- Gateway API is TypeScript/Postgres-first and does not currently carry a
  MongoDB driver dependency. Customer APIs that manipulate worker-owned MongoDB
  state, such as reminders, call authenticated bridge-internal endpoints
  instead of writing MongoDB directly from gateway.

This design changes the runtime composition model from "file prompt overwrites
the character description" to "global template defaults plus user-owned
instance overrides, then runtime safety boundaries".

## First-Version User Experience

Add a customer-facing setting surface:

- `/account/my-agent`
- navigation label: `我的智能体` in Chinese and `My Agent` in English

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
   - Runtime uses the preference only to gate optional internal follow-up /
     proactive behavior. User-created reminders still fire through the Reminder
     System contract.

5. **Memory And Personalization**
   - Enabled or disabled.
   - Runtime uses the preference only to decide whether optional long-term
     personalization may be included in the instance profile. It does not grant
     blanket access to all memo or conversation data.

6. **Reset**
   - Clears all user-provided override fields on the active `agent_instances`
     document (sets them to `null` or removes them). Does **not** delete the
     document itself — the row remains as an empty override, and runtime
     fallback to the default character template still applies.
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
  "owner_user_id": "ck_xxx",
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

- Partial unique index on `(owner_user_id, base_agent_type)` filtered to
  `{ active: true }`.

A compound index on all three fields (`owner_user_id + base_agent_type +
active`) does **not** enforce uniqueness because multiple inactive documents
would share the same `active: false` value and violate the index. Use a
partial unique index in MongoDB:
`db.agent_instances.createIndex({ owner_user_id: 1, base_agent_type: 1 }, { unique: true, partialFilterExpression: { active: true } })`

The first version should enforce one active `agent_instance` per user for
`base_agent_type = coke_companion`.

`owner_user_id` is the Coke customer/account id used by customer auth and the
worker runtime, for example `ck_*` or `acct_*`. It is not the gateway
`identityId`. `agent_instance_id` is the public stable id for the instance;
MongoDB still has its own `_id`.

## Character Name Mapping

`base_agent_type = "coke_companion"` maps to character name `"kap"` in the
file-backed character prompt registry at
`agent/prompt/character/__init__.py`. Runtime lookups must use `"kap"` as
the key when calling `get_character_prompt()`. Do not hardcode
`"coke_companion"` in the prompt lookup path.

If new character types are added in the future, extend `CHARACTER_PROMPTS` in
`agent/prompt/character/__init__.py` and add the corresponding
`base_agent_type` mapping in the DAO or composition layer.

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

`relations` remains keyed by the existing `(uid, cid)` pair in the first
version, where `cid` is the base character id. Do not migrate `relations.cid`
to `agent_instance_id` until the product actually supports more than one active
bot per user.

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

Implementation must carry the composed profile into the active Agno instruction
path, not only into an arbitrary legacy context key:

1. `context_prepare()` may load and normalize the active instance.
2. `build_agent_run_context()` must explicitly copy the composed profile into a
   typed or metadata field on `AgentRunContext`.
3. `build_chat_response_instructions()` must render the block between trusted
   runtime context and the user-visible reply boundary.

Do not rely on `context["agent_instance_profile"]` alone; the current
`AgentRunContext` builder intentionally drops unknown raw context fields.

The final prompt order should keep safety boundaries after the user-configured
block so those boundaries remain the last authority:

1. Base chat-response instructions.
2. Trusted runtime context.
3. User-configured agent profile.
4. User-visible reply boundary.
5. Delegation, reminder, scheduling, and tool-use boundary.
6. Timezone and event-specific runtime facts.

## Gateway API Contract

Add a customer-facing API under the existing customer auth pattern. Gateway is
the customer-auth adapter; it must not write the MongoDB `agent_instances`
collection directly. Follow the reminder pattern:

- Add `gateway/packages/api/src/lib/agent-instance-runtime-client.ts` to call
  bridge-internal endpoints with `COKE_BRIDGE_API_KEY`.
- Add `gateway/packages/api/src/routes/customer-agent-instance-routes.ts` for
  customer auth, validation, and error mapping.
- Import and mount the router in `gateway/packages/api/src/index.ts`.

Three customer endpoints are needed:

```
GET  /api/customer/agent-instance
     → 200 { agent_instance, effective_profile }
     → 401 if not authenticated
     → 403 if customer claim is inactive
     → 404 if the customer account no longer exists

PATCH /api/customer/agent-instance
     body: allowed override fields only (display_name, nickname,
           user_address_name, persona, background, speaking_style,
           extra_rules, status, proactive, memory)
     → 200 { agent_instance, effective_profile }
     → 400 on validation failure (field too long, etc.)
     → 401 if not authenticated
     → 403 if customer claim is inactive
     → 404 if the customer account no longer exists

POST /api/customer/agent-instance/reset
     → 200 { agent_instance, effective_profile }
     → 401 if not authenticated
     → 403 if customer claim is inactive
     → 404 if the customer account no longer exists
```

The concrete HTTP response should use the existing gateway wrapper
`{ ok: true, data: ... }`; the shapes above describe `data`.

The API must reject any fields not in the allowed override list. It must not
accept `base_agent_type`, `base_character_id`, `owner_user_id`, `active`, or
any field not in the config composition allow-list.

`effective_profile` is the default template merged with the current overrides,
so the UI can render meaningful default values without persisting an empty row.
`agent_instance` returns the stored or synthesized override document.

## Bridge/Internal Runtime Contract

The bridge/worker side owns MongoDB writes for `agent_instances`.

Add an internal service, for example
`connector/clawscale_bridge/agent_instance_service.py`, backed by
`dao/agent_instance_dao.py`. Wire it into `connector/clawscale_bridge/app.py`
with bridge-authenticated endpoints:

```
GET   /bridge/internal/agent-instances?customer_id=ck_xxx
PATCH /bridge/internal/agent-instances
POST /bridge/internal/agent-instances/reset
```

The request body for update/reset includes `customer_id`; the service derives
`owner_user_id` from that trusted value and never accepts it from the customer
request body. The service is also responsible for:

- seeding or resolving the default `base_character_id` for `coke_companion`
- synthesizing the no-row response from the base character template
- validating length limits and nested boolean/status shapes
- creating the MongoDB partial unique index
- returning the same serialized shape used by gateway:
  `{ agent_instance, effective_profile }`

Do not add a direct MongoDB dependency to `gateway/packages/api` for this
feature.

## Frontend Contract

Add the customer page at
`gateway/packages/web/app/(customer)/account/my-agent/page.tsx`.

Frontend work should also add:

- `gateway/packages/web/lib/customer-agent-instance.ts` for typed API helpers
- page tests beside the new page
- customer API helper tests
- a `CustomerShell` navigation item for `/account/my-agent`
- localized copy in `gateway/packages/web/lib/i18n.ts`

The page should follow the existing account-page pattern for authentication:
load the instance on mount, redirect unauthenticated users to
`/auth/login?next=/account/my-agent`, support save and reset failures, and keep
unsaved form edits local until the user saves.

## Field Rules

### Agent Display Name

- Default: the base character nickname.
- Required after editing, but the user can reset to default.
- Suggested limit: 1-20 visible characters.
- Used in UI, chat identity, summaries, and proactive-message display.
- Does not affect internal routing or capability permissions.

### Nickname

- Optional. Defaults to the base character nickname.
- Suggested limit: 1–20 visible characters.
- Used interchangeably with display name in chat context and proactive
  messages. If set, runtime uses this value; otherwise falls back to
  display name.

### User Address Name

- Optional. How the agent addresses the user (e.g., `"姐姐"`, `"老师"`).
- Suggested limit: 1–10 visible characters.
- Used in the structured profile block rendered into the prompt.
- If not set, the agent uses no special address form.

### Status

- Optional. Object with `place` (string, ≤20 chars) and `action` (string,
  ≤20 chars).
- Represents the agent's current displayed location/activity.
- Defaults to the base character's status values when not set.
- User-editable in the first version but does not affect routing or
  capability permissions.

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

- Optional boolean. Default: `true` (proactive follow-up enabled).
- If `null` or absent on the stored document, runtime treats the value as
  `true`.
- `enabled=false` prevents optional proactive follow-up behavior from being
  created from the instance profile.
- User-created reminders still fire according to the reminder system contract.

### Memory

- Optional boolean. Default: `true` (long-term personalization enabled).
- If `null` or absent on the stored document, runtime treats the value as
  `true`.
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

## Runtime Integration Point

The active instance must be loaded and composed in `context_prepare()` in
`agent/runner/context.py`, after the file-backed character prompt is applied
and before the final context dict is returned.

Concretely:
1. Call `get_active_agent_instance(user_id, base_agent_type="coke_companion")`.
2. If the result is `None`, synthesize the default profile from the current
   character template for model-facing composition, without writing a MongoDB
   row.
3. If an instance is found, merge only the allowed override fields onto the
   base template.
4. Store the normalized object in a stable key such as
   `context["agent_instance_profile"]`.
5. Extend `build_agent_run_context()` and `AgentRunContext` so the active
   single-Agent runtime carries the profile into
   `build_chat_response_instructions()`.

Add `get_active_agent_instance`, `upsert_active_agent_instance`, and
`reset_active_agent_instance` to a new `dao/agent_instance_dao.py`. Keep
`dao/user_dao.py` focused on existing profile/settings/characters behavior.

## Migration Strategy

The first version can be additive:

1. Keep the existing default character template.
2. Add `agent_instances` storage and DAO methods.
3. On read, if the user has no active instance, synthesize an implicit
   instance from the default character template. The synthesized instance
   should have all override fields set to `null` or empty string, while
   `effective_profile` carries the merged default values for display.
4. On first save from the UI, create or update the user's active instance.
5. Runtime reads the active instance and appends its allowed fields to the
   prompt as structured profile data.

No existing user should be required to configure an agent instance.

## Documentation Updates

Implementation must update `docs/product-specs/FEATURE_TREE.md` when the
customer route/API is added. Because `agent_instances` stores user-provided
profile text, implementation must either add a dedicated retention-policy row
to `docs/design-docs/data-retention-policy.md` or explicitly map the collection
to `user_content_retention` in the relevant ownership docs.

## Verification Expectations

Minimum tests and checks:

- A user with no `agent_instance` uses the default agent name and profile.
- `build_agent_run_context()` carries the composed profile into
  `AgentRunContext`, and `build_chat_response_instructions()` renders it in the
  required order.
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
- Gateway route tests prove customer ids come from the authenticated session,
  not from request query/body fields.
- Bridge service/app tests prove the internal endpoints enforce bridge auth,
  validate fields, synthesize defaults, and write only owner-scoped documents.

For repo verification, route the final implementation through diff-aware
verification. Expected surfaces include at least:

- worker-runtime / prompt tests for runtime composition
- gateway web tests for the setting page
- gateway customer API tests and API topology mount tests
- bridge/internal service tests
- repo-OS docs checks for feature discovery and retention-doc updates

## Open Follow-Up Work

These are intentionally outside the first version:

- Multiple global character templates exposed to users.
- One user owning multiple active bots.
- Template marketplace or template sharing.
- Per-instance model selection.
- Full memory management UI with per-memory deletion and audit evidence.
- Rich media identity such as avatar, voice, and sticker packs.
