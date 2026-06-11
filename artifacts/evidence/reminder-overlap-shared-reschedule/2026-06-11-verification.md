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

## Live GCP Deployment And WeChat Smoke

Runtime target: GCP clean stack `gcp-coke:/home/whoami/coke-clean`.

Final deployed runtime commit:

```text
cat /home/whoami/coke-clean/.deployed-sha
3fbf838d283700f0b62ef5c9f9184f3de8b51aeb

curl -fsS http://127.0.0.1:8000/healthz
{"ok":true}
```

Services after deploy:

```text
coke-api            Up (healthy)
coke-worker         Up
coke-scheduler      Up
coke-outbox-relay   Up
```

### Bugs Found During Real Smoke

1. Personal conflict wording initially asked whether to still set the reminder
   in the conflicting slot. Fixed in `39885e01` by constraining conflict
   replies to ask for another time instead of implying override.
2. Shared reminder conflict initially returned a false success when the planner
   omitted `local_trigger_at` and only repeated the existing duration. Fixed in
   `2418ef7c` by rejecting no-op shared updates without mutation.
3. Shared reminder time-only reschedule initially asked for duration because v2
   plan/handler did not preserve duration through `time_phrase`. Fixed in
   `fa71e487`.
4. After the no-op guard, close materialization re-ran a staged shared update
   and failed as `needs_update_fields` even though the handler had already
   applied the row change. Fixed in `69f07596` by marking v2 staged update
   payloads as internal idempotent replays and allowing already-reached target
   state only for that replay path.
5. After materialization was fixed, v2 pipeline still allowed planner
   `intentional_no_reply` on executed staged actions, so the DB changed but no
   WeChat reply was sent. Fixed in `3fbf838d` by allowing no-reply only when no
   action outcome exists.

Focused regression after the final two fixes:

```text
/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/turn/v2/test_social_handler.py tests/unit/coke/turn/v2/test_pipeline.py tests/unit/coke/turn/v2/test_plan.py tests/unit/coke/turn/v2/test_plan_cases.py tests/unit/coke/llm/test_interaction_agent.py -q
196 passed in 2.50s
```

### Final Real WeChat Results

All messages were sent one at a time through:

```text
POST https://coke.keep4oforever.com/webhooks/wechat/personal
account_id=ae02ff016fcd4d39a189e51c8c8a31e6
wxid=o9cq8048QW6ys6Eu_gH3NrWjTfK0@im.wechat
```

Shared reminder time-only reschedule success:

```text
event: manual_V6RS20260611T032547Z_shared_success_retry4_040640
message: 把我和 lizihao 的 V6RS20260611T032547Z success shared 共享提醒改到明天下午4点15分
turn: 0f10445b-949b-42b6-a2b4-9ae1f7a46ffb completed=true
output_disposition: replied / reply_ready
staged_command: social_scheduling.update_shared_reminder materialized
reply: 已改好，你和 lizihao 的「V6RS20260611T032547Z success shared」改到明天16:15，持续30分钟
delivery_attempt: sent
shared_reminder.local_trigger_at: 2026-06-12 16:15:00 Asia/Shanghai
projection reminder next_fire_at: 2026-06-12 08:15:00+00 for both participants
```

Shared reminder reschedule conflict:

```text
event: manual_V6RS20260611T032547Z_shared_conflict_retry_040840
message: 把我和 lizihao 的 V6RS20260611T032547Z conflict shared 共享提醒改到明天下午5点半
turn: ad3bb464-891e-4237-9224-f1fc4b0e65d4 completed=true
output_disposition: replied / reply_ready
staged_command rows: 0
reply: 改不了，lizihao 在那个时间段有冲突，只有你有空
delivery_attempt: sent
shared_reminder.local_trigger_at unchanged: 2026-06-12 18:00:00 Asia/Shanghai
projection reminder next_fire_at unchanged: 2026-06-12 10:00:00+00 for both participants
```

Personal reminder overlap:

```text
event: manual_V6RS20260611T032547Z_overlap_retry_041040
message: 明天上午10点半到11点半提醒我 V6RS20260611T032547Z personal exercise retry
turn: 203a966d-443a-447e-9b92-6e9b214834e8 completed=true
output_disposition: replied / reply_ready
staged_command rows: 0
reply: 明天10:30-11:30和「V6RS20260611T032547Z personal busy」冲突了（它占到11:00）\n\n换个时间？
delivery_attempt: sent
new matching reminder rows: 0
busy fixture remained active during assertion: a2cc713a-af3b-426a-8a77-9f2c0ce3ee70
```

### Cleanup

The test fixtures created for `V6RS20260611T032547Z` were cancelled after
verification:

```text
projection_cancelled: 4
reminders_deleted: 6
shared_cancelled: 2

remaining_v6rs_active_reminders: 0
remaining_v6rs_active_shared: 0
remaining_old_debt_candidates: 0
```

## Final Surface Verification

```text
zsh scripts/suggest-verification --base 53fc867a
suggested surfaces: clean-rebuild-docs clean-rebuild-backend repo-os-docs

zsh scripts/review-trigger --base 53fc867a
human_review_required: no
risk_triggers: yes
- sensitive_repo_os_change [medium]
- oversized_change [medium]

zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs
clean-rebuild-docs: passed
clean-rebuild-backend: 1076 passed in 21.15s
repo-os-docs: passed
```
