# Task: Coke Native Guardrails

- Status: Verified
- Owner: Codex
- Date: 2026-04-29

## Goal

Learn from Entrix/Routa and add a Coke-native guardrail slice that maps changed
files to verification surfaces and flags review escalation risks.

## Scope

- In scope:
  - add a machine-readable Coke surface map
  - add verification suggestion and review-trigger scripts
  - keep `scripts/verify-surface` as the command authority
  - document the new guardrail entrypoints
- Out of scope:
  - adopting Entrix as a dependency
  - scoring, weighting, graph impact, or UI integration
  - changing runtime behavior

## Touched Surfaces

- repo-os

## Acceptance Criteria

- Changed files can be mapped to Coke surfaces in the same order used by the
  repository verification contract.
- Suggested verification reuses `scripts/verify-surface --dry-run`.
- Review triggers catch bridge/gateway cross-boundary changes and non-trivial
  changes without task evidence.
- Repo-OS structure checks include the new guardrail files.

## Verification

- Command: `.venv/bin/python -m pytest tests/unit/test_guardrail_scripts.py -v`
- Command: `.venv/bin/python -m pytest tests/unit/test_repo_os_structure.py tests/unit/test_verify_surface.py -v`
- Command: `zsh scripts/check`
- Expected evidence: all commands exit 0.

## Notes

This is the first Coke-native practice step after reviewing Routa's Entrix
usage. The implementation intentionally starts with surfaces and review
triggers only; broader scoring and runtime/UI reporting can be added later.
