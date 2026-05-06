# Verification Checklist

Use this checklist when a task spans workflow docs, repository structure, and
runtime behavior.

## Structure

- required files exist
- canonical paths are valid
- root routing docs point to the canonical locations
- `scripts/check` passes

## Workflow

- execution plan exists when the work is multi-step or risky
- canonical docs were updated for workflow changes
- generated evidence is stored under `artifacts/evidence/`

## Runtime

- run the relevant targeted tests for touched code
- run broader smoke or deployment verification when required
- record any intentionally unverified areas

## Review

- inspect the diff
- note assumptions and remaining risks
- avoid claiming success without command evidence
