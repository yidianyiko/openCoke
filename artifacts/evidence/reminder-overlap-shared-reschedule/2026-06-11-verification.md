# Reminder Overlap + Shared Reschedule Verification

Date: 2026-06-11
Branch: `feature/reminder-overlap-shared-reschedule`

## Local Verification

Targeted unit tests passed:

```text
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_service.py tests/unit/coke/turn/v2/test_reminder_handler.py tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/turn/v2/test_social_handler.py -q
101 passed in 2.15s

/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/smoke/test_v6_wechat_smoke.py tests/unit/coke/llm/test_semantic_interpreter.py tests/unit/coke/llm/test_interaction_agent.py::test_social_scheduling_tool_doc_describes_shared_reminder_creation tests/unit/coke/llm/test_interaction_agent.py::test_social_scheduling_tool_doc_describes_friend_list_availability_and_cancel tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/turn/test_output_protocol.py -q
84 passed in 2.29s
```

Diff-aware routing:

```text
zsh scripts/suggest-verification --base HEAD~1
suggested_command: zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs

zsh scripts/review-trigger --base HEAD~1
human_review_required: no
risk_triggers: yes
```

Full suggested surface passed:

```text
zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs
clean-rebuild-docs: check passed
clean-rebuild-backend: 1067 passed in 21.03s
repo-os-docs: check passed
```

During the first full backend run, three existing tests failed because they used
normal reminder creation to fabricate two reminders with the same owner and
same due time. Under the new product contract, that input is now rejected as a
time conflict. The tests were classified as test/eval mismatch and updated to
insert historical reminders directly into the repository, preserving coverage
for calendar merge and scheduler fire grouping without weakening the runtime
creation contract.

Regression rerun for the three adjusted tests passed:

```text
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/reminder/test_reminder_calendar_read_model.py::test_calendar_includes_undelivered_and_merged_same_time_groups tests/unit/coke/reminder/test_reminder_scheduler.py::test_same_owner_same_due_time_is_one_grouped_fire_turn_with_ordered_fire_ids tests/unit/coke/reminder/test_reminder_scheduler.py::test_restart_catch_up_keeps_personal_and_shared_but_discards_missed_proactive -q
3 passed in 0.52s
```
