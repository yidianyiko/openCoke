---
kind: verification_report
surface: agent-runtime
created_at: 2026-05-28
---

# Scheduling Domain Schema and Reminder Label Leak

## Production Evidence

Reviewed production logs and message history for the two hours before
2026-05-28 13:14 UTC.

- `coke-agent`, `coke-bridge`, and `gateway` were running and health checks
  passed.
- `outbound_deliveries` in the reviewed window all had `status=succeeded`.
- Agent logs showed `scheduling_domain(...)` validation errors for top-level
  `title`, `fire_at`, and `duration_minutes` arguments at 2026-05-28 13:09:42
  and 13:10:39 UTC, followed by the no-visible-reply fallback.
- Mongo `outputmessages` showed `reminders:思考会` delivered to olivers at
  2026-05-28 13:00:15 UTC.

## Local Verification

Commands run after the fix:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -k "top_level_create_args or top_level_action_args" -q
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py -k "internal_label_leak" -q
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/agent/test_execution_agents.py -q
git diff --check -- agent/agno_agent/runtime/agent_runtime.py tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_output_rules.py docs/issues/2026-05-28-scheduling-domain-schema-and-reminder-label-leak.md
zsh scripts/verify-surface repo-os-docs worker-runtime
```

Observed results:

- Top-level scheduling create/action regression tests passed.
- Reminder internal-label repair regression test passed.
- Targeted agent-runtime tests passed: 141 passed.
- Diff whitespace check passed.
- `repo-os-docs` surface passed `zsh scripts/check`.
- `worker-runtime` surface passed:
  - runner unit tests: 72 passed.
  - agent unit tests: 559 passed.
  - ClawScale-only topology tests: 7 passed.
