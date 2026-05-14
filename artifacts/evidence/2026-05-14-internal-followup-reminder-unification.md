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
