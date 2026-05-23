# Dead Code Cleanup Evidence - 2026-05-24

## Scanner Inputs

- Root Python scan:
  `.venv/bin/vulture agent connector dao entity framework util scripts tests memo-runtime/memo_runtime memo-runtime/tests --exclude ".venv,gateway,__pycache__,.pytest_cache,.ruff_cache,alibabacloud-nls-python-sdk-dev"`
- Gateway TypeScript scan:
  `pnpm dlx knip --reporter compact` from `gateway/`

## Confirmed Removals

Removed only candidates that were reported by `vulture` and had no repository
callers in `rg` searches, excluding dynamic entry points such as Flask routes,
pytest hooks/fixtures, Pydantic validators, and public protocol surfaces.

## Verification

- `git diff --check`
- `.venv/bin/python -m compileall agent/agno_agent/capabilities/reminder_intent.py agent/agno_agent/tools/timezone_tools.py agent/runner/context.py agent/runner/reminder_scheduler.py agent/util/message_util.py util/message_log_util.py memo-runtime/memo_runtime/contract.py memo-runtime/memo_runtime/storage/postgres.py util/time_util.py util/embedding_util.py util/oss.py`
- `.venv/bin/python -m pytest tests/unit/test_time_util.py tests/unit/test_timezone_tools.py tests/unit/runner/test_reminder_scheduler.py -q`
- `/data/projects/coke/.venv/bin/python -m pytest tests/test_postgres_schema.py -q` from `memo-runtime/`
- `zsh scripts/verify-surface worker-runtime product-reminder product-memo product-timezone`
  - `worker-runtime` passed.
  - `product-reminder` passed.
  - `product-memo` failed only because the script runs `memo-runtime/tests`
    from the repository root while those tests read package-relative paths.
- `/data/projects/coke/.venv/bin/python -m pytest tests -v` from
  `memo-runtime/`: 38 passed, 3 skipped.
- `.venv/bin/python -m pytest tests/unit/agent/test_timezone_port.py tests/unit/agent/test_timezone_service.py tests/unit/test_timezone_tools.py tests/unit/test_user_dao_timezone.py -v`
- `zsh scripts/check`

## Scanner Follow-Up

- `pnpm dlx knip --reporter compact` returned clean output.
- `.venv/bin/vulture ... --min-confidence 100` reports only
  `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py:140`
  `return_document`, which is a required fake method signature parameter for
  the call under test, not removable dead code.
