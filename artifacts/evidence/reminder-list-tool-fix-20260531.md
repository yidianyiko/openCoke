# Reminder List Tool Fix Evidence

Date: 2026-05-31

## Production Root Cause

Production run evidence for `现在我一共有几个提醒？` showed:

```text
semantic_decision.intent_family=reminder_op
semantic_decision.intent_action=list_reminders
tool_name=reminder_tool
tool_args={"operation": "list_reminders", "account_id": "ae02ff01..."}
tool_result.ok=false
tool_result.reason_code=unsupported_reminder_operation
```

The affected account's active reminders were present in Postgres, so the issue
was a missing Interaction Agent tool operation, not unavailable reminder state.

## Commands

```text
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_reminder_tool_list_reminders_returns_active_count_without_write_guard -q
```

Result: failed before implementation because `ReminderToolAdapter.execute`
entered the write guard before recognizing `list_reminders`.

```text
.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py::test_tool_ports_are_exposed_as_agno_tools_and_execute_with_guard -q
```

Result: failed before implementation because the reminder tool doc did not
expose `list_reminders`.

```text
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_reminder_tool_list_reminders_returns_active_count_without_write_guard -q
.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py::test_tool_ports_are_exposed_as_agno_tools_and_execute_with_guard -q
.venv/bin/python -m pytest tests/integration/coke/test_composition_turn_integration.py::test_inbound_reminder_count_uses_tool_result_for_visible_reply -q
```

Result: all focused tests passed after implementation.

```text
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/llm/test_interaction_agent.py tests/integration/coke/test_composition_turn_integration.py -q
```

Result: 81 passed in 2.25s.

```text
.venv/bin/python -m pytest tests/unit/coke -q
zsh scripts/check
git diff --check
```

Result: 588 unit tests passed in 17.42s; repo structure check passed; whitespace
check passed.

```text
zsh scripts/verify-surface clean-rebuild-backend repo-os-docs
```

Result: clean-rebuild-backend passed with 588 unit tests in 17.61s;
repo-os-docs passed.

```text
zsh scripts/review-trigger --base HEAD~1
```

Result: `human_review_required: no`. Remaining medium risk triggers were
repo-OS issue-record changes; the evidence gap was resolved after this evidence
file was added to the indexed diff.
