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
- Agent sessions for later Eva/olivers shared-invite attempts had no tool
  events and returned account-not-found wording from the main model despite
  active friendship rows.
- Mongo `outputmessages` showed `reminders:思考会` delivered to olivers at
  2026-05-28 13:00:15 UTC.

## Local Verification

Commands run after the fix:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -k "top_level_create_args or top_level_action_args" -q
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py -k "internal_label_leak" -q
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/agent/test_execution_agents.py -q
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -k "explicit_shared_invite_without_focus or activity_reservation_phrase or personal_contact_reminder" -q
git diff --check -- agent/agno_agent/runtime/agent_runtime.py tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_output_rules.py docs/issues/2026-05-28-scheduling-domain-schema-and-reminder-label-leak.md
zsh scripts/verify-surface repo-os-docs worker-runtime
```

Observed results:

- Top-level scheduling create/action regression tests passed.
- Explicit shared-invite routing without focus passed, while personal contact
  reminder and external activity reservation counterexamples stayed out of
  scheduling preselection.
- Reminder internal-label repair regression test passed.
- Targeted agent-runtime tests passed: 142 passed.
- Diff whitespace check passed.
- `repo-os-docs` surface passed `zsh scripts/check`.
- `worker-runtime` surface passed:
  - runner unit tests: 72 passed.
  - agent unit tests: 560 passed.
  - ClawScale-only topology tests: 7 passed.

## Production Deploy Verification

Commands run after deploying commit `0c25ec95` with
`./scripts/deploy-compose-to-gcp.sh --restart`:

```bash
ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml exec -T coke-agent python - <<PY ... PY'
ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml ps'
ssh gcp-coke 'curl -sS http://127.0.0.1:4041/health && curl -sS http://127.0.0.1:8090/bridge/healthz'
ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml logs --since=10m coke-agent coke-bridge gateway | egrep -i "unexpected keyword argument|internal_protocol_label_leak|Traceback|ERROR|CRITICAL|Exception" || true'
```

Observed results:

- Deploy script completed and verified the public site at
  `https://coke.keep4oforever.com`.
- `coke-agent`, `coke-bridge`, and `gateway` were up after restart; bridge and
  gateway were healthy.
- Local health endpoints returned `{"ok":true,"version":"0.1.0"}` and
  `{"ok":true}`.
- Container smoke returned
  `{'missing_params': [], 'label_leak_code': 'internal_protocol_label_leak', 'retryable': True}`.
- Post-deploy logs in the checked window had no matching new runtime errors.
