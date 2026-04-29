# 2026-04-29 Coke Native Guardrails

## Goal

Make the first Entrix/Routa-inspired guardrail mechanism executable in Coke:
changed files should suggest the right verification surfaces and identify
review escalation risks.

## Scope

- In scope:
  - machine-readable surface mapping in `docs/fitness/surfaces.yaml`
  - `scripts/suggest-verification`
  - `scripts/review-trigger`
  - focused unit coverage and repo-OS checks
- Out of scope:
  - Entrix dependency adoption
  - scoring and weighted fitness reports
  - graph impact, release triggers, or UI integration

## Inputs

- Related task: `tasks/2026-04-29-coke-native-guardrails.md`
- Related references:
  - `docs/fitness/coke-verification-matrix.md`
  - `docs/design-docs/coke-working-contract.md`
  - Routa `docs/fitness/README.md`
  - Routa `docs/fitness/review-triggers.yaml`

## Touched Surfaces

- repo-os

## Work Breakdown

1. Add failing tests for surface suggestion and review-trigger behavior.
2. Add `docs/fitness/surfaces.yaml` with Coke surfaces and first review rules.
3. Add a small Python guardrail implementation plus zsh wrappers.
4. Document the new entrypoints and include them in repo-OS checks.
5. Run focused tests and repo-OS verification.

## Verification

- Command: `.venv/bin/python -m pytest tests/unit/test_guardrail_scripts.py -v`
- Command: `.venv/bin/python -m pytest tests/unit/test_repo_os_structure.py tests/unit/test_verify_surface.py -v`
- Command: `zsh scripts/check`
- Expected evidence: focused behavior tests pass and repo-OS structure checks
  include the new guardrail files.

## Notes

The design keeps `scripts/verify-surface` as the authority for command
execution. `suggest-verification` only chooses surfaces and prints the existing
dry-run command set.
