---
title: Agent misclassifies own user-link requests as friend-add requests
kind: incident
date: 2026-05-25
status: resolved
affected_surfaces:
  - agent/agno_agent/capabilities/scheduling.py
  - agent/agno_agent/runtime/agent_runtime.py
  - tests/unit/agent/test_agent_runtime_construction.py
  - tests/unit/agent/test_scheduling_capability.py
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260524t170107Z.json
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260524t170520Z.json
---

# Agent misclassifies own user-link requests as friend-add requests

## What happened

Smoke batch `20260524t170107Z` diverged in Phase 1. Alice asked:

`把我自己的好友邀请链接给我，我要分享给一个朋友。`

The assistant replied that it could not get the invite link. Direct gateway
verification immediately succeeded:

`POST /api/internal/scheduling/tools/get_user_link`

returned an active code and URL for `ck_smoke_20260524t170107Z_alice`.

## Why it matters

The first shared-reminder smoke phase depends on Alice getting her own public
user link. When the agent misroutes that read-only request as a friend-add
write, users are told the system cannot fetch a link even though the gateway
tool works.

## Evidence

`agent_sessions` for Alice's turn showed:

- chat agent called `scheduling_domain` with `{"get_user_link": {}}`
- runtime preselected the scheduling intent from the raw text as
  `send_friend_request_by_user_link_code`
- scheduling execution returned `no_tool_called`

The root cause was twofold:

- `_normalize_scheduling_intent` ignored mappings whose key is the tool name,
  such as `{"get_user_link": {}}`.
- `_infer_scheduling_intent_from_message` treated any Chinese text containing
  `邀请链接` plus `好友` as `send_friend_request_by_user_link_code`, including
  "my own friend invite link" requests.

Follow-up live batch `20260524t170520Z` showed the domain tool then executed
successfully, but the assistant still returned the empty fallback because the
successful `get_user_link` read result had no `visible_summary` for runtime
fallback when the chat model produced empty final text.

## Fix

Recognize scheduling tool-name keys in dict intents, and classify first-person
own-link wording (`我的` / `我自己的` / `自己的` plus link words) as
`get_user_link` unless it is a reset or disable request.

For successful `get_user_link` results, add a visible summary containing the
public invite URL so the runtime can return the link even if the model emits
empty final text after the tool call.

## Resolution

- Resolution commit: `e037b313`.
- Verified green at 2026-05-25.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_scheduling_intent_inference_treats_own_invite_link_as_get_user_link -q`
  failed before the fix with `send_friend_request_by_user_link_code`.
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_honors_tool_key_intent -q`
  failed before the fix with `send_friend_request_by_user_link_code`.
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_scheduling_intent_inference_treats_own_invite_link_as_get_user_link tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_honors_tool_key_intent tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_normalizes_dict_intent -q`
  passed after the fix.
- `.venv/bin/python -m pytest tests/unit/agent/test_scheduling_capability.py::test_get_user_link_provides_visible_summary_for_empty_chat_text -q`
  failed before the visible-summary fix with `KeyError: 'visible_summary'`.
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_scheduling_capability.py -q`
  passed after both fixes.
