# Internal Follow-up Reminder Unification Evidence

- Date: 2026-05-14
- Scope: internal proactive follow-up moved from `deferred_actions` to
  internal reminders in MongoDB `reminders`.
- Commit range: `aeb0b4b..1f25c83` for approved Tasks 1-5, plus Task 6
  docs/evidence changes in this worktree before the Task 6 commit.
- Worktree:
  `/data/projects/coke/.worktrees/internal-followup-reminder-unification`

## Data Inspection

- Local active `deferred_actions.kind=proactive_followup` count: not measured.
  Read-only count against `mongodb://127.0.0.1:27017/`, database `mymongo`,
  selector `{"kind": "proactive_followup", "lifecycle_state": "active"}`
  failed with `ServerSelectionTimeoutError` after a 3 second server-selection
  timeout.
- Production active `deferred_actions.kind=proactive_followup` count: not run.
  A safe read-only production inspection path was not already set up in this
  task, and production Mongo must not be mutated.
- Operator action: none.

## Task 1-5 Verification Available In This Branch

- `d18c378 feat(reminders): classify visible and internal reminders`
- `eccbe77 feat(reminders): add internal followup service path`
- `720752d feat(agent): write followups through reminder service`
- `9e19218 feat(reminders): fire internal followups through runtime`
- `1f25c83 refactor(deferred-actions): remove proactive followup path`

The Task 1-5 commits cover the reminder model classification, visible-only DAO
selectors, internal follow-up service helpers, post-analyze reminder writes,
`fire_mode=followup` runtime handling, and old proactive `deferred_actions`
runtime-path deletion.

## Task 6 Verification

```bash
/data/projects/coke/.venv/bin/python - <<'PY'
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from conf.config import CONF
uri = f"mongodb://{CONF['mongodb']['mongodb_ip']}:{CONF['mongodb']['mongodb_port']}/"
db_name = CONF['mongodb']['mongodb_name']
selector = {'kind': 'proactive_followup', 'lifecycle_state': 'active'}
try:
    client = MongoClient(uri, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000, socketTimeoutMS=3000, tz_aware=True)
    count = client[db_name]['deferred_actions'].count_documents(selector, maxTimeMS=3000)
    print(f"count={count}")
except PyMongoError as exc:
    print(f"error={type(exc).__name__}: {exc}")
    raise SystemExit(2)
PY
```

Result: failed with `ServerSelectionTimeoutError`; classified as local Mongo
availability/timeout, not a code failure. No writes were attempted.

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/connector/clawscale_bridge/test_reminder_management_service.py \
  tests/unit/connector/clawscale_bridge/test_bridge_app.py \
  -k "reminder or reminders" -v
```

Result: passed, `37 passed, 43 deselected in 2.40s`.

```bash
cd gateway/packages/api && npm test -- src/lib/reminder-runtime-client.test.ts src/routes/customer-reminder-routes.test.ts
```

Result: initially blocked before submodule initialization because
`gateway/packages/api` was absent. After `git submodule update --init gateway`
and `pnpm install --frozen-lockfile` in `gateway`, passed:
`2 passed` test files, `19 passed` tests.

```bash
cd gateway/packages/web && npm test -- lib/customer-reminders.test.ts app/'(customer)'/account/reminders/page.test.tsx app/'(customer)'/account/layout.test.tsx
```

Result: initially blocked before submodule initialization because
`gateway/packages/web` was absent. After `git submodule update --init gateway`
and `pnpm install --frozen-lockfile` in `gateway`, passed:
`3 passed` test files, `16 passed` tests.

```bash
zsh scripts/check
```

Result: passed.

## Limits

- Full worker-runtime broad suite was not rerun in Task 6. The local Mongo
  read-only inspection reproduced the known local Mongo timeout, which also
  limits broad Mongo-backed runtime verification in this environment.
- Production data inspection was not run because no preconfigured safe
  read-only production Mongo inspection path was used in this task.
- Gateway dependencies were installed locally under the initialized submodule
  to run the requested tests; no gateway source files were changed.

## Final Branch Verification

After Task 6 approval, final verification also included:

```bash
zsh scripts/suggest-verification --base HEAD~6
```

Result: suggested `repo-os-docs` and `worker-runtime`.

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/reminder/ tests/unit/dao/test_reminder_dao.py -v
```

Result: passed, `97 passed`.

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/runner/test_reminder_scheduler.py \
  tests/unit/runner/test_reminder_event_handler.py -v
```

Result: passed, `29 passed`.

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/agent/test_visible_reminder_protocol_tool.py \
  tests/unit/test_tool_results_context.py -v
```

Initial result: failed because an existing prompt contract test expected
`RFC 5545 RRULE` and `Multiple reminder operations`, while the prompt only
said `RRULE` and `Multiple`. The branch fixed that pre-existing drift in a
separate follow-up commit, then the command passed with `50 passed`.

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/e2e/test_reminder_system_flow.py -v
```

Result: passed, `5 passed`.

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/runner/test_deferred_action_policy.py \
  tests/unit/runner/test_deferred_action_scheduler.py \
  tests/unit/runner/test_agent_runner_deferred_actions.py \
  tests/unit/runner/test_deferred_action_executor.py \
  tests/unit/runner/test_deferred_action_message_source.py \
  tests/unit/runner/test_background_handler_deferred_only.py \
  tests/unit/runner/test_background_conversation_participants.py -v
```

Result: passed, `50 passed`.

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/unit/agent/test_deferred_action_service.py \
  tests/unit/test_context_retrieve_deferred_reminders.py \
  tests/unit/agent/test_agent_handler.py \
  tests/unit/test_clawscale_only_topology.py -v
```

Result: passed, `37 passed`.

```bash
/data/projects/coke/.venv/bin/python -m pytest \
  tests/e2e/test_deferred_actions_flow.py -v
```

Result: passed, `2 passed`.

```bash
zsh scripts/check
```

Result: passed.

```bash
zsh scripts/verify-surface worker-runtime
```

Result: `tests/unit/runner/ -v` passed with `103 passed`, then
`tests/unit/agent/ -v` failed on the first collected test while importing
`agent.runner.agent_handler`: `MongoDBLockManager.__init__` attempted to create
an index on local Mongo at `127.0.0.1:27017` and hit
`ServerSelectionTimeoutError`. Classified as the same local Mongo availability
limit recorded above, not a code-path assertion failure.

```bash
zsh scripts/review-trigger --base HEAD~7
```

Result: `human_review_required: yes` for sensitive repo-OS changes and
oversized diff size.

```bash
git diff --check
git status --short --branch
git -C gateway status --short --branch
```

Result: diff check passed. Root tracked status was clean. Gateway tracked
status was clean on detached `HEAD`.
