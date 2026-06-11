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

Follow-up residual cleanup:
- Migrated the pre-reply interrupt coalescing integration test away from its
  deleted v1 fixture and onto the v2 Express path.
- Added v2 propagation of the current open input window into Plan and Express,
  so coalesced inbounds are visible beyond the latest trigger payload.
- Removed the obsolete render-agent `semantic_decision` prompt/context channel
  and its tests; no production path generated that field after v1 removal.

Follow-up verification:
- `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/turn/v2/test_pipeline.py::test_plan_request_and_planner_payload_preserve_current_input_window tests/integration/coke/test_pre_reply_interrupt_coalescing.py -q`
  - Result: 2 passed.
- `/data/projects/coke/.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/v2 tests/unit/coke/turn/test_turn_runner.py tests/integration/coke/test_pre_reply_interrupt_coalescing.py tests/integration/coke/test_runtime_wiring.py -q`
  - Result: 228 passed.
- `/data/projects/coke/.venv/bin/python -m compileall -q coke tests/unit/coke tests/integration/coke`
  - Result: passed.
- `/data/projects/coke/.venv/bin/python -m black --check coke/llm/agno_interaction_agent.py coke/turn/context.py coke/turn/runner.py coke/turn/v2/express.py coke/turn/v2/pipeline.py coke/turn/v2/plan.py tests/integration/coke/test_pre_reply_interrupt_coalescing.py tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/v2/test_pipeline.py`
  - Result: passed.
- `/data/projects/coke/.venv/bin/python -m isort --check-only coke/llm/agno_interaction_agent.py coke/turn/context.py coke/turn/runner.py coke/turn/v2/express.py coke/turn/v2/pipeline.py coke/turn/v2/plan.py tests/integration/coke/test_pre_reply_interrupt_coalescing.py tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/turn/v2/test_pipeline.py`
  - Result: passed.
- Residual scan for deleted v1 symbols across `coke`, `tests`, and deploy
  config found only retained guardrails:
  `COKE_TURN_PIPELINE` absence assertion and drop-migration/downgrade schema
  assertions for the retired recoverable-intent table.
- `zsh scripts/suggest-verification --base 8e2148c5`
  - Suggested: `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs`.
- `zsh scripts/review-trigger --base 8e2148c5`
  - Result: human_review_required=no; risk_triggers=no.
- `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs`
  - Result: passed.
  - Included: `python3 -m pytest tests/unit/coke -v` and `zsh scripts/check`.
  - Unit test result inside surface verification: 924 passed.
