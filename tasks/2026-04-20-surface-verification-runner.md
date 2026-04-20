# Task: Add Surface Verification Runner

- Status: Verified
- Owner: Codex
- Date: 2026-04-20

## Goal

Turn Coke's verification matrix into an executable script so contributors can
run verification by touched surface instead of reconstructing commands from
memory.

## Scope

- In scope:
  - add a repository script that maps Coke surfaces to verification commands
  - support dry-run output so the mapping can be regression-tested cheaply
  - document the script in the verification matrix and root routing docs
- Out of scope:
  - changing runtime behavior
  - replacing targeted test selection inside existing plans

## Touched Surfaces

- repo-os
- bridge
- gateway-api
- gateway-web
- deploy
- worker-runtime

## Acceptance Criteria

- `scripts/verify-surface` exists and supports the defined Coke surfaces.
- A regression test proves the command mapping is stable.
- The verification docs point readers to the script as the default entrypoint
  when they want surface-based verification.

## Verification

- Command: `pytest tests/unit/test_verify_surface.py -v`
- Command: `zsh scripts/verify-surface --dry-run repo-os bridge`
- Expected evidence: the test passes and the dry-run output lists the correct
  command groups.

## Notes

This is the first "practice one by one" step after the repo-OS bootstrap: make
one of the new contracts executable instead of purely documentary.

Verified on 2026-04-20 with:

- `pytest tests/unit/test_verify_surface.py -v`
- `pytest tests/unit/test_repo_os_structure.py -v`
- `zsh scripts/check`
- `zsh scripts/verify-surface --dry-run repo-os bridge gateway-api gateway-web deploy`
- `zsh scripts/verify-surface repo-os`
