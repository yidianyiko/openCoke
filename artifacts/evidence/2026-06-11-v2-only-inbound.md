# V2-Only Inbound Verification

Date: 2026-06-11

Scope:
- Removed the old inbound v1 path and made interactive inbound turns use v2 only.
- Retained render-mode Interaction Agent for notification, access-denied,
  reminder-fire, and other structured render turns.
- Removed the temporary turn-pipeline flag and retired the
  `recoverable_scheduling_intent` schema with a drop migration.

Manual smoke:
- V6 real-account smoke was not rerun in this change because the user reported it
  was already completed and instructed not to continue V6.

Fresh verification:
- `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn/v2 tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/llm/test_config.py tests/unit/coke/test_backend_foundation.py tests/unit/coke/settings/test_settings_composition.py tests/unit/coke/social_scheduling/test_social_scheduling_schema_contract.py tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/test_clean_schema_contract.py tests/unit/coke/test_turn_latency_telemetry.py tests/unit/coke/deploy/test_clean_compose_deploy_contract.py tests/integration/coke/test_runtime_wiring.py -q`
  - Result: 283 passed.
- `/data/projects/coke/.venv/bin/python -m compileall -q coke tests/unit/coke tests/integration/coke`
  - Result: passed.
- `git diff --name-only --diff-filter=ACM -- '*.py' | xargs /data/projects/coke/.venv/bin/python -m black --check`
  - Result: passed.
- `git diff --name-only --diff-filter=ACM -- '*.py' | xargs /data/projects/coke/.venv/bin/python -m isort --check-only`
  - Result: passed.
- `zsh scripts/suggest-verification --base HEAD~1`
  - Suggested: `zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs deploy`.
- `zsh scripts/review-trigger --base HEAD~1`
  - Result: human_review_required=no; risk triggers were deploy/docs/oversized/evidence-gap.
- `zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs deploy`
  - Result: passed.
  - Included: `bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh`, `zsh scripts/check`, and `python3 -m pytest tests/unit/coke -v`.
  - Unit test result inside surface verification: 924 passed.
