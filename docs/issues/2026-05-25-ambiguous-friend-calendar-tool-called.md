---
kind: active_issue
status: resolved
surface:
  - agent-runtime
  - scheduling-domain
created_at: 2026-05-25
updated_at: 2026-05-25
---

# 2026-05-25 Ambiguous Friend Calendar Query Calls Calendar Tool

## What Happened

Live smoke batch `ambiguous-friend-calendar-20260525t085139Z` set up Alice with
two active friends:

- `Bob Ambiguous`
- `Bobby Ambiguous`

Alice then asked:

```text
看 B 那个朋友这周的空闲时间。
```

The final user-visible reply was acceptable:

```text
你通讯录里好几位朋友名字里带 B 的，说的是哪位呀？
```

But `agent_sessions` showed the assistant first called:

```json
{"intent": {"list_friend_calendar_facts": {"friend_name": "B"}}}
```

The scheduling domain failed with `friend_name_ambiguous`, and the assistant
then made an unrelated `calendar_import` tool call before finally asking the
clarifying question.

## Why It Matters

The smoke skill's ambiguous-friend contract is explicit: when the friend name
is ambiguous, the assistant must ask which friend and must not call the calendar
tool. Calling `list_friend_calendar_facts` before disambiguation risks leaking
or probing another user's calendar boundary if backend ambiguity detection is
ever incomplete.

The follow-up `calendar_import` call is also wrong for this path. Alice asked
about a friend's availability, not her own calendar import setup.

## Evidence

- Artifact:
  `artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-ambiguous-friend-calendar-20260525t085139Z.json`
- Postgres precondition:
  two active `friendships` rows for Alice, one with Bob and one with Bobby.
- `agent_sessions`:
  `scheduling_domain -> list_friend_calendar_facts(friend_name="B")`, then
  `calendar_import`, then clarification reply.

## Current Status

Resolved locally. The scheduling domain now returns a clarification result at
the domain boundary for partial friend references like `B 那个朋友`, including
the preselected-intent path where no structured `friend_name` argument exists
yet.

## Resolution

- Fix: `agent/agno_agent/runtime/execution_agents.py` now turns partial
  one-letter friend references in calendar queries into a scheduling
  `needs_clarification` result before creating scheduling ports or worker
  tools.
- Regression coverage:
  `tests/unit/agent/test_execution_agents.py`
- Verification:
  `.venv/bin/python -m pytest tests/unit/agent/test_execution_agents.py tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_preserves_tool_key_args -q`
  passed with 23 tests.
- Live smoke:
  `artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-ambiguous-friend-calendar-fix-20260525t093412z.json`
  passed. The tool trace shows `scheduling_domain` returning
  `outcome='needs_clarification'`, `operations=[]`, and
  `safety_boundary='ambiguous_friend_name'`; no `list_friend_calendar_facts`
  operation or `calendar_import` call occurred.
