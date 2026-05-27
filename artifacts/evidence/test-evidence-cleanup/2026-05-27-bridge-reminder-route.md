# 2026-05-27 Bridge Reminder Route Evidence

## Change Under Test

Bridge reminder management no longer treats missing explicit conversation
resolution or missing delivery route keys as successful reminder creation.

## Commands

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/test_reminder_management_service.py \
  tests/unit/connector/clawscale_bridge/test_bridge_app.py \
  -k "reminder or reminders" -q
```

Result: 50 passed, 52 deselected.

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/ \
  tests/unit/agent/test_message_util_clawscale_routing.py -q
```

Result: 177 passed.

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/reminder/ \
  tests/unit/runner/test_reminder_event_handler.py \
  tests/unit/runner/test_reminder_scheduler.py -q
```

Result: 132 passed.

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/agent/test_reminder_intent_capability.py \
  tests/unit/agent/test_reminder_command_executor.py -q
```

Result: 123 passed.

```bash
git diff --check
```

Result: passed.

## Known Gap

`zsh scripts/check` was attempted in the isolated root worktree and failed
because the worktree has empty `gateway/` and `memo-runtime/` gitlink
directories, so ownership files and gateway route files were not present there.
This is an environment/worktree layout gap, not a result from the changed
files. Re-run `scripts/check` from the main checkout after merging back.
