# Pre-Reply Input Coalescing Review Evidence

Date: 2026-06-01
Branch: feature/pre-reply-input-coalescing

## Independent Review

- Reviewer: Darwin subagent
- Result before fixes: not ready to merge
- Main findings addressed:
  - Durable cross-worker interrupt was missing.
  - Inbound sequence assignment needed an atomic storage invariant.
  - Pending async reply transition had to preserve the existing disposition id.
  - Waiting-reply main-branch changes needed to use input-window turn semantics.

## Fix Summary

- `record_inbound` now records interrupted active interactive turns durably and carries interrupted trigger ids through outbox payloads.
- Workers cancel provider runs from durable interrupted trigger ids before submitting the new turn.
- Async turn execution waits for the Redis conversation lock instead of failing the turn when another worker holds it.
- Inbound ordering is protected by `(conversation_id, direction, seq)` uniqueness and local duplicate checks.
- Pending async disposition transitions reuse the existing `OutputDisposition.id`.
- Main's waiting-reply dispatcher was reconciled with the input-window API and no longer passes retired `based_on_inbound_seq`.
- Reminder read-only list/filter operations remain unstaged and do not open write guards.
- Semantic `intentional_no_reply` hints still reach the interaction agent; the agent remains the owner of the final visible/no-reply decision.

## Verification

- `.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py tests/unit/coke/conversation_runtime/test_schema_contract.py tests/unit/coke/test_clean_schema_contract.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/worker/test_interactive_supervisor.py tests/unit/coke/worker/test_worker_topic_resilience.py tests/unit/coke/worker/test_waiting_reply.py tests/integration/coke/test_composition_turn_integration.py::test_superseded_inbound_blocks_state_commit_and_records_superseded -q`
  - Result: 177 passed
- `git diff --check`
  - Result: passed
- `zsh scripts/verify-surface clean-rebuild-docs clean-rebuild-backend repo-os-docs repo-os`
  - Result: passed
  - Included: `tests/unit/coke -v` with 673 passed, canonical docs sync, `scripts/check`, and no-legacy-import guard.
- `zsh scripts/suggest-verification --base main`
  - Result: suggested `clean-rebuild-docs clean-rebuild-backend repo-os-docs`
- `zsh scripts/review-trigger --base main`
  - Result: `human_review_required: no`

