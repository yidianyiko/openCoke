# Prompt Rule Ownership Boundary Verification

Date: 2026-05-26

Change: move scheduling-domain argument/default/privacy details out of the
chat-response delegation prompt and into the scheduling worker prompt plus the
scheduling capability port.

## Red checks

```text
.venv/bin/python -m pytest \
  tests/unit/agent/test_chat_response_scheduling_instructions.py::test_delegation_boundary_restores_scheduling_safety_policy \
  tests/unit/agent/test_chat_response_scheduling_instructions.py::test_friend_calendar_policy_keeps_backend_facts_and_llm_reasoning_separate \
  tests/unit/agent/test_chat_response_scheduling_instructions.py::test_shared_reminder_status_policy_routes_to_list_shared_reminders \
  tests/unit/agent/test_chat_response_scheduling_instructions.py::test_shared_reminder_title_policy_prefers_current_user_activity \
  tests/unit/agent/test_scheduling_capability.py::test_list_friend_calendar_facts_sanitizes_private_event_fields -q
```

Result before implementation:

```text
4 prompt ownership assertions failed
1 friend-calendar sanitizer test failed
```

## Focused verification

```text
.venv/bin/python -m pytest \
  tests/unit/agent/test_chat_response_scheduling_instructions.py \
  tests/unit/agent/test_scheduling_capability.py \
  tests/unit/agent/test_execution_agents.py \
  tests/unit/prompt/test_prompt_token_budgets.py -q
```

Result:

```text
72 passed
```

```text
git diff --check
git diff --cached --check
```

Result: passed with no output.

## Routed verification

```text
zsh scripts/suggest-verification --base HEAD
```

Result:

```text
changed_surfaces: repo-os-docs worker-runtime
suggested_command: zsh scripts/verify-surface repo-os-docs worker-runtime
```

```text
zsh scripts/verify-surface repo-os-docs worker-runtime
```

Result:

```text
repo-os-docs: scripts/check passed
tests/unit/runner/: 67 passed
tests/unit/agent/: 511 passed
tests/unit/test_clawscale_only_topology.py: 7 passed
```

## Review trigger

```text
zsh scripts/review-trigger --base HEAD~1
```

Result after commit, with unrelated unstaged product-notification files still
present in the working tree:

```text
human_review_required: yes
- sensitive_repo_os_change [medium]
- oversized_change [medium]
- evidence_gap [medium]
```

The command still counted the unrelated dirty product-notification files in
the working tree. The committed prompt-boundary change itself is 11 files.
