---
kind: active_issue
status: blocked
surface:
  - clean-rebuild-backend
  - deploy
created_at: 2026-06-15
updated_at: 2026-06-15
---

# 2026-06-15 Z.AI GLM-5.2 Permission Blocker

## What Happened

Z.AI official docs list `glm-5.2` as the latest GLM Coding Plan model. Before
deploying Coke's text LLM defaults to that model, the production clean host was
probed with the existing `ZAI_API_KEY` from `/home/whoami/coke-clean/.env`.

Both endpoints rejected `glm-5.2`:

- `https://api.z.ai/api/coding/paas/v4/chat/completions`
- `https://api.z.ai/api/paas/v4/chat/completions`

The response was HTTP 403 with provider error code `1220` and message
`You do not have permission to access glm-5.2`.

The same key successfully called `glm-5.1` on the general endpoint with
`thinking: {"type": "disabled"}`, returning `content=ok`.

The model-list probes for both general and coding endpoints returned:

```text
glm-4.5, glm-4.5-air, glm-4.6, glm-4.7, glm-5, glm-5-turbo, glm-5.1
```

`glm-5.2` was not in the accessible model list.

## Why It Matters

If Coke defaults to `glm-5.2` before the production Z.AI key is entitled for
that model, all real text LLM calls on the turn path can fail with provider
403s. That would affect planner, interaction, and detector calls.

## Current Status

Blocked on Z.AI account/model entitlement. Do not deploy `glm-5.2` defaults
with the current production key.

Production remains on the previously working `glm-5.1` default.

## Next Step

After the Z.AI account is upgraded or a key with `glm-5.2` access is installed
in the clean production `.env`, rerun the remote probes:

1. `glm-5.2` chat-completions with `thinking: {"type": "disabled"}`.
2. `/models` listing for the selected endpoint.
3. Coke backend deploy and health checks.
4. A post-deploy production trace check for `public.turn`,
   `public.output_disposition`, and `ai.agno_sessions` to confirm no hidden
   retry/recovery spike.
