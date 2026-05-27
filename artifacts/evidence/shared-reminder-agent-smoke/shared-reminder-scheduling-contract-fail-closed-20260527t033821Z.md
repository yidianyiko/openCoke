# Shared Reminder Scheduling Contract Fail-Closed Evidence

Date: 2026-05-27T03:38:21Z

Issue: `docs/issues/2026-05-27-shared-reminder-scheduling-contract-fail-closed.md`

## Local Verification

- Focused runtime tests:
  - Command: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/agent/test_execution_agents.py -q`
  - Result: `121 passed in 3.46s`
- Diff-aware routing:
  - Command: `zsh scripts/suggest-verification --base HEAD~1`
  - Result: suggested `zsh scripts/verify-surface repo-os-docs worker-runtime`
- Risk trigger report:
  - Command: `zsh scripts/review-trigger --base HEAD~1`
  - Result: `human_review_required: no`; non-blocking triggers were repo-OS docs touched, oversized diff, and evidence gap.
- Diff whitespace check:
  - Command: `git diff --check`
  - Result: passed with no output.
- Surface verification:
  - Command: `zsh scripts/verify-surface repo-os-docs worker-runtime`
  - Result: `scripts/check` passed; `tests/unit/runner/ -v` had `67 passed`; `tests/unit/agent/ -v` had `522 passed`; `tests/unit/test_clawscale_only_topology.py -v` had `7 passed`.

## Production Deploy And Smoke

- Deploy:
  - Command: `./scripts/deploy-compose-to-gcp.sh --restart`
  - Result: completed successfully; remote health endpoints and public site verification passed.
- Compose status:
  - Command: `ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml ps'`
  - Result: `coke-agent`, `coke-bridge`, `gateway`, `mongo`, `postgres`, and `redis` running; bridge and gateway healthy.
- Internal health:
  - Command: `ssh gcp-coke 'printf "agent="; curl -fsS http://127.0.0.1:4041/health; printf "\nbridge="; curl -fsS http://127.0.0.1:8090/bridge/healthz; printf "\n"'`
  - Result: agent `{"ok":true,"version":"0.1.0"}` and bridge `{"ok":true}`.
- Public health:
  - Command: `curl -k -fsS https://coke.keep4oforever.com/health && curl -k -fsS https://coke.keep4oforever.com/bridge/healthz`
  - Result: `{"ok":true,"version":"0.1.0"}` and `{"ok":true}`.
- Recent error logs:
  - Command: `ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml logs --since 15m coke-agent coke-bridge gateway 2>&1 | grep -Ei "scheduling intent could not be resolved|invalid_scheduling|invalid_body|traceback|exception|error" || true'`
  - Result: no matches.
- Deployed source marker check:
  - Command: `ssh gcp-coke 'cd ~/coke && grep -nE "multiple_scheduling_calls_after_write|invalid_scheduling_args|_SHARED_REMINDER_INVITE_WRITE_CLAIM_PATTERNS" agent/agno_agent/runtime/agent_runtime.py'`
  - Result: strict-contract markers present in deployed source.

No artificial production shared-reminder invite was created during smoke to avoid sending a real user notification.
