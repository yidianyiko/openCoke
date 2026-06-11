# Turn Pipeline Rename Verification

Date: 2026-06-12

Scope:
- Renamed the current inbound turn package to `coke.turn.inbound`.
- Renamed the turn probe to `scripts/turn_pipeline_probe.py`.
- Moved unit tests to `tests/unit/coke/turn/inbound`.
- Removed current runtime, test, and canonical-doc references that framed the
  inbound turn path as a version comparison.

Fresh verification:
- `/data/projects/coke/.venv/bin/python -m black coke/composition.py coke/turn/runner.py coke/turn/inbound scripts/turn_pipeline_probe.py tests/unit/coke/turn/inbound tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/settings/test_settings_composition.py tests/unit/coke/deploy/test_clean_compose_deploy_contract.py tests/integration/coke/repositories/test_pending_clarification_repository_contract.py tests/integration/coke/test_pre_reply_interrupt_coalescing.py`
  - Result: passed.
- `/data/projects/coke/.venv/bin/python -m isort coke/composition.py coke/turn/runner.py coke/turn/inbound scripts/turn_pipeline_probe.py tests/unit/coke/turn/inbound tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/settings/test_settings_composition.py tests/unit/coke/deploy/test_clean_compose_deploy_contract.py tests/integration/coke/repositories/test_pending_clarification_repository_contract.py tests/integration/coke/test_pre_reply_interrupt_coalescing.py`
  - Result: passed.
- `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn/inbound tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/settings/test_settings_composition.py tests/unit/coke/deploy/test_clean_compose_deploy_contract.py tests/integration/coke/repositories/test_pending_clarification_repository_contract.py tests/integration/coke/test_pre_reply_interrupt_coalescing.py -q`
  - Result: 170 passed, 2 skipped.
  - Skip reason: repository integration tests require `COKE_TEST_DATABASE_URL`.
- `/data/projects/coke/.venv/bin/python -m compileall -q coke/turn/inbound coke/turn/runner.py coke/composition.py scripts/turn_pipeline_probe.py`
  - Result: passed.
- `/data/projects/coke/.venv/bin/python scripts/turn_pipeline_probe.py --check-imports`
  - Result: `OK: turn pipeline probe imports resolved without runtime construction`.
- `git diff --check`
  - Result: passed.
- Residual scan for old turn package paths, old probe names, versioned turn
  pipeline markers, and the retired turn-pipeline cutover flag across `coke`,
  `tests`, `scripts`, current architecture docs, current turn plans/specs,
  deploy, and Docker surfaces.
  - Result: only external service API version URLs remained in deploy and LLM
    provider config/tests.
- `zsh scripts/suggest-verification --base HEAD~1`
  - Suggested: `zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs`.
- `zsh scripts/review-trigger --base HEAD~1`
  - Result: human_review_required=no.
  - Risk triggers: `sensitive_repo_os_change`, `oversized_change`.
- `zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs`
  - Result: passed.
  - Included: `bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh`,
    `zsh scripts/check`, and `python3 -m pytest tests/unit/coke -v`.
  - Unit test result inside surface verification: 924 passed.
