# Semantic Intent Routing Worker A Evidence

Date: 2026-05-27
Branch: `worker-a-semantic-intent-routing`
Surface: `worker-runtime`

## Change Under Test

- Removed regex/direct pre-routing for supported shared and personal reminder
  user utterances in `agent/agno_agent/runtime/agent_runtime.py`.
- Kept pre-agent explicit-past and retired-account-control checks as runtime
  safety guards that reject impossible or retired writes, not as supported
  intent routers.
- Updated focused runtime construction tests to prove regex-matching reminder
  utterances no longer bypass the semantic interpreter or interaction-agent
  tool path.

## Verification

- RED check before implementation:
  `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_routes_explicit_reminder_through_agent_tool tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_does_not_regex_preselect_friend_invite_with_concrete_time tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_does_not_directly_execute_explicit_personal_reminder tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_does_not_directly_execute_explicit_personal_reminder_crud -q`
  failed because the runtime still called `run_reminder_domain` /
  `run_scheduling_domain` before the interaction-agent path.
- Targeted regression:
  `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -q`
  passed, `63 passed`.
- Semantic interpreter:
  `.venv/bin/python -m pytest tests/unit/agent/test_semantic_interpreter.py -q`
  passed, `8 passed`.
- Diff-aware routing:
  `zsh scripts/suggest-verification --base HEAD~1` suggested
  `zsh scripts/verify-surface repo-os-docs worker-runtime`; the apparent
  `repo-os-docs` surface came from `HEAD~1` including a pre-existing docs issue
  file outside this patch.
- Worker runtime surface:
  `PATH="/data/projects/coke/.venv/bin:$PATH" zsh scripts/verify-surface worker-runtime`
  passed: `69 passed`, `533 passed`, `7 passed`.
- Hygiene:
  `git diff --check` passed.
  `zsh scripts/review-trigger --base HEAD` reported
  `human_review_required: no`.
