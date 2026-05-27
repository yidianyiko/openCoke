---
kind: active_issue
status: resolved
surface:
  - agent-runtime
  - reminder-intent
created_at: 2026-05-27
updated_at: 2026-05-27
---

# 2026-05-27 Personal Reminder CRUD Bypassed Reminder Runtime

## What Happened

Production real-user CRUD regression used `olivers` through the live bridge with
marker `crud-real-20260527T065638Z`.

Passing paths:

- Create without duration:
  `2029年1月7日10:00提醒我喝水-crud-real-20260527T065638Z-c1。`
- Cancel:
  `取消拉伸-crud-real-20260527T065638Z-c4这个提醒。`

Failures or suspicious behavior:

- Update input:
  `把喝水-crud-real-20260527T065638Z-c1这个提醒改到2029年1月7日11:00，标题改成喝水更新-crud-real-20260527T065638Z-c1。`
  updated the existing reminder in Mongo, but the user-visible reply said
  `已创建提醒：...`.
- Complete input:
  `完成做俯卧撑-crud-real-20260527T065638Z-c3这个提醒。`
  replied `找不到这个提醒，我帮你查一下现在有哪些提醒？` even though the
  reminder existed and was active.

The complete turn also caused PostAnalyze to create a temporary internal
follow-up reminder titled:

```text
查询提醒列表后，根据结果帮用户完成「俯卧撑-crud-real-20260527T065638Z
```

That follow-up was later cancelled during cleanup.

## Root Cause

The 2026-05-27 direct Reminder Runtime route only matched create-style verbs
from `_REMINDER_VERB_PATTERN`, such as `提醒我` and `叫我`. Explicit personal
reminder CRUD operations like `完成...提醒`, `取消...提醒`, `改...提醒`, and
`列...提醒` still went through the general interaction agent and model tool
selection.

The model then handled complete/update inconsistently:

- update used the reminder capability but surfaced create wording;
- complete did not execute the matching reminder operation and fell back to a
  list/check response.

## Resolution

`agent/agno_agent/runtime/agent_runtime.py` now routes explicit personal
reminder CRUD phrases directly to Reminder Runtime, not only create phrases.
The route remains closed for shared-reminder turns containing `共享提醒`.

The first post-deploy production retest with marker
`crud-fix-20260527T071209Z` confirmed the route fix:

- Complete input
  `完成做俯卧撑-crud-fix-20260527T071209Z-c3这个提醒。` replied
  `已完成提醒：做俯卧撑-crud-fix-20260527T071209Z-c3` and moved reminder
  `6a1699edceae234bc1be8bb6` to `completed`.
- Update input updated the existing reminder
  `6a1699d2ceae234bc1be8b64`, but still replied
  `已创建提醒：喝水更新-crud-fix-20260527T071209Z-c1...`.

That remaining visible-output bug was isolated to
`agent/agno_agent/adapters/reminder_command_executor.py`: create and update
share `_visible_reminder_summary`, but it always used the `已创建提醒` prefix.
The summary builder now uses `已更新提醒` for update actions while preserving
the create prefix for create actions.

Regression coverage:

```bash
.venv/bin/python -m pytest \
  tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_directly_executes_explicit_personal_reminder_crud \
  tests/unit/agent/test_agent_runtime_construction.py::test_direct_personal_reminder_route_ignores_shared_reminder_acceptance \
  -q

.venv/bin/python -m pytest \
  tests/unit/agent/test_reminder_command_executor.py::test_dict_decision_input_is_supported_and_empty_operations_becomes_none \
  -q
```

The production test reminders from marker `crud-real-20260527T065638Z` were
cleaned up:

- `6a1696306645e7bf138ae8ef` cancelled.
- `6a1696646645e7bf138ae958` cancelled.
- `6a1696966645e7bf138ae9c2` cancelled by the natural cancel case.

## Final Production Retest

Deployed commit `bb724367` with `./scripts/deploy-compose-to-gcp.sh --restart`.
The deploy health check completed successfully.

Focused production real-user update retest used olivers through the live bridge
with marker `crud-update-fix-20260527T072706Z`:

- Create input:
  `2029年1月12日10:00提醒我喝水-crud-update-fix-20260527T072706Z-c1。`
  replied
  `已创建提醒：喝水-crud-update-fix-20260527T072706Z-c1（2029-01-12 周五 10:00）`.
- Update input:
  `把喝水-crud-update-fix-20260527T072706Z-c1这个提醒改到2029年1月12日11:00，标题改成喝水更新-crud-update-fix-20260527T072706Z-c1。`
  replied
  `已更新提醒：喝水更新-crud-update-fix-20260527T072706Z-c1（2029-01-12 周五 11:00）`.
- Mongo showed exactly one marked reminder:
  `6a169d52fb9c9ae2c4db7963`, title
  `喝水更新-crud-update-fix-20260527T072706Z-c1`, `next_fire_at`
  `2029-01-12 03:00:00+00:00`.
- Cleanup cancelled `6a169d52fb9c9ae2c4db7963`; remaining active reminders for
  the marker: `0`.

Remote services after retest:

- `coke-agent`: up.
- `coke-bridge`: healthy.
- `gateway`: healthy.
