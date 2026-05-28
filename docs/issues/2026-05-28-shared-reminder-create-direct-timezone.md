---
kind: incident
status: resolved
area: agent-runtime
created_at: 2026-05-28
---

# Shared Reminder Create Direct Timezone Rejection

## What Happened

During production real-account validation, 李梓豪 sent:

- `帮我和olivers约一个今天晚上十点去喝酒`
- `帮我和eva约一个今天晚上十一点去喝茶`

The agent called `scheduling_domain`, but no `shared_reminders` rows were
created for `喝酒` or `喝茶`.

## Impact

User-visible shared-reminder creation failed even though the named friends were
active. The failure was not a provider delivery failure and was not a gateway
database write failure.

## Evidence

Production `agent_sessions` showed the model supplied canonical create fields
inside `intent`, but supplied `timezone` as a direct tool argument:

```json
{
  "intent": {
    "action": "create_shared_reminder",
    "receiver_name": "olivers",
    "title": "喝酒",
    "fire_at": "2026-05-28T22:00:00",
    "duration_minutes": 120
  },
  "timezone": "Asia/Shanghai"
}
```

The runtime normalized the `intent` payload correctly, then validated the direct
`timezone` argument by itself as if it were a full `create_shared_reminder`
payload. That produced `invalid_scheduling_args` with missing
`counterparty`, `title`, and `fire_at`.

## Fix

For `create_shared_reminder`, when forced args are already present from the
`intent` payload, merge direct tool args such as `timezone` into those forced
args before running canonical create validation.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_merges_direct_timezone_into_create_args tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_rejects_noncanonical_create_payloads -q`
- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -q`
- `zsh scripts/check`
- `.venv/bin/python -m pytest tests/unit/agent/ -q`
- `.venv/bin/python -m pytest tests/unit/runner/ -q`
- `.venv/bin/python -m pytest tests/unit/test_clawscale_only_topology.py -q`
