# 2026-05-29 friend-count prompt routing

## Scope

- Incident thread: after switching `chat_response` and `semantic_interpreter`
  to `Pro/moonshotai/Kimi-K2.6`, shared meeting creation worked in the marked
  production smoke, but the friend-count query still answered that no
  friend-list function was available.
- Root cause narrowed in code:
  - `list_friends` already exists and can summarize friend count.
  - `chat_response` did not explicitly classify "我现在有几个好友" as
    `list_friends`.
  - semantic pre-execution was only triggered for explicit friend-invite
    scheduling phrases, so friend count/list queries never entered the
    semantic interpreter before the final chat model.
- Fix shape: prompt/routing-boundary change, not a broad validation layer.

## RED

- Command:
  `.venv/bin/python -m pytest tests/unit/agent/test_chat_response_scheduling_instructions.py::test_delegation_boundary_routes_friend_count_queries_to_list_friends tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_runs_semantic_interpreter_for_friend_count_query -q`
- Expected failures before the fix:
  - Prompt test failed because `"我现在有几个好友"` was absent from the
    `chat_response` delegation boundary.
  - Runtime test failed because the semantic client was not invoked for
    `"我现在有几个好友？"`; the path logged `has_preselected_intent=False`.

## GREEN

- Added explicit `list_friends` delegation guidance for friend count/list
  questions in `chat_response`.
- Added matching `list_friends` semantic-interpreter guidance.
- Added narrow explicit scheduling-interpreter trigger patterns for friend
  count/list wording.
- Same command passed: `2 passed in 2.17s`.

## Verification

- Format:
  `.venv/bin/python -m black agent/agno_agent/runtime/chat_response_instructions.py agent/agno_agent/runtime/semantic_interpreter.py agent/agno_agent/runtime/agent_runtime.py tests/unit/agent/test_chat_response_scheduling_instructions.py tests/unit/agent/test_agent_runtime_construction.py`
- Focused tests:
  `.venv/bin/python -m pytest tests/unit/agent/test_chat_response_scheduling_instructions.py tests/unit/agent/test_semantic_interpreter.py tests/unit/agent/test_agent_runtime_construction.py -q`
  passed: `102 passed in 2.96s`.
- Repo checks:
  `zsh scripts/check` passed.
- Suggested worker-runtime support:
  `.venv/bin/python -m pytest tests/unit/runner/ -v` passed:
  `72 passed in 2.33s`.
  `.venv/bin/python -m pytest tests/unit/test_clawscale_only_topology.py -v`
  passed: `7 passed in 0.24s`.
- Full agent unit suite:
  `.venv/bin/python -m pytest tests/unit/agent/ -v` passed:
  `563 passed in 841.20s`.

## Status

- Committed local fix: `4f6a8061`.
- Production deployment:
  - Full deploy script was not used because the local worktree still had
    unrelated dirty files.
  - Backed up and synced only these runtime files to `gcp-coke`:
    `agent_runtime.py`, `chat_response_instructions.py`,
    `semantic_interpreter.py`.
  - Rebuilt and restarted only `coke-agent` with
    `docker compose -f docker-compose.prod.yml up -d --build coke-agent`.
  - Health checks after restart:
    - bridge `/bridge/healthz`: `{"ok":true}`
    - gateway `/health`: `{"ok":true,"version":"0.1.0"}`
- Production smoke:
  - Marker: `friend-count-prompt-20260528T163000Z`.
  - Requester: Li Zihao, `ck_CsFu-A91jbCSBwtizPx1K`.
  - Prompt: `我现在有几个好友？`
  - Bridge response:
    `ok=true`, `output_id=6a186d58a3abe0a13c80aed9`,
    `business_conversation_key=bc_6a1019b60fedec4719365fd5`.
  - Visible reply:
    `哎，之前是我搞错了。你现在有2个好友：olivers 和 eva。`
  - Mongo output row:
    `6a186d58a3abe0a13c80aed9`, `status=handled`, no
    `fallback_kind`, same causal inbound event id.
  - Postgres active friendships for the requester matched the reply:
    `olivers` and `eva`.
  - Agent runtime log for the turn:
    `tools=0, has_preselected_intent=True`, which means the final chat model
    received a preselected scheduling-domain result instead of choosing tools
    itself.
