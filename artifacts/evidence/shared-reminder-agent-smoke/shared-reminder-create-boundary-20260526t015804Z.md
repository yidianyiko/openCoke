# Shared Reminder Create Boundary Verification

## Change

- `agent/agno_agent/runtime/agent_runtime.py` now treats outer
  `create_shared_reminder` tool-key arguments as intent selection only.
- The inner scheduling worker remains responsible for deriving title, time, and
  duration from the current user message.

## Regression

- Real incident text:
  `今天上午十点半，帮我和 EVA 约一个一个小时的时间去做测试`
- Red test before implementation:
  `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_scheduling_domain_does_not_force_shared_reminder_create_args -q`
- Expected failure before fix:
  `forced_args` contained `title: 一起运动`.
- Passing after fix:
  same command, `1 passed`.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -q`
  - `60 passed`
- `.venv/bin/python -m pytest tests/unit/agent/test_execution_agents.py tests/unit/agent/test_agent_runtime_scheduling_tools.py -q`
  - `35 passed`
- `.venv/bin/python -m pytest tests/unit/agent/test_chat_response_scheduling_instructions.py::test_shared_reminder_status_policy_routes_to_list_shared_reminders -q`
  - `1 passed`
- `zsh scripts/verify-surface worker-runtime`
  - `tests/unit/runner/`: `67 passed`
  - `tests/unit/agent/`: `496 passed`
  - `tests/unit/test_clawscale_only_topology.py`: `7 passed`
- `git diff --check`
  - passed

## Notes

- The first `worker-runtime` run failed only because one prompt text assertion
  expected an older equivalent wording. The test assertion was updated to the
  current prompt contract and the full surface passed after rerun.
